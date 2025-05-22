# simulacion_trafico_engine/node/zone_node.py
import asyncio
import pygame # Necesario para pygame.Rect
import uuid
import random
import json
from typing import List, Dict, Optional, Any, Tuple, TYPE_CHECKING

# Importaciones relativas correctas
from ..core.vehicle import Vehicle
from ..core.traffic_light import TrafficLight
from ..core.zone_map import ZoneMap
from ..distribution.rabbitclient import RabbitMQClient # Asegúrate que este exista y funcione
from ..performance.metrics import TrafficMetrics      # Asegúrate que este exista y funcione
# from ..ui.theme import Theme # Theme se usa indirectamente a través de los componentes del core y ui

if TYPE_CHECKING:
    # Estas declaraciones ayudan a los linters y type checkers
    # sin crear dependencias circulares en tiempo de ejecución.
    # Si RabbitMQClient o TrafficMetrics no son clases, ajusta esto.
    pass


class ZoneNode:
    def __init__(self, zone_id: str, zone_config: Dict,
                 rabbit_client: RabbitMQClient, # Tipado directo si no hay problemas circulares
                 metrics_client: TrafficMetrics, # Tipado directo
                 global_city_config: Dict):
        self.zone_id = zone_id
        self.zone_config = zone_config
        self.bounds = pygame.Rect(
            int(zone_config["bounds"]["x"]), int(zone_config["bounds"]["y"]),
            int(zone_config["bounds"]["width"]), int(zone_config["bounds"]["height"])
        )
        self.rabbit_client = rabbit_client
        self.metrics_client = metrics_client
        self.global_city_config = global_city_config

        self.zone_map = ZoneMap(zone_id, zone_config["bounds"], rabbit_client, metrics_client)
        self.zone_map.initialize_map_elements(TrafficLightClass=TrafficLight) # Pasar la clase TrafficLight

        self.vehicles: Dict[str, Vehicle] = {}
        self.max_vehicles_in_zone = self.zone_config.get("max_vehicles_local", 20)
        self.spawn_timer = 0
        self.spawn_interval = random.randint(45, 90) # Ticks (a 30 FPS, ~1.5 a 3 segundos)

        self.is_running = True
        self.message_queue_name = f"zone.{self.zone_id}.migrations"
        # Usar el nombre del exchange definido en la configuración global o un default
        self.general_migration_exchange = self.global_city_config.get("rabbitmq_exchange", "city_traffic_exchange")

        self.manual_spawn_pending = False
        self.pending_spawn_tasks: List[asyncio.Task] = []

        # print(f"[ZoneNode {self.zone_id}] Initialized. Bounds: {self.bounds}")

    def trigger_manual_spawn(self) -> bool:
        if len(self.vehicles) < self.max_vehicles_in_zone:
            self.manual_spawn_pending = True
            return True
        return False

    async def setup_rabbitmq_subscriptions(self):
        if self.rabbit_client and self.rabbit_client.async_channel:
            try:
                # Asegurar que el exchange existe (puede ser declarado por el orquestador)
                await self.rabbit_client.async_channel.exchange_declare(
                    name=self.general_migration_exchange, type='topic', durable=True)
                
                queue = await self.rabbit_client.async_channel.declare_queue(
                    name=self.message_queue_name, durable=True)
                
                # Bind la cola al exchange usando el zone_id como routing_key
                await queue.bind(exchange=self.general_migration_exchange, routing_key=self.zone_id)
                
                await queue.consume(self._on_rabbitmq_message)
                # print(f"[ZoneNode {self.zone_id}] Subscribed to RabbitMQ for migrations on queue '{self.message_queue_name}'.")
            except Exception as e:
                print(f"[ZoneNode {self.zone_id}] ERROR setting up RabbitMQ subscriptions: {e}")
        # else:
            # print(f"[ZoneNode {self.zone_id}] RabbitMQ client not available for subscriptions.")


    async def _on_rabbitmq_message(self, message: Any): # message es aio_pika.IncomingMessage
        async with message.process(): # Importante para ack/nack
            try:
                body_str = message.body.decode()
                data = json.loads(body_str)
                
                # Asumimos que los mensajes a esta cola son para migración ENTRANTE
                if "vehicle_state" in data and data.get("target_zone") == self.zone_id:
                    await self._handle_incoming_vehicle_migration(data)
                # else:
                    # print(f"[ZoneNode {self.zone_id}] Received unhandled RabbitMQ message: type {data.get('type')}")
            # except json.JSONDecodeError:
                # print(f"[ZoneNode {self.zone_id}] ERROR: Could not decode JSON from RabbitMQ message.")
            except Exception as e:
                print(f"[ZoneNode {self.zone_id}] ERROR processing RabbitMQ message: {e}")


    async def _handle_incoming_vehicle_migration(self, migration_payload: Dict):
        veh_data = migration_payload.get("vehicle_state", {})
        veh_id = veh_data.get("id")

        if not veh_id: return
        if veh_id in self.vehicles: return 
        if len(self.vehicles) >= self.max_vehicles_in_zone: return

        new_vehicle = Vehicle(
            id=str(veh_id),
            global_x=float(veh_data["position"]["x"]),
            global_y=float(veh_data["position"]["y"]),
            width=int(veh_data.get("asset_width", Vehicle.TARGET_DRAW_WIDTH_HORIZ)), 
            height=int(veh_data.get("asset_height", Vehicle.TARGET_DRAW_HEIGHT_HORIZ)),
            speed=float(veh_data.get("speed", 2.0)),
            original_speed=float(veh_data.get("original_speed", veh_data.get("speed", 2.0))),
            direction=str(veh_data.get("direction", "right")),
            current_zone_id=self.zone_id,
            rabbit_client=self.rabbit_client,
            metrics_client=self.metrics_client,
            map_ref=self.zone_map
        )
        # Opcional: si image_path se envía en la migración, intentar cargar ese asset específico
        if "image_path" in veh_data and veh_data["image_path"]:
            try:
                new_vehicle.raw_unscaled_image = pygame.image.load(veh_data["image_path"]).convert_alpha()
                # Rehacer la lógica de escalado/orientación de Vehicle.__init__ si se carga una nueva raw_unscaled_image
                # Esto es un poco más complejo, ya que __init__ de Vehicle lo hace basado en dirección.
                # Para simplicidad, por ahora Vehicle elegirá aleatoriamente, pero esto es donde lo harías.
            except pygame.error:
                # print(f"Could not load migrated vehicle image: {veh_data['image_path']}")
                pass # Vehicle usará su asset aleatorio por defecto

        self.vehicles[new_vehicle.id] = new_vehicle
        asyncio.create_task(new_vehicle.publish_state("migrated_in_zone", 
                            extra_data={"previous_zone": migration_payload.get("current_zone")}))


    async def _spawn_new_vehicle_at_entry(self, manual_spawn=False):
        if len(self.vehicles) >= self.max_vehicles_in_zone: return

        spawn_points_local = self.zone_map.get_spawn_points_local()
        if not spawn_points_local: return
        
        spawn_choice = random.choice(spawn_points_local)
        # Coordenadas de spawn globales
        global_spawn_x = self.bounds.x + spawn_choice["x"]
        global_spawn_y = self.bounds.y + spawn_choice["y"]
        
        new_id = f"veh_{self.zone_id}_{uuid.uuid4().hex[:6]}"
        
        # Vehicle.__init__ usará Vehicle.TARGET_DRAW_WIDTH_HORIZ y TARGET_DRAW_HEIGHT_HORIZ
        # así que no es necesario pasar width/height aquí a menos que quieras anular esos para este spawn.
        new_vehicle = Vehicle(
            id=new_id,
            global_x=global_spawn_x, global_y=global_spawn_y,
            speed= random.uniform(1.8, 3.8),
            direction=spawn_choice["direction"],
            current_zone_id=self.zone_id,
            rabbit_client=self.rabbit_client,
            metrics_client=self.metrics_client,
            map_ref=self.zone_map
        )
        self.vehicles[new_vehicle.id] = new_vehicle
        spawn_type = "manual_spawned" if manual_spawn else "auto_spawned"
        task = asyncio.create_task(new_vehicle.publish_state(
            "spawned_in_zone", 
            extra_data={"entry_point": spawn_choice.get("entry_edge"), "spawn_type": spawn_type}
        ))
        self.pending_spawn_tasks.append(task)

    async def _check_and_handle_migrations_out(self):
        vehicles_to_remove_ids: List[str] = []
        for veh_id, vehicle in list(self.vehicles.items()):
            if vehicle.is_despawned_globally:
                vehicles_to_remove_ids.append(veh_id); continue

            vehicle_global_rect = vehicle.get_global_rect()
            if not self.bounds.collidepoint(vehicle_global_rect.centerx, vehicle_global_rect.centery):
                target_zone_id = self._determine_target_zone(vehicle)
                if target_zone_id:
                    migration_payload = {
                        "type": "vehicle_migration", "id": vehicle.id, 
                        "current_zone": self.zone_id, "target_zone": target_zone_id,
                        "vehicle_state": { 
                            "id": vehicle.id, 
                            "position": {"x": vehicle.global_x, "y": vehicle.global_y},
                            "speed": vehicle.speed, "direction": vehicle.direction, 
                            "stopped": vehicle.stopped,
                            "asset_width": getattr(vehicle, 'asset_width', Vehicle.TARGET_DRAW_WIDTH_HORIZ),
                            "asset_height": getattr(vehicle, 'asset_height', Vehicle.TARGET_DRAW_HEIGHT_HORIZ),
                            "original_speed": vehicle.original_speed, 
                            "image_path": vehicle.image_path 
                        }
                    }
                    if self.rabbit_client and self.rabbit_client.async_exchange :
                        try:
                            await self.rabbit_client.publish_async(routing_key=target_zone_id, message=migration_payload)
                            vehicles_to_remove_ids.append(veh_id) 
                        except Exception as e:
                            print(f"[ZoneNode {self.zone_id}] ERROR publishing migration for {vehicle.id}: {e}")
                else: 
                    if not vehicle.is_despawned_globally:
                        vehicle.is_despawned_globally = True
                        asyncio.create_task(vehicle.publish_state("despawned_global"))
                        vehicles_to_remove_ids.append(veh_id)
            
        for vid in vehicles_to_remove_ids:
            if vid in self.vehicles:
                del self.vehicles[vid]

    def _determine_target_zone(self, vehicle: Vehicle) -> Optional[str]:
        adj_zones_ids = self.zone_config.get("adjacencies", [])
        if not adj_zones_ids: return None
        
        vehicle_center_global_x = vehicle.global_x + vehicle.draw_width / 2
        vehicle_center_global_y = vehicle.global_y + vehicle.draw_height / 2

        for adj_zone_id in adj_zones_ids:
            adj_zone_conf = next((z for z in self.global_city_config.get("zones", []) if z["id"] == adj_zone_id), None)
            if not adj_zone_conf: continue
            
            adj_bounds = pygame.Rect(
                int(adj_zone_conf["bounds"]["x"]), int(adj_zone_conf["bounds"]["y"]),
                int(adj_zone_conf["bounds"]["width"]), int(adj_zone_conf["bounds"]["height"])
            )
            if adj_bounds.collidepoint(vehicle_center_global_x, vehicle_center_global_y):
                return adj_zone_id
        return None

    async def update_tick(self):
        if not self.is_running: return

        if self.manual_spawn_pending:
            await self._spawn_new_vehicle_at_entry(manual_spawn=True)
            self.manual_spawn_pending = False
        
        self.pending_spawn_tasks = [task for task in self.pending_spawn_tasks if not task.done()]

        await self.zone_map.update() # Actualiza el estado de los semáforos
        
        self.spawn_timer +=1
        if self.spawn_timer >= self.spawn_interval:
            self.spawn_timer = 0
            await self._spawn_new_vehicle_at_entry(manual_spawn=False)

        zone_w, zone_h = self.zone_map.get_dimensions()
        current_zone_vehicles_list = list(self.vehicles.values()) 
        
        vehicle_update_tasks = []
        for vehicle in current_zone_vehicles_list:
            if not vehicle.is_despawned_globally:
                task = vehicle.update_in_zone( 
                    self.zone_map.get_traffic_lights_local(), 
                    current_zone_vehicles_list,
                    zone_w, zone_h, 
                    self.bounds.x, self.bounds.y 
                )
                vehicle_update_tasks.append(task)
        
        if vehicle_update_tasks: 
            results = await asyncio.gather(*vehicle_update_tasks, return_exceptions=True)
            for res in results: # Opcional: manejar excepciones de `update_in_zone`
                if isinstance(res, Exception):
                    # print(f"[ZoneNode {self.zone_id}] Error during vehicle update: {res}")
                    pass 
        
        await self._check_and_handle_migrations_out()

    def get_map_dimensions(self) -> Tuple[int,int]: return self.zone_map.get_dimensions()
    def get_drawable_vehicles(self) -> List[Vehicle]: return [v for v in self.vehicles.values() if not v.is_despawned_globally]
    
    def draw_zone_elements(self, main_screen_surface: pygame.Surface):
        """
        Dibuja los elementos de la zona que SÍ se renderizan dinámicamente (semáforos)
        directamente en la superficie principal de la pantalla.
        El fondo y las carreteras ahora son parte de una imagen estática manejada por MainGUI.
        """
        # ZoneMap.draw() ya no dibuja el fondo ni las carreteras si es una imagen.
        # Podría usarse si ZoneMap tuviera otros elementos dinámicos para dibujar, pero no es el caso ahora.
        # self.zone_map.draw(main_screen_surface, self.bounds.x, self.bounds.y)

        # Dibujar los semáforos de esta zona
        for light in self.zone_map.get_traffic_lights_local():
            # TrafficLight.draw() necesita el offset global de la zona para posicionarse correctamente
            # en la `main_screen_surface`.
            light.draw(main_screen_surface, self.bounds.x, self.bounds.y)

    def stop(self): self.is_running = False
    def get_pending_spawn_count(self) -> int: return len(self.pending_spawn_tasks)
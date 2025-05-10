# simulacion_trafico_engine/node/zone_node.py
import asyncio
import pygame
import uuid
import random
import json # Para serializar/deserializar mensajes
from typing import List, Dict, Optional, Any, Tuple

from simulacion_trafico_engine.core.vehicle import Vehicle
from simulacion_trafico_engine.core.traffic_light import TrafficLight
from simulacion_trafico_engine.core.zone_map import ZoneMap
from simulacion_trafico_engine.distribution.rabbitclient import RabbitMQClient
from simulacion_trafico_engine.performance.metrics import TrafficMetrics
from simulacion_trafico_engine.ui.theme import Theme, draw_rounded_rect

class ZoneNode:
    def __init__(self, zone_id: str, zone_config: Dict,
                 rabbit_client: RabbitMQClient,
                 metrics_client: TrafficMetrics,
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
        self.zone_map.initialize_map_elements(TrafficLightClass=TrafficLight)

        self.vehicles: Dict[str, Vehicle] = {}
        self.max_vehicles_in_zone = self.zone_config.get("max_vehicles_local", 20) # Configurable per zone
        self.spawn_timer = 0
        self.spawn_interval = random.randint(45, 90) # Randomize spawn interval slightly per zone

        self.is_running = True
        self.message_queue_name = f"zone.{self.zone_id}.migrations" # Cola específica para este nodo
        self.general_migration_exchange = "city_migrations_exchange" # Un exchange para todas las migraciones

        print(f"[ZoneNode {self.zone_id}] Initialized. Listening on {self.message_queue_name}")

    async def setup_rabbitmq_subscriptions(self):
        """Configura las suscripciones de RabbitMQ para este nodo."""
        if self.rabbit_client and self.rabbit_client.async_channel:
            try:
                # Declarar un exchange de tipo TOPIC para el routing de migraciones
                await self.rabbit_client.async_channel.exchange_declare(
                    name=self.general_migration_exchange,
                    type='topic', # Usaremos topic para routing basado en target_zone_id
                    durable=True
                )
                
                # Declarar una cola específica para este nodo
                queue = await self.rabbit_client.async_channel.declare_queue(
                    name=self.message_queue_name,
                    durable=True # La cola persistirá si el broker se reinicia
                )
                # Bind la cola al exchange con un routing key específico para esta zona
                # El routing key será el ID de la zona. Los mensajes se publicarán con este routing key.
                await queue.bind(exchange=self.general_migration_exchange, routing_key=self.zone_id)
                
                # Consumir mensajes de la cola
                await queue.consume(self._on_rabbitmq_message)
                print(f"[ZoneNode {self.zone_id}] Subscribed to RabbitMQ queue '{self.message_queue_name}' bound to '{self.general_migration_exchange}' with key '{self.zone_id}'.")
            except Exception as e:
                print(f"[ZoneNode {self.zone_id}] ERROR setting up RabbitMQ subscriptions: {e}")
        else:
            print(f"[ZoneNode {self.zone_id}] RabbitMQ client not ready for subscriptions.")

    async def _on_rabbitmq_message(self, message: Any): # message es aio_pika.IncomingMessage
        """Callback para procesar mensajes recibidos de RabbitMQ."""
        async with message.process(): # Importante para el ack/nack
            try:
                body_str = message.body.decode()
                # print(f"[ZoneNode {self.zone_id}] Received RabbitMQ message: {body_str[:200]}...") # Log সংক্ষিপ্ত
                data = json.loads(body_str)
                
                message_type = data.get("type") # Podríamos añadir un tipo al mensaje

                # Asumimos que todos los mensajes a esta cola son para migración ENTRANTE
                # En el futuro, podríamos tener diferentes tipos de mensajes
                if "vehicle_state" in data and data.get("target_zone") == self.zone_id:
                    print(f"[ZoneNode {self.zone_id}] Processing incoming migration for vehicle: {data.get('id')}")
                    await self._handle_incoming_vehicle_migration(data)
                else:
                    print(f"[ZoneNode {self.zone_id}] Received unhandled or misrouted message: {data.get('type', 'Unknown type')}")

            except json.JSONDecodeError:
                print(f"[ZoneNode {self.zone_id}] ERROR: Could not decode JSON from RabbitMQ message: {message.body[:100]}")
            except Exception as e:
                print(f"[ZoneNode {self.zone_id}] ERROR processing RabbitMQ message: {e}")


    async def _handle_incoming_vehicle_migration(self, migration_payload: Dict):
        veh_data = migration_payload.get("vehicle_state", {})
        veh_id = veh_data.get("id")

        if not veh_id:
            print(f"[ZoneNode {self.zone_id}] Invalid migration data: missing vehicle ID.")
            return
        if veh_id in self.vehicles:
            print(f"[ZoneNode {self.zone_id}] Vehicle {veh_id} already in zone, ignoring migration.")
            # Podría ser una confirmación tardía o un mensaje duplicado.
            # En un sistema robusto, se necesitaría un manejo de idempotencia.
            return
        if len(self.vehicles) >= self.max_vehicles_in_zone:
            print(f"[ZoneNode {self.zone_id}] Zone full, cannot accept migrated vehicle {veh_id}.")
            # Aquí se podría reenviar a otra zona o manejar la congestión.
            return

        print(f"[ZoneNode {self.zone_id}] Accepting migrated vehicle {veh_id} from zone {migration_payload.get('current_zone')}")

        color_tuple = veh_data.get("color_tuple", (128, 128, 128))
        try:
            vehicle_color = pygame.Color(int(color_tuple[0]), int(color_tuple[1]), int(color_tuple[2]))
        except (ValueError, TypeError):
            vehicle_color = Theme.get_vehicle_color()

        new_vehicle = Vehicle(
            id=str(veh_id),
            global_x=float(veh_data["position"]["x"]),
            global_y=float(veh_data["position"]["y"]),
            width=int(veh_data.get("width", 30)),
            height=int(veh_data.get("height", 15)),
            speed=float(veh_data.get("speed", veh_data.get("original_speed", 2.0))), # Usar speed, luego original_speed
            original_speed=float(veh_data.get("original_speed", veh_data.get("speed", 2.0))),
            direction=str(veh_data.get("direction", "right")),
            color=vehicle_color,
            current_zone_id=self.zone_id,
            rabbit_client=self.rabbit_client,
            metrics_client=self.metrics_client,
            map_ref=self.zone_map
        )
        self.vehicles[new_vehicle.id] = new_vehicle
        await new_vehicle.publish_state("migrated_in_zone", extra_data={"previous_zone": migration_payload.get("current_zone")})


    async def _spawn_new_vehicle_at_entry(self):
        if len(self.vehicles) >= self.max_vehicles_in_zone:
            return

        spawn_points_local = self.zone_map.get_spawn_points_local()
        if not spawn_points_local: 
            print(f"[ZoneNode {self.zone_id}] No spawn points available from zone_map.get_spawn_points_local().") # DEBUG
            return
        
        # --- DEBUG PRINT PARA SPAWN CHOICE ---
        spawn_choice = random.choice(spawn_points_local)
        print(f"[ZoneNode {self.zone_id}] Selected spawn_choice: {spawn_choice}")
        # --- FIN DEBUG PRINT ---

        global_spawn_x = self.bounds.x + spawn_choice["x"]
        global_spawn_y = self.bounds.y + spawn_choice["y"]
        
        new_id = f"veh_{self.zone_id}_{uuid.uuid4().hex[:4]}"
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
        # print(f"[ZoneNode {self.zone_id}] Spawned new vehicle {new_vehicle.id} at global ({global_spawn_x:.1f},{global_spawn_y:.1f}), local_choice: {spawn_choice}") # DEBUG
        await new_vehicle.publish_state("spawned_in_zone", extra_data={"entry_point": spawn_choice.get("entry_edge")})
    async def _check_and_handle_migrations_out(self): # Renombrado para claridad
        vehicles_to_remove_ids: List[str] = []
        
        for veh_id, vehicle in list(self.vehicles.items()):
            if vehicle.is_despawned_globally:
                vehicles_to_remove_ids.append(veh_id)
                continue

            vehicle_global_rect = vehicle.get_global_rect() # Usar el rect global del vehículo

            # Si el centro del vehículo ya no está en esta zona
            if not self.bounds.collidepoint(vehicle_global_rect.centerx, vehicle_global_rect.centery):
                target_zone_id = self._determine_target_zone(vehicle) # Usa la posición global
                
                if target_zone_id:
                    # print(f"[ZoneNode {self.zone_id}] Vehicle {vehicle.id} trying to migrate to {target_zone_id}")
                    color_val = vehicle.color
                    serializable_color = (color_val.r, color_val.g, color_val.b) if isinstance(color_val, pygame.Color) else (128,128,128)

                    # Mensaje que se envía para que OTRO NODO lo procese
                    migration_payload = {
                        "type": "vehicle_migration", # Tipo de mensaje
                        "id": vehicle.id, # ID del vehículo (para el mensaje, no necesariamente el del objeto)
                        "current_zone": self.zone_id, 
                        "target_zone": target_zone_id, # El routing key para RabbitMQ
                        "vehicle_state": { # Datos completos del vehículo
                            "id": vehicle.id, 
                            "position": {"x": vehicle.global_x, "y": vehicle.global_y},
                            "speed": vehicle.speed, 
                            "direction": vehicle.direction, 
                            "stopped": vehicle.stopped,
                            "width": vehicle.draw_width, 
                            "height": vehicle.draw_height,
                            "original_speed": vehicle.original_speed, 
                            "color_tuple": serializable_color 
                        }
                    }
                    
                    if self.rabbit_client and self.rabbit_client.async_exchange : # async_exchange debe estar listo
                        try:
                            # Publicar al exchange general, con el target_zone_id como routing key
                            await self.rabbit_client.publish_async(
                                routing_key=target_zone_id, # El nodo destino está suscrito a este key
                                message=migration_payload # El objeto JSON completo
                            )
                            print(f"[ZoneNode {self.zone_id}] >>> Sent migration request for {vehicle.id} to {target_zone_id} (routing_key: {target_zone_id}).")
                            vehicles_to_remove_ids.append(veh_id) # Marcar para eliminar de este nodo
                        except Exception as e:
                            print(f"[ZoneNode {self.zone_id}] ERROR publishing migration for {vehicle.id}: {e}")
                else: 
                    if not vehicle.is_despawned_globally:
                        vehicle.is_despawned_globally = True
                        # print(f"[ZoneNode {self.zone_id}] Vehicle {vehicle.id} despawned globally (no target zone).")
                        await vehicle.publish_state("despawned_global")
                        vehicles_to_remove_ids.append(veh_id)
            
        for vid in vehicles_to_remove_ids:
            if vid in self.vehicles:
                # print(f"[ZoneNode {self.zone_id}] --- Removing vehicle {vid} from local list (migrated/despawned).")
                del self.vehicles[vid]

    # _determine_target_zone y otras funciones de ayuda permanecen igual
    # ... (copia el resto de _determine_target_zone, update_tick, get_drawable_vehicles, etc.
    #      de la versión anterior de zone_node.py que te funcionaba, asegurando que
    #      _check_and_handle_migrations_out se llame en update_tick)
    # Es importante que `update_tick` llame a `_check_and_handle_migrations_out`

    def _determine_target_zone(self, vehicle: Vehicle) -> Optional[str]:
        adj_zones_ids = self.zone_config.get("adjacencies", [])
        if not adj_zones_ids: return None
        for adj_zone_id in adj_zones_ids:
            adj_zone_conf = next((z for z in self.global_city_config.get("zones", []) if z["id"] == adj_zone_id), None)
            if not adj_zone_conf: continue
            adj_bounds = pygame.Rect( int(adj_zone_conf["bounds"]["x"]), int(adj_zone_conf["bounds"]["y"]), int(adj_zone_conf["bounds"]["width"]), int(adj_zone_conf["bounds"]["height"]))
            vehicle_center_x = vehicle.global_x + vehicle.draw_width / 2
            vehicle_center_y = vehicle.global_y + vehicle.draw_height / 2
            if adj_bounds.collidepoint(vehicle_center_x, vehicle_center_y):
                return adj_zone_id
        return None

    async def update_tick(self):
        if not self.is_running: return
        await self.zone_map.update()
        self.spawn_timer +=1
        if self.spawn_timer >= self.spawn_interval:
            self.spawn_timer = 0
            await self._spawn_new_vehicle_at_entry()

        zone_w, zone_h = self.zone_map.get_dimensions()
        vehicle_update_tasks = []
        current_zone_vehicles_list = list(self.vehicles.values()) 
        for vehicle in current_zone_vehicles_list:
            if not vehicle.is_despawned_globally:
                task = vehicle.update_in_zone( self.zone_map.get_traffic_lights_local(), current_zone_vehicles_list, zone_w, zone_h, self.bounds.x, self.bounds.y)
                vehicle_update_tasks.append(task)
        if vehicle_update_tasks: 
            results = await asyncio.gather(*vehicle_update_tasks, return_exceptions=True)
            for i, res in enumerate(results):
                if isinstance(res, Exception): print(f"[ZoneNode {self.zone_id}] Error updating a vehicle: {res}")
        
        await self._check_and_handle_migrations_out() # Cambio de nombre aquí

    def get_map_dimensions(self) -> Tuple[int,int]: return self.zone_map.get_dimensions()
    def get_drawable_vehicles(self) -> List[Vehicle]: return [v for v in self.vehicles.values() if not v.is_despawned_globally]
    def draw_zone_elements(self, main_screen_surface: pygame.Surface): self.zone_map.draw(main_screen_surface, self.bounds.x, self.bounds.y)
    def stop(self): self.is_running = False
    # run_simulation_loop_standalone_debug puede permanecer igual para pruebas aisladas
    async def run_simulation_loop_standalone_debug(self):
        pygame.init(); debug_screen = pygame.display.set_mode((self.bounds.width, self.bounds.height)); pygame.display.set_caption(f"Debug Zone: {self.zone_id}"); clock = pygame.time.Clock()
        while self.is_running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT: self.is_running = False
            await self.update_tick()
            debug_screen.fill(Theme.COLOR_GRASS)
            self.zone_map.draw(debug_screen, 0, 0) 
            for vehicle in self.get_drawable_vehicles(): draw_rounded_rect(debug_screen, vehicle.color, vehicle.rect, Theme.BORDER_RADIUS//2)
            pygame.display.flip(); clock.tick(30); await asyncio.sleep(0) 
        pygame.quit()
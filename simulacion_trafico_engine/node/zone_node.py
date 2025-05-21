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
        self.max_vehicles_in_zone = self.zone_config.get("max_vehicles_local", 20) 
        self.spawn_timer = 0
        self.spawn_interval = random.randint(45, 90) 

        self.is_running = True
        self.message_queue_name = f"zone.{self.zone_id}.migrations"
        self.general_migration_exchange = self.global_city_config.get("rabbitmq_exchange", "city_traffic_exchange") # Use global exchange name

        # --- ADDED FOR MANUAL SPAWNING ---
        self.manual_spawn_pending = False
        self.pending_spawn_tasks = [] # To keep track of async spawn tasks
        # --- END ADDED ---

        print(f"[ZoneNode {self.zone_id}] Initialized. Listening on {self.message_queue_name}")

    # --- ADDED METHOD FOR MANUAL SPAWNING ---
    def trigger_manual_spawn(self):
        """Requests a manual vehicle spawn in the next update tick."""
        if len(self.vehicles) < self.max_vehicles_in_zone:
            self.manual_spawn_pending = True
            print(f"[ZoneNode {self.zone_id}] Manual spawn requested.")
            return True
        else:
            print(f"[ZoneNode {self.zone_id}] Manual spawn requested, but zone is full.")
            return False
    # --- END ADDED METHOD ---

    async def setup_rabbitmq_subscriptions(self):
        if self.rabbit_client and self.rabbit_client.async_channel:
            try:
                # Ensure the exchange exists (it might be declared by the orchestrator too)
                await self.rabbit_client.async_channel.exchange_declare(
                    name=self.general_migration_exchange,
                    type='topic', 
                    durable=True
                )
                
                queue = await self.rabbit_client.async_channel.declare_queue(
                    name=self.message_queue_name,
                    durable=True
                )
                await queue.bind(exchange=self.general_migration_exchange, routing_key=self.zone_id)
                
                await queue.consume(self._on_rabbitmq_message)
                print(f"[ZoneNode {self.zone_id}] Subscribed to RabbitMQ queue '{self.message_queue_name}' bound to '{self.general_migration_exchange}' with key '{self.zone_id}'.")
            except Exception as e:
                print(f"[ZoneNode {self.zone_id}] ERROR setting up RabbitMQ subscriptions: {e}")
        else:
            print(f"[ZoneNode {self.zone_id}] RabbitMQ client not ready for subscriptions.")

    async def _on_rabbitmq_message(self, message: Any): 
        async with message.process(): 
            try:
                body_str = message.body.decode()
                data = json.loads(body_str)
                
                message_type = data.get("type")

                if "vehicle_state" in data and data.get("target_zone") == self.zone_id:
                    # print(f"[ZoneNode {self.zone_id}] Processing incoming migration for vehicle: {data.get('id')}")
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
            return
        if len(self.vehicles) >= self.max_vehicles_in_zone:
            print(f"[ZoneNode {self.zone_id}] Zone full, cannot accept migrated vehicle {veh_id}.")
            return

        # print(f"[ZoneNode {self.zone_id}] Accepting migrated vehicle {veh_id} from zone {migration_payload.get('current_zone')}")

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
            speed=float(veh_data.get("speed", veh_data.get("original_speed", 2.0))),
            original_speed=float(veh_data.get("original_speed", veh_data.get("speed", 2.0))),
            direction=str(veh_data.get("direction", "right")),
            color=vehicle_color,
            current_zone_id=self.zone_id,
            rabbit_client=self.rabbit_client,
            metrics_client=self.metrics_client,
            map_ref=self.zone_map
        )
        self.vehicles[new_vehicle.id] = new_vehicle
        # Use create_task for fire-and-forget async operations
        asyncio.create_task(new_vehicle.publish_state("migrated_in_zone", extra_data={"previous_zone": migration_payload.get("current_zone")}))


    async def _spawn_new_vehicle_at_entry(self, manual_spawn=False): # Added manual_spawn flag
        if len(self.vehicles) >= self.max_vehicles_in_zone:
            if manual_spawn: print(f"[ZoneNode {self.zone_id}] Manual spawn failed: Zone is full.")
            return

        spawn_points_local = self.zone_map.get_spawn_points_local()
        if not spawn_points_local: 
            # print(f"[ZoneNode {self.zone_id}] No spawn points available.")
            return
        
        spawn_choice = random.choice(spawn_points_local)
        # print(f"[ZoneNode {self.zone_id}] Selected spawn_choice: {spawn_choice}")

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
        spawn_type = "manual_spawned" if manual_spawn else "auto_spawned"
        # print(f"[ZoneNode {self.zone_id}] {spawn_type.capitalize()} new vehicle {new_vehicle.id}")
        # Use create_task for fire-and-forget async operations
        task = asyncio.create_task(new_vehicle.publish_state(
            "spawned_in_zone", 
            extra_data={"entry_point": spawn_choice.get("entry_edge"), "spawn_type": spawn_type}
        ))
        self.pending_spawn_tasks.append(task)


    async def _check_and_handle_migrations_out(self):
        vehicles_to_remove_ids: List[str] = []
        
        for veh_id, vehicle in list(self.vehicles.items()):
            if vehicle.is_despawned_globally:
                vehicles_to_remove_ids.append(veh_id)
                continue

            vehicle_global_rect = vehicle.get_global_rect()

            if not self.bounds.collidepoint(vehicle_global_rect.centerx, vehicle_global_rect.centery):
                target_zone_id = self._determine_target_zone(vehicle)
                
                if target_zone_id:
                    color_val = vehicle.color
                    serializable_color = (color_val.r, color_val.g, color_val.b) if isinstance(color_val, pygame.Color) else (128,128,128)

                    migration_payload = {
                        "type": "vehicle_migration",
                        "id": vehicle.id, 
                        "current_zone": self.zone_id, 
                        "target_zone": target_zone_id,
                        "vehicle_state": {
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
                    
                    if self.rabbit_client and self.rabbit_client.async_exchange :
                        try:
                            await self.rabbit_client.publish_async(
                                routing_key=target_zone_id, 
                                message=migration_payload
                            )
                            # print(f"[ZoneNode {self.zone_id}] >>> Sent migration request for {vehicle.id} to {target_zone_id}.")
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

        # --- MODIFIED FOR MANUAL SPAWNING ---
        if self.manual_spawn_pending:
            await self._spawn_new_vehicle_at_entry(manual_spawn=True)
            self.manual_spawn_pending = False # Reset flag
        # --- END MODIFIED ---
        
        # Clean up completed spawn tasks
        self.pending_spawn_tasks = [task for task in self.pending_spawn_tasks if not task.done()]


        await self.zone_map.update()
        
        # Automatic spawning
        self.spawn_timer +=1
        if self.spawn_timer >= self.spawn_interval:
            self.spawn_timer = 0
            await self._spawn_new_vehicle_at_entry(manual_spawn=False)

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
                if isinstance(res, Exception): 
                    # This can be noisy, consider logging to file or less frequent printing
                    # print(f"[ZoneNode {self.zone_id}] Error updating a vehicle: {res}")
                    pass 
        
        await self._check_and_handle_migrations_out()

    def get_map_dimensions(self) -> Tuple[int,int]: return self.zone_map.get_dimensions()
    def get_drawable_vehicles(self) -> List[Vehicle]: return [v for v in self.vehicles.values() if not v.is_despawned_globally]
    def draw_zone_elements(self, main_screen_surface: pygame.Surface): self.zone_map.draw(main_screen_surface, self.bounds.x, self.bounds.y)
    def stop(self): self.is_running = False
    
    def get_pending_spawn_count(self) -> int:
        return len(self.pending_spawn_tasks)


    async def run_simulation_loop_standalone_debug(self):
        # This method is for isolated debugging and might not reflect full GUI integration.
        pygame.init()
        debug_screen = pygame.display.set_mode((self.bounds.width, self.bounds.height))
        pygame.display.set_caption(f"Debug Zone: {self.zone_id}")
        clock = pygame.time.Clock()
        
        # For debug: Setup RabbitMQ if not done by an orchestrator
        if self.rabbit_client and not self.rabbit_client.async_connection:
            try:
                await self.rabbit_client.connect_async()
                await self.setup_rabbitmq_subscriptions() # Important for migrations
            except Exception as e:
                print(f"[Debug {self.zone_id}] Failed to connect/setup RabbitMQ: {e}")


        while self.is_running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT: self.is_running = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        self.trigger_manual_spawn() # Test manual spawn

            await self.update_tick()
            
            debug_screen.fill(Theme.COLOR_GRASS) # Or use zone_map background
            self.zone_map.draw(debug_screen, 0, 0) # Draw map relative to debug_screen
            
            # Draw vehicles relative to the debug_screen (local coordinates)
            for vehicle in self.get_drawable_vehicles():
                # For debug drawing, vehicle.rect is local to its zone.
                # If global_offset_x/y for the zone is 0,0 then vehicle.rect is already correct.
                # If this debug mode is for a zone NOT at 0,0, vehicle.rect would need adjustment.
                # However, vehicle.rect is updated in update_in_zone using local coords already.
                local_draw_rect = vehicle.rect.copy()
                local_draw_rect.topleft = (
                    vehicle.global_x - self.bounds.x, 
                    vehicle.global_y - self.bounds.y
                )
                draw_rounded_rect(debug_screen, vehicle.color, local_draw_rect, Theme.BORDER_RADIUS//2)

            pygame.display.flip()
            clock.tick(30)
            await asyncio.sleep(0) # Yield control for other async tasks
            
        if self.rabbit_client and self.rabbit_client.async_connection:
            await self.rabbit_client.disconnect_async()
        pygame.quit()
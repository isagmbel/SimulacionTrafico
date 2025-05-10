# simulacion_trafico_engine/ui/gui.py
import pygame
import random
import asyncio
import concurrent.futures
import time
import sys
import os
from typing import List, Dict, Any, Optional, TYPE_CHECKING

from simulacion_trafico_engine.environment.vehicle import Vehicle
from simulacion_trafico_engine.environment.trafficlight import TrafficLight
from simulacion_trafico_engine.environment.map import Map
from .theme import Theme # Import Theme
from .info_panel import InfoPanel # Import InfoPanel

if TYPE_CHECKING:
    from simulacion_trafico_engine.distribution.rabbitclient import RabbitMQClient
    from simulacion_trafico_engine.performance.metrics import TrafficMetrics

class GUI:
    def __init__(self, width: int = 1280, height: int = 720, fps: int = 30,
                 rabbit_client: Optional['RabbitMQClient'] = None,
                 metrics_client: Optional['TrafficMetrics'] = None):
        pygame.init()
        self.width = width
        self.height = height
        self.fps = fps
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("Async Traffic Simulation Engine - Pastel Edition") # Normal Caption
        self.running = True

        self.rabbit_client = rabbit_client
        self.metrics_client = metrics_client
        
        self.simulation_area_width = self.width * (1 - Theme.INFO_PANEL_WIDTH_RATIO)

        self.map = Map(self.width, self.height, rabbit_client=self.rabbit_client, metrics_client=self.metrics_client)
        self.map.initialize_map_elements(TrafficLightClass=TrafficLight)

        self.vehicles: List[Vehicle] = []
        # --- REVERTED TO NORMAL SPAWNING ---
        self.spawn_timer = 0
        self.spawn_interval = int(1.0 * fps) # Normal spawn interval (e.g., 1 car per second at 30fps)
        self.max_vehicles = 30 # Normal max vehicles
        # --- END REVERTED ---

        self.font = Theme.get_font(Theme.FONT_SIZE_NORMAL)
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=(os.cpu_count() or 1) + 4)
        self.vehicle_creation_tasks: List[asyncio.Task] = []
        self.actual_fps = float(fps)

        self.info_panel = InfoPanel(self.width, self.height, self.get_metrics_for_panel)
        # print("[GUI DEBUG] GUI Initialized.") # Optional: keep for init confirmation

    def get_metrics_for_panel(self) -> dict:
        if self.metrics_client:
            return self.metrics_client.get_metrics()
        return {}

    def _blocking_vehicle_create_logic(self, spawn_config: Dict[str, Any]) -> Vehicle:
        # print(f"[GUI DEBUG (blocking_logic)] Spawning vehicle with config: {spawn_config}") # Optional
        vehicle_instance = Vehicle(
            x=spawn_config["x"], y=spawn_config["y"],
            speed=random.uniform(2.0, 4.0),
            direction=spawn_config["direction"],
            rabbit_client=self.rabbit_client, metrics_client=self.metrics_client, map_ref=self.map
        )
        # print(f"[GUI DEBUG (blocking_logic)] CREATED Vehicle: id={vehicle_instance.id}, rect={vehicle_instance.rect}") # Optional
        return vehicle_instance

    async def _create_vehicle_offloaded(self, spawn_config: Dict[str, Any]) -> Optional[Vehicle]:
        loop = asyncio.get_running_loop()
        try:
            vehicle = await loop.run_in_executor(self.executor, self._blocking_vehicle_create_logic, spawn_config)
            return vehicle
        except Exception as e:
            print(f"[GUI ERROR] Error during vehicle creation in executor: {e}")
            if self.metrics_client: self.metrics_client.log_event(f"Error during vehicle creation: {e}", "error")
            return None

    async def manage_vehicle_spawning(self) -> None:
        # --- REVERTED TO NORMAL SPAWNING LOGIC ---
        self.spawn_timer += 1
        if self.spawn_timer >= self.spawn_interval and \
           len(self.vehicles) + len(self.vehicle_creation_tasks) < self.max_vehicles:
            self.spawn_timer = 0
            spawn_points = self.map.get_spawn_points()
            if not spawn_points: return
            spawn_config = random.choice(spawn_points)
            # print(f"[GUI DEBUG (manage_spawning)] Spawning vehicle with config: {spawn_config}") # Optional
            task = asyncio.create_task(self._create_vehicle_offloaded(spawn_config))
            self.vehicle_creation_tasks.append(task)
        # --- END REVERTED ---

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: self.running = False
                # --- RE-ENABLED MANUAL SPAWN ---
                elif event.key == pygame.K_SPACE:
                    if len(self.vehicles) + len(self.vehicle_creation_tasks) < self.max_vehicles + 5: # Allow a few extra via manual spawn
                        spawn_points = self.map.get_spawn_points()
                        if spawn_points:
                            spawn_config = random.choice(spawn_points)
                            print(f"[GUI DEBUG] Manual spawn initiated with config: {spawn_config}") # Optional
                            task = asyncio.create_task(self._create_vehicle_offloaded(spawn_config))
                            self.vehicle_creation_tasks.append(task)
                # --- END RE-ENABLED ---

    async def update_simulation_state(self) -> None:
        if self.metrics_client: self.metrics_client.simulation_step_start()

        if self.vehicle_creation_tasks:
            done_tasks, pending_tasks = await asyncio.wait(self.vehicle_creation_tasks, timeout=0)
            for task in done_tasks:
                try:
                    vehicle = task.result()
                    if vehicle:
                        self.vehicles.append(vehicle)
                        # print(f"[GUI DEBUG (update_sim)] ADDED vehicle {vehicle.id}. Total: {len(self.vehicles)}") # Optional
                        if vehicle.rabbit_client: # Publish spawn state from main async loop
                            asyncio.create_task(vehicle.publish_state("spawned"))
                except Exception as e:
                    print(f"[GUI ERROR (update_sim)] Vehicle creation task failed: {e}")
            self.vehicle_creation_tasks = list(pending_tasks)

        await self.map.update()

        # --- REMOVED SINGLE CAR DEBUG PRINTS ---
        current_vehicles_list = list(self.vehicles)
        vehicle_update_coroutines = [
            v.update_async(self.map.get_traffic_lights(), current_vehicles_list, int(self.simulation_area_width), self.height)
            for v in self.vehicles if not v.is_despawned
        ]
        if vehicle_update_coroutines:
            results = await asyncio.gather(*vehicle_update_coroutines, return_exceptions=True)
            # Optional: Error handling for results if needed
            for i, res in enumerate(results):
                if isinstance(res, Exception):
                    # This part for identifying the vehicle could be improved
                    # For now, just log that an error occurred during an update
                    print(f"[GUI ERROR (update_sim)] Error during vehicle update: {res}")


        self.vehicles = [v for v in self.vehicles if not v.is_despawned]
        await self.manage_vehicle_spawning() # Normal spawning enabled
        if self.metrics_client: self.metrics_client.simulation_step_end()

    def render_graphics(self) -> None:
        self.screen.fill(Theme.COLOR_BACKGROUND)
        self.map.draw(self.screen)
        
        for vehicle_obj in self.vehicles:
            vehicle_obj.draw(self.screen)
        
        gui_metrics_for_panel = {
            "max_vehicles": self.max_vehicles,
            "actual_fps": self.actual_fps,
            "target_fps": self.fps,
            "pending_spawns": len(self.vehicle_creation_tasks)
        }
        self.info_panel.draw(self.screen, gui_metrics_for_panel)
        
        pygame.display.flip()

    async def run(self) -> None:
        current_loop = asyncio.get_running_loop()
        target_frame_duration = 1.0 / self.fps
        try:
            while self.running:
                frame_start_time = current_loop.time()
                self.handle_events()
                if not self.running: break
                await self.update_simulation_state()
                self.render_graphics()
                elapsed_time = current_loop.time() - frame_start_time
                sleep_duration = target_frame_duration - elapsed_time
                if sleep_duration > 0: await asyncio.sleep(sleep_duration)
                actual_duration = current_loop.time() - frame_start_time
                self.actual_fps = 1.0 / actual_duration if actual_duration > 0 else float('inf')
        finally:
            # print("[GUI DEBUG] Simulation loop ending.") # Optional
            if self.metrics_client: self.metrics_client.log_event("Simulation loop gracefully ended.")
            for task in self.vehicle_creation_tasks:
                if not task.done(): task.cancel()
            if self.vehicle_creation_tasks: await asyncio.gather(*self.vehicle_creation_tasks, return_exceptions=True)
            self.executor.shutdown(wait=True)
            if self.metrics_client: self.metrics_client.save_metrics_to_file("gui_shutdown_final_")
            pygame.quit()
            # print("[GUI DEBUG] Pygame quit.") # Optional
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
    def __init__(self, width: int = 1280, height: int = 720, fps: int = 30, # Default to larger size
                 rabbit_client: Optional['RabbitMQClient'] = None,
                 metrics_client: Optional['TrafficMetrics'] = None):
        pygame.init()
        self.width = width
        self.height = height
        self.fps = fps
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("Async Traffic Simulation Engine - Pastel Edition")
        self.running = True

        self.rabbit_client = rabbit_client
        self.metrics_client = metrics_client
        
        # Calculate simulation area width before initializing map
        self.simulation_area_width = self.width * (1 - Theme.INFO_PANEL_WIDTH_RATIO)

        self.map = Map(self.width, self.height, rabbit_client=self.rabbit_client, metrics_client=self.metrics_client) # Map still gets full width for now
        self.map.initialize_map_elements(TrafficLightClass=TrafficLight)

        self.vehicles: List[Vehicle] = []
        self.spawn_timer = 0
        self.spawn_interval = int(1.0 * fps) # Faster spawning
        self.max_vehicles = 30

        self.font = Theme.get_font(Theme.FONT_SIZE_NORMAL) # Use Theme font
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=(os.cpu_count() or 1) + 4)
        self.vehicle_creation_tasks: List[asyncio.Task] = []
        self.actual_fps = float(fps)

        # Initialize InfoPanel
        self.info_panel = InfoPanel(self.width, self.height, self.get_metrics_for_panel)
        print("[GUI DEBUG] GUI Initialized with InfoPanel.")

    def get_metrics_for_panel(self) -> dict:
        """Provides metrics from the metrics_client to the info panel."""
        if self.metrics_client:
            return self.metrics_client.get_metrics()
        return {} # Return empty dict if no metrics client

    def _blocking_vehicle_create_logic(self, spawn_config: Dict[str, Any]) -> Vehicle:
        # print(f"[GUI DEBUG] _blocking_vehicle_create_logic: Attempting to create vehicle with config: {spawn_config}")
        # Color is now handled by Vehicle using Theme
        vehicle_instance = Vehicle(
            x=spawn_config["x"], y=spawn_config["y"],
            speed=random.uniform(2.0, 4.0), # Slightly faster vehicles
            direction=spawn_config["direction"],
            rabbit_client=self.rabbit_client, metrics_client=self.metrics_client, map_ref=self.map
        )
        # print(f"[GUI DEBUG] _blocking_vehicle_create_logic: CREATED Vehicle: id={vehicle_instance.id}, rect={vehicle_instance.rect}")
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
        self.spawn_timer += 1
        if self.spawn_timer >= self.spawn_interval and len(self.vehicles) + len(self.vehicle_creation_tasks) < self.max_vehicles:
            self.spawn_timer = 0
            spawn_points = self.map.get_spawn_points()
            if not spawn_points: return
            spawn_config = random.choice(spawn_points)
            task = asyncio.create_task(self._create_vehicle_offloaded(spawn_config))
            self.vehicle_creation_tasks.append(task)

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: self.running = False
                elif event.key == pygame.K_SPACE:
                    spawn_points = self.map.get_spawn_points()
                    if spawn_points:
                        spawn_config = random.choice(spawn_points)
                        task = asyncio.create_task(self._create_vehicle_offloaded(spawn_config))
                        self.vehicle_creation_tasks.append(task)

    async def update_simulation_state(self) -> None:
        if self.metrics_client: self.metrics_client.simulation_step_start()

        if self.vehicle_creation_tasks:
            done_tasks, pending_tasks = await asyncio.wait(self.vehicle_creation_tasks, timeout=0)
            for task in done_tasks:
                try:
                    vehicle = task.result()
                    if vehicle: self.vehicles.append(vehicle)
                        # print(f"[GUI DEBUG] Added vehicle {vehicle.id}. Total: {len(self.vehicles)}")
                except Exception as e:
                    print(f"[GUI ERROR] Vehicle creation task failed: {e}")
                    if self.metrics_client: self.metrics_client.log_event(f"Vehicle creation task failed: {e}", "error")
            self.vehicle_creation_tasks = list(pending_tasks)

        await self.map.update()
        current_vehicles_list = list(self.vehicles)
        vehicle_update_coroutines = [
            # Pass simulation_area_width for boundary checks
            v.update_async(self.map.get_traffic_lights(), current_vehicles_list, int(self.simulation_area_width), self.height)
            for v in self.vehicles if not v.is_despawned
        ]
        if vehicle_update_coroutines:
            await asyncio.gather(*vehicle_update_coroutines, return_exceptions=True) # Errors handled by printing

        self.vehicles = [v for v in self.vehicles if not v.is_despawned]
        await self.manage_vehicle_spawning()
        if self.metrics_client: self.metrics_client.simulation_step_end()

    def render_graphics(self) -> None:
        # Fill entire screen with a base color (can be same as map bg or different)
        self.screen.fill(Theme.COLOR_BACKGROUND) 
        
        self.map.draw(self.screen) # Map draws only in its simulation_area_width
        for vehicle in self.vehicles:
            vehicle.draw(self.screen)

        # Prepare GUI specific metrics for the panel
        gui_metrics_for_panel = {
            "max_vehicles": self.max_vehicles,
            "actual_fps": self.actual_fps,
            "target_fps": self.fps,
            "pending_spawns": len(self.vehicle_creation_tasks)
        }
        self.info_panel.draw(self.screen, gui_metrics_for_panel) # Draw info panel on top
        
        pygame.display.flip()

    async def run(self) -> None:
        # ... (run loop remains largely the same as your last good version) ...
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
            if self.metrics_client: self.metrics_client.log_event("Simulation loop gracefully ended.")
            for task in self.vehicle_creation_tasks:
                if not task.done(): task.cancel()
            if self.vehicle_creation_tasks: await asyncio.gather(*self.vehicle_creation_tasks, return_exceptions=True)
            self.executor.shutdown(wait=True)
            if self.metrics_client: self.metrics_client.save_metrics_to_file("gui_shutdown_final_")
            pygame.quit()
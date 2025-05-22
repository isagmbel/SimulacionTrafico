import pygame
import asyncio
from typing import List, Dict, Optional, Any, TYPE_CHECKING

# Core engine components
from simulacion_trafico_engine.core.vehicle import Vehicle 
from simulacion_trafico_engine.core.traffic_light import TrafficLight
from simulacion_trafico_engine.core.zone_map import ZoneMap 

# UI components
from .theme import Theme, draw_rounded_rect 
from .info_panel import InfoPanel # InfoPanel is already imported
from .main_menu import MainMenu 

if TYPE_CHECKING:
    from simulacion_trafico_engine.distribution.rabbitclient import RabbitMQClient
    from simulacion_trafico_engine.performance.metrics import TrafficMetrics
    from simulacion_trafico_engine.node.zone_node import ZoneNode

class MainGUI:
    STATE_MENU = 0
    STATE_SIMULATION = 1

    def __init__(self, city_config: Dict,
                 metrics_client: Optional['TrafficMetrics'] = None):
        self.city_config = city_config
        
        # --- FIXED WINDOW SIZE BASED ON MAP DIMENSIONS ---
        self.map_render_width = city_config["global_map_width"]
        self.map_render_height = city_config["global_map_height"]
        # --- END FIXED WINDOW SIZE ---
        
        pygame.init()
        pygame.font.init() 
        # --- SET SCREEN TO MAP DIMENSIONS ---
        self.screen = pygame.display.set_mode((self.map_render_width, self.map_render_height))
        pygame.display.set_caption("Rush Hour") # New window title
        # --- END SET SCREEN ---
        
        self.running = True
        self.fps = 30 
        self.actual_fps = float(self.fps)
        
        self.metrics_client = metrics_client
        # --- INFO PANEL INITIALIZED WITH MAP DIMENSIONS ---
        self.info_panel = InfoPanel(self.map_render_width, self.map_render_height, self._get_sim_metrics)
        # --- END INFO PANEL INIT ---

        self.zone_nodes: Dict[str, 'ZoneNode'] = {} 

        self.game_state = MainGUI.STATE_MENU
        # --- MAIN MENU INITIALIZED WITH MAP DIMENSIONS ---
        self.main_menu = MainMenu(self.map_render_width, self.map_render_height)
        # --- END MAIN MENU INIT ---


    def register_zone_node(self, node: 'ZoneNode'):
        self.zone_nodes[node.zone_id] = node

    def _get_sim_metrics(self) -> dict:
        if self.metrics_client:
            return self.metrics_client.get_metrics() 
        return {}

    def handle_events(self):
        mouse_pos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT: 
                self.running = False
            
            # --- Pass event to InfoPanel first if in simulation state ---
            if self.game_state == MainGUI.STATE_SIMULATION:
                if self.info_panel.handle_event(event, mouse_pos):
                    continue # Event was handled by the panel (e.g., toggle)

            if self.game_state == MainGUI.STATE_MENU:
                action = self.main_menu.handle_event(event, mouse_pos)
                if action == MainMenu.ACTION_START_SIM:
                    self.game_state = MainGUI.STATE_SIMULATION
                    print("[MainGUI] Starting simulation...")
                    if self.metrics_client: 
                        self.metrics_client.metrics_data["simulation_time_steps"] = 0 
                elif action == MainMenu.ACTION_QUIT:
                    self.running = False
            
            elif self.game_state == MainGUI.STATE_SIMULATION:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.game_state = MainGUI.STATE_MENU 
                        print("[MainGUI] Returning to main menu.")
                    elif event.key == pygame.K_SPACE:
                        if self.zone_nodes:
                            # Simplified: spawn in the first available node
                            try:
                                node_id_to_spawn_in = list(self.zone_nodes.keys())[0] 
                                target_node = self.zone_nodes.get(node_id_to_spawn_in)
                                if target_node:
                                    target_node.trigger_manual_spawn()
                            except IndexError:
                                print("[MainGUI] No zones available to spawn vehicle.")
                    elif event.key == pygame.K_TAB: # --- TOGGLE INFO PANEL ---
                        self.info_panel.toggle_expansion()


    def render(self):
        if self.game_state == MainGUI.STATE_MENU:
            self.main_menu.draw(self.screen)
        elif self.game_state == MainGUI.STATE_SIMULATION:
            # --- SIMULATION AREA IS NOW THE FULL SCREEN ---
            self.screen.fill(Theme.COLOR_GRASS) # Base background for map area

            for zone_id, node in self.zone_nodes.items():
                # ZoneMap.draw now draws directly onto self.screen (the main simulation surface)
                # at the zone's global offset.
                node.draw_zone_elements(self.screen) 
                for vehicle in node.get_drawable_vehicles():
                    # Vehicle.draw also draws directly onto self.screen using global coords.
                    vehicle.draw(self.screen)
            
            # --- DRAW INFO PANEL OVER THE SIMULATION ---
            active_vehicle_count = sum(len(node.get_drawable_vehicles()) for node in self.zone_nodes.values())
            total_max_vehicles_estimate = sum(node.max_vehicles_in_zone for node in self.zone_nodes.values())
            total_pending_spawns = 0
            if self.zone_nodes:
                 total_pending_spawns = sum(node.get_pending_spawn_count() for node in self.zone_nodes.values() if hasattr(node, 'get_pending_spawn_count'))

            gui_panel_metrics = {
                 "max_vehicles": f"~{total_max_vehicles_estimate}", # Simplified
                 "actual_fps": self.actual_fps,
                 "target_fps": self.fps,
                 "pending_spawns": total_pending_spawns,
                 "current_vehicle_count": active_vehicle_count 
            }
            self.info_panel.draw(self.screen, gui_panel_metrics) # Draw info panel last
        
        pygame.display.flip()

    async def run_gui_loop(self):
        loop = asyncio.get_running_loop()
        target_frame_duration = 1.0 / self.fps
        simulation_running_this_frame = False

        while self.running:
            frame_start_time = loop.time()
            
            self.handle_events() 
            if not self.running: break
            
            if self.game_state == MainGUI.STATE_SIMULATION:
                if not simulation_running_this_frame: 
                    if self.metrics_client: self.metrics_client.log_event("Simulation view started.")
                simulation_running_this_frame = True
                if self.metrics_client: self.metrics_client.simulation_step_start()
            else: 
                if simulation_running_this_frame: 
                     if self.metrics_client: self.metrics_client.log_event("Simulation view paused/stopped (menu).")
                simulation_running_this_frame = False

            self.render() 
            
            if self.game_state == MainGUI.STATE_SIMULATION and self.metrics_client:
                self.metrics_client.simulation_step_end()

            elapsed = loop.time() - frame_start_time
            await asyncio.sleep(max(0, target_frame_duration - elapsed))
            
            frame_time_taken = loop.time() - frame_start_time
            if frame_time_taken > 0 :
                 self.actual_fps = 1.0 / frame_time_taken
            else:
                 self.actual_fps = float('inf')
        
        pygame.quit()
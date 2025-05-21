import pygame
import asyncio
from typing import List, Dict, Optional, Any, TYPE_CHECKING

from simulacion_trafico_engine.core.vehicle import Vehicle 
from simulacion_trafico_engine.core.traffic_light import TrafficLight
from simulacion_trafico_engine.core.zone_map import ZoneMap 
from .theme import Theme, draw_rounded_rect # Ensure draw_rounded_rect is imported
from .info_panel import InfoPanel

if TYPE_CHECKING:
    from simulacion_trafico_engine.distribution.rabbitclient import RabbitMQClient
    from simulacion_trafico_engine.performance.metrics import TrafficMetrics
    from simulacion_trafico_engine.node.zone_node import ZoneNode

class MainGUI:
    # --- ADDED GAME STATES ---
    STATE_MENU = 0
    STATE_SIMULATION = 1
    # --- END ADDED ---

    def __init__(self, city_config: Dict,
                 metrics_client: Optional['TrafficMetrics'] = None):
        self.city_config = city_config
        self.info_panel_pixel_width = int(city_config["global_map_width"] * Theme.INFO_PANEL_WIDTH_RATIO)
        self.global_render_width = city_config["global_map_width"] + self.info_panel_pixel_width
        self.global_render_height = city_config["global_map_height"]
        
        pygame.init()
        pygame.font.init() # Ensure font module is initialized
        self.screen = pygame.display.set_mode((self.global_render_width, self.global_render_height))
        pygame.display.set_caption(f"{city_config.get('city_name', 'Distributed')} Traffic Sim")
        
        self.running = True
        self.fps = 30 
        self.actual_fps = float(self.fps)
        
        self.metrics_client = metrics_client
        self.info_panel = InfoPanel(self.global_render_width, self.global_render_height, self._get_sim_metrics)

        self.zone_nodes: Dict[str, 'ZoneNode'] = {} 

        # --- ADDED FOR MENU ---
        self.game_state = MainGUI.STATE_MENU
        self.font_menu_title = Theme.get_font(Theme.FONT_SIZE_LARGE + 10)
        self.font_menu_button = Theme.get_font(Theme.FONT_SIZE_NORMAL)
        
        # Define button properties (rects will be calculated in draw_main_menu)
        self.button_start_rect = None
        self.button_quit_rect = None
        self.button_padding = 20
        self.button_height = 50
        self.button_width = 250
        # --- END ADDED ---

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
            
            if self.game_state == MainGUI.STATE_MENU:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1: # Left mouse button
                        if self.button_start_rect and self.button_start_rect.collidepoint(mouse_pos):
                            self.game_state = MainGUI.STATE_SIMULATION
                            print("[MainGUI] Starting simulation...")
                            if self.metrics_client: # Reset steps if desired when sim starts
                                self.metrics_client.metrics_data["simulation_time_steps"] = 0
                        elif self.button_quit_rect and self.button_quit_rect.collidepoint(mouse_pos):
                            self.running = False
            
            elif self.game_state == MainGUI.STATE_SIMULATION:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False # Or go back to menu: self.game_state = MainGUI.STATE_MENU
                    elif event.key == pygame.K_SPACE:
                        # --- ADDED SPACE KEY SPAWNING ---
                        # Assuming a single zone for now as per current config
                        # For multiple zones, you'd need a way to select which zone
                        if self.zone_nodes:
                            # Get the first (and likely only) zone_node
                            # A more robust way for multiple zones would be needed if applicable
                            node_id_to_spawn_in = list(self.zone_nodes.keys())[0] 
                            target_node = self.zone_nodes.get(node_id_to_spawn_in)
                            if target_node:
                                if target_node.trigger_manual_spawn():
                                    print(f"[MainGUI] Space pressed. Requested manual spawn in {target_node.zone_id}")
                                else:
                                    print(f"[MainGUI] Space pressed. Manual spawn failed (likely zone full) in {target_node.zone_id}")
                            else:
                                print("[MainGUI] Space pressed, but no target zone node found.")
                        else:
                            print("[MainGUI] Space pressed, but no zone nodes registered.")
                        # --- END ADDED ---

    def draw_main_menu(self):
        self.screen.fill(Theme.COLOR_BACKGROUND) # Dark background for menu

        title_text = "Metroville Traffic Simulator"
        title_surf = self.font_menu_title.render(title_text, True, Theme.COLOR_TEXT_ON_DARK)
        title_rect = title_surf.get_rect(center=(self.global_render_width // 2, self.global_render_height // 4))
        self.screen.blit(title_surf, title_rect)

        # Start Button
        start_text_surf = self.font_menu_button.render("Start Simulation", True, Theme.COLOR_TEXT_ON_DARK)
        self.button_start_rect = pygame.Rect(
            (self.global_render_width - self.button_width) // 2,
            title_rect.bottom + 50,
            self.button_width,
            self.button_height
        )
        draw_rounded_rect(self.screen, Theme.COLOR_ROAD, self.button_start_rect, Theme.BORDER_RADIUS)
        start_text_rect = start_text_surf.get_rect(center=self.button_start_rect.center)
        self.screen.blit(start_text_surf, start_text_rect)

        # Quit Button
        quit_text_surf = self.font_menu_button.render("Quit", True, Theme.COLOR_TEXT_ON_DARK)
        self.button_quit_rect = pygame.Rect(
            (self.global_render_width - self.button_width) // 2,
            self.button_start_rect.bottom + self.button_padding,
            self.button_width,
            self.button_height
        )
        draw_rounded_rect(self.screen, Theme.COLOR_ROAD, self.button_quit_rect, Theme.BORDER_RADIUS)
        quit_text_rect = quit_text_surf.get_rect(center=self.button_quit_rect.center)
        self.screen.blit(quit_text_surf, quit_text_rect)
        
        # Simple hover effect (optional)
        mouse_pos = pygame.mouse.get_pos()
        if self.button_start_rect.collidepoint(mouse_pos):
            pygame.draw.rect(self.screen, Theme.COLOR_LINE, self.button_start_rect, 2, border_radius=Theme.BORDER_RADIUS)
        if self.button_quit_rect.collidepoint(mouse_pos):
            pygame.draw.rect(self.screen, Theme.COLOR_LINE, self.button_quit_rect, 2, border_radius=Theme.BORDER_RADIUS)


    def render(self):
        if self.game_state == MainGUI.STATE_MENU:
            self.draw_main_menu()
        elif self.game_state == MainGUI.STATE_SIMULATION:
            self.screen.fill(Theme.COLOR_BACKGROUND) 
            sim_area_surface = self.screen.subsurface(
                pygame.Rect(0, 0, self.city_config["global_map_width"], self.global_render_height)
            )
            sim_area_surface.fill(Theme.COLOR_GRASS) 

            for zone_id, node in self.zone_nodes.items():
                node.draw_zone_elements(sim_area_surface) 
                for vehicle in node.get_drawable_vehicles():
                    vehicle.draw(sim_area_surface)
            
            active_vehicle_count = sum(len(node.get_drawable_vehicles()) for node in self.zone_nodes.values())
            total_max_vehicles_estimate = sum(node.max_vehicles_in_zone for node in self.zone_nodes.values())
            
            # Calculate pending spawns from all nodes
            total_pending_spawns = 0
            if self.zone_nodes: # Check if zone_nodes is populated
                 total_pending_spawns = sum(node.get_pending_spawn_count() for node in self.zone_nodes.values() if hasattr(node, 'get_pending_spawn_count'))


            gui_panel_metrics = {
                 "max_vehicles": f"~{total_max_vehicles_estimate} (Dist.)",
                 "actual_fps": self.actual_fps,
                 "target_fps": self.fps,
                 "pending_spawns": total_pending_spawns, # Updated
                 "current_vehicle_count": active_vehicle_count # This key might be redundant if metrics_client provides it
            }
            self.info_panel.draw(self.screen, gui_panel_metrics)
        
        pygame.display.flip()

    async def run_gui_loop(self):
        loop = asyncio.get_running_loop()
        target_frame_duration = 1.0 / self.fps
        
        simulation_running_this_frame = False

        while self.running:
            frame_start_time = loop.time()
            
            self.handle_events() # Handles state changes and input
            if not self.running: break
            
            # Metrics update should ideally only reflect active simulation time
            if self.game_state == MainGUI.STATE_SIMULATION:
                if not simulation_running_this_frame: # First frame of simulation
                    if self.metrics_client: self.metrics_client.log_event("Simulation view started.")
                simulation_running_this_frame = True
                if self.metrics_client: self.metrics_client.simulation_step_start()
            else:
                if simulation_running_this_frame: # Was running, now menu
                     if self.metrics_client: self.metrics_client.log_event("Simulation view paused/stopped (menu).")
                simulation_running_this_frame = False

            self.render() # Draws based on current game_state
            
            if self.game_state == MainGUI.STATE_SIMULATION and self.metrics_client:
                self.metrics_client.simulation_step_end()

            elapsed = loop.time() - frame_start_time
            await asyncio.sleep(max(0, target_frame_duration - elapsed))
            
            frame_time_taken = loop.time() - frame_start_time
            if frame_time_taken > 0 :
                 self.actual_fps = 1.0 / frame_time_taken
            else:
                 self.actual_fps = float('inf') # Or some high number if frame was too fast
        
        pygame.quit()
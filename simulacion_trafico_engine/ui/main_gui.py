# simulacion_trafico_engine/ui/main_gui.py
import pygame
import asyncio
from typing import List, Dict, Optional, Any, TYPE_CHECKING

from simulacion_trafico_engine.core.vehicle import Vehicle 
from simulacion_trafico_engine.core.traffic_light import TrafficLight # Necesario para type hints
from simulacion_trafico_engine.core.zone_map import ZoneMap 

from .theme import Theme 
from .info_panel import InfoPanel
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
        self.map_render_width = city_config["global_map_width"]
        self.map_render_height = city_config["global_map_height"]
        
        pygame.init()
        pygame.font.init() 
        self.screen = pygame.display.set_mode((self.map_render_width, self.map_render_height))
        pygame.display.set_caption("Rush Hour") 
        
        self.running = True
        self.fps = 30 
        self.actual_fps = float(self.fps)
        
        self.metrics_client = metrics_client
        self.info_panel = InfoPanel(self.map_render_width, self.map_render_height, self._get_sim_metrics)
        self.zone_nodes: Dict[str, 'ZoneNode'] = {} 
        self.game_state = MainGUI.STATE_MENU
        self.main_menu = MainMenu(self.map_render_width, self.map_render_height)

        # --- Cargar imagen de fondo del MAPA DE JUEGO ---
        try:
            raw_game_map_bg = pygame.image.load(Theme.GAME_MAP_BACKGROUND_PATH).convert()
            # Escalar si es necesario para que coincida con las dimensiones de renderizado del mapa
            if raw_game_map_bg.get_size() != (self.map_render_width, self.map_render_height):
                self.game_map_background_image = pygame.transform.scale(
                    raw_game_map_bg, (self.map_render_width, self.map_render_height)
                )
            else:
                self.game_map_background_image = raw_game_map_bg
        except pygame.error as e:
            print(f"Error loading game map background image '{Theme.GAME_MAP_BACKGROUND_PATH}': {e}")
            self.game_map_background_image = None # Fallback si no se carga
        # --- Fin Cargar imagen de fondo ---

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
            
            if self.game_state == MainGUI.STATE_SIMULATION:
                if self.info_panel.handle_event(event, mouse_pos):
                    continue 

            if self.game_state == MainGUI.STATE_MENU:
                action = self.main_menu.handle_event(event, mouse_pos)
                if action == MainMenu.ACTION_START_SIM:
                    self.game_state = MainGUI.STATE_SIMULATION
                    if self.metrics_client: self.metrics_client.metrics_data["simulation_time_steps"] = 0 
                elif action == MainMenu.ACTION_QUIT: self.running = False
            
            elif self.game_state == MainGUI.STATE_SIMULATION:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE: self.game_state = MainGUI.STATE_MENU 
                    elif event.key == pygame.K_SPACE:
                        if self.zone_nodes:
                            try:
                                node_id_to_spawn_in = list(self.zone_nodes.keys())[0] 
                                target_node = self.zone_nodes.get(node_id_to_spawn_in)
                                if target_node: target_node.trigger_manual_spawn()
                            except IndexError: pass # No zones to spawn in
                    elif event.key == pygame.K_TAB: self.info_panel.toggle_expansion()

    def render(self):
        if self.game_state == MainGUI.STATE_MENU:
            self.main_menu.draw(self.screen)
        elif self.game_state == MainGUI.STATE_SIMULATION:
            # --- DIBUJAR FONDO DEL MAPA DE JUEGO ---
            if self.game_map_background_image:
                self.screen.blit(self.game_map_background_image, (0,0))
            else:
                # Fallback si la imagen del mapa no cargó
                self.screen.fill(Theme.COLOR_GRASS if hasattr(Theme, 'COLOR_GRASS') else (100, 150, 100)) 
            # --- FIN DIBUJAR FONDO ---

            # Dibujar elementos de cada zona (semáforos)
            for zone_id, node in self.zone_nodes.items():
                # node.draw_zone_elements ahora espera dibujar semáforos en self.screen
                # pasando los offsets de la zona.
                node.draw_zone_elements(self.screen) 
            
            # Dibujar vehículos
            for zone_id, node in self.zone_nodes.items(): # Iterar de nuevo o combinar bucles si es seguro
                for vehicle in node.get_drawable_vehicles():
                    vehicle.draw(self.screen) 
            
            # Dibujar el panel de información encima de todo
            active_vehicle_count = sum(len(node.get_drawable_vehicles()) for node in self.zone_nodes.values())
            total_max_vehicles_estimate = sum(node.max_vehicles_in_zone for node in self.zone_nodes.values())
            total_pending_spawns = 0
            if self.zone_nodes:
                 total_pending_spawns = sum(node.get_pending_spawn_count() for node in self.zone_nodes.values() if hasattr(node, 'get_pending_spawn_count'))

            gui_panel_metrics = {
                 "max_vehicles": f"~{total_max_vehicles_estimate}", 
                 "actual_fps": self.actual_fps, "target_fps": self.fps,
                 "pending_spawns": total_pending_spawns, "current_vehicle_count": active_vehicle_count }
            self.info_panel.draw(self.screen, gui_panel_metrics)
        
        pygame.display.flip()

    # ... (run_gui_loop se mantiene igual) ...
    async def run_gui_loop(self):
        loop = asyncio.get_running_loop()
        target_frame_duration = 1.0 / self.fps
        simulation_running_this_frame = False

        while self.running:
            frame_start_time = loop.time()
            self.handle_events() 
            if not self.running: break
            
            if self.game_state == MainGUI.STATE_SIMULATION:
                if not simulation_running_this_frame and self.metrics_client: self.metrics_client.log_event("Simulation view started.")
                simulation_running_this_frame = True
                if self.metrics_client: self.metrics_client.simulation_step_start()
            else: 
                if simulation_running_this_frame and self.metrics_client: self.metrics_client.log_event("Simulation view paused/stopped (menu).")
                simulation_running_this_frame = False

            self.render() 
            
            if self.game_state == MainGUI.STATE_SIMULATION and self.metrics_client:
                self.metrics_client.simulation_step_end()

            elapsed = loop.time() - frame_start_time
            await asyncio.sleep(max(0, target_frame_duration - elapsed))
            
            frame_time_taken = loop.time() - frame_start_time
            self.actual_fps = 1.0 / frame_time_taken if frame_time_taken > 0 else float('inf')
        
        pygame.quit()
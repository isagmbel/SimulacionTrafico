# simulacion_trafico_engine/ui/main_gui.py
import pygame
import asyncio
from typing import List, Dict, Optional, Any, TYPE_CHECKING

from simulacion_trafico_engine.core.vehicle import Vehicle 
from simulacion_trafico_engine.core.traffic_light import TrafficLight
from simulacion_trafico_engine.core.zone_map import ZoneMap 
from .theme import Theme
from .info_panel import InfoPanel

if TYPE_CHECKING:
    from simulacion_trafico_engine.distribution.rabbitclient import RabbitMQClient
    from simulacion_trafico_engine.performance.metrics import TrafficMetrics
    from simulacion_trafico_engine.node.zone_node import ZoneNode

class MainGUI:
    def __init__(self, city_config: Dict,
                 metrics_client: Optional['TrafficMetrics'] = None):
        self.city_config = city_config
        self.info_panel_pixel_width = int(city_config["global_map_width"] * Theme.INFO_PANEL_WIDTH_RATIO)
        self.global_render_width = city_config["global_map_width"] + self.info_panel_pixel_width
        self.global_render_height = city_config["global_map_height"]
        
        pygame.init()
        self.screen = pygame.display.set_mode((self.global_render_width, self.global_render_height))
        pygame.display.set_caption(f"{city_config.get('city_name', 'Distributed')} Traffic Sim")
        self.running = True
        self.fps = 30 
        self.actual_fps = float(self.fps)
        
        self.metrics_client = metrics_client
        self.info_panel = InfoPanel(self.global_render_width, self.global_render_height, self._get_sim_metrics)

        self.zone_nodes: Dict[str, 'ZoneNode'] = {} 

    def register_zone_node(self, node: 'ZoneNode'):
        self.zone_nodes[node.zone_id] = node

    def _get_sim_metrics(self) -> dict:
        if self.metrics_client:
            return self.metrics_client.get_metrics() 
        return {}

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT: self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: self.running = False
                # Podrías re-añadir el spawn manual aquí si lo deseas,
                # pero necesitaría lógica para decidir en qué zona spawnear.

    def render(self):
        self.screen.fill(Theme.COLOR_BACKGROUND) 

        # sim_area_surface es la parte de la pantalla donde se dibuja el mapa y los vehículos
        # Su origen (0,0) corresponde al (0,0) global de la ciudad.
        sim_area_surface = self.screen.subsurface(
            pygame.Rect(0, 0, self.city_config["global_map_width"], self.global_render_height)
        )
        sim_area_surface.fill(Theme.COLOR_GRASS) 

        for zone_id, node in self.zone_nodes.items():
            # zone_map.draw blitea su contenido (carreteras, edificios de la zona)
            # en sim_area_surface en la posición global correcta de la zona.
            node.draw_zone_elements(sim_area_surface) 

            # Dibujar vehículos de esta zona directamente en sim_area_surface
            for vehicle in node.get_drawable_vehicles():
                # --- LLAMADA A vehicle.draw MODIFICADA ---
                vehicle.draw(sim_area_surface) # Ahora vehicle.draw usa sus propias coords globales
        
        active_vehicle_count = sum(len(node.get_drawable_vehicles()) for node in self.zone_nodes.values())
        total_max_vehicles_estimate = sum(node.max_vehicles_in_zone for node in self.zone_nodes.values())

        gui_panel_metrics = {
             "max_vehicles": f"~{total_max_vehicles_estimate} (Dist.)",
             "actual_fps": self.actual_fps,
             "target_fps": self.fps,
             "pending_spawns": sum(len(node.vehicle_creation_tasks) for node in self.zone_nodes.values() if hasattr(node, 'vehicle_creation_tasks')), # Agregado
             "current_vehicle_count": active_vehicle_count
        }
        self.info_panel.draw(self.screen, gui_panel_metrics)
        pygame.display.flip()

    async def run_gui_loop(self):
        loop = asyncio.get_running_loop()
        target_frame_duration = 1.0 / self.fps
        while self.running:
            frame_start_time = loop.time()
            self.handle_events()
            if not self.running: break
            
            self.render()
            
            elapsed = loop.time() - frame_start_time
            await asyncio.sleep(max(0, target_frame_duration - elapsed))
            self.actual_fps = 1.0 / (loop.time() - frame_start_time) if (loop.time() - frame_start_time) > 0 else float('inf')
        
        pygame.quit()
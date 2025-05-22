import pygame
import asyncio
import uuid
import random
from typing import Tuple, List, Dict, Any, Optional, TYPE_CHECKING

from ..ui.theme import Theme, draw_rounded_rect 

if TYPE_CHECKING:
    from .traffic_light import TrafficLight 
    from ..distribution.rabbitclient import RabbitMQClient
    from ..performance.metrics import TrafficMetrics

# La clase Building ya no es necesaria porque no generamos edificios aleatorios.
# class Building:
# ...

class ZoneMap:
    def __init__(self, zone_id: str, zone_bounds: Dict[str, int],
                 rabbit_client: Optional['RabbitMQClient'] = None,
                 metrics_client: Optional['TrafficMetrics'] = None):
        self.zone_id = zone_id
        self.width = zone_bounds["width"]  # Ancho de esta zona
        self.height = zone_bounds["height"] # Alto de esta zona
        self.global_offset_x = zone_bounds["x"] # Posición X global de esta zona
        self.global_offset_y = zone_bounds["y"] # Posición Y global de esta zona

        self.rabbit_client = rabbit_client
        self.metrics_client = metrics_client
        
        self.roads: List[Dict[str, Any]] = []
        self.traffic_lights: List['TrafficLight'] = [] 
        self.intersections: List[pygame.Rect] = []
        # self.buildings: List[Building] = [] # No más edificios generados aquí

        # Estos colores se usan para dibujar las carreteras y líneas por ahora
        self.grass_color = Theme.COLOR_GRASS # Usado como fondo de la zone_surface
        self.road_color = Theme.COLOR_ROAD
        self.line_color = Theme.COLOR_LINE
        
    def _generate_local_roads_and_intersections(self):
        self.roads.clear()
        self.intersections.clear()
        # road_width debe coincidir con el ancho de las carreteras en tu imagen de fondo
        # si planeas reemplazar el dibujo de carreteras.
        road_width = 60 
        
        h_road_y = self.height // 2 - road_width // 2
        self.roads.append({
            "rect": pygame.Rect(0, h_road_y, self.width, road_width), 
            "direction": "horizontal"
        })

        v_road_x = self.width // 2 - road_width // 2
        self.roads.append({
            "rect": pygame.Rect(v_road_x, 0, road_width, self.height), 
            "direction": "vertical"
        })

        if len(self.roads) == 2:
            h_road_rect = self.roads[0]["rect"]
            v_road_rect = self.roads[1]["rect"]
            intersection = h_road_rect.clip(v_road_rect)
            if intersection.width > 5 and intersection.height > 5: 
                self.intersections.append(intersection)
        
        # print(f"[ZoneMap {self.zone_id}] Defined road geometry for logic.")

    # _generate_buildings() ya no se usa.

    def initialize_map_elements(self, TrafficLightClass: type):
        self._generate_local_roads_and_intersections() # La geometría de las carreteras es esencial
        # No se generan edificios
        self.traffic_lights.clear()

        if not self.intersections:
            # print(f"[ZoneMap {self.zone_id}] No intersections found, cannot place traffic lights.")
            return

        intersection = self.intersections[0]
        h_road_rect = self.roads[0]["rect"] 
        v_road_rect = self.roads[1]["rect"] 
        road_w = h_road_rect.height 

        ls_v = (12, 36); ls_h = (36, 12); offset = 5      
        common_params = {"rabbit_client": self.rabbit_client, "metrics_client": self.metrics_client, "theme": Theme()}
        base_cycle_time = random.randint(240, 360)
        SECOND_PAIR_OFFSET_FACTOR = 0.55 

        y_pos_E = (h_road_rect.top + road_w * 0.25) - ls_v[1] / 2
        self.traffic_lights.append(TrafficLightClass(id=f"{self.zone_id}_tl0_E", x=intersection.right + offset, y=y_pos_E, width=ls_v[0], height=ls_v[1], orientation="vertical", cycle_time=base_cycle_time, initial_offset_factor=0.0, **common_params ))
        y_pos_W = (h_road_rect.top + road_w * 0.75) - ls_v[1] / 2
        self.traffic_lights.append(TrafficLightClass(id=f"{self.zone_id}_tl0_W", x=intersection.left - ls_v[0] - offset, y=y_pos_W, width=ls_v[0], height=ls_v[1], orientation="vertical", cycle_time=base_cycle_time, initial_offset_factor=0.0, **common_params ))
        x_pos_N = (v_road_rect.left + road_w * 0.75) - ls_h[0] / 2
        self.traffic_lights.append(TrafficLightClass(id=f"{self.zone_id}_tl0_N", x=x_pos_N, y=intersection.top - ls_h[1] - offset, width=ls_h[0], height=ls_h[1], orientation="horizontal", cycle_time=base_cycle_time, initial_offset_factor=SECOND_PAIR_OFFSET_FACTOR, **common_params ))
        x_pos_S = (v_road_rect.left + road_w * 0.25) - ls_h[0] / 2
        self.traffic_lights.append(TrafficLightClass(id=f"{self.zone_id}_tl0_S", x=x_pos_S, y=intersection.bottom + offset, width=ls_h[0], height=ls_h[1], orientation="horizontal", cycle_time=base_cycle_time, initial_offset_factor=SECOND_PAIR_OFFSET_FACTOR, **common_params ))
        
        # print(f"[ZoneMap {self.zone_id}] Placed {len(self.traffic_lights)} traffic lights.")

    async def update(self) -> None:
        if self.traffic_lights and hasattr(self.traffic_lights[0], 'update_async'):
            await asyncio.gather(*(light.update_async() for light in self.traffic_lights))

    def draw(self, surface: pygame.Surface, global_x_offset: int, global_y_offset: int):
        """
        Dibuja los elementos de la zona (carreteras, semáforos) en una superficie temporal (zone_surface),
        y luego blitea esa zone_surface en la superficie principal en la posición global correcta.
        """
        # Crear una superficie para dibujar los elementos de esta zona.
        # Todos los dibujos dentro de esta sección usarán coordenadas locales a esta zone_surface.
        zone_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        zone_surface.fill(self.grass_color) # Fondo base de la zona
        
        # NO dibujar edificios (ya que están eliminados de la lógica de generación)
        
        # DIBUJAR CARRETERAS (usando Pygame, en coordenadas locales a zone_surface)
        for road_data in self.roads:
            draw_rounded_rect(zone_surface, self.road_color, road_data["rect"], Theme.BORDER_RADIUS // 3)
            road_rect = road_data["rect"]
            is_horizontal = road_data["direction"] == "horizontal"
            center_y, center_x = road_rect.centery, road_rect.centerx
            dash_len, gap_len = 20, 15
            
            if is_horizontal:
                current_x = road_rect.left
                while current_x < road_rect.right:
                    end_x = min(current_x + dash_len, road_rect.right)
                    pygame.draw.line(zone_surface, self.line_color, (current_x, center_y), (end_x, center_y), 2)
                    current_x += dash_len + gap_len
            else: 
                current_y = road_rect.top
                while current_y < road_rect.bottom:
                    end_y = min(current_y + dash_len, road_rect.bottom)
                    pygame.draw.line(zone_surface, self.line_color, (center_x, current_y), (center_x, end_y), 2)
                    current_y += dash_len + gap_len
        
        # DIBUJAR SEMÁFOROS (en coordenadas locales a zone_surface)
        # TrafficLight.draw ahora toma zone_offset_x y zone_offset_y.
        # Como estamos dibujando en `zone_surface` (cuyo origen es (0,0) para esta zona),
        # los offsets que le pasamos a TrafficLight.draw son (0,0).
        # TrafficLight.draw usará sus `self.local_x` y `self.local_y` directamente.
        for light in self.traffic_lights:
            if hasattr(light,'draw'): 
                light.draw(zone_surface, 0, 0) 
            
        # Blitear la `zone_surface` completa (con hierba, carreteras, semáforos) 
        # en la pantalla principal (`surface`) en la posición global correcta de la zona.
        surface.blit(zone_surface,(global_x_offset, global_y_offset))

    def get_spawn_points_local(self) -> List[Dict[str, Any]]:
        spawn_points = []
        if not self.roads or len(self.roads) < 2: return spawn_points
            
        vehicle_buffer = 20; car_approx_length = 30 
        default_vehicle_w_horiz = 30; default_vehicle_h_horiz = 15
        default_vehicle_w_vert = 15; default_vehicle_h_vert = 30 

        road_width = self.roads[0]["rect"].height 
        if self.roads[0]["direction"] == "vertical": road_width = self.roads[0]["rect"].width

        h_road_rect = next(r["rect"] for r in self.roads if r["direction"] == "horizontal")
        v_road_rect = next(r["rect"] for r in self.roads if r["direction"] == "vertical")

        spawn_y_E = h_road_rect.top + (road_width*0.25) - (default_vehicle_h_horiz/2)
        spawn_points.append({"x": self.width - vehicle_buffer, "y": spawn_y_E, "direction": "left", "entry_edge": "east" })
        spawn_y_W = h_road_rect.top + (road_width*0.75) - (default_vehicle_h_horiz/2)
        spawn_points.append({"x": vehicle_buffer - car_approx_length, "y": spawn_y_W, "direction": "right", "entry_edge": "west" })
        spawn_x_S = v_road_rect.left + (road_width*0.25) - (default_vehicle_w_vert/2)
        spawn_points.append({"x": spawn_x_S, "y": self.height - vehicle_buffer, "direction": "up", "entry_edge": "south" })
        spawn_x_N = v_road_rect.left + (road_width*0.75) - (default_vehicle_w_vert/2)
        spawn_points.append({"x": spawn_x_N, "y": vehicle_buffer - car_approx_length, "direction": "down", "entry_edge": "north" })
        
        return spawn_points

    def get_traffic_lights_local(self) -> List['TrafficLight']: 
        return self.traffic_lights

    def get_dimensions(self) -> Tuple[int, int]: 
        return self.width, self.height
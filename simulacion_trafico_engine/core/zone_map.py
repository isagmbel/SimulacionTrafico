# simulacion_trafico_engine/core/zone_map.py
import pygame
import asyncio
import uuid
import random
from typing import Tuple, List, Dict, Any, Optional, TYPE_CHECKING

# draw_rounded_rect ya no es necesario aquí si no dibujamos carreteras
from ..ui.theme import Theme # Todavía necesario para los parámetros de los semáforos

if TYPE_CHECKING:
    from .traffic_light import TrafficLight 
    from ..distribution.rabbitclient import RabbitMQClient
    from ..performance.metrics import TrafficMetrics

class ZoneMap:
    def __init__(self, zone_id: str, zone_bounds: Dict[str, int],
                 rabbit_client: Optional['RabbitMQClient'] = None,
                 metrics_client: Optional['TrafficMetrics'] = None):
        self.zone_id = zone_id
        self.width = zone_bounds["width"]
        self.height = zone_bounds["height"]
        self.global_offset_x = zone_bounds["x"]
        self.global_offset_y = zone_bounds["y"]

        self.rabbit_client = rabbit_client
        self.metrics_client = metrics_client
        
        self.roads: List[Dict[str, Any]] = [] # Geometría de carreteras AÚN ES NECESARIA
        self.traffic_lights: List['TrafficLight'] = [] 
        self.intersections: List[pygame.Rect] = []
        
        # Colores para dibujar carreteras ya no son necesarios si el mapa es una imagen
        # self.grass_color = Theme.COLOR_GRASS 
        # self.road_color = Theme.COLOR_ROAD
        # self.line_color = Theme.COLOR_LINE
        
    def _generate_local_roads_and_intersections(self): # Esta lógica DEBE permanecer
        self.roads.clear()
        self.intersections.clear()
        # Este road_width debe coincidir con el de tu imagen de mapa.PNG para que la lógica funcione
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
        
    def initialize_map_elements(self, TrafficLightClass: type):
        self._generate_local_roads_and_intersections()
        self.traffic_lights.clear()

        if not self.intersections: return

        intersection = self.intersections[0]
        h_road_rect = self.roads[0]["rect"]; v_road_rect = self.roads[1]["rect"] 
        road_w = h_road_rect.height 
        ls_v=(12,36); ls_h=(36,12); offset=5      
        common_params = {"rabbit_client": self.rabbit_client, "metrics_client": self.metrics_client, "theme": Theme()}
        base_cycle_time = random.randint(240, 360); SECOND_PAIR_OFFSET_FACTOR = 0.55 

        y_E = (h_road_rect.top + road_w*0.25) - ls_v[1]/2
        self.traffic_lights.append(TrafficLightClass(id=f"{self.zone_id}_tl0_E", x=intersection.right + offset, y=y_E, width=ls_v[0], height=ls_v[1], orientation="vertical", cycle_time=base_cycle_time, initial_offset_factor=0.0, **common_params ))
        y_W = (h_road_rect.top + road_w*0.75) - ls_v[1]/2
        self.traffic_lights.append(TrafficLightClass(id=f"{self.zone_id}_tl0_W", x=intersection.left - ls_v[0] - offset, y=y_W, width=ls_v[0], height=ls_v[1], orientation="vertical", cycle_time=base_cycle_time, initial_offset_factor=0.0, **common_params ))
        x_N = (v_road_rect.left + road_w*0.75) - ls_h[0]/2
        self.traffic_lights.append(TrafficLightClass(id=f"{self.zone_id}_tl0_N", x=x_N, y=intersection.top - ls_h[1] - offset, width=ls_h[0], height=ls_h[1], orientation="horizontal", cycle_time=base_cycle_time, initial_offset_factor=SECOND_PAIR_OFFSET_FACTOR, **common_params ))
        x_S = (v_road_rect.left + road_w*0.25) - ls_h[0]/2
        self.traffic_lights.append(TrafficLightClass(id=f"{self.zone_id}_tl0_S", x=x_S, y=intersection.bottom + offset, width=ls_h[0], height=ls_h[1], orientation="horizontal", cycle_time=base_cycle_time, initial_offset_factor=SECOND_PAIR_OFFSET_FACTOR, **common_params ))
        
    async def update(self) -> None:
        if self.traffic_lights and hasattr(self.traffic_lights[0], 'update_async'):
            await asyncio.gather(*(light.update_async() for light in self.traffic_lights))

    def draw(self, surface: pygame.Surface, global_x_offset: int, global_y_offset: int):
        """
        Este método ahora NO DIBUJA NADA por sí mismo si el fondo y las carreteras son una imagen.
        Los semáforos son dibujados por ZoneNode.draw_zone_elements llamando a TrafficLight.draw.
        Mantenemos el método por si en el futuro se añaden otros elementos dinámicos al mapa.
        """
        # Ya no se dibuja el fondo de hierba aquí.
        # Ya no se dibujan las carreteras aquí.
        # Los semáforos son manejados por el llamador (ZoneNode) que itera self.get_traffic_lights_local()
        pass


    def get_spawn_points_local(self) -> List[Dict[str, Any]]:
        spawn_points = []
        if not self.roads or len(self.roads) < 2: return spawn_points
            
        vehicle_buffer = 20; car_approx_length = 30 
        default_vehicle_w_horiz = 30; default_vehicle_h_horiz = 15 # Estos deben coincidir con el tamaño de tus assets
        default_vehicle_w_vert = 15; default_vehicle_h_vert = 30   # o ser pasados/consultados desde Vehicle

        road_width = 60 # IMPORTANTE: Este valor DEBE COINCIDIR con el ancho de las carreteras en tu mapa.PNG
        # Si es diferente, los puntos de spawn y la lógica de los semáforos no se alinearán.

        # Asumimos que h_road_rect y v_road_rect se obtienen correctamente
        try:
            h_road_rect = next(r["rect"] for r in self.roads if r["direction"] == "horizontal")
            v_road_rect = next(r["rect"] for r in self.roads if r["direction"] == "vertical")
        except StopIteration:
            print(f"[ZoneMap {self.zone_id}] CRITICAL: Could not find defined horizontal/vertical roads for spawn points.")
            return []


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
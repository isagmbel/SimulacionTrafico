# simulacion_trafico_engine/environment/map.py
import pygame
import asyncio
import uuid
import random
from typing import Tuple, List, Dict, Any, Optional, TYPE_CHECKING

from ..ui.theme import Theme, draw_rounded_rect

if TYPE_CHECKING:
    from .trafficlight import TrafficLight
    from ..distribution.rabbitclient import RabbitMQClient
    from ..performance.metrics import TrafficMetrics

# --- REMOVED: Building class ---

class Map:
    def __init__(self, width: int = 800, height: int = 600,
                 rabbit_client: Optional['RabbitMQClient'] = None,
                 metrics_client: Optional['TrafficMetrics'] = None):
        self.width = width
        self.height = height
        self.simulation_area_width = int(width * (1 - Theme.INFO_PANEL_WIDTH_RATIO))
        
        self.rabbit_client = rabbit_client
        self.metrics_client = metrics_client
        self.roads: List[Dict[str, Any]] = []
        self.traffic_lights: List[Any] = []
        self.intersections: List[pygame.Rect] = []
        # --- REMOVED: self.buildings ---

        self.grass_color = Theme.COLOR_GRASS
        self.road_color = Theme.COLOR_ROAD
        self.line_color = Theme.COLOR_LINE

    # --- REMOVED: _is_area_free and _generate_buildings methods ---

    def initialize_map_elements(self, TrafficLightClass: type):
        sim_w = self.simulation_area_width
        sim_h = self.height

        if not self.roads:
            road_width = 60
            h_roads_params = [(sim_h // 3 - road_width // 2, road_width), (2 * sim_h // 3 - road_width // 2, road_width)]
            v_roads_params = [(sim_w // 3 - road_width // 2, road_width), (2 * sim_w // 3 - road_width // 2, road_width)]
            for y, h in h_roads_params: self.roads.append({"rect": pygame.Rect(0, y, sim_w, h), "direction": "horizontal"})
            for x, w in v_roads_params: self.roads.append({"rect": pygame.Rect(x, 0, w, sim_h), "direction": "vertical"})
            for hr in [r for r in self.roads if r["direction"] == "horizontal"]:
                for vr in [r for r in self.roads if r["direction"] == "vertical"]:
                    self.intersections.append(hr["rect"].clip(vr["rect"]))
        
        # --- REMOVED: Call to _generate_buildings() ---

        self.traffic_lights.clear()
        for i, intersection in enumerate(self.intersections):
            light_size_v, light_size_h, offset = (12, 36), (36, 12), 6
            common = {"rabbit_client": self.rabbit_client, "metrics_client": self.metrics_client, "theme": Theme}
            # Traffic light creation logic remains the same
            self.traffic_lights.append(TrafficLightClass(id=f"tl_int{i}_E", x=intersection.left - light_size_v[0] - offset, y=intersection.top + intersection.height * 0.25 - light_size_v[1] * 0.5, width=light_size_v[0], height=light_size_v[1], orientation="vertical", cycle_time=random.randint(150, 200), **common))
            self.traffic_lights.append(TrafficLightClass(id=f"tl_int{i}_W", x=intersection.right + offset, y=intersection.top + intersection.height * 0.75 - light_size_v[1] * 0.5, width=light_size_v[0], height=light_size_v[1], orientation="vertical", cycle_time=random.randint(150, 200), initial_offset_factor=0.0, **common))
            self.traffic_lights.append(TrafficLightClass(id=f"tl_int{i}_S", x=intersection.left + intersection.width * 0.25 - light_size_h[0] * 0.5, y=intersection.top - light_size_h[1] - offset, width=light_size_h[0], height=light_size_h[1], orientation="horizontal", cycle_time=random.randint(150, 200), initial_offset_factor=0.5, **common))
            self.traffic_lights.append(TrafficLightClass(id=f"tl_int{i}_N", x=intersection.left + intersection.width * 0.75 - light_size_h[0] * 0.5, y=intersection.bottom + offset, width=light_size_h[0], height=light_size_h[1], orientation="horizontal", cycle_time=random.randint(150, 200), initial_offset_factor=0.5, **common))


    async def update(self) -> None:
        if self.traffic_lights and hasattr(self.traffic_lights[0], 'update_async'):
            await asyncio.gather(*(light.update_async() for light in self.traffic_lights))

    def draw(self, surface: pygame.Surface) -> None:
        sim_area_rect = pygame.Rect(0, 0, self.simulation_area_width, self.height)
        
        surface.fill(self.grass_color, sim_area_rect)

        # --- REMOVED: Drawing buildings ---

        # Draw roads
        for road_data in self.roads:
            draw_rounded_rect(surface, self.road_color, road_data["rect"], Theme.BORDER_RADIUS)
            line_y = road_data["rect"].centery if road_data["direction"] == "horizontal" else 0
            line_x = road_data["rect"].centerx if road_data["direction"] == "vertical" else 0
            dash_length, gap_length = 15, 15
            if road_data["direction"] == "horizontal":
                for x_start in range(0, int(self.simulation_area_width), dash_length + gap_length):
                    pygame.draw.line(surface, self.line_color, (x_start, line_y), (x_start + dash_length, line_y), 2)
            else:
                for y_start in range(0, self.height, dash_length + gap_length):
                    pygame.draw.line(surface, self.line_color, (line_x, y_start), (line_x, y_start + dash_length), 2)
        
        for light in self.traffic_lights:
            if hasattr(light, 'draw'): light.draw(surface)

    def get_spawn_points(self) -> List[Dict[str, Any]]:
        spawn_points = []
        if not self.roads: return spawn_points
        offset_factor, offscreen_buffer = 0.25, 50
        sim_w = self.simulation_area_width
        for road in self.roads:
            r = road["rect"]
            if road["direction"] == "horizontal":
                spawn_points.append({"x": -offscreen_buffer, "y": r.y + r.height * offset_factor, "direction": "right"})
                spawn_points.append({"x": sim_w + offscreen_buffer, "y": r.y + r.height * (1 - offset_factor), "direction": "left"})
            else:
                spawn_points.append({"x": r.x + r.width * offset_factor, "y": -offscreen_buffer, "direction": "down"})
                spawn_points.append({"x": r.x + r.width * (1 - offset_factor), "y": self.height + offscreen_buffer, "direction": "up"})
        return spawn_points

    def get_traffic_lights(self) -> List[Any]:
        return self.traffic_lights
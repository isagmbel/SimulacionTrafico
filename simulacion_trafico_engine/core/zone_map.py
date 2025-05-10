# simulacion_trafico_engine/core/zone_map.py
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

class Building:
    def __init__(self, rect: pygame.Rect, body_color: pygame.Color, roof_color: pygame.Color, has_door=False, door_pos_ratio=0.5):
        self.rect = rect
        self.body_color = body_color
        self.roof_color = roof_color
        self.roof_height_ratio = 0.2
        self.has_door = has_door
        self.door_pos_ratio = door_pos_ratio

    def draw(self, surface: pygame.Surface):
        draw_rounded_rect(surface, self.body_color, self.rect, Theme.BORDER_RADIUS // 2)
        roof_rect = self.rect.copy()
        if self.rect.width > self.rect.height:
            roof_rect.height = int(self.rect.height * self.roof_height_ratio)
        else:
            roof_rect.width = int(self.rect.width * self.roof_height_ratio)
        roof_rect.center = self.rect.center
        
        roof_rect_inner = roof_rect.inflate(-Theme.BORDER_WIDTH, -Theme.BORDER_WIDTH)
        if roof_rect_inner.width > 0 and roof_rect_inner.height > 0:
             draw_rounded_rect(surface, self.roof_color, roof_rect_inner, Theme.BORDER_RADIUS // 3)
        
        if self.has_door and min(self.rect.width, self.rect.height) > 25:
            door_w, door_h = min(10, self.rect.width//3), min(15, self.rect.height//3)
            door_color = pygame.Color(max(0,self.body_color.r-60), max(0,self.body_color.g-60), max(0,self.body_color.b-60))
            if self.rect.width > self.rect.height:
                door_x = self.rect.left + (self.rect.width - door_w) * self.door_pos_ratio
                door_r = pygame.Rect(door_x, self.rect.bottom - door_h, door_w, door_h)
            else:
                door_y = self.rect.top + (self.rect.height - door_h) * self.door_pos_ratio
                door_r = pygame.Rect(self.rect.right - door_w, door_y, door_w, door_h)
            if surface.get_clip().colliderect(door_r):
                draw_rounded_rect(surface, door_color, door_r, 2)

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
        
        self.roads: List[Dict[str, Any]] = []
        self.traffic_lights: List['TrafficLight'] = [] 
        self.intersections: List[pygame.Rect] = []
        self.buildings: List[Building] = [] 

        self.grass_color = Theme.COLOR_GRASS
        self.road_color = Theme.COLOR_ROAD
        self.line_color = Theme.COLOR_LINE
        
    def _generate_local_roads_and_intersections(self):
        self.roads.clear()
        self.intersections.clear()
        road_width = 60 
        
        h_positions = []
        if self.height >= road_width:
            num_h_roads = max(1, self.height // (road_width * 3)) 
            if num_h_roads == 1: h_positions.append(self.height // 2)
            else: h_positions.extend([self.height // 4, self.height * 3 // 4])

        v_positions = []
        if self.width >= road_width:
            num_v_roads = max(1, self.width // (road_width * 3))
            if num_v_roads == 1: v_positions.append(self.width // 2)
            else: v_positions.extend([self.width // 4, self.width * 3 // 4])

        for y_center in h_positions:
            y_top = y_center - road_width // 2
            self.roads.append({"rect": pygame.Rect(0, y_top, self.width, road_width), "direction": "horizontal"})

        for x_center in v_positions:
            x_left = x_center - road_width // 2
            self.roads.append({"rect": pygame.Rect(x_left, 0, road_width, self.height), "direction": "vertical"})

        # --- DEBUG PRINT PARA CARRETERAS ---
        print(f"--- [ZoneMap DEBUG {self.zone_id}] Road Generation ---")
        print(f"Zone Dims: w={self.width}, h={self.height}")
        if not self.roads:
            print("No roads generated.")
        for i, road_data in enumerate(self.roads):
            print(f"  Road {i}: rect={road_data['rect']}, dir={road_data['direction']}")
        # --- FIN DEBUG PRINT ---

        h_roads = [r for r in self.roads if r["direction"] == "horizontal"]
        v_roads = [r for r in self.roads if r["direction"] == "vertical"]
        for hr_data in h_roads:
            for vr_data in v_roads:
                intersection = hr_data["rect"].clip(vr_data["rect"])
                if intersection.width > 5 and intersection.height > 5:
                    self.intersections.append(intersection)

    def _generate_buildings(self):
        self.buildings.clear()
        num_buildings_per_zone = random.randint(3,7) 
        min_size, max_size = 40, 110
        road_m, building_m, edge_m = 15, 8, 10
        all_road_rects_inflated = [pygame.Rect(r['rect']).inflate(road_m*2, road_m*2) for r in self.roads]
        attempts, placed = 0, 0
        while placed < num_buildings_per_zone and attempts < num_buildings_per_zone * 20:
            attempts += 1; b_w = random.randint(min_size,max_size); b_h = random.randint(min_size,max_size)
            if random.random()<0.7: b_h = int(b_w*random.uniform(0.5,0.8)) if random.random()<0.5 else int(b_h*random.uniform(0.5,0.8))
            if self.width-b_w-edge_m*2<=0 or self.height-b_h-edge_m*2<=0: continue
            b_x=random.randint(edge_m,self.width-b_w-edge_m); b_y=random.randint(edge_m,self.height-b_h-edge_m)
            b_rect=pygame.Rect(b_x,b_y,b_w,b_h)
            if b_rect.right>self.width-edge_m or b_rect.bottom>self.height-edge_m: continue
            if any(b_rect.colliderect(rr) for rr in all_road_rects_inflated): continue
            if any(b_rect.colliderect(b.rect.inflate(building_m,building_m)) for b in self.buildings): continue
            bc,rc=Theme.get_building_colors(); self.buildings.append(Building(b_rect,bc,rc,random.random()>0.4,random.random())); placed+=1

    def initialize_map_elements(self, TrafficLightClass: type):
        self._generate_local_roads_and_intersections()
        self._generate_buildings()
        self.traffic_lights.clear()
        for i, intersection in enumerate(self.intersections):
            ls_v,ls_h,off=(12,36),(36,12),5; com={"rabbit_client":self.rabbit_client,"metrics_client":self.metrics_client,"theme":Theme}
            self.traffic_lights.append(TrafficLightClass(id=f"{self.zone_id}_tl{i}_E",x=intersection.left-ls_v[0]-off,y=intersection.top+intersection.height*0.25-ls_v[1]*0.5,width=ls_v[0],height=ls_v[1],orientation="vertical",cycle_time=random.randint(150,200),**com))
            self.traffic_lights.append(TrafficLightClass(id=f"{self.zone_id}_tl{i}_W",x=intersection.right+off,y=intersection.top+intersection.height*0.75-ls_v[1]*0.5,width=ls_v[0],height=ls_v[1],orientation="vertical",cycle_time=random.randint(150,200),initial_offset_factor=0.0,**com))
            self.traffic_lights.append(TrafficLightClass(id=f"{self.zone_id}_tl{i}_S",x=intersection.left+intersection.width*0.25-ls_h[0]*0.5,y=intersection.top-ls_h[1]-off,width=ls_h[0],height=ls_h[1],orientation="horizontal",cycle_time=random.randint(150,200),initial_offset_factor=0.5,**com))
            self.traffic_lights.append(TrafficLightClass(id=f"{self.zone_id}_tl{i}_N",x=intersection.left+intersection.width*0.75-ls_h[0]*0.5,y=intersection.bottom+off,width=ls_h[0],height=ls_h[1],orientation="horizontal",cycle_time=random.randint(150,200),initial_offset_factor=0.5,**com))

    async def update(self) -> None:
        if self.traffic_lights and hasattr(self.traffic_lights[0], 'update_async'):
            await asyncio.gather(*(light.update_async() for light in self.traffic_lights))

    def draw(self, surface: pygame.Surface, global_x_offset: int, global_y_offset: int):
        zone_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        zone_surface.fill(self.grass_color)
        for building in self.buildings: building.draw(zone_surface)
        for road_data in self.roads:
            draw_rounded_rect(zone_surface, self.road_color, road_data["rect"], Theme.BORDER_RADIUS)
            ly,lx=road_data["rect"].centery,road_data["rect"].centerx; dl,gl=20,15
            if road_data["direction"]=="horizontal":
                for xs in range(0,self.width,dl+gl): pygame.draw.line(zone_surface,self.line_color,(xs,ly),(xs+dl,ly),2)
            else:
                for ys in range(0,self.height,dl+gl): pygame.draw.line(zone_surface,self.line_color,(lx,ys),(lx,ys+dl),2)
        for light in self.traffic_lights:
            if hasattr(light,'draw'): light.draw(zone_surface)
        surface.blit(zone_surface,(global_x_offset,global_y_offset))

    def get_spawn_points_local(self) -> List[Dict[str, Any]]:
        spawn_points = []
        if not self.roads: return spawn_points
            
        vehicle_buffer = 20 # Aumentar un poco el buffer para asegurar que esté bien dentro
        car_dim_approx = 30 # Para compensar el tamaño del coche al spawnear

        print(f"--- [ZoneMap DEBUG {self.zone_id}] Generating Spawn Points ---") # DEBUG
        print(f"Zone Dims: w={self.width}, h={self.height}") # DEBUG

        for road_dict in self.roads:
            r = road_dict["rect"]
            direction = road_dict["direction"]
            # Usar 0.25 para carril de ida, 0.75 para carril de vuelta (respecto al borde de la carretera)
            lane_offset_go = r.height * 0.25 if direction == "horizontal" else r.width * 0.25
            lane_offset_return = r.height * 0.75 if direction == "horizontal" else r.width * 0.75
            
            print(f"  Checking Road: rect={r}, dir={direction}") # DEBUG

            if direction == "horizontal":
                if r.left <= 5: # Entra por la izquierda, va a la derecha
                    y_pos = r.top + lane_offset_go
                    spawn_points.append({"x": vehicle_buffer, "y": y_pos, "direction": "right", "entry_edge": "left"})
                    print(f"    Added LEFT entry spawn: x={vehicle_buffer}, y={y_pos}, dir=right") # DEBUG
                if r.right >= self.width - 5: # Entra por la derecha, va a la izquierda
                    y_pos = r.top + lane_offset_return
                    spawn_points.append({"x": self.width - vehicle_buffer - car_dim_approx, "y": y_pos, "direction": "left", "entry_edge": "right"})
                    print(f"    Added RIGHT entry spawn: x={self.width - vehicle_buffer - car_dim_approx}, y={y_pos}, dir=left") # DEBUG
            elif direction == "vertical":
                if r.top <= 5: # Entra por arriba, va hacia abajo
                    x_pos = r.left + lane_offset_go
                    spawn_points.append({"x": x_pos, "y": vehicle_buffer, "direction": "down", "entry_edge": "top"})
                    print(f"    Added TOP entry spawn: x={x_pos}, y={vehicle_buffer}, dir=down") # DEBUG
                if r.bottom >= self.height - 5: # Entra por abajo, va hacia arriba
                    x_pos = r.left + lane_offset_return
                    spawn_points.append({"x": x_pos, "y": self.height - vehicle_buffer - car_dim_approx, "direction": "up", "entry_edge": "bottom"})
                    print(f"    Added BOTTOM entry spawn: x={x_pos}, y={self.height - vehicle_buffer - car_dim_approx}, dir=up") # DEBUG
        
        if not spawn_points:
            print(f"[ZoneMap {self.zone_id}] WARNING: No spawn points generated after detailed check!")
        else:
            print(f"[ZoneMap {self.zone_id}] Final {len(spawn_points)} spawn points: {spawn_points}")
        print(f"--- [ZoneMap DEBUG {self.zone_id}] End Generating Spawn Points ---") # DEBUG
        return spawn_points

    def get_traffic_lights_local(self) -> List['TrafficLight']: return self.traffic_lights
    def get_dimensions(self) -> Tuple[int, int]: return self.width, self.height
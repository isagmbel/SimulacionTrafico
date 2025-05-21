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
        
        # print(f"[ZoneMap {self.zone_id}] Generated {len(self.roads)} roads and {len(self.intersections)} intersections.")


    def _generate_buildings(self):
        self.buildings.clear()
        num_buildings_per_zone = random.randint(8,15) 
        min_size, max_size = 40, 110
        road_m, building_m, edge_m = 20, 10, 10 
        
        all_road_rects_inflated = [pygame.Rect(r['rect']).inflate(road_m*2, road_m*2) for r in self.roads]
        
        attempts, placed = 0, 0
        while placed < num_buildings_per_zone and attempts < num_buildings_per_zone * 30:
            attempts += 1
            b_w = random.randint(min_size,max_size)
            b_h = random.randint(min_size,max_size)
            if random.random()<0.7: 
                if random.random()<0.5:
                    b_h = int(b_w*random.uniform(0.5,0.8)) 
                else:
                    b_w = int(b_h*random.uniform(0.5,0.8))
            
            if b_w <=0 or b_h <=0: continue
            if self.width-b_w-edge_m*2<=0 or self.height-b_h-edge_m*2<=0: continue
            b_x=random.randint(edge_m,self.width-b_w-edge_m)
            b_y=random.randint(edge_m,self.height-b_h-edge_m)
            b_rect=pygame.Rect(b_x,b_y,b_w,b_h)

            if b_rect.right > self.width-edge_m or b_rect.bottom > self.height-edge_m : continue
            if any(b_rect.colliderect(inflated_road_r) for inflated_road_r in all_road_rects_inflated): continue
            if any(b_rect.colliderect(b.rect.inflate(building_m,building_m)) for b in self.buildings): continue
            
            bc,rc=Theme.get_building_colors()
            self.buildings.append(Building(b_rect,bc,rc,random.random()>0.4,random.random()))
            placed+=1
        # print(f"[ZoneMap {self.zone_id}] Placed {placed} buildings.")

    def initialize_map_elements(self, TrafficLightClass: type):
        self._generate_local_roads_and_intersections()
        self._generate_buildings()
        self.traffic_lights.clear()

        if not self.intersections:
            print(f"[ZoneMap {self.zone_id}] No intersections found, cannot place traffic lights.")
            return

        intersection = self.intersections[0] # The central intersection rect
        
        # Road details for precise light placement
        h_road_rect = self.roads[0]["rect"] # Assuming horizontal road is first
        v_road_rect = self.roads[1]["rect"] # Assuming vertical road is second
        road_w = h_road_rect.height # Effective width of a single road segment

        ls_v = (12, 36) # width, height for vertical lights
        ls_h = (36, 12) # width, height for horizontal lights
        offset = 5      # Offset from intersection edge

        common_params = {
            "rabbit_client": self.rabbit_client,
            "metrics_client": self.metrics_client,
            "theme": Theme() 
        }
        base_cycle_time = random.randint(240, 360)
        SECOND_PAIR_OFFSET_FACTOR = 0.55 

        # --- CORRECTED TRAFFIC LIGHT PLACEMENT ---
        # Traffic lights are named by the direction *from which* traffic approaches.
        # E.g., _tl0_N controls traffic approaching FROM the North.

        # Pair 1: Control East-West approaches (lights are Vertical)
        # These will start with offset 0.0 (Green initially for E-W traffic flow)

        # Light for traffic approaching FROM EAST (vehicles moving LEFT, use top lane of H-road)
        # Placed EAST of the intersection.
        y_pos_for_E_approach_light = (h_road_rect.top + road_w * 0.25) - ls_v[1] / 2
        self.traffic_lights.append(TrafficLightClass(
            id=f"{self.zone_id}_tl0_E", 
            x=intersection.right + offset, # East of intersection
            y=y_pos_for_E_approach_light,
            width=ls_v[0], height=ls_v[1],
            orientation="vertical", cycle_time=base_cycle_time, initial_offset_factor=0.0,
            **common_params
        ))
        
        # Light for traffic approaching FROM WEST (vehicles moving RIGHT, use bottom lane of H-road)
        # Placed WEST of the intersection.
        y_pos_for_W_approach_light = (h_road_rect.top + road_w * 0.75) - ls_v[1] / 2
        self.traffic_lights.append(TrafficLightClass(
            id=f"{self.zone_id}_tl0_W", 
            x=intersection.left - ls_v[0] - offset, # West of intersection
            y=y_pos_for_W_approach_light,
            width=ls_v[0], height=ls_v[1],
            orientation="vertical", cycle_time=base_cycle_time, initial_offset_factor=0.0, 
            **common_params
        ))

        # Pair 2: Control North-South approaches (lights are Horizontal)
        # These will start with offset SECOND_PAIR_OFFSET_FACTOR (Red initially for N-S traffic flow)

        # Light for traffic approaching FROM NORTH (vehicles moving DOWN, use right lane of V-road)
        # Placed NORTH of the intersection.
        x_pos_for_N_approach_light = (v_road_rect.left + road_w * 0.75) - ls_h[0] / 2
        self.traffic_lights.append(TrafficLightClass(
            id=f"{self.zone_id}_tl0_N", 
            x=x_pos_for_N_approach_light,
            y=intersection.top - ls_h[1] - offset, # North of intersection
            width=ls_h[0], height=ls_h[1],
            orientation="horizontal", cycle_time=base_cycle_time, initial_offset_factor=SECOND_PAIR_OFFSET_FACTOR, 
            **common_params
        ))

        # Light for traffic approaching FROM SOUTH (vehicles moving UP, use left lane of V-road)
        # Placed SOUTH of the intersection.
        x_pos_for_S_approach_light = (v_road_rect.left + road_w * 0.25) - ls_h[0] / 2
        self.traffic_lights.append(TrafficLightClass(
            id=f"{self.zone_id}_tl0_S", 
            x=x_pos_for_S_approach_light, 
            y=intersection.bottom + offset, # South of intersection
            width=ls_h[0], height=ls_h[1],
            orientation="horizontal", cycle_time=base_cycle_time, initial_offset_factor=SECOND_PAIR_OFFSET_FACTOR, 
            **common_params
        ))
        # --- END CORRECTED PLACEMENT ---
        print(f"[ZoneMap {self.zone_id}] Placed {len(self.traffic_lights)} traffic lights with corrected positions and base_cycle_time: {base_cycle_time}.")


    async def update(self) -> None:
        if self.traffic_lights and hasattr(self.traffic_lights[0], 'update_async'):
            await asyncio.gather(*(light.update_async() for light in self.traffic_lights))

    def draw(self, surface: pygame.Surface, global_x_offset: int, global_y_offset: int):
        zone_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        zone_surface.fill(self.grass_color)
        
        for building in self.buildings: 
            building.draw(zone_surface)
        
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
        
        for light in self.traffic_lights:
            if hasattr(light,'draw'): 
                light.draw(zone_surface)
            
        surface.blit(zone_surface,(global_x_offset,global_y_offset))

    def get_spawn_points_local(self) -> List[Dict[str, Any]]:
        spawn_points = []
        if not self.roads or len(self.roads) < 2: 
            # print(f"[ZoneMap {self.zone_id}] WARNING: Not enough roads for spawn points.")
            return spawn_points
            
        vehicle_buffer = 20 
        car_approx_length = 30 
        car_half_width_for_vehicle_body = Theme.get_font(Theme.FONT_SIZE_NORMAL).size(" ")[0] / 4 # A bit arbitrary, adjust if needed
                                                                                          # Or use a fixed value like 7-8
        
        # Use a more robust way to get road width, assuming all roads have same width from config
        road_width = self.roads[0]["rect"].height # Assuming horizontal road's height is the road width
        if self.roads[0]["direction"] == "vertical": # if for some reason order changed
            road_width = self.roads[0]["rect"].width

        h_road_rect = next(r["rect"] for r in self.roads if r["direction"] == "horizontal")
        v_road_rect = next(r["rect"] for r in self.roads if r["direction"] == "vertical")


        # EAST entry (vehicle moves LEFT, uses top lane of horizontal road)
        # Lane center Y = h_road_rect.top + road_width * 0.25
        spawn_y_east_entry = h_road_rect.top + (road_width * 0.25) - car_half_width_for_vehicle_body
        spawn_points.append({
            "x": self.width - vehicle_buffer, "y": spawn_y_east_entry, 
            "direction": "left", "entry_edge": "east"
        })

        # WEST entry (vehicle moves RIGHT, uses bottom lane of horizontal road)
        # Lane center Y = h_road_rect.top + road_width * 0.75
        spawn_y_west_entry = h_road_rect.top + (road_width * 0.75) - car_half_width_for_vehicle_body
        spawn_points.append({
            "x": vehicle_buffer - car_approx_length, "y": spawn_y_west_entry, 
            "direction": "right", "entry_edge": "west"
        })

        # SOUTH entry (vehicle moves UP, uses left lane of vertical road - from map perspective)
        # Lane center X = v_road_rect.left + road_width * 0.25
        spawn_x_south_entry = v_road_rect.left + (road_width * 0.25) - car_half_width_for_vehicle_body
        spawn_points.append({
            "x": spawn_x_south_entry, "y": self.height - vehicle_buffer,
            "direction": "up", "entry_edge": "south"
        })
        
        # NORTH entry (vehicle moves DOWN, uses right lane of vertical road - from map perspective)
        # Lane center X = v_road_rect.left + road_width * 0.75
        spawn_x_north_entry = v_road_rect.left + (road_width * 0.75) - car_half_width_for_vehicle_body
        spawn_points.append({
            "x": spawn_x_north_entry, "y": vehicle_buffer - car_approx_length, 
            "direction": "down", "entry_edge": "north"
        })
        
        if not spawn_points:
            # print(f"[ZoneMap {self.zone_id}] WARNING: No spawn points generated for intersection layout!")
            pass
        else:
            pass
        return spawn_points

    def get_traffic_lights_local(self) -> List['TrafficLight']: 
        return self.traffic_lights

    def get_dimensions(self) -> Tuple[int, int]: 
        return self.width, self.height
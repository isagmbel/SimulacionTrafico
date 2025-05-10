# simulacion_trafico_engine/environment/vehicle.py
import pygame
import math
import uuid
import asyncio
from typing import Tuple, List, Dict, Optional, TYPE_CHECKING

from ..ui.theme import Theme, draw_rounded_rect # Import Theme

if TYPE_CHECKING:
    from .trafficlight import TrafficLight
    from .map import Map
    from ..distribution.rabbitclient import RabbitMQClient
    from ..performance.metrics import TrafficMetrics

class Vehicle:
    def __init__(self, x: float, y: float, width: int = 30, height: int = 15, # Slightly larger default
                 color: Optional[Tuple[int, int, int]] = None, # Color is now optional, uses Theme
                 speed: float = 2.0,
                 direction: str = "right",
                 rabbit_client: Optional['RabbitMQClient'] = None,
                 metrics_client: Optional['TrafficMetrics'] = None,
                 map_ref: Optional['Map'] = None):
        self.id = f"veh_{uuid.uuid4().hex[:6]}"
        self.x = x
        self.y = y
        self.color = color if color else Theme.get_vehicle_color() # Use Theme color
        self.original_speed = speed
        self.speed = speed
        self.direction = direction
        self.stopped = False

        self.rabbit_client = rabbit_client
        self.metrics_client = metrics_client
        self.map_ref = map_ref

        if direction in ["left", "right"]:
            self.draw_width, self.draw_height = width, height
        else:
            self.draw_width, self.draw_height = height, width

        self.rect = pygame.Rect(float(self.x), float(self.y), self.draw_width, self.draw_height)
        self.is_despawned = False

        # print(f"[VEHICLE DEBUG] New Vehicle: id={self.id}, pos=({self.x},{self.y}), rect={self.rect}, dir={self.direction}")
        if self.metrics_client: self.metrics_client.vehicle_spawned(self.id)
        if self.rabbit_client: asyncio.create_task(self.publish_state("spawned"))

    async def publish_state(self, event_type: str = "update") -> None:
        if not (self.rabbit_client and hasattr(self.rabbit_client, 'async_channel') and self.rabbit_client.async_channel): return
        message = {"vehicle_id": self.id, "event_type": event_type, "position": {"x": self.x, "y": self.y}, "speed_px_frame": self.speed, "direction": self.direction, "stopped": self.stopped, "timestamp": asyncio.get_event_loop().time()}
        await self.rabbit_client.publish_async(f"traffic.vehicle.state.{self.id}", message)

    async def update_async(self, traffic_lights: List['TrafficLight'], all_vehicles: List['Vehicle'],
                           map_sim_width: int, map_height: int) -> None: # Use map_sim_width
        if self.is_despawned: return
        old_x, old_y, old_speed, old_stopped = self.x, self.y, self.speed, self.stopped

        if self.stopped:
            action = self._check_action_at_light(traffic_lights)
            if action == "proceed": self.resume()
            else:
                if self.metrics_client: self.metrics_client.accumulate_vehicle_speed(self.speed)
                return

        current_speed = self.speed
        if self.direction == "right": self.x += current_speed
        elif self.direction == "left": self.x -= current_speed
        elif self.direction == "up": self.y -= current_speed
        elif self.direction == "down": self.y += current_speed
        self.rect.topleft = (self.x, self.y)

        # Boundary check using map_sim_width
        if self.rect.right < -10 or self.rect.left > map_sim_width + 10 or \
           self.rect.bottom < -10 or self.rect.top > map_height + 10: # Allow slight overshoot before despawn
            if not self.is_despawned: # To ensure despawn logic runs once
                self.is_despawned = True
                # print(f"[VEHICLE DEBUG] Despawned {self.id} at {self.rect.topleft}, sim_width={map_sim_width}")
                if self.metrics_client: self.metrics_client.vehicle_despawned(self.id)
                await self.publish_state("despawned")
            return
        
        # ... (rest of traffic light and collision logic - keep from previous good version) ...
        # For brevity, I'm assuming the traffic light and collision logic from the previous
        # "just give me back the script" version of vehicle.py was mostly okay,
        # the main issue was drawing/despawning.
        # If cars still don't stop, that logic needs review.
        light_action = self._check_action_at_light(traffic_lights)
        if light_action == "stop":
            self.x, self.y = old_x, old_y 
            self.rect.topleft = (self.x, self.y) 
            self.stop(reason="traffic_light")
            if self.speed != old_speed or self.stopped != old_stopped: await self.publish_state("stopped_at_light")
            if self.metrics_client: self.metrics_client.accumulate_vehicle_speed(self.speed)
            return

        safe_distance_factor = 0.1 
        for other in all_vehicles:
            if other.id == self.id or other.is_despawned: continue
            if self.rect.colliderect(other.rect):
                is_in_front_and_dangerously_close = False
                if self.direction == "right" and other.rect.left > self.rect.left and other.rect.left < self.rect.right + self.draw_width * safe_distance_factor :
                    if abs(self.rect.centery - other.rect.centery) < self.draw_height: 
                        is_in_front_and_dangerously_close = True
                elif self.direction == "left" and other.rect.right < self.rect.right and other.rect.right > self.rect.left - self.draw_width * safe_distance_factor:
                    if abs(self.rect.centery - other.rect.centery) < self.draw_height:
                        is_in_front_and_dangerously_close = True
                elif self.direction == "down" and other.rect.top > self.rect.top and other.rect.top < self.rect.bottom + self.draw_height * safe_distance_factor:
                    if abs(self.rect.centerx - other.rect.centerx) < self.draw_width: 
                        is_in_front_and_dangerously_close = True
                elif self.direction == "up" and other.rect.bottom < self.rect.bottom and other.rect.bottom > self.rect.top - self.draw_height * safe_distance_factor:
                    if abs(self.rect.centerx - other.rect.centerx) < self.draw_width:
                        is_in_front_and_dangerously_close = True
                if is_in_front_and_dangerously_close:
                    self.x, self.y = old_x, old_y
                    self.rect.topleft = (self.x, self.y)
                    self.stop(reason="collision_avoidance")
                    if self.speed != old_speed or self.stopped != old_stopped: await self.publish_state("stopped_avoidance")
                    if self.metrics_client: self.metrics_client.accumulate_vehicle_speed(self.speed)
                    return
        if self.stopped: self.resume_speed()
        if self.x != old_x or self.y != old_y or self.speed != old_speed or self.stopped != old_stopped:
            await self.publish_state("updated")
        if self.metrics_client: self.metrics_client.accumulate_vehicle_speed(self.speed)

    def _get_relevant_light(self, traffic_lights: List['TrafficLight']) -> Optional['TrafficLight']:
        min_dist_sq = float('inf')
        relevant_light = None
        lookahead_distance = self.original_speed * 25 + self.draw_width 
        for light in traffic_lights:
            correct_orientation = (self.direction in ["right", "left"] and light.orientation == "vertical") or \
                                  (self.direction in ["up", "down"] and light.orientation == "horizontal")
            if not correct_orientation: continue
            is_light_ahead_and_aligned = False
            dist_to_light_interaction_point_sq = float('inf')
            if self.direction == "right":
                if light.x > self.rect.right and abs(light.y + light.height / 2 - self.rect.centery) < self.map_ref.roads[0]["rect"].height / 2:
                    is_light_ahead_and_aligned = True
                    dist_to_light_interaction_point_sq = (light.x - self.rect.right)**2
            elif self.direction == "left":
                if (light.x + light.width) < self.rect.left and abs(light.y + light.height / 2 - self.rect.centery) < self.map_ref.roads[0]["rect"].height / 2:
                    is_light_ahead_and_aligned = True
                    dist_to_light_interaction_point_sq = (self.rect.left - (light.x + light.width))**2
            elif self.direction == "down":
                if light.y > self.rect.bottom and abs(light.x + light.width / 2 - self.rect.centerx) < self.map_ref.roads[0]["rect"].width / 2:
                    is_light_ahead_and_aligned = True
                    dist_to_light_interaction_point_sq = (light.y - self.rect.bottom)**2
            elif self.direction == "up":
                if (light.y + light.height) < self.rect.top and abs(light.x + light.width / 2 - self.rect.centerx) < self.map_ref.roads[0]["rect"].width / 2:
                    is_light_ahead_and_aligned = True
                    dist_to_light_interaction_point_sq = (self.rect.top - (light.y + light.height))**2
            if is_light_ahead_and_aligned and dist_to_light_interaction_point_sq < lookahead_distance**2:
                if dist_to_light_interaction_point_sq < min_dist_sq:
                    min_dist_sq = dist_to_light_interaction_point_sq
                    relevant_light = light
        return relevant_light

    def _check_action_at_light(self, traffic_lights: List['TrafficLight']) -> str:
        light = self._get_relevant_light(traffic_lights)
        if not light: return "proceed"
        dist_to_light_edge = float('inf')
        if self.direction == "right": dist_to_light_edge = light.x - self.rect.right
        elif self.direction == "left": dist_to_light_edge = self.rect.left - (light.x + light.width)
        elif self.direction == "down": dist_to_light_edge = light.y - self.rect.bottom
        elif self.direction == "up": dist_to_light_edge = self.rect.top - (light.y + light.height)
        decision_buffer_distance = self.original_speed * 2.0 
        if dist_to_light_edge < decision_buffer_distance: 
            if light.state == "red": return "stop"
            elif light.state == "yellow":
                if dist_to_light_edge < (self.original_speed * 1.0): return "stop"
        return "proceed"
    # End of copied traffic light and collision logic placeholder

    def stop(self, reason: str = "unknown") -> None:
        if not self.stopped:
            self.stopped = True; self.speed = 0.0
            if self.metrics_client: self.metrics_client.vehicle_started_waiting(self.id)

    def resume(self) -> None:
        if self.stopped:
            self.stopped = False; self.resume_speed()
            if self.metrics_client: self.metrics_client.vehicle_stopped_waiting(self.id)

    def resume_speed(self) -> None: self.speed = self.original_speed

    def draw(self, surface: pygame.Surface) -> None:
        if self.is_despawned: return
        # Use the rounded rect helper for vehicles too
        draw_rounded_rect(surface, self.color, self.rect, Theme.BORDER_RADIUS // 2) # Smaller radius for cars
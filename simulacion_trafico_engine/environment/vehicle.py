# simulacion_trafico_engine/environment/vehicle.py
import pygame
import math
import uuid
import asyncio
from typing import Tuple, List, Dict, Optional, TYPE_CHECKING

# Assuming theme.py is in ..ui/ relative to this environment folder
# This import needs to be correct based on your project structure.
# If vehicle.py is in simulacion_trafico_engine/environment/
# and theme.py is in simulacion_trafico_engine/ui/
# then 'from ..ui.theme import Theme, draw_rounded_rect' is correct.
from ..ui.theme import Theme, draw_rounded_rect

if TYPE_CHECKING:
    from .trafficlight import TrafficLight # Relative import: from the same 'environment' package
    from .map import Map                   # Relative import: from the same 'environment' package
    from ..distribution.rabbitclient import RabbitMQClient # Relative import: from sibling 'distribution' package
    from ..performance.metrics import TrafficMetrics   # Relative import: from sibling 'performance' package

class Vehicle:
    def __init__(self, x: float, y: float, width: int = 30, height: int = 15,
                 color: Optional[Tuple[int, int, int]] = None,
                 speed: float = 2.0,
                 direction: str = "right",
                 rabbit_client: Optional['RabbitMQClient'] = None,
                 metrics_client: Optional['TrafficMetrics'] = None,
                 map_ref: Optional['Map'] = None):
        self.id = f"veh_{uuid.uuid4().hex[:6]}"
        self.x = x
        self.y = y
        self.color = color if color else Theme.get_vehicle_color()
        self.original_speed = speed
        self.speed = speed
        self.direction = direction
        self.stopped = False

        self.rabbit_client = rabbit_client
        self.metrics_client = metrics_client
        self.map_ref = map_ref

        if direction in ["left", "right"]:
            self.draw_width, self.draw_height = width, height
        else: # up, down
            self.draw_width, self.draw_height = height, width

        self.rect = pygame.Rect(float(self.x), float(self.y), self.draw_width, self.draw_height)
        self.is_despawned = False

        # print(f"[VEHICLE DEBUG] New Vehicle INIT: id={self.id}, pos=({self.x},{self.y}), rect={self.rect}, dir={self.direction}")

        if self.metrics_client:
            self.metrics_client.vehicle_spawned(self.id)
        # DO NOT call asyncio.create_task here.
        # The GUI (main async thread) will handle calling publish_state("spawned")
        # after the vehicle object is successfully created and returned from the executor.

    async def publish_state(self, event_type: str = "update") -> None:
        if not (self.rabbit_client and
                hasattr(self.rabbit_client, 'async_connection') and self.rabbit_client.async_connection and
                not self.rabbit_client.async_connection.is_closed and
                hasattr(self.rabbit_client, 'async_exchange') and self.rabbit_client.async_exchange):
            # print(f"[VEHICLE {self.id} DEBUG] publish_state ({event_type}): RabbitMQ client not ready or no exchange.")
            return

        message = {
            "vehicle_id": self.id, "event_type": event_type,
            "position": {"x": self.x, "y": self.y},
            "speed_px_frame": self.speed, "direction": self.direction,
            "stopped": self.stopped, "timestamp": asyncio.get_event_loop().time()
        }
        try:
            # print(f"[VEHICLE {self.id} DEBUG] Publishing state ({event_type}) via RabbitMQ.")
            await self.rabbit_client.publish_async(f"traffic.vehicle.state.{self.id}.{event_type}", message)
        except Exception as e:
            print(f"[VEHICLE {self.id} ERROR] Error publishing state via RabbitMQ: {e}")

    async def update_async(self, traffic_lights: List['TrafficLight'], all_vehicles: List['Vehicle'],
                           map_sim_width: int, map_height: int) -> None:
        if self.is_despawned:
            return

        old_x, old_y = self.x, self.y
        old_speed, old_stopped = self.speed, self.stopped

        if self.stopped:
            action = self._check_action_at_light(traffic_lights)
            if action == "proceed":
                self.resume()
            else: # Still stopped
                if self.metrics_client:
                    self.metrics_client.accumulate_vehicle_speed(self.speed)
                return

        current_speed = self.speed # Use a local variable for this frame's movement
        if self.direction == "right": self.x += current_speed
        elif self.direction == "left": self.x -= current_speed
        elif self.direction == "up": self.y -= current_speed
        elif self.direction == "down": self.y += current_speed
        
        self.rect.topleft = (self.x, self.y) # Update rect position AFTER updating x, y

        # Boundary check using map_sim_width
        # Allow some part of the car to be off-screen before despawning completely
        despawn_buffer = self.draw_width * 2 # Or some other reasonable buffer
        if self.rect.right < -despawn_buffer or self.rect.left > map_sim_width + despawn_buffer or \
           self.rect.bottom < -despawn_buffer or self.rect.top > map_height + despawn_buffer:
            if not self.is_despawned: # To ensure despawn logic runs once
                self.is_despawned = True
                # print(f"[VEHICLE DEBUG] Despawned {self.id} at {self.rect.topleft}, sim_width={map_sim_width}")
                if self.metrics_client: self.metrics_client.vehicle_despawned(self.id)
                await self.publish_state("despawned")
            return
        
        light_action = self._check_action_at_light(traffic_lights)
        if light_action == "stop":
            self.x, self.y = old_x, old_y # Revert move
            self.rect.topleft = (self.x, self.y) # Revert rect as well
            self.stop(reason="traffic_light")
            if self.speed != old_speed or self.stopped != old_stopped: await self.publish_state("stopped_at_light")
            if self.metrics_client: self.metrics_client.accumulate_vehicle_speed(self.speed)
            return

        # Collision avoidance
        safe_distance_factor = 0.2 # Increase buffer slightly for safety
        for other in all_vehicles:
            if other.id == self.id or other.is_despawned: continue

            if self.rect.colliderect(other.rect):
                is_in_front_and_dangerously_close = False
                # Refined conditions to check if 'other' is ACTUALLY in the forward path and close
                if self.direction == "right" and other.rect.left > self.rect.centerx and other.rect.left < self.rect.right + self.draw_width * safe_distance_factor:
                    if abs(self.rect.centery - other.rect.centery) < (self.draw_height + other.draw_height) / 2 * 0.8: # Check for significant Y overlap
                        is_in_front_and_dangerously_close = True
                elif self.direction == "left" and other.rect.right < self.rect.centerx and other.rect.right > self.rect.left - self.draw_width * safe_distance_factor:
                    if abs(self.rect.centery - other.rect.centery) < (self.draw_height + other.draw_height) / 2 * 0.8:
                        is_in_front_and_dangerously_close = True
                elif self.direction == "down" and other.rect.top > self.rect.centery and other.rect.top < self.rect.bottom + self.draw_height * safe_distance_factor:
                    if abs(self.rect.centerx - other.rect.centerx) < (self.draw_width + other.draw_width) / 2 * 0.8: # Check for significant X overlap
                        is_in_front_and_dangerously_close = True
                elif self.direction == "up" and other.rect.bottom < self.rect.centery and other.rect.bottom > self.rect.top - self.draw_height * safe_distance_factor:
                    if abs(self.rect.centerx - other.rect.centerx) < (self.draw_width + other.draw_width) / 2 * 0.8:
                        is_in_front_and_dangerously_close = True
                
                if is_in_front_and_dangerously_close:
                    self.x, self.y = old_x, old_y
                    self.rect.topleft = (self.x, self.y)
                    self.stop(reason="collision_avoidance")
                    if self.speed != old_speed or self.stopped != old_stopped: await self.publish_state("stopped_avoidance")
                    if self.metrics_client: self.metrics_client.accumulate_vehicle_speed(self.speed)
                    return

        # If it was stopped but no longer needs to be (e.g., collision cleared, light green)
        if old_stopped and not self.stopped : # Check if it *was* stopped and now isn't
             pass # resume() already called if light is green, collision check passed
        elif self.stopped: # If it's still marked as stopped but shouldn't be (e.g. a previous collision that's now clear)
            # This case needs more careful handling. For now, assume traffic light logic or prior collision check handles resume.
            pass


        # Ensure speed is normal if not stopped
        if not self.stopped and self.speed == 0.0:
            self.resume_speed()

        if self.x != old_x or self.y != old_y or self.speed != old_speed or self.stopped != old_stopped:
            await self.publish_state("updated")
        if self.metrics_client: self.metrics_client.accumulate_vehicle_speed(self.speed)

    def _get_relevant_light(self, traffic_lights: List['TrafficLight']) -> Optional['TrafficLight']:
        min_dist_sq = float('inf')
        relevant_light = None
        # Look ahead distance: how many frames of movement + car length.
        # Base this on original_speed to avoid issues when speed is 0.
        lookahead_distance = (self.original_speed * 20) + self.draw_width # Approx 20 frames + car length

        for light in traffic_lights:
            correct_orientation = (self.direction in ["right", "left"] and light.orientation == "vertical") or \
                                  (self.direction in ["up", "down"] and light.orientation == "horizontal")
            if not correct_orientation: continue

            is_light_ahead_and_aligned = False
            dist_to_light_interaction_point_sq = float('inf') # Squared distance

            # Check if light is in the vehicle's forward path and within lookahead distance
            if self.direction == "right":
                # Light must be to the right of vehicle's front
                # And vehicle's y must be within light's y-range (for vertical lights)
                if light.x > self.rect.right and \
                   self.rect.centery > light.y and self.rect.centery < light.y + light.height:
                    is_light_ahead_and_aligned = True
                    dist_to_light_interaction_point_sq = (light.x - self.rect.right)**2
            elif self.direction == "left":
                if (light.x + light.width) < self.rect.left and \
                   self.rect.centery > light.y and self.rect.centery < light.y + light.height:
                    is_light_ahead_and_aligned = True
                    dist_to_light_interaction_point_sq = (self.rect.left - (light.x + light.width))**2
            elif self.direction == "down":
                if light.y > self.rect.bottom and \
                   self.rect.centerx > light.x and self.rect.centerx < light.x + light.width:
                    is_light_ahead_and_aligned = True
                    dist_to_light_interaction_point_sq = (light.y - self.rect.bottom)**2
            elif self.direction == "up":
                if (light.y + light.height) < self.rect.top and \
                   self.rect.centerx > light.x and self.rect.centerx < light.x + light.width:
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

        # How far the front of the car is from the near edge of the light housing
        dist_to_light_edge = float('inf')
        if self.direction == "right": dist_to_light_edge = light.x - self.rect.right
        elif self.direction == "left": dist_to_light_edge = self.rect.left - (light.x + light.width)
        elif self.direction == "down": dist_to_light_edge = light.y - self.rect.bottom
        elif self.direction == "up": dist_to_light_edge = self.rect.top - (light.y + light.height)

        # Stop if car is within this distance (e.g., 1-2 car lengths) of the light edge for red/yellow
        # Base this on original_speed as current speed might be 0
        stopping_decision_threshold = self.original_speed * 2.0 + self.draw_width * 0.5 
        # Consider a small negative threshold to stop even if slightly past the line
        stop_past_line_threshold = -self.draw_width * 0.2 

        if dist_to_light_edge < stopping_decision_threshold and dist_to_light_edge > stop_past_line_threshold :
            if light.state == "red":
                return "stop"
            elif light.state == "yellow":
                # If on yellow and can't clear (or too close to stop safely), then stop.
                # Simplified: stop on yellow if within a closer threshold.
                yellow_stop_threshold = self.original_speed * 1.0 + self.draw_width * 0.1
                if dist_to_light_edge < yellow_stop_threshold and dist_to_light_edge > stop_past_line_threshold:
                     return "stop"
        return "proceed"

    def stop(self, reason: str = "unknown") -> None:
        if not self.stopped:
            self.stopped = True
            self.speed = 0.0
            # print(f"[VEHICLE DEBUG] Vehicle {self.id} STOPPED. Reason: {reason}. Pos: ({self.x:.1f},{self.y:.1f})")
            if self.metrics_client: self.metrics_client.vehicle_started_waiting(self.id)

    def resume(self) -> None:
        if self.stopped:
            self.stopped = False
            self.resume_speed() # This will set self.speed to self.original_speed
            # print(f"[VEHICLE DEBUG] Vehicle {self.id} RESUMED. Pos: ({self.x:.1f},{self.y:.1f}) Speed: {self.speed:.1f}")
            if self.metrics_client: self.metrics_client.vehicle_stopped_waiting(self.id)

    def resume_speed(self) -> None:
        self.speed = self.original_speed

    def draw(self, surface: pygame.Surface) -> None:
        if self.is_despawned:
            return
        # Use the rounded rect helper for vehicles too
        draw_rounded_rect(surface, self.color, self.rect, Theme.BORDER_RADIUS // 2) # Smaller radius for cars
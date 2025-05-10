# simulacion_trafico_engine/core/vehicle.py
import pygame
import uuid
import asyncio
from typing import Tuple, List, Dict, Optional, TYPE_CHECKING

from simulacion_trafico_engine.ui.theme import Theme, draw_rounded_rect # Ajusta si la ruta es diferente

if TYPE_CHECKING:
    from simulacion_trafico_engine.core.traffic_light import TrafficLight
    from simulacion_trafico_engine.core.zone_map import ZoneMap 
    from simulacion_trafico_engine.distribution.rabbitclient import RabbitMQClient
    from simulacion_trafico_engine.performance.metrics import TrafficMetrics

class Vehicle:
    def __init__(self, id: str,
                 global_x: float, global_y: float,
                 width: int = 30, height: int = 15,
                 color: Optional[Tuple[int, int, int]] = None,
                 speed: float = 2.0,
                 original_speed: Optional[float] = None,
                 direction: str = "right",
                 current_zone_id: str = "unknown",
                 rabbit_client: Optional['RabbitMQClient'] = None,
                 metrics_client: Optional['TrafficMetrics'] = None,
                 map_ref: Optional['ZoneMap'] = None):

        self.id = id
        self.global_x = global_x
        self.global_y = global_y
        self.color = pygame.Color(color) if color and isinstance(color, (tuple, list)) and len(color) >= 3 else Theme.get_vehicle_color()
        self.original_speed = original_speed if original_speed is not None else speed
        self.speed = speed
        self.direction = direction
        self.stopped = False
        self.current_zone_id = current_zone_id

        self.rabbit_client = rabbit_client
        self.metrics_client = metrics_client
        self.map_ref = map_ref

        if direction in ["left", "right"]:
            self.draw_width, self.draw_height = width, height
        else:
            self.draw_width, self.draw_height = height, width

        self.rect = pygame.Rect(0, 0, self.draw_width, self.draw_height) 
        self.is_despawned_globally = False

        if self.metrics_client: self.metrics_client.vehicle_spawned(self.id)

    def get_global_rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.global_x), int(self.global_y), self.draw_width, self.draw_height)

    async def publish_state(self, event_type: str = "update", extra_data: Optional[Dict] = None) -> None:
        if not (self.rabbit_client and hasattr(self.rabbit_client, 'async_exchange') and self.rabbit_client.async_exchange):
            return
        message = {
            "vehicle_id": self.id, "event_type": event_type, "zone_id": self.current_zone_id,
            "position": {"x": self.global_x, "y": self.global_y},
            "speed_px_frame": self.speed, "direction": self.direction,
            "stopped": self.stopped, "timestamp": asyncio.get_event_loop().time()
        }
        if extra_data: message.update(extra_data)
        
        routing_key_base = f"city.vehicle.{self.id}"
        if event_type == "migration_request": routing_key_base = f"city.migration.request"
        elif event_type == "despawned_global": routing_key_base = f"city.vehicle.despawned"

        try:
            await self.rabbit_client.publish_async(f"{routing_key_base}.{event_type}", message)
        except Exception as e: print(f"[Vehicle {self.id}] Error publishing: {e}")


    async def update_in_zone(self, 
                             zone_traffic_lights: List['TrafficLight'],
                             zone_vehicles: List['Vehicle'],
                             zone_width: int, zone_height: int,
                             zone_global_offset_x: int, zone_global_offset_y: int):
        if self.is_despawned_globally: return

        old_global_x, old_global_y = self.global_x, self.global_y
        old_speed, old_stopped = self.speed, self.stopped

        local_x = self.global_x - zone_global_offset_x
        local_y = self.global_y - zone_global_offset_y
        self.rect.topleft = (int(local_x), int(local_y)) 
        old_local_x, old_local_y = local_x, local_y


        if self.stopped:
            action = self._check_action_at_light_local(zone_traffic_lights, local_x, local_y)
            if action == "proceed": self.resume()
            else:
                if self.metrics_client: self.metrics_client.accumulate_vehicle_speed(self.speed)
                return

        current_speed = self.speed
        if self.direction == "right": self.global_x += current_speed
        elif self.direction == "left": self.global_x -= current_speed
        elif self.direction == "up": self.global_y -= current_speed
        elif self.direction == "down": self.global_y += current_speed
        
        local_x = self.global_x - zone_global_offset_x
        local_y = self.global_y - zone_global_offset_y
        self.rect.topleft = (int(local_x), int(local_y))

        light_action = self._check_action_at_light_local(zone_traffic_lights, local_x, local_y)
        if light_action == "stop":
            self.global_x, self.global_y = old_global_x, old_global_y
            self.rect.topleft = (int(old_local_x), int(old_local_y)) 
            self.stop(reason="traffic_light")
            if self.speed != old_speed or self.stopped != old_stopped: await self.publish_state("stopped_at_light")
            if self.metrics_client: self.metrics_client.accumulate_vehicle_speed(self.speed)
            return

        safe_dist_factor = 0.2
        for other_veh in zone_vehicles:
            if other_veh.id == self.id or other_veh.is_despawned_globally: continue
            if self.rect.colliderect(other_veh.rect):
                is_front_collision = False
                if self.direction == "right" and other_veh.rect.left > self.rect.centerx and other_veh.rect.left < self.rect.right + self.draw_width * safe_dist_factor :
                    if abs(self.rect.centery - other_veh.rect.centery) < (self.draw_height + other_veh.draw_height) / 2 * 0.9: is_front_collision = True 
                elif self.direction == "left" and other_veh.rect.right < self.rect.centerx and other_veh.rect.right > self.rect.left - self.draw_width * safe_dist_factor:
                    if abs(self.rect.centery - other_veh.rect.centery) < (self.draw_height + other_veh.draw_height) / 2 * 0.9: is_front_collision = True
                elif self.direction == "down" and other_veh.rect.top > self.rect.centery and other_veh.rect.top < self.rect.bottom + self.draw_height * safe_dist_factor: # draw_height es en realidad "longitud" del coche en esta orientación
                    if abs(self.rect.centerx - other_veh.rect.centerx) < (self.draw_width + other_veh.draw_width) / 2 * 0.9: is_front_collision = True
                elif self.direction == "up" and other_veh.rect.bottom < self.rect.centery and other_veh.rect.bottom > self.rect.top - self.draw_height * safe_dist_factor: # draw_height es en realidad "longitud" del coche en esta orientación
                    if abs(self.rect.centerx - other_veh.rect.centerx) < (self.draw_width + other_veh.draw_width) / 2 * 0.9: is_front_collision = True
                
                if is_front_collision:
                    self.global_x, self.global_y = old_global_x, old_global_y
                    self.rect.topleft = (int(old_local_x), int(old_local_y))
                    self.stop(reason="collision_avoidance")
                    if self.speed!=old_speed or self.stopped!=old_stopped: await self.publish_state("stopped_avoidance")
                    if self.metrics_client: self.metrics_client.accumulate_vehicle_speed(self.speed)
                    return
        
        if old_stopped and not self.stopped: pass 
        elif self.stopped: pass 
        if not self.stopped and self.speed == 0.0: self.resume_speed()

        if self.global_x != old_global_x or self.global_y != old_global_y or \
           self.speed != old_speed or self.stopped != old_stopped:
            await self.publish_state("updated")
        if self.metrics_client: self.metrics_client.accumulate_vehicle_speed(self.speed)


    def _get_relevant_light_local(self, zone_traffic_lights: List['TrafficLight'], current_local_x: float, current_local_y: float) -> Optional['TrafficLight']:
        min_dist = float('inf')
        relevant_light = None
        lookahead = (self.original_speed * 20) + self.draw_width 

        vehicle_local_rect = self.rect 

        for light in zone_traffic_lights: 
            # --- MODIFICACIÓN AQUÍ ---
            # Usar light.rect para acceder a propiedades geométricas del semáforo
            correct_orientation = (self.direction in ["right", "left"] and light.orientation == "vertical") or \
                                  (self.direction in ["up", "down"] and light.orientation == "horizontal")
            if not correct_orientation: continue

            is_ahead_and_aligned = False
            dist_edge = float('inf')

            if self.direction == "right":
                if light.rect.left >= vehicle_local_rect.right and \
                   abs(light.rect.centery - vehicle_local_rect.centery) < light.rect.height: 
                    is_ahead_and_aligned = True
                    dist_edge = light.rect.left - vehicle_local_rect.right
            elif self.direction == "left":
                if light.rect.right <= vehicle_local_rect.left and \
                   abs(light.rect.centery - vehicle_local_rect.centery) < light.rect.height:
                    is_ahead_and_aligned = True
                    dist_edge = vehicle_local_rect.left - light.rect.right
            elif self.direction == "down":
                if light.rect.top >= vehicle_local_rect.bottom and \
                   abs(light.rect.centerx - vehicle_local_rect.centerx) < light.rect.width:
                    is_ahead_and_aligned = True
                    dist_edge = light.rect.top - vehicle_local_rect.bottom
            elif self.direction == "up":
                if light.rect.bottom <= vehicle_local_rect.top and \
                   abs(light.rect.centerx - vehicle_local_rect.centerx) < light.rect.width:
                    is_ahead_and_aligned = True
                    dist_edge = vehicle_local_rect.top - light.rect.bottom
            # --- FIN MODIFICACIÓN ---
            
            if is_ahead_and_aligned and 0 <= dist_edge < lookahead:
                if dist_edge < min_dist:
                    min_dist = dist_edge
                    relevant_light = light
        return relevant_light


    def _check_action_at_light_local(self, zone_traffic_lights: List['TrafficLight'], current_local_x: float, current_local_y: float) -> str:
        light = self._get_relevant_light_local(zone_traffic_lights, current_local_x, current_local_y)
        if not light: return "proceed"

        dist_to_light_edge = float('inf')
        # --- MODIFICACIÓN AQUÍ ---
        # Usar light.rect para calcular distancias al borde del semáforo
        if self.direction == "right": dist_to_light_edge = light.rect.left - self.rect.right 
        elif self.direction == "left": dist_to_light_edge = self.rect.left - light.rect.right
        elif self.direction == "down": dist_to_light_edge = light.rect.top - self.rect.bottom
        elif self.direction == "up": dist_to_light_edge = self.rect.top - light.rect.bottom
        # --- FIN MODIFICACIÓN ---
        
        stopping_decision_threshold = self.original_speed * 2.5 + self.draw_width * 0.3 
        stop_past_line_threshold = -self.draw_width * 0.5 

        if dist_to_light_edge < stopping_decision_threshold and dist_to_light_edge > stop_past_line_threshold :
            if light.state == "red":
                return "stop"
            elif light.state == "yellow":
                yellow_stop_threshold = self.original_speed * 1.5 + self.draw_width * 0.1
                if dist_to_light_edge < yellow_stop_threshold and dist_to_light_edge > stop_past_line_threshold:
                     return "stop"
        return "proceed"

    def stop(self, reason: str = "unknown") -> None:
        if not self.stopped:
            self.stopped = True; self.speed = 0.0
            if self.metrics_client: self.metrics_client.vehicle_started_waiting(self.id)

    def resume(self) -> None:
        if self.stopped:
            self.stopped = False; self.resume_speed()
            if self.metrics_client: self.metrics_client.vehicle_stopped_waiting(self.id)

    def resume_speed(self) -> None: self.speed = self.original_speed

    def draw(self, surface: pygame.Surface):
        if self.is_despawned_globally: 
            return
        
        global_draw_rect = pygame.Rect(
            int(self.global_x), 
            int(self.global_y), 
            self.draw_width, 
            self.draw_height
        )
        
        draw_rounded_rect(surface, self.color, global_draw_rect, Theme.BORDER_RADIUS // 2)
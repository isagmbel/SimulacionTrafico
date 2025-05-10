# simulacion_trafico_engine/environment/trafficlight.py
import pygame
import asyncio
from typing import Tuple, Dict, Optional, TYPE_CHECKING

from ..ui.theme import Theme, draw_rounded_rect # Import Theme

if TYPE_CHECKING:
    from simulacion_trafico_engine.distribution.rabbitclient import RabbitMQClient
    from simulacion_trafico_engine.performance.metrics import TrafficMetrics

class TrafficLight:
    def __init__(self, id: str, x: int, y: int, width: int, height: int,
                 orientation: str = "vertical", cycle_time: int = 150,
                 initial_offset_factor: float = 0.0,
                 rabbit_client: Optional['RabbitMQClient'] = None,
                 metrics_client: Optional['TrafficMetrics'] = None,
                 theme: Optional[Theme] = None): # Added theme
        self.id = id
        self.x = x # Coordenada local x del top-left del housing
        self.y = y # Coordenada local y del top-left del housing
        self.width = width # Ancho del housing
        self.height = height # Alto del housing
        
        # --- MODIFICACIÓN AQUÍ ---
        # Añadir un atributo rect para representar la geometría del semáforo
        self.rect = pygame.Rect(x, y, width, height)
        # --- FIN MODIFICACIÓN ---
        
        self.orientation = orientation
        self.rabbit_client = rabbit_client
        self.metrics_client = metrics_client
        self.theme = theme if theme else Theme() # Use passed theme or default

        self.cycle_time = cycle_time
        self.state_durations_ratio = {"green": 0.45, "yellow": 0.10, "red": 0.45}
        self.timings = {s: int(dr * cycle_time) for s, dr in self.state_durations_ratio.items()}
        self.timings["red"] = cycle_time - (self.timings["green"] + self.timings["yellow"])
        self.current_cycle_time = int(initial_offset_factor * cycle_time)
        self.state = self._get_state_at_time(self.current_cycle_time)

        # Using Theme for colors
        self.colors = {
            "green": self.theme.TL_GREEN, "yellow": self.theme.TL_YELLOW,
            "red": self.theme.TL_RED, "off": self.theme.TL_OFF
        }

        if self.rabbit_client and hasattr(self.rabbit_client, 'async_channel'):
            asyncio.create_task(self.publish_state())

    def _get_state_at_time(self, time_in_cycle: int) -> str:
        if time_in_cycle < self.timings["green"]: return "green"
        elif time_in_cycle < self.timings["green"] + self.timings["yellow"]: return "yellow"
        return "red"

    async def update_async(self) -> None:
        self.current_cycle_time = (self.current_cycle_time + 1) % self.cycle_time
        new_state = self._get_state_at_time(self.current_cycle_time)
        if new_state != self.state:
            self.state = new_state
            if self.metrics_client: self.metrics_client.traffic_light_changed(self.id, self.state)
            if self.rabbit_client and hasattr(self.rabbit_client, 'async_channel'): await self.publish_state()

    async def publish_state(self) -> None:
        if not (self.rabbit_client and hasattr(self.rabbit_client, 'async_channel') and self.rabbit_client.async_channel):
            return
        message = {"light_id": self.id, "state": self.state, "position": {"x": self.x, "y": self.y}, "orientation": self.orientation, "timestamp": asyncio.get_event_loop().time()}
        await self.rabbit_client.publish_async(f"traffic.light.status.{self.id}", message)

    def draw(self, surface: pygame.Surface) -> None:
        # El rect para dibujar el housing sigue siendo self.rect (antes housing_rect local)
        draw_rounded_rect(surface, self.theme.TL_HOUSING, self.rect, self.theme.BORDER_RADIUS)

        padding = 4 
        if self.orientation == "vertical":
            light_diameter = min(self.rect.width - 2 * padding, (self.rect.height - 4 * padding) / 3)
            radius = light_diameter / 2
            centers = [
                (self.rect.centerx, self.rect.top + padding + radius),
                (self.rect.centerx, self.rect.top + padding * 2 + light_diameter + radius),
                (self.rect.centerx, self.rect.top + padding * 3 + light_diameter * 2 + radius)
            ]
            ordered_states = ["red", "yellow", "green"] 
        else: # horizontal
            light_diameter = min(self.rect.height - 2 * padding, (self.rect.width - 4 * padding) / 3)
            radius = light_diameter / 2
            centers = [
                (self.rect.left + padding + radius, self.rect.centery),
                (self.rect.left + padding * 2 + light_diameter + radius, self.rect.centery),
                (self.rect.left + padding * 3 + light_diameter * 2 + radius, self.rect.centery)
            ]
            ordered_states = ["red", "yellow", "green"] 

        for i, state_name in enumerate(ordered_states):
            color_to_draw = self.colors[state_name] if self.state == state_name else self.colors["off"]
            pygame.draw.circle(surface, color_to_draw, centers[i], radius)
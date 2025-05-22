# simulacion_trafico_engine/core/traffic_light.py
import pygame
import asyncio
from typing import Tuple, Dict, Optional, TYPE_CHECKING

# Asegúrate de que esta ruta de importación sea correcta para tu estructura de proyecto
# Si TrafficLight está en 'core' y Theme en 'ui', esto es correcto:
from ..ui.theme import Theme, draw_rounded_rect 

if TYPE_CHECKING:
    # Asegúrate de que estas rutas sean correctas
    from simulacion_trafico_engine.distribution.rabbitclient import RabbitMQClient
    from simulacion_trafico_engine.performance.metrics import TrafficMetrics

class TrafficLight:
    def __init__(self, id: str, x: int, y: int, width: int, height: int,
                 orientation: str = "vertical", cycle_time: int = 150,
                 initial_offset_factor: float = 0.0,
                 rabbit_client: Optional['RabbitMQClient'] = None,
                 metrics_client: Optional['TrafficMetrics'] = None,
                 theme: Optional[Theme] = None): 
        self.id = id
        self.local_x = x # Coordenada local X del top-left del housing, relativa a la zona
        self.local_y = y # Coordenada local Y del top-left del housing, relativa a la zona
        self.width = width 
        self.height = height 
        
        # self.rect se refiere al rect local del semáforo dentro de su zona.
        # Se usa para la lógica de detección del vehículo (_get_relevant_light_local).
        self.rect = pygame.Rect(self.local_x, self.local_y, self.width, self.height)
        
        self.orientation = orientation
        self.rabbit_client = rabbit_client
        self.metrics_client = metrics_client
        self.theme = theme if theme else Theme() 

        self.cycle_time = cycle_time
        self.state_durations_ratio = {"green": 0.45, "yellow": 0.10, "red": 0.45}
        self.timings = {s: int(dr * cycle_time) for s, dr in self.state_durations_ratio.items()}
        self.timings["red"] = cycle_time - (self.timings["green"] + self.timings["yellow"])
        self.current_cycle_time = int(initial_offset_factor * cycle_time) % cycle_time
        self.state = self._get_state_at_time(self.current_cycle_time)

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
            if self.rabbit_client and hasattr(self.rabbit_client, 'async_channel') and self.rabbit_client.async_channel: 
                await self.publish_state()

    async def publish_state(self) -> None:
        if not (self.rabbit_client and hasattr(self.rabbit_client, 'async_channel') and self.rabbit_client.async_channel):
            return
        # Publicar coordenadas locales; el consumidor puede necesitar saber la zona para globalizarlas
        message = {"light_id": self.id, "state": self.state, 
                   "position": {"x": self.local_x, "y": self.local_y}, 
                   "orientation": self.orientation, "timestamp": asyncio.get_event_loop().time()}
        try:
            await self.rabbit_client.publish_async(f"traffic.light.status.{self.id}", message)
        except Exception as e:
            print(f"[TrafficLight {self.id}] Error publishing state: {e}")


    def draw(self, surface: pygame.Surface, zone_offset_x: int = 0, zone_offset_y: int = 0):
        """
        Dibuja el semáforo en la superficie dada, aplicando los offsets de la zona.
        `zone_offset_x` y `zone_offset_y` son las coordenadas globales del origen (0,0) de la zona.
        """
        # Calcular las coordenadas globales de dibujo del housing del semáforo
        global_draw_x = self.local_x + zone_offset_x
        global_draw_y = self.local_y + zone_offset_y
        
        # El rect para dibujar el housing del semáforo, en coordenadas globales
        housing_rect_global = pygame.Rect(global_draw_x, global_draw_y, self.width, self.height)
        
        draw_rounded_rect(surface, self.theme.TL_HOUSING, housing_rect_global, self.theme.BORDER_RADIUS)

        padding = 4 
        if self.orientation == "vertical":
            # Cálculos basados en las dimensiones del housing_rect_global
            light_diameter = min(housing_rect_global.width - 2 * padding, (housing_rect_global.height - 4 * padding) / 3)
            radius = light_diameter / 2
            centers = [
                (housing_rect_global.centerx, housing_rect_global.top + padding + radius),
                (housing_rect_global.centerx, housing_rect_global.top + padding * 2 + light_diameter + radius),
                (housing_rect_global.centerx, housing_rect_global.top + padding * 3 + light_diameter * 2 + radius)
            ]
            ordered_states = ["red", "yellow", "green"] 
        else: # horizontal
            light_diameter = min(housing_rect_global.height - 2 * padding, (housing_rect_global.width - 4 * padding) / 3)
            radius = light_diameter / 2
            centers = [
                (housing_rect_global.left + padding + radius, housing_rect_global.centery),
                (housing_rect_global.left + padding * 2 + light_diameter + radius, housing_rect_global.centery),
                (housing_rect_global.left + padding * 3 + light_diameter * 2 + radius, housing_rect_global.centery)
            ]
            ordered_states = ["red", "yellow", "green"] # Orden visual estándar

        for i, state_name in enumerate(ordered_states):
            color_to_draw = self.colors[state_name] if self.state == state_name else self.colors["off"]
            pygame.draw.circle(surface, color_to_draw, centers[i], radius)
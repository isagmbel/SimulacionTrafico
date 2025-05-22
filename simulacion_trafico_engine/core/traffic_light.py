# simulacion_trafico_engine/core/traffic_light.py
import pygame
import asyncio
from typing import Tuple, Dict, Optional, TYPE_CHECKING

# Importar Theme para acceder a colores y radios, y la función de dibujo.
# Se asume que la estructura de carpetas es simulacion_trafico_engine/ui/theme.py
from ..ui.theme import Theme, draw_rounded_rect 

if TYPE_CHECKING:
    # Para type hinting sin causar importaciones circulares en tiempo de ejecución.
    # Estas rutas deben ser correctas según tu estructura de proyecto.
    from simulacion_trafico_engine.distribution.rabbitclient import RabbitMQClient
    from simulacion_trafico_engine.performance.metrics import TrafficMetrics

class TrafficLight:
    """
    Representa un semáforo en la simulación de tráfico.
    Gestiona su estado (rojo, amarillo, verde), temporización del ciclo,
    y su representación visual. Puede interactuar con RabbitMQ para publicar su estado
    y con un cliente de métricas para registrar cambios.
    """

    def __init__(self, id: str, x: int, y: int, width: int, height: int,
                 orientation: str = "vertical", cycle_time: int = 150,
                 initial_offset_factor: float = 0.0,
                 rabbit_client: Optional['RabbitMQClient'] = None,
                 metrics_client: Optional['TrafficMetrics'] = None,
                 theme: Optional[Theme] = None): 
        """
        Inicializa un nuevo semáforo.
        Args:
            id (str): Identificador único para el semáforo.
            x (int): Coordenada X local (relativa a su zona) de la esquina superior izquierda.
            y (int): Coordenada Y local (relativa a su zona) de la esquina superior izquierda.
            width (int): Ancho del housing del semáforo.
            height (int): Alto del housing del semáforo.
            orientation (str, optional): Orientación del semáforo ("vertical" u "horizontal").
                                         Afecta la disposición de las luces. Por defecto "vertical".
            cycle_time (int, optional): Duración total de un ciclo completo del semáforo (en ticks de simulación).
                                        Por defecto 150.
            initial_offset_factor (float, optional): Factor (0.0 a 1.0) para desfasar el inicio del ciclo
                                                     de este semáforo respecto a otros. Por defecto 0.0.
            rabbit_client (Optional['RabbitMQClient'], optional): Cliente RabbitMQ para publicar cambios de estado.
            metrics_client (Optional['TrafficMetrics'], optional): Cliente para registrar métricas de cambios.
            theme (Optional[Theme], optional): Instancia de la clase Theme para usar sus colores y estilos.
                                               Si es None, se crea una instancia por defecto de Theme.
        """
        self.id: str = id
        self.local_x: int = x  # Coordenada local X del housing, relativa a la zona.
        self.local_y: int = y  # Coordenada local Y del housing, relativa a la zona.
        self.width: int = width
        self.height: int = height
        
        # self.rect representa el bounding box del semáforo en coordenadas locales a su zona.
        # Es utilizado por los vehículos para detectar la presencia y posición del semáforo.
        self.rect: pygame.Rect = pygame.Rect(self.local_x, self.local_y, self.width, self.height)
        
        self.orientation: str = orientation
        self.rabbit_client: Optional['RabbitMQClient'] = rabbit_client
        self.metrics_client: Optional['TrafficMetrics'] = metrics_client
        self.theme: Theme = theme if theme else Theme() # Usar tema provisto o uno por defecto.

        # --- Configuración de Temporización del Ciclo del Semáforo ---
        self.cycle_time: int = cycle_time # Duración total del ciclo en ticks.
        # Proporciones de duración para cada estado del semáforo.
        self.state_durations_ratio: Dict[str, float] = {"green": 0.45, "yellow": 0.10, "red": 0.45}
        # Calcular duraciones absolutas (en ticks) para cada estado.
        self.timings: Dict[str, int] = {
            state: int(ratio * cycle_time) 
            for state, ratio in self.state_durations_ratio.items()
        }
        # Ajustar la duración del rojo para asegurar que la suma total sea `cycle_time`.
        self.timings["red"] = cycle_time - (self.timings["green"] + self.timings["yellow"])
        
        # Tiempo actual dentro del ciclo, inicializado con un offset si se proveyó.
        # El módulo asegura que el tiempo inicial esté dentro del rango del ciclo.
        self.current_cycle_time: int = int(initial_offset_factor * cycle_time) % cycle_time
        # Estado inicial del semáforo basado en el tiempo de ciclo actual.
        self.state: str = self._get_state_at_time(self.current_cycle_time)

        # --- Configuración de Colores del Semáforo (desde el Tema) ---
        self.colors: Dict[str, pygame.Color] = {
            "green": self.theme.TL_GREEN,
            "yellow": self.theme.TL_YELLOW,
            "red": self.theme.TL_RED,
            "off": self.theme.TL_OFF # Color para las luces que no están activas.
        }

        # Si hay un cliente RabbitMQ y tiene un canal asíncrono, publicar el estado inicial.
        if self.rabbit_client and hasattr(self.rabbit_client, 'async_channel') and self.rabbit_client.async_channel:
            asyncio.create_task(self.publish_state())

    def _get_state_at_time(self, time_in_cycle: int) -> str:
        """
        Determina el estado del semáforo (rojo, amarillo, verde) basado en el tiempo
        actual dentro de su ciclo.
        Args:
            time_in_cycle (int): El tiempo transcurrido dentro del ciclo actual del semáforo.
        Returns:
            str: El estado del semáforo ("green", "yellow", o "red").
        """
        if time_in_cycle < self.timings["green"]:
            return "green"
        elif time_in_cycle < (self.timings["green"] + self.timings["yellow"]):
            return "yellow"
        else:
            return "red"

    async def update_async(self) -> None:
        """
        Actualiza el estado del semáforo para el siguiente tick de simulación.
        Avanza el tiempo del ciclo y cambia el estado si es necesario.
        Si el estado cambia, registra la métrica y publica el nuevo estado vía RabbitMQ.
        """
        # Avanzar el tiempo del ciclo, volviendo a 0 si se completa el ciclo.
        self.current_cycle_time = (self.current_cycle_time + 1) % self.cycle_time
        new_state = self._get_state_at_time(self.current_cycle_time)
        
        # Si el estado calculado es diferente al estado actual, actualizar.
        if new_state != self.state:
            self.state = new_state
            # Registrar el cambio de estado en las métricas.
            if self.metrics_client:
                self.metrics_client.traffic_light_changed(self.id, self.state)
            # Publicar el nuevo estado a través de RabbitMQ.
            if self.rabbit_client and hasattr(self.rabbit_client, 'async_channel') and self.rabbit_client.async_channel: 
                await self.publish_state()

    async def publish_state(self) -> None:
        """
        Publica el estado actual del semáforo a un topic de RabbitMQ.
        El mensaje incluye ID, estado, posición local, orientación y timestamp.
        """
        if not (self.rabbit_client and hasattr(self.rabbit_client, 'async_channel') and self.rabbit_client.async_channel):
            # No publicar si el cliente RabbitMQ no está configurado o el canal no está listo.
            return
        
        message = {
            "light_id": self.id,
            "state": self.state,
            "position": {"x": self.local_x, "y": self.local_y}, # Posición local dentro de la zona.
            "orientation": self.orientation,
            "timestamp": asyncio.get_event_loop().time() # Timestamp del evento.
        }
        try:
            # El routing key incluye el ID del semáforo para suscripciones específicas.
            await self.rabbit_client.publish_async(f"traffic.light.status.{self.id}", message)
        except Exception as e:
            print(f"[TrafficLight {self.id}] Error al publicar estado vía RabbitMQ: {e}")


    def draw(self, surface: pygame.Surface, zone_offset_x: int = 0, zone_offset_y: int = 0):
        """
        Dibuja el semáforo en la superficie de Pygame proporcionada.
        Args:
            surface (pygame.Surface): La superficie principal donde se dibujará el semáforo.
            zone_offset_x (int): El desplazamiento X global de la zona a la que pertenece este semáforo.
            zone_offset_y (int): El desplazamiento Y global de la zona a la que pertenece este semáforo.
        """
        # --- Dibujo del Housing del Semáforo ---
        # Calcular las coordenadas globales de dibujo sumando los offsets de la zona
        # a las coordenadas locales del semáforo.
        global_draw_x = self.local_x + zone_offset_x
        global_draw_y = self.local_y + zone_offset_y
        
        # Crear el rectángulo para el housing del semáforo en coordenadas globales.
        housing_rect_global = pygame.Rect(global_draw_x, global_draw_y, self.width, self.height)
        
        # Dibujar el housing usando la función de utilidad y colores del tema.
        draw_rounded_rect(surface, self.theme.TL_HOUSING, housing_rect_global, self.theme.BORDER_RADIUS)

        # --- Dibujo de las Luces Individuales (Círculos) ---
        padding = 4 # Espacio entre las luces y el borde del housing.
        
        light_diameter: float
        radius: float
        centers: List[Tuple[float, float]]
        ordered_states = ["red", "yellow", "green"] # Orden visual estándar de las luces.

        if self.orientation == "vertical":
            # Calcular diámetro y radio para luces dispuestas verticalmente.
            light_diameter = min(housing_rect_global.width - 2 * padding, 
                                 (housing_rect_global.height - 4 * padding) / 3) # 3 luces, 4 espacios de padding.
            radius = light_diameter / 2
            # Calcular centros de los círculos de luz (de arriba hacia abajo: rojo, amarillo, verde).
            centers = [
                (housing_rect_global.centerx, housing_rect_global.top + padding + radius),
                (housing_rect_global.centerx, housing_rect_global.top + padding * 2 + light_diameter + radius),
                (housing_rect_global.centerx, housing_rect_global.top + padding * 3 + light_diameter * 2 + radius)
            ]
        else: # Orientación "horizontal"
            # Calcular diámetro y radio para luces dispuestas horizontalmente.
            light_diameter = min(housing_rect_global.height - 2 * padding, 
                                 (housing_rect_global.width - 4 * padding) / 3)
            radius = light_diameter / 2
            # Calcular centros (de izquierda a derecha: rojo, amarillo, verde, si es el estándar).
            centers = [
                (housing_rect_global.left + padding + radius, housing_rect_global.centery),
                (housing_rect_global.left + padding * 2 + light_diameter + radius, housing_rect_global.centery),
                (housing_rect_global.left + padding * 3 + light_diameter * 2 + radius, housing_rect_global.centery)
            ]
            # El orden de los estados (y colores) se mantiene para el bucle.

        # Dibujar cada luz (círculo).
        for i, state_name in enumerate(ordered_states):
            # Determinar el color de la luz: el color del estado actual si coincide, o el color "apagado".
            color_to_draw = self.colors[state_name] if self.state == state_name else self.colors["off"]
            pygame.draw.circle(surface, color_to_draw, centers[i], radius)
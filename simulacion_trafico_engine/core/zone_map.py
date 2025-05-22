# simulacion_trafico_engine/core/zone_map.py
import pygame
import asyncio
import uuid # No usado directamente aquí, pero podría serlo en futuras expansiones
import random
from typing import Tuple, List, Dict, Any, Optional, TYPE_CHECKING

# Importar Theme solo si se necesita para parámetros que no vengan de TrafficLight (ej. colores de fallback)
# o si se dibujaran elementos del mapa aquí. Actualmente, solo para common_params de TrafficLight.
from ..ui.theme import Theme 
# draw_rounded_rect ya no es necesario si ZoneMap no dibuja carreteras.

if TYPE_CHECKING:
    from .traffic_light import TrafficLight 
    from ..distribution.rabbitclient import RabbitMQClient
    from ..performance.metrics import TrafficMetrics

class ZoneMap:
    """
    Representa la estructura de una zona específica dentro del mapa de la ciudad.
    Define la geometría de las carreteras y la ubicación de los semáforos.
    Ya NO se encarga de dibujar el fondo del mapa, las carreteras o los edificios,
    asumiendo que estos son parte de una imagen de fondo estática gestionada por la GUI.
    Su principal responsabilidad de dibujo es delegar el dibujo de semáforos.
    La geometría de las carreteras sigue siendo crucial para la lógica de simulación
    (puntos de spawn, detección de intersecciones para semáforos).
    """
    def __init__(self, zone_id: str, zone_bounds: Dict[str, int],
                 rabbit_client: Optional['RabbitMQClient'] = None,
                 metrics_client: Optional['TrafficMetrics'] = None):
        """
        Inicializa el mapa de la zona.
        Args:
            zone_id (str): Identificador único de la zona.
            zone_bounds (Dict[str, int]): Diccionario con los límites globales de la zona
                                          ('x', 'y', 'width', 'height').
            rabbit_client (Optional['RabbitMQClient']): Cliente RabbitMQ (pasado a semáforos).
            metrics_client (Optional['TrafficMetrics']): Cliente de métricas (pasado a semáforos).
        """
        self.zone_id: str = zone_id
        self.width: int = zone_bounds["width"]    # Ancho de esta zona.
        self.height: int = zone_bounds["height"]  # Alto de esta zona.
        # Coordenadas globales de la esquina superior izquierda de esta zona.
        self.global_offset_x: int = zone_bounds["x"] 
        self.global_offset_y: int = zone_bounds["y"]

        self.rabbit_client: Optional['RabbitMQClient'] = rabbit_client
        self.metrics_client: Optional['TrafficMetrics'] = metrics_client
        
        # --- Estructuras del Mapa de la Zona ---
        # Lista de diccionarios que definen las carreteras (sus rects locales y dirección).
        # Esta geometría es usada por la lógica de spawn y posicionamiento de semáforos.
        self.roads: List[Dict[str, Any]] = [] 
        # Lista de instancias de TrafficLight en esta zona.
        self.traffic_lights: List['TrafficLight'] = [] 
        # Lista de pygame.Rect que representan las intersecciones (locales a la zona).
        self.intersections: List[pygame.Rect] = []
        
    def _generate_local_roads_and_intersections(self):
        """
        Define la geometría de las carreteras y las intersecciones DENTRO de esta zona.
        Las coordenadas son locales (origen 0,0 en la esquina superior izquierda de la zona).
        Esta información es fundamental para la lógica de la simulación, incluso si las carreteras
        no se dibujan dinámicamente por esta clase.
        """
        self.roads.clear()
        self.intersections.clear()
        
        # Ancho estándar de las carreteras. Este valor debe ser consistente con
        # el diseño visual de tu imagen de mapa de fondo (mapa.PNG).
        road_width: int = 60 
        
        # Definir una carretera horizontal centrada en la zona.
        h_road_y = self.height // 2 - road_width // 2
        self.roads.append({
            "rect": pygame.Rect(0, h_road_y, self.width, road_width), 
            "direction": "horizontal"
        })

        # Definir una carretera vertical centrada en la zona.
        v_road_x = self.width // 2 - road_width // 2
        self.roads.append({
            "rect": pygame.Rect(v_road_x, 0, road_width, self.height), 
            "direction": "vertical"
        })

        # Identificar la intersección central (asumiendo un cruce simple).
        if len(self.roads) == 2: # Esperamos una horizontal y una vertical.
            h_road_rect = self.roads[0]["rect"]
            v_road_rect = self.roads[1]["rect"]
            intersection = h_road_rect.clip(v_road_rect) # Área de solapamiento.
            if intersection.width > 5 and intersection.height > 5: # Comprobación básica.
                self.intersections.append(intersection)
        
        # print(f"[ZoneMap {self.zone_id}] Geometría de carreteras y {len(self.intersections)} interseccione(s) definida(s).")

    def initialize_map_elements(self, TrafficLightClass: type):
        """
        Inicializa todos los elementos del mapa de la zona, como la geometría de las carreteras
        y la creación y posicionamiento de los semáforos.
        Args:
            TrafficLightClass (type): La clase `TrafficLight` que se usará para instanciar semáforos.
        """
        self._generate_local_roads_and_intersections() # Esencial para la lógica.
        self.traffic_lights.clear() # Limpiar semáforos existentes si se reinicializa.

        if not self.intersections: # No se pueden colocar semáforos si no hay intersecciones.
            # print(f"[ZoneMap {self.zone_id}] No hay intersecciones definidas, no se colocarán semáforos.")
            return

        # Asumir una única intersección central para esta configuración.
        intersection: pygame.Rect = self.intersections[0]
        # Obtener los rects de las carreteras para ayudar a posicionar los semáforos.
        # Se asume un orden específico (horizontal primero, luego vertical) de `_generate_local_roads_and_intersections`.
        h_road_rect: pygame.Rect = self.roads[0]["rect"]
        v_road_rect: pygame.Rect = self.roads[1]["rect"] 
        road_width: int = h_road_rect.height # Ancho visual de un segmento de carretera.

        # --- Parámetros para la Creación de Semáforos ---
        light_housing_size_vertical: Tuple[int, int] = (12, 36) # (ancho, alto) para semáforos verticales.
        light_housing_size_horizontal: Tuple[int, int] = (36, 12)# (ancho, alto) para semáforos horizontales.
        offset_from_intersection_edge: int = 5 # Distancia del housing del semáforo al borde de la intersección.

        common_tl_params: Dict[str, Any] = {
            "rabbit_client": self.rabbit_client, 
            "metrics_client": self.metrics_client, 
            "theme": Theme() # Cada semáforo puede tener su instancia de Theme o compartir una.
        }
        base_cycle_time: int = random.randint(240, 360) # Duración aleatoria del ciclo para variar.
        # Factor de desfase para el segundo par de semáforos, para asegurar que empiezan en rojo
        # si el primer par empieza en verde (0.45 green + 0.10 yellow = 0.55).
        SECOND_PAIR_OFFSET_FACTOR: float = 0.55 

        # --- Creación y Posicionamiento de Semáforos ---
        # Los semáforos se nombran según la dirección DESDE la que se aproxima el tráfico que controlan.
        # Ej: _tl0_E controla el tráfico que viene DEL ESTE (y se mueve hacia la izquierda).

        # Semáforo para tráfico aproximándose desde el ESTE (mueve IZQUIERDA).
        # Se coloca al ESTE de la intersección, controlando el carril superior de la carretera horizontal.
        y_pos_east_approach = (h_road_rect.top + road_width * 0.25) - light_housing_size_vertical[1] / 2
        self.traffic_lights.append(TrafficLightClass(
            id=f"{self.zone_id}_tl0_E", 
            x=intersection.right + offset_from_intersection_edge, 
            y=int(y_pos_east_approach), 
            width=light_housing_size_vertical[0], height=light_housing_size_vertical[1], 
            orientation="vertical", cycle_time=base_cycle_time, initial_offset_factor=0.0, 
            **common_tl_params ))
        
        # Semáforo para tráfico aproximándose desde el OESTE (mueve DERECHA).
        # Se coloca al OESTE de la intersección, controlando el carril inferior de la carretera horizontal.
        y_pos_west_approach = (h_road_rect.top + road_width * 0.75) - light_housing_size_vertical[1] / 2
        self.traffic_lights.append(TrafficLightClass(
            id=f"{self.zone_id}_tl0_W", 
            x=intersection.left - light_housing_size_vertical[0] - offset_from_intersection_edge, 
            y=int(y_pos_west_approach), 
            width=light_housing_size_vertical[0], height=light_housing_size_vertical[1], 
            orientation="vertical", cycle_time=base_cycle_time, initial_offset_factor=0.0, 
            **common_tl_params ))

        # Semáforo para tráfico aproximándose desde el NORTE (mueve ABAJO).
        # Se coloca al NORTE de la intersección, controlando el carril derecho de la carretera vertical.
        x_pos_north_approach = (v_road_rect.left + road_width * 0.75) - light_housing_size_horizontal[0] / 2
        self.traffic_lights.append(TrafficLightClass(
            id=f"{self.zone_id}_tl0_N", 
            x=int(x_pos_north_approach), 
            y=intersection.top - light_housing_size_horizontal[1] - offset_from_intersection_edge, 
            width=light_housing_size_horizontal[0], height=light_housing_size_horizontal[1], 
            orientation="horizontal", cycle_time=base_cycle_time, initial_offset_factor=SECOND_PAIR_OFFSET_FACTOR, 
            **common_tl_params ))
        
        # Semáforo para tráfico aproximándose desde el SUR (mueve ARRIBA).
        # Se coloca al SUR de la intersección, controlando el carril izquierdo de la carretera vertical.
        x_pos_south_approach = (v_road_rect.left + road_width * 0.25) - light_housing_size_horizontal[0] / 2
        self.traffic_lights.append(TrafficLightClass(
            id=f"{self.zone_id}_tl0_S", 
            x=int(x_pos_south_approach), 
            y=intersection.bottom + offset_from_intersection_edge, 
            width=light_housing_size_horizontal[0], height=light_housing_size_horizontal[1], 
            orientation="horizontal", cycle_time=base_cycle_time, initial_offset_factor=SECOND_PAIR_OFFSET_FACTOR, 
            **common_tl_params ))
        
        # print(f"[ZoneMap {self.zone_id}] {len(self.traffic_lights)} semáforos colocados.")
        
    async def update(self) -> None:
        """Actualiza el estado de todos los semáforos en esta zona."""
        if self.traffic_lights: # Solo si hay semáforos
            # Usar asyncio.gather para actualizar todos los semáforos concurrentemente.
            await asyncio.gather(*(light.update_async() for light in self.traffic_lights if hasattr(light, 'update_async')))

    def draw(self, surface: pygame.Surface, global_x_offset: int, global_y_offset: int):
        """
        Este método ya no dibuja el mapa base (carreteras, fondo de hierba) porque se asume
        que es una imagen estática manejada por MainGUI.
        La responsabilidad de dibujar los semáforos se delega a ZoneNode.draw_zone_elements,
        que llama directamente a TrafficLight.draw() con los offsets correctos.
        Este método se mantiene por si en el futuro se añaden otros elementos dinámicos
        que deban ser dibujados por ZoneMap en una `zone_surface` intermedia.
        """
        pass # No hay nada que ZoneMap dibuje directamente si el mapa es una imagen estática.

    def get_spawn_points_local(self) -> List[Dict[str, Any]]:
        """
        Calcula y devuelve una lista de puntos de spawn para vehículos en los bordes de la zona.
        Las coordenadas son locales a la zona.
        Returns:
            List[Dict[str, Any]]: Lista de diccionarios, cada uno representando un punto de spawn
                                  con 'x', 'y', 'direction', y 'entry_edge'.
        """
        spawn_points: List[Dict[str, Any]] = []
        if not self.roads or len(self.roads) < 2: # Necesita al menos una carretera H y una V.
            # print(f"ADVERTENCIA [ZoneMap {self.zone_id}]: No hay suficientes carreteras definidas para generar puntos de spawn.")
            return spawn_points # Devuelve lista vacía.
            
        vehicle_buffer: int = 20      # Distancia desde el borde del mapa para el centro del vehículo al spawnear.
        car_approx_length: int = 30   # Longitud aproximada del coche, para evitar que spawnee parcialmente fuera.
        
        # Dimensiones de vehículo por defecto para calcular el centrado en el carril.
        # Estos deberían idealmente coincidir o ser proporcionales a Vehicle.TARGET_DRAW_...
        default_vehicle_width_for_lane_centering_horiz = 15 # "Alto" visual del coche horizontal.
        default_vehicle_width_for_lane_centering_vert = 15  # "Ancho" visual del coche vertical.

        # Ancho de carretera (debe ser consistente con el diseño visual del mapa.PNG).
        road_width_from_map_design: int = 60 
        
        try: # Obtener los rects de las carreteras horizontal y vertical.
            h_road_rect = next(r["rect"] for r in self.roads if r["direction"] == "horizontal")
            v_road_rect = next(r["rect"] for r in self.roads if r["direction"] == "vertical")
        except StopIteration: # Si no se encuentran las carreteras esperadas.
            print(f"ERROR CRÍTICO [ZoneMap {self.zone_id}]: No se pudieron encontrar las carreteras H/V definidas para los puntos de spawn.")
            return []

        # --- Puntos de Spawn para Entradas Horizontales ---
        # Entrada desde el ESTE (vehículo se mueve hacia la IZQUIERDA, usa el carril superior de la carretera H).
        spawn_y_east_entry = h_road_rect.top + (road_width_from_map_design * 0.25) - (default_vehicle_width_for_lane_centering_horiz / 2)
        spawn_points.append({"x": self.width - vehicle_buffer, "y": int(spawn_y_east_entry), 
                             "direction": "left", "entry_edge": "east" })
        # Entrada desde el OESTE (vehículo se mueve hacia la DERECHA, usa el carril inferior de la carretera H).
        spawn_y_west_entry = h_road_rect.top + (road_width_from_map_design * 0.75) - (default_vehicle_width_for_lane_centering_horiz / 2)
        spawn_points.append({"x": vehicle_buffer - car_approx_length, "y": int(spawn_y_west_entry), 
                             "direction": "right", "entry_edge": "west" })

        # --- Puntos de Spawn para Entradas Verticales ---
        # Entrada desde el SUR (vehículo se mueve HACIA ARRIBA, usa el carril izquierdo de la carretera V, desde la perspectiva del mapa).
        spawn_x_south_entry = v_road_rect.left + (road_width_from_map_design * 0.25) - (default_vehicle_width_for_lane_centering_vert / 2)
        spawn_points.append({"x": int(spawn_x_south_entry), "y": self.height - vehicle_buffer,
                             "direction": "up", "entry_edge": "south" })
        # Entrada desde el NORTE (vehículo se mueve HACIA ABAJO, usa el carril derecho de la carretera V).
        spawn_x_north_entry = v_road_rect.left + (road_width_from_map_design * 0.75) - (default_vehicle_width_for_lane_centering_vert / 2)
        spawn_points.append({"x": int(spawn_x_north_entry), "y": vehicle_buffer - car_approx_length, 
                             "direction": "down", "entry_edge": "north" })
        
        return spawn_points

    def get_traffic_lights_local(self) -> List['TrafficLight']: 
        """Devuelve la lista de instancias de TrafficLight en esta zona."""
        return self.traffic_lights

    def get_dimensions(self) -> Tuple[int, int]: 
        """Devuelve el ancho y alto de esta zona."""
        return (self.width, self.height)
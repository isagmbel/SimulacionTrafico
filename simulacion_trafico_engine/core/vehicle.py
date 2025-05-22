# simulacion_trafico_engine/core/vehicle.py
import pygame
import uuid
import asyncio
from typing import Tuple, List, Dict, Optional, TYPE_CHECKING, Any

# Importar Theme para acceder a rutas de assets y colores de fallback.
from simulacion_trafico_engine.ui.theme import Theme 

if TYPE_CHECKING:
    # Para type hinting sin causar importaciones circulares.
    from simulacion_trafico_engine.core.traffic_light import TrafficLight
    from simulacion_trafico_engine.core.zone_map import ZoneMap 
    from simulacion_trafico_engine.distribution.rabbitclient import RabbitMQClient
    from simulacion_trafico_engine.performance.metrics import TrafficMetrics

class Vehicle:
    """
    Representa un vehículo en la simulación de tráfico.
    Gestiona su estado (posición, velocidad, dirección), su representación visual
    (usando assets gráficos), y su interacción con semáforos y otros vehículos.
    Puede publicar su estado vía RabbitMQ y registrar métricas.
    """

    # --- Dimensiones Objetivo para el Renderizado de Assets ---
    # Estos valores definen a qué tamaño se escalarán los assets PNG de los vehículos.
    # Deben ajustarse para que los vehículos se vean del tamaño adecuado en el mapa.
    TARGET_DRAW_WIDTH_HORIZ: int = 40  # Ancho deseado en pantalla para vehículos horizontales.
    TARGET_DRAW_HEIGHT_HORIZ: int = 20 # Alto deseado en pantalla para vehículos horizontales.
    
    TARGET_DRAW_WIDTH_VERT: int = 20   # Ancho deseado en pantalla para vehículos verticales.
    TARGET_DRAW_HEIGHT_VERT: int = 40  # Alto deseado en pantalla para vehículos verticales.

    def __init__(self, id: str,
                 global_x: float, global_y: float,
                 width: int = 0, # Ya no se usa directamente para el tamaño de dibujo con assets.
                 height: int = 0, # Podría usarse para tipos de vehículos con diferentes tamaños base.
                 color: Optional[Tuple[int, int, int]] = None, # No usado para dibujar si se usan imágenes.
                 speed: float = 2.0,
                 original_speed: Optional[float] = None,
                 direction: str = "right",
                 current_zone_id: str = "unknown",
                 rabbit_client: Optional['RabbitMQClient'] = None,
                 metrics_client: Optional['TrafficMetrics'] = None,
                 map_ref: Optional['ZoneMap'] = None):
        """
        Inicializa un nuevo vehículo.
        Args:
            id (str): Identificador único del vehículo.
            global_x (float): Coordenada X global inicial del vehículo.
            global_y (float): Coordenada Y global inicial del vehículo.
            width (int, optional): Ancho lógico (no necesariamente visual con assets).
            height (int, optional): Alto lógico.
            color (Optional[Tuple[int, int, int]], optional): No usado directamente para dibujar con assets.
            speed (float, optional): Velocidad inicial del vehículo en píxeles por tick.
            original_speed (Optional[float], optional): Velocidad base del vehículo para cuando retoma movimiento.
            direction (str, optional): Dirección inicial ("left", "right", "up", "down").
            current_zone_id (str, optional): ID de la zona actual del vehículo.
            rabbit_client (Optional['RabbitMQClient'], optional): Cliente RabbitMQ para publicar estado.
            metrics_client (Optional['TrafficMetrics'], optional): Cliente para registrar métricas.
            map_ref (Optional['ZoneMap'], optional): Referencia al objeto ZoneMap de su zona.
        """
        self.id: str = id
        self.global_x: float = global_x
        self.global_y: float = global_y
        
        self.direction: str = direction 
        # Cargar el asset gráfico del vehículo según su dirección inicial.
        self.image_path: str = Theme.get_vehicle_image_path(self.direction)
        try:
            self.raw_unscaled_image: pygame.Surface = pygame.image.load(self.image_path).convert_alpha()
        except pygame.error as e:
            print(f"CRÍTICO: Error cargando imagen de vehículo '{self.image_path}': {e}")
            # Fallback a un Surface simple si la imagen no carga.
            is_horiz_fallback = self.direction in ["left", "right"]
            fb_w = Vehicle.TARGET_DRAW_WIDTH_HORIZ if is_horiz_fallback else Vehicle.TARGET_DRAW_WIDTH_VERT
            fb_h = Vehicle.TARGET_DRAW_HEIGHT_HORIZ if is_horiz_fallback else Vehicle.TARGET_DRAW_HEIGHT_VERT
            self.raw_unscaled_image = pygame.Surface((fb_w, fb_h), pygame.SRCALPHA)
            self.raw_unscaled_image.fill(Theme.get_vehicle_color()) # Usar un color de fallback.

        # --- Configuración de Movimiento y Estado ---
        self.original_speed: float = original_speed if original_speed is not None else speed
        self.speed: float = speed
        self.stopped: bool = False
        self.current_zone_id: str = current_zone_id

        # --- Referencias a Otros Componentes ---
        self.rabbit_client: Optional['RabbitMQClient'] = rabbit_client
        self.metrics_client: Optional['TrafficMetrics'] = metrics_client
        self.map_ref: Optional['ZoneMap'] = map_ref # Referencia al mapa de la zona actual.

        # --- Preparación de la Imagen Visual del Vehículo (Escalado y Orientación) ---
        self.image: Optional[pygame.Surface] = None # La imagen final a dibujar.
        
        # Determinar dimensiones objetivo y aplicar transformaciones según la dirección.
        if self.direction in ["left", "right"]: # Vehículo horizontal
            self.draw_width: int = Vehicle.TARGET_DRAW_WIDTH_HORIZ
            self.draw_height: int = Vehicle.TARGET_DRAW_HEIGHT_HORIZ
            # Escalar la imagen cruda a las dimensiones objetivo horizontales.
            scaled_image_temp = pygame.transform.smoothscale(
                self.raw_unscaled_image, (self.draw_width, self.draw_height))
            # Asumir que los assets horizontales miran a la DERECHA por defecto.
            if self.direction == "left":
                self.image = pygame.transform.flip(scaled_image_temp, True, False) # Espejar.
            else: # "right"
                self.image = scaled_image_temp # Usar como está.
        
        elif self.direction in ["up", "down"]: # Vehículo vertical
            self.draw_width: int = Vehicle.TARGET_DRAW_WIDTH_VERT
            self.draw_height: int = Vehicle.TARGET_DRAW_HEIGHT_VERT
            # Escalar la imagen cruda a las dimensiones objetivo verticales.
            scaled_image_temp = pygame.transform.smoothscale(
                self.raw_unscaled_image, (self.draw_width, self.draw_height))
            # ASUNCIÓN: Assets verticales están orientados HACIA ABAJO por defecto.
            if self.direction == "up":
                self.image = pygame.transform.flip(scaled_image_temp, False, True) # Espejar verticalmente.
            else: # "down"
                self.image = scaled_image_temp # Usar como está.
        
        if self.image is None: # Fallback si la dirección no es válida
            print(f"ADVERTENCIA: Vehículo {self.id} - dirección inválida '{self.direction}'. Usando imagen por defecto.")
            self.draw_width = Vehicle.TARGET_DRAW_WIDTH_HORIZ
            self.draw_height = Vehicle.TARGET_DRAW_HEIGHT_HORIZ
            self.image = pygame.transform.smoothscale(self.raw_unscaled_image, (self.draw_width, self.draw_height))

        # Dimensiones finales del asset visual (útil para colisiones y referencia).
        self.asset_width: int = self.image.get_width()
        self.asset_height: int = self.image.get_height()
        # Asegurar que draw_width y draw_height reflejen las dimensiones de la imagen final.
        self.draw_width = self.asset_width 
        self.draw_height = self.asset_height
        
        # Rectángulo local del vehículo (usado para colisiones dentro de la zona).
        # Sus coordenadas (topleft) se actualizan en `update_in_zone`.
        self.rect: pygame.Rect = pygame.Rect(0, 0, self.draw_width, self.draw_height) 
        self.is_despawned_globally: bool = False # Si el vehículo ha salido del mapa.

        if self.metrics_client: # Registrar spawn en métricas.
            self.metrics_client.vehicle_spawned(self.id)

    def get_global_rect(self) -> pygame.Rect:
        """Devuelve el pygame.Rect del vehículo en coordenadas globales."""
        return pygame.Rect(int(self.global_x), int(self.global_y), self.draw_width, self.draw_height)

    async def publish_state(self, event_type: str = "update", extra_data: Optional[Dict[str, Any]] = None) -> None:
        """Publica el estado actual del vehículo a RabbitMQ."""
        if not (self.rabbit_client and hasattr(self.rabbit_client, 'async_exchange') and self.rabbit_client.async_exchange):
            return # No publicar si no hay cliente RabbitMQ o exchange configurado.
        
        message = {
            "vehicle_id": self.id, "event_type": event_type, "zone_id": self.current_zone_id,
            "position": {"x": self.global_x, "y": self.global_y},
            "speed_px_frame": self.speed, "direction": self.direction,
            "stopped": self.stopped, "timestamp": asyncio.get_event_loop().time(),
            "image_path": self.image_path # Incluir ruta de imagen para posible recreación/depuración.
        }
        if extra_data: message.update(extra_data) # Añadir datos extra si los hay.
        
        # Determinar routing key base según el tipo de evento.
        routing_key_base = f"city.vehicle.{self.id}"
        if event_type == "migration_request": routing_key_base = f"city.migration.request" 
        elif event_type == "despawned_global": routing_key_base = f"city.vehicle.despawned" 
        final_routing_key = f"{routing_key_base}.{event_type}"
        
        try:
            await self.rabbit_client.publish_async(final_routing_key, message)
        except Exception as e: 
            print(f"[Vehículo {self.id}] Error publicando estado '{event_type}' vía RabbitMQ: {e}")

    async def update_in_zone(self, 
                             zone_traffic_lights: List['TrafficLight'],
                             zone_vehicles: List['Vehicle'],
                             zone_width: int, zone_height: int,
                             zone_global_offset_x: int, zone_global_offset_y: int):
        """
        Actualiza el estado del vehículo para un tick de simulación dentro de su zona actual.
        Maneja movimiento, interacción con semáforos y evasión de colisiones.
        Args:
            zone_traffic_lights: Lista de semáforos en la zona actual.
            zone_vehicles: Lista de otros vehículos en la zona actual.
            zone_width: Ancho de la zona actual.
            zone_height: Alto de la zona actual.
            zone_global_offset_x: Coordenada X global de la esquina superior izquierda de la zona.
            zone_global_offset_y: Coordenada Y global de la esquina superior izquierda de la zona.
        """
        if self.is_despawned_globally: return # No actualizar si ya ha salido del mapa.

        # Guardar estado anterior para comparaciones y posible reversión.
        old_global_x, old_global_y = self.global_x, self.global_y
        old_speed, old_stopped = self.speed, self.stopped
        
        # Calcular coordenadas locales y actualizar el `self.rect` local.
        local_x = self.global_x - zone_global_offset_x
        local_y = self.global_y - zone_global_offset_y
        self.rect.topleft = (int(local_x), int(local_y)) 
        self.rect.width = self.draw_width # Asegurar que el rect tenga el tamaño del asset.
        self.rect.height = self.draw_height
        old_local_x, old_local_y = local_x, local_y # Guardar posición local anterior.

        # --- Lógica de Estado: Detenido o en Movimiento ---
        if self.stopped: # Si el vehículo estaba detenido en el tick anterior.
            # Comprobar si la condición de parada (ej. semáforo rojo) sigue activa.
            action_at_light = self._check_action_at_light_local(zone_traffic_lights, local_x, local_y)
            if action_at_light == "proceed": 
                self.resume() # Cambiar estado a no detenido y restaurar velocidad.
            else: # Sigue detenido.
                if self.metrics_client: self.metrics_client.accumulate_vehicle_speed(self.speed) # Acumular velocidad 0.
                return # No hay más que hacer si sigue detenido.
        
        # --- Lógica de Movimiento ---
        current_speed = self.speed # Usar velocidad actual (puede ser 0 si acaba de parar).
        if self.direction == "right": self.global_x += current_speed
        elif self.direction == "left": self.global_x -= current_speed
        elif self.direction == "up": self.global_y -= current_speed
        elif self.direction == "down": self.global_y += current_speed
        
        # Actualizar `self.rect` local con la nueva posición global.
        local_x = self.global_x - zone_global_offset_x
        local_y = self.global_y - zone_global_offset_y
        self.rect.topleft = (int(local_x), int(local_y))
        self.rect.width = self.draw_width; self.rect.height = self.draw_height # Reafirmar tamaño.

        # --- Lógica de Interacción con Semáforos (después de mover) ---
        light_action = self._check_action_at_light_local(zone_traffic_lights, local_x, local_y)
        if light_action == "stop":
            # Si debe parar, revertir el movimiento y actualizar estado.
            self.global_x, self.global_y = old_global_x, old_global_y
            self.rect.topleft = (int(old_local_x), int(old_local_y)) 
            self.rect.width = self.draw_width; self.rect.height = self.draw_height 
            self.stop(reason="traffic_light")
            if self.speed != old_speed or self.stopped != old_stopped: # Publicar si el estado cambió.
                await self.publish_state("stopped_at_light")
            if self.metrics_client: self.metrics_client.accumulate_vehicle_speed(self.speed)
            return # Terminar actualización para este tick.
        
        # --- Lógica de Evasión de Colisiones (Simplificada) ---
        # Comprobar colisiones con otros vehículos en la misma zona.
        safe_dist_factor = 0.2 # Factor de distancia segura (multiplicador del tamaño del coche).
        for other_veh in zone_vehicles:
            if other_veh.id == self.id or other_veh.is_despawned_globally: continue # Ignorar a sí mismo y vehículos despawneados.
            
            # Usar `self.rect` y `other_veh.rect` (ambos en coordenadas locales de la zona).
            if self.rect.colliderect(other_veh.rect):
                is_front_collision = False # Asumir que no es colisión frontal inicialmente.
                # Lógica para determinar si la colisión es con un vehículo directamente en frente.
                # Esto considera la dirección y un área de "mirada hacia adelante".
                if self.direction=="right" and other_veh.rect.left > self.rect.centerx and \
                   other_veh.rect.left < self.rect.right + self.draw_width*safe_dist_factor and \
                   abs(self.rect.centery - other_veh.rect.centery) < (self.draw_height+other_veh.draw_height)/2*0.9: 
                    is_front_collision=True 
                elif self.direction=="left" and other_veh.rect.right < self.rect.centerx and \
                     other_veh.rect.right > self.rect.left - self.draw_width*safe_dist_factor and \
                     abs(self.rect.centery - other_veh.rect.centery) < (self.draw_height+other_veh.draw_height)/2*0.9: 
                    is_front_collision=True
                elif self.direction=="down" and other_veh.rect.top > self.rect.centery and \
                     other_veh.rect.top < self.rect.bottom + self.draw_height*safe_dist_factor and \
                     abs(self.rect.centerx - other_veh.rect.centerx) < (self.draw_width+other_veh.draw_width)/2*0.9: 
                    is_front_collision=True
                elif self.direction=="up" and other_veh.rect.bottom < self.rect.centery and \
                     other_veh.rect.bottom > self.rect.top - self.draw_height*safe_dist_factor and \
                     abs(self.rect.centerx - other_veh.rect.centerx) < (self.draw_width+other_veh.draw_width)/2*0.9: 
                    is_front_collision=True
                
                if is_front_collision: # Si es una colisión frontal inminente.
                    # Revertir movimiento y detener el vehículo.
                    self.global_x, self.global_y = old_global_x, old_global_y
                    self.rect.topleft = (int(old_local_x), int(old_local_y))
                    self.rect.width = self.draw_width; self.rect.height = self.draw_height 
                    self.stop(reason="collision_avoidance")
                    if self.speed!=old_speed or self.stopped!=old_stopped: # Publicar si el estado cambió.
                        await self.publish_state("stopped_avoidance")
                    if self.metrics_client: self.metrics_client.accumulate_vehicle_speed(self.speed)
                    return # Terminar actualización.
        
        # --- Ajustes Finales de Estado y Velocidad ---
        if old_stopped and not self.stopped: pass # Ya manejado por resume().
        elif self.stopped: pass # Si sigue detenido por alguna razón.
        
        # Si no está detenido pero su velocidad es 0 (ej. justo después de resume() pero antes de moverse),
        # asegurar que recupere su velocidad original.
        if not self.stopped and self.speed == 0.0: 
            self.resume_speed()

        # --- Publicar Estado si Hubo Cambios ---
        if self.global_x != old_global_x or self.global_y != old_global_y or \
           self.speed != old_speed or self.stopped != old_stopped:
            await self.publish_state("updated") # Publicar estado general de actualización.
        
        if self.metrics_client: # Acumular velocidad para cálculo de promedio.
            self.metrics_client.accumulate_vehicle_speed(self.speed)

    def _get_relevant_light_local(self, zone_traffic_lights: List['TrafficLight'], 
                                  current_local_x: float, current_local_y: float) -> Optional['TrafficLight']:
        """
        Encuentra el semáforo más relevante para este vehículo en su posición local actual.
        Considera la dirección del vehículo, la orientación del semáforo, si está en frente,
        y si está dentro de una distancia de "mirada" (lookahead).
        Args:
            zone_traffic_lights: Lista de todos los semáforos en la zona.
            current_local_x: Coordenada X local actual del vehículo. (No se usa directamente, se usa self.rect)
            current_local_y: Coordenada Y local actual del vehículo. (No se usa directamente, se usa self.rect)
        Returns:
            Optional[TrafficLight]: El semáforo relevante, o None si no hay ninguno.
        """
        min_dist = float('inf')
        relevant_light: Optional[TrafficLight] = None
        # `self.draw_width` aquí es la longitud del vehículo en su dirección de movimiento.
        lookahead_distance = (self.original_speed * 20) + self.draw_width 
        
        vehicle_local_rect = self.rect # `self.rect` ya está en coordenadas locales y con tamaño correcto.
        alignment_tolerance_factor = 0.6 # Factor para la precisión de la alineación con el semáforo.

        for light in zone_traffic_lights: 
            # Comprobar si la orientación del semáforo es pertinente para la dirección del vehículo.
            correct_orientation = (self.direction in ["right", "left"] and light.orientation == "vertical") or \
                                  (self.direction in ["up", "down"] and light.orientation == "horizontal")
            if not correct_orientation: continue # Ignorar semáforos con orientación no relevante.

            is_ahead_and_aligned = False
            distance_to_light_edge = float('inf') 
            
            # Comprobar si el semáforo está en frente y alineado con el carril del vehículo.
            if self.direction == "right": 
                if light.rect.left >= vehicle_local_rect.right and \
                   abs(light.rect.centery - vehicle_local_rect.centery) < (light.rect.height * alignment_tolerance_factor): 
                    is_ahead_and_aligned = True
                    distance_to_light_edge = light.rect.left - vehicle_local_rect.right
            elif self.direction == "left": 
                if light.rect.right <= vehicle_local_rect.left and \
                   abs(light.rect.centery - vehicle_local_rect.centery) < (light.rect.height * alignment_tolerance_factor):
                    is_ahead_and_aligned = True
                    distance_to_light_edge = vehicle_local_rect.left - light.rect.right
            elif self.direction == "down": 
                if light.rect.top >= vehicle_local_rect.bottom and \
                   abs(light.rect.centerx - vehicle_local_rect.centerx) < (light.rect.width * alignment_tolerance_factor):
                    is_ahead_and_aligned = True
                    distance_to_light_edge = light.rect.top - vehicle_local_rect.bottom
            elif self.direction == "up": 
                if light.rect.bottom <= vehicle_local_rect.top and \
                   abs(light.rect.centerx - vehicle_local_rect.centerx) < (light.rect.width * alignment_tolerance_factor):
                    is_ahead_and_aligned = True
                    distance_to_light_edge = vehicle_local_rect.top - light.rect.bottom
            
            # Si está en frente, alineado, dentro de la distancia de mirada, y es el más cercano hasta ahora.
            if is_ahead_and_aligned and 0 <= distance_to_light_edge < lookahead_distance:
                if distance_to_light_edge < min_dist:
                    min_dist = distance_to_light_edge
                    relevant_light = light
        return relevant_light

    def _check_action_at_light_local(self, zone_traffic_lights: List['TrafficLight'], 
                                     current_local_x: float, current_local_y: float) -> str:
        """
        Determina la acción a tomar (parar o proceder) basado en el semáforo relevante.
        Args:
            zone_traffic_lights: Lista de semáforos en la zona.
            current_local_x: Coordenada X local actual del vehículo.
            current_local_y: Coordenada Y local actual del vehículo.
        Returns:
            str: "stop" si el vehículo debe detenerse, "proceed" en caso contrario.
        """
        relevant_light = self._get_relevant_light_local(zone_traffic_lights, current_local_x, current_local_y)
        if not relevant_light: return "proceed" # No hay semáforo relevante, proceder.

        # Calcular distancia al borde del semáforo donde el vehículo debería parar.
        dist_to_light_edge = float('inf')
        if self.direction == "right": dist_to_light_edge = relevant_light.rect.left - self.rect.right 
        elif self.direction == "left": dist_to_light_edge = self.rect.left - relevant_light.rect.right
        elif self.direction == "down": dist_to_light_edge = relevant_light.rect.top - self.rect.bottom
        elif self.direction == "up": dist_to_light_edge = self.rect.top - relevant_light.rect.bottom
        
        # Umbrales para la decisión de parar.
        # `self.draw_width` aquí representa la longitud del vehículo en su dirección de movimiento.
        stopping_decision_threshold = self.original_speed * 2.5 + self.draw_width * 0.3 
        # Límite para considerar si ya se pasó la línea de detención (permite que la nariz esté un poco encima).
        stop_past_line_threshold = -self.draw_width * 0.5 

        # Si está dentro de la distancia de decisión y no ha pasado demasiado la línea.
        if dist_to_light_edge < stopping_decision_threshold and dist_to_light_edge > stop_past_line_threshold :
            if relevant_light.state == "red":
                return "stop"
            elif relevant_light.state == "yellow":
                # Para amarillo, parar si no está demasiado cerca o ya habiendo pasado la línea.
                yellow_stop_threshold = self.original_speed * 1.5 + self.draw_width * 0.1 
                if dist_to_light_edge < yellow_stop_threshold and dist_to_light_edge > stop_past_line_threshold:
                     return "stop" 
        return "proceed" # Si ninguna condición de parada se cumple.

    def stop(self, reason: str = "unknown") -> None:
        """Detiene el vehículo (establece `stopped` a True y velocidad a 0)."""
        if not self.stopped: # Solo actuar si no estaba ya detenido.
            self.stopped = True
            self.speed = 0.0
            if self.metrics_client: self.metrics_client.vehicle_started_waiting(self.id)

    def resume(self) -> None:
        """Reanuda el movimiento del vehículo (establece `stopped` a False y restaura velocidad)."""
        if self.stopped: # Solo actuar si estaba detenido.
            self.stopped = False
            self.resume_speed() # Restaura la velocidad original.
            if self.metrics_client: self.metrics_client.vehicle_stopped_waiting(self.id)

    def resume_speed(self) -> None: 
        """Restaura la velocidad del vehículo a su velocidad original."""
        self.speed = self.original_speed

    def draw(self, surface: pygame.Surface):
        """Dibuja el vehículo (su asset gráfico) en la superficie dada."""
        if self.is_despawned_globally or self.image is None: 
            return # No dibujar si está despawneado o no tiene imagen.
        
        # `self.image` ya está escalada y orientada correctamente.
        # Se dibuja en las coordenadas globales del vehículo.
        surface.blit(self.image, (int(self.global_x), int(self.global_y)))
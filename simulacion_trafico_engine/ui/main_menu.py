# simulacion_trafico_engine/ui/main_menu.py
import pygame
from .theme import Theme # Para acceder a las rutas de assets y, potencialmente, fuentes/colores del menú

class MainMenu:
    """
    Gestiona la lógica y el renderizado del menú principal del juego.
    Permite iniciar la simulación o salir del juego.
    """

    # --- Constantes de Acción ---
    ACTION_NONE = 0        # No se ha realizado ninguna acción significativa
    ACTION_START_SIM = 1   # El usuario ha elegido iniciar la simulación
    ACTION_QUIT = 2        # El usuario ha elegido salir del juego (ej. con ESC)

    def __init__(self, screen_width: int, screen_height: int):
        """
        Inicializa el menú principal.
        Args:
            screen_width (int): Ancho de la pantalla donde se dibujará el menú.
            screen_height (int): Alto de la pantalla donde se dibujará el menú.
        """
        self.screen_width = screen_width
        self.screen_height = screen_height

        # --- Carga de Assets Gráficos del Menú ---
        self._load_assets()

        # --- Configuración de la Animación de Hover para el Texto ---
        # Factor de escala para el texto cuando el ratón está encima
        self.hover_scale_factor_target = 1.08 
        # Escala actual del texto, usada para la animación suave
        self.current_hover_scale = 1.0       
        # Velocidad de la animación (0.0 a 1.0; valores más pequeños son más lentos/suaves)
        self.animation_speed = 0.07        
        self.is_hovering = False # Estado actual del hover sobre el texto

    def _load_assets(self):
        """Carga y prepara las imágenes necesarias para el menú."""
        # Cargar y escalar imagen de fondo del menú
        try:
            raw_bg_image = pygame.image.load(Theme.MAIN_MENU_BG_PATH).convert()
            self.scaled_background_image = pygame.transform.scale(
                raw_bg_image, (self.screen_width, self.screen_height)
            )
        except pygame.error as e:
            print(f"ERROR: Cargando imagen de fondo del menú '{Theme.MAIN_MENU_BG_PATH}': {e}")
            self.scaled_background_image = pygame.Surface((self.screen_width, self.screen_height))
            self.scaled_background_image.fill(Theme.COLOR_BACKGROUND) # Fallback a color sólido

        # Cargar imagen del texto del menú (ej. "RUSH HOUR")
        try:
            self.text_image_original_unscaled = pygame.image.load(Theme.MAIN_MENU_TEXT_PATH).convert_alpha()
        except pygame.error as e:
            print(f"ERROR: Cargando imagen de texto del menú '{Theme.MAIN_MENU_TEXT_PATH}': {e}")
            # Fallback a texto renderizado por Pygame si la imagen no carga
            fallback_font = Theme.get_font(100) # Usar un tamaño grande para el título de fallback
            self.text_image_original_unscaled = fallback_font.render("RUSH HOUR", True, Theme.COLOR_TEXT_ON_DARK)
            # Asegurar canal alfa para convert_alpha() si es necesario
            if not self.text_image_original_unscaled.get_alpha():
                 self.text_image_original_unscaled = self.text_image_original_unscaled.convert_alpha()
        
        self._calculate_text_layout()

    def _calculate_text_layout(self):
        """Calcula el tamaño y posición del texto del menú en la pantalla."""
        original_text_w, original_text_h = self.text_image_original_unscaled.get_size()

        # Definir el ancho deseado del texto como un porcentaje del ancho de la pantalla
        desired_text_screen_width_ratio = 0.85 
        target_text_width = int(self.screen_width * desired_text_screen_width_ratio)

        # Calcular el alto manteniendo la relación de aspecto
        if original_text_w == 0: # Evitar división por cero
            aspect_ratio = 1 # O alguna proporción por defecto
            target_text_height = int(target_text_width * aspect_ratio) # Podría ser problemático si original_text_w es 0
            print("ADVERTENCIA: Ancho de imagen de texto original es 0. Usando aspect ratio 1.")
        else:
            aspect_ratio = original_text_h / original_text_w
            target_text_height = int(target_text_width * aspect_ratio)

        # Escalar la imagen original (sin escalar) del texto a este nuevo tamaño objetivo
        # Esta será la imagen del texto "en reposo" (sin hover)
        self.text_image_at_rest = pygame.transform.smoothscale(
            self.text_image_original_unscaled, (target_text_width, target_text_height)
        )

        # Rect para la imagen de texto en reposo, usado para posicionamiento y detección de colisiones
        # Se centra en la pantalla. Ajusta el offset vertical si es necesario.
        self.text_image_rect_at_rest = self.text_image_at_rest.get_rect(
            center=(self.screen_width // 2, self.screen_height // 2) 
        )

    def handle_event(self, event: pygame.event.Event, mouse_pos: tuple) -> int:
        """
        Maneja un evento de Pygame para el menú principal.
        Determina si el ratón está sobre el área interactiva y procesa clicks o teclas.
        Args:
            event: El evento de Pygame a procesar.
            mouse_pos: La posición actual del ratón (x, y).
        Returns:
            int: Un código de acción (ACTION_START_SIM, ACTION_QUIT, o ACTION_NONE).
        """
        action = MainMenu.ACTION_NONE
        
        # Actualizar el estado de hover basado en la posición del ratón
        if self.text_image_rect_at_rest.collidepoint(mouse_pos):
            self.is_hovering = True
        else:
            self.is_hovering = False

        # Procesar eventos de teclado
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                action = MainMenu.ACTION_QUIT
            # Iniciar simulación con Enter o Espacio si el ratón está sobre el texto interactivo
            elif (event.key == pygame.K_RETURN or event.key == pygame.K_SPACE) and self.is_hovering:
                action = MainMenu.ACTION_START_SIM
                
        # Procesar eventos de click del ratón
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1: # Botón izquierdo del ratón
                if self.is_hovering: # Si se hizo click mientras el ratón estaba sobre el texto
                    action = MainMenu.ACTION_START_SIM
        return action

    def update_animation(self):
        """Actualiza la escala actual del texto para una animación de hover suave."""
        target_scale = self.hover_scale_factor_target if self.is_hovering else 1.0
        
        # Interpolar suavemente la escala actual hacia la escala objetivo
        self.current_hover_scale += (target_scale - self.current_hover_scale) * self.animation_speed
        
        # Si la escala actual está muy cerca de la objetivo, ajústala directamente para evitar oscilaciones mínimas
        if abs(target_scale - self.current_hover_scale) < 0.001:
            self.current_hover_scale = target_scale

    def draw(self, surface: pygame.Surface):
        """Dibuja el menú principal en la superficie dada."""
        # Actualizar el estado de la animación de hover antes de dibujar
        self.update_animation() 

        # 1. Dibujar la imagen de fondo escalada del menú
        surface.blit(self.scaled_background_image, (0, 0))

        # 2. Preparar y dibujar la imagen del texto con la escala de animación actual
        current_text_image_to_draw: pygame.Surface
        current_text_rect: pygame.Rect

        # Si la escala es prácticamente 1.0 (sin hover o animación completada), usar la imagen en reposo
        if abs(self.current_hover_scale - 1.0) < 0.001:
            current_text_image_to_draw = self.text_image_at_rest
            current_text_rect = self.text_image_rect_at_rest
        else:
            # Calcular nuevas dimensiones basadas en la escala de hover actual
            scaled_width = int(self.text_image_at_rest.get_width() * self.current_hover_scale)
            scaled_height = int(self.text_image_at_rest.get_height() * self.current_hover_scale)
            
            # Asegurarse de que los tamaños no sean cero o negativos para evitar error en smoothscale
            if scaled_width <= 0 or scaled_height <= 0:
                current_text_image_to_draw = self.text_image_at_rest
                current_text_rect = self.text_image_rect_at_rest
            else:
                try:
                    # Escalar la imagen base ("en reposo") a las dimensiones animadas
                    current_text_image_to_draw = pygame.transform.smoothscale(
                        self.text_image_at_rest, (scaled_width, scaled_height)
                    )
                    # Recalcular el rect para que la imagen escalada permanezca centrada
                    current_text_rect = current_text_image_to_draw.get_rect(
                        center=self.text_image_rect_at_rest.center
                    )
                except ValueError: 
                    # Fallback si smoothscale falla (ej. por tamaño 0 temporal durante animación rápida)
                    current_text_image_to_draw = self.text_image_at_rest
                    current_text_rect = self.text_image_rect_at_rest.copy() # Usar una copia
        
        # Dibujar la imagen de texto (normal o animada)
        surface.blit(current_text_image_to_draw, current_text_rect.topleft)
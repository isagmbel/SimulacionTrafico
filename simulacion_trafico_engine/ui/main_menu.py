# simulacion_trafico_engine/ui/main_menu.py
import pygame
from .theme import Theme

class MainMenu:
    ACTION_NONE = 0
    ACTION_START_SIM = 1
    ACTION_QUIT = 2 

    def __init__(self, screen_width: int, screen_height: int):
        self.screen_width = screen_width
        self.screen_height = screen_height

        # Cargar imagen de fondo del menú
        try:
            raw_bg_image = pygame.image.load(Theme.MAIN_MENU_BG_PATH).convert()
            self.scaled_background_image = pygame.transform.scale(
                raw_bg_image, (self.screen_width, self.screen_height)
            )
        except pygame.error as e:
            print(f"Error loading main menu BG image '{Theme.MAIN_MENU_BG_PATH}': {e}")
            self.scaled_background_image = pygame.Surface((self.screen_width, self.screen_height))
            self.scaled_background_image.fill((30, 30, 50)) 

        # Cargar imagen del texto del menú
        try:
            self.text_image_original_unscaled = pygame.image.load(Theme.MAIN_MENU_TEXT_PATH).convert_alpha()
        except pygame.error as e:
            print(f"Error loading main menu TEXT image '{Theme.MAIN_MENU_TEXT_PATH}': {e}")
            fallback_font = pygame.font.SysFont(None, 120) # Usar una fuente más grande para el fallback
            self.text_image_original_unscaled = fallback_font.render("RUSH HOUR", True, (220,220,220))
            if not self.text_image_original_unscaled.get_alpha(): # Asegurar que tiene canal alfa
                 self.text_image_original_unscaled = self.text_image_original_unscaled.convert_alpha()

        # --- Escalar y Posicionar la imagen del texto (RushHourText.PNG) ---
        original_text_w, original_text_h = self.text_image_original_unscaled.get_size()

        desired_text_screen_width_ratio = 0.85 
        target_text_width = int(self.screen_width * desired_text_screen_width_ratio)

        if original_text_w == 0: # Evitar división por cero si la imagen no cargó bien
            aspect_ratio = 1 
        else:
            aspect_ratio = original_text_h / original_text_w
        target_text_height = int(target_text_width * aspect_ratio)

        self.text_image_at_rest = pygame.transform.smoothscale(
            self.text_image_original_unscaled, (target_text_width, target_text_height)
        )

        self.text_image_rect_at_rest = self.text_image_at_rest.get_rect(
            center=(self.screen_width // 2, self.screen_height // 2) 
        )
        
        # Para la animación de hover
        self.hover_scale_factor_target = 1.08 
        self.current_hover_scale = 1.0       
        self.animation_speed = 0.07 # Ajusta para más/menos suavidad (0.05 a 0.2 son buenos rangos)
        self.is_hovering = False

    def handle_event(self, event: pygame.event.Event, mouse_pos: tuple) -> int:
        action = MainMenu.ACTION_NONE
        
        if self.text_image_rect_at_rest.collidepoint(mouse_pos):
            self.is_hovering = True
        else:
            self.is_hovering = False

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                action = MainMenu.ACTION_QUIT
            elif (event.key == pygame.K_RETURN or event.key == pygame.K_SPACE) and self.is_hovering:
                action = MainMenu.ACTION_START_SIM
                
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1: 
                if self.is_hovering:
                    action = MainMenu.ACTION_START_SIM
        return action

    def update_animation(self):
        target_scale = self.hover_scale_factor_target if self.is_hovering else 1.0
        
        self.current_hover_scale += (target_scale - self.current_hover_scale) * self.animation_speed
        
        if abs(target_scale - self.current_hover_scale) < 0.001:
            self.current_hover_scale = target_scale

    def draw(self, surface: pygame.Surface):
        self.update_animation() 

        surface.blit(self.scaled_background_image, (0, 0))

        if abs(self.current_hover_scale - 1.0) < 0.001: # Si está prácticamente en escala 1.0
            current_text_image_to_draw = self.text_image_at_rest
            current_text_rect = self.text_image_rect_at_rest
        else:
            scaled_width = int(self.text_image_at_rest.get_width() * self.current_hover_scale)
            scaled_height = int(self.text_image_at_rest.get_height() * self.current_hover_scale)
            
            # Asegurarse de que los tamaños no sean cero, lo que causaría error en smoothscale
            if scaled_width <= 0 or scaled_height <= 0:
                current_text_image_to_draw = self.text_image_at_rest
                current_text_rect = self.text_image_rect_at_rest
            else:
                try:
                    current_text_image_to_draw = pygame.transform.smoothscale(
                        self.text_image_at_rest, (scaled_width, scaled_height)
                    )
                    current_text_rect = current_text_image_to_draw.get_rect(
                        center=self.text_image_rect_at_rest.center
                    )
                except ValueError: 
                    current_text_image_to_draw = self.text_image_at_rest
                    current_text_rect = self.text_image_rect_at_rest.copy()
        
        surface.blit(current_text_image_to_draw, current_text_rect.topleft)
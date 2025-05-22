# simulacion_trafico_engine/ui/main_menu.py
import pygame
from .theme import Theme, draw_rounded_rect 

class MainMenu:
    ACTION_NONE = 0
    ACTION_START_SIM = 1
    ACTION_QUIT = 2

    def __init__(self, screen_width: int, screen_height: int):
        self.screen_width = screen_width
        self.screen_height = screen_height

        self.font_title = Theme.get_font(Theme.FONT_SIZE_LARGE + 12) 
        self.font_button = Theme.get_font(Theme.FONT_SIZE_NORMAL + 2) 

        self.button_width = 300 
        self.button_height = 60
        self.button_padding = 25

        self.title_text = "RUSH HOUR"
        self.start_button_text = "Start Simulation"
        self.quit_button_text = "Quit"

        self.button_start_rect = None
        self.button_quit_rect = None
        
        self._calculate_layout()

    def _calculate_layout(self):
        """Calculates the positions of menu elements."""
        # Title
        title_surf = self.font_title.render(self.title_text, True, Theme.COLOR_TEXT_ON_DARK)
        self.title_rect = title_surf.get_rect(center=(self.screen_width // 2, self.screen_height // 3)) # Positioned higher

        # Start Button
        self.button_start_rect = pygame.Rect(
            (self.screen_width - self.button_width) // 2,
            self.title_rect.bottom + 70, # More space after title
            self.button_width,
            self.button_height
        )

        # Quit Button
        self.button_quit_rect = pygame.Rect(
            (self.screen_width - self.button_width) // 2,
            self.button_start_rect.bottom + self.button_padding,
            self.button_width,
            self.button_height
        )

    def handle_event(self, event: pygame.event.Event, mouse_pos: tuple) -> int:
        """
        Handles a single Pygame event for the main menu.
        Returns an action code (ACTION_START_SIM, ACTION_QUIT, or ACTION_NONE).
        """
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return MainMenu.ACTION_QUIT
            elif event.key == pygame.K_RETURN or event.key == pygame.K_SPACE: # Start with Enter/Space
                return MainMenu.ACTION_START_SIM
                
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1: # Left mouse button
                if self.button_start_rect and self.button_start_rect.collidepoint(mouse_pos):
                    return MainMenu.ACTION_START_SIM
                elif self.button_quit_rect and self.button_quit_rect.collidepoint(mouse_pos):
                    return MainMenu.ACTION_QUIT
        return MainMenu.ACTION_NONE

    def draw(self, surface: pygame.Surface):
        """Draws the main menu onto the given surface."""
        surface.fill(Theme.COLOR_BACKGROUND)

        # Draw Title
        title_surf = self.font_title.render(self.title_text, True, Theme.COLOR_TEXT_ON_DARK)
        surface.blit(title_surf, self.title_rect)

        # Draw Start Button
        start_text_surf = self.font_button.render(self.start_button_text, True, Theme.COLOR_TEXT_ON_DARK)
        draw_rounded_rect(surface, Theme.COLOR_ROAD, self.button_start_rect, Theme.BORDER_RADIUS)
        start_text_rect = start_text_surf.get_rect(center=self.button_start_rect.center)
        surface.blit(start_text_surf, start_text_rect)

        # Draw Quit Button
        quit_text_surf = self.font_button.render(self.quit_button_text, True, Theme.COLOR_TEXT_ON_DARK)
        draw_rounded_rect(surface, Theme.COLOR_ROAD, self.button_quit_rect, Theme.BORDER_RADIUS)
        quit_text_rect = quit_text_surf.get_rect(center=self.button_quit_rect.center)
        surface.blit(quit_text_surf, quit_text_rect)
        
        # Hover effect
        mouse_pos = pygame.mouse.get_pos()
        if self.button_start_rect.collidepoint(mouse_pos):
            pygame.draw.rect(surface, Theme.COLOR_LINE, self.button_start_rect, 3, border_radius=Theme.BORDER_RADIUS) # Thicker hover
        if self.button_quit_rect.collidepoint(mouse_pos):
            pygame.draw.rect(surface, Theme.COLOR_LINE, self.button_quit_rect, 3, border_radius=Theme.BORDER_RADIUS)
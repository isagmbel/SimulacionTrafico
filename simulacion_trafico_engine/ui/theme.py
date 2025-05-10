# simulacion_trafico_engine/ui/theme.py
import pygame
import random
from typing import Any, Optional # <--- AÑADIDO Any y Optional

class Theme:
    # Pastel Palette & General UI
    COLOR_BACKGROUND = pygame.Color("#2E3440")
    COLOR_ROAD = pygame.Color("#4C566A")
    COLOR_LINE = pygame.Color("#D8DEE9")
    COLOR_TEXT_ON_DARK = pygame.Color("#ECEFF4")
    
    COLOR_INFO_PANEL_BG = pygame.Color("#88C0D0")
    COLOR_INFO_PANEL_BORDER = pygame.Color("#5E81AC")
    COLOR_TEXT_ON_INFO_PANEL = COLOR_ROAD

    COLOR_GRASS = pygame.Color("#9AB990")

    BUILDING_COLORS_PALETTE = [
        pygame.Color("#EBCB8B"), pygame.Color("#BF616A"), pygame.Color("#B48EAD"),
        pygame.Color("#81A1C1"), pygame.Color("#D08770"), pygame.Color("#D8DEE9"),
        pygame.Color("#4C566A"), pygame.Color("#A3BE8C"),
    ]
    BUILDING_ROOF_DARKEN_FACTOR = 0.7

    VEHICLE_COLORS = [
        pygame.Color("#BF616A"), pygame.Color("#A3BE8C"), pygame.Color("#EBCB8B"),
        pygame.Color("#B48EAD"), pygame.Color("#81A1C1"), pygame.Color("#D08770")
    ]

    TL_RED = pygame.Color("#BF616A")
    TL_YELLOW = pygame.Color("#EBCB8B")
    TL_GREEN = pygame.Color("#A3BE8C")
    TL_OFF = pygame.Color("#434C5E") 
    TL_HOUSING = pygame.Color("#3B4252")

    BORDER_RADIUS = 6
    BORDER_WIDTH = 2
    INFO_PANEL_WIDTH_RATIO = 0.25

    FONT_NAME = None
    FONT_SIZE_NORMAL = 20
    FONT_SIZE_LARGE = 24
    FONT_SIZE_SMALL = 16

    @staticmethod
    def get_vehicle_color() -> pygame.Color:
        return random.choice(Theme.VEHICLE_COLORS)

    @staticmethod
    def get_building_colors() -> tuple[pygame.Color, pygame.Color]:
        body_color = random.choice(Theme.BUILDING_COLORS_PALETTE)
        possible_roof_colors = [c for c in Theme.BUILDING_COLORS_PALETTE if c != body_color]
        if random.random() < 0.7 and possible_roof_colors:
            roof_color = random.choice(possible_roof_colors)
        else:
            roof_color = pygame.Color(
                max(0, int(body_color.r * Theme.BUILDING_ROOF_DARKEN_FACTOR)),
                max(0, int(body_color.g * Theme.BUILDING_ROOF_DARKEN_FACTOR)),
                max(0, int(body_color.b * Theme.BUILDING_ROOF_DARKEN_FACTOR))
            )
            if roof_color == body_color:
                 roof_color = pygame.Color(max(0, body_color.r - 30), max(0, body_color.g - 30), max(0, body_color.b - 30))
            if roof_color == pygame.Color(0,0,0) and body_color != pygame.Color(0,0,0):
                roof_color = pygame.Color(20,20,20)
        return body_color, roof_color

    @staticmethod
    def get_font(size: int) -> pygame.font.Font:
        return pygame.font.Font(Theme.FONT_NAME, size)

# La función draw_rounded_rect está fuera de la clase Theme
def draw_rounded_rect(surface: pygame.Surface, color: pygame.Color, rect: Any, radius: int, border_width: int = 0, border_color: Optional[pygame.Color] = None):
    if not isinstance(rect, pygame.Rect):
        try:
            current_rect = pygame.Rect(rect)
        except TypeError:
            print(f"ERROR en draw_rounded_rect: 'rect' debe ser pygame.Rect o tupla/lista compatible, se recibió {type(rect)} valor {rect}")
            return 
    else:
        current_rect = rect
        
    if radius < 0: radius = 0
    max_radius_w = current_rect.width // 2 if current_rect.width > 0 else 0
    max_radius_h = current_rect.height // 2 if current_rect.height > 0 else 0
    
    if current_rect.width < 1 or current_rect.height < 1: # Si el rect no tiene área, no se puede dibujar radio
        pygame.draw.rect(surface, color, current_rect, border_width if border_width > 0 else 0)
        return
        
    effective_radius = min(radius, max_radius_w, max_radius_h)

    pygame.draw.rect(surface, color, current_rect, 0, border_radius=effective_radius)

    if border_width > 0:
        border_c = border_color
        if border_color is None:
            border_c = pygame.Color(
                max(0, color.r - 40) if color.r > 40 else min(255, color.r + 40),
                max(0, color.g - 40) if color.g > 40 else min(255, color.g + 40),
                max(0, color.b - 40) if color.b > 40 else min(255, color.b + 40)
            )
        pygame.draw.rect(surface, border_c, current_rect, border_width, border_radius=effective_radius)
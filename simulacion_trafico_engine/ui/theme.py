# simulacion_trafico_engine/ui/theme.py
import pygame
import random

class Theme:
    # Pastel Palette & General UI
    COLOR_BACKGROUND = pygame.Color("#2E3440")
    COLOR_ROAD = pygame.Color("#4C566A")
    COLOR_LINE = pygame.Color("#D8DEE9")
    COLOR_TEXT_ON_DARK = pygame.Color("#ECEFF4")
    
    COLOR_INFO_PANEL_BG = pygame.Color("#88C0D0")
    COLOR_INFO_PANEL_BORDER = pygame.Color("#5E81AC")
    COLOR_TEXT_ON_INFO_PANEL = COLOR_ROAD

    COLOR_GRASS = pygame.Color("#9AB990") # Muted Pastel Green


    # Vehicle Colors
    VEHICLE_COLORS = [
        pygame.Color("#BF616A"), pygame.Color("#A3BE8C"), pygame.Color("#EBCB8B"),
        pygame.Color("#B48EAD"), pygame.Color("#81A1C1"), pygame.Color("#D08770")
    ]

    # Traffic Light Colors
    TL_RED = pygame.Color("#BF616A")
    TL_YELLOW = pygame.Color("#EBCB8B")
    TL_GREEN = pygame.Color("#A3BE8C")
    TL_OFF = pygame.Color("#434C5E") 
    TL_HOUSING = pygame.Color("#3B4252")

    # Sizes and Styles
    BORDER_RADIUS = 6
    BORDER_WIDTH = 2
    INFO_PANEL_WIDTH_RATIO = 0.25

    FONT_NAME = None
    FONT_SIZE_NORMAL = 20
    FONT_SIZE_LARGE = 24
    FONT_SIZE_SMALL = 16

    @staticmethod
    def get_vehicle_color():
        return random.choice(Theme.VEHICLE_COLORS)

    @staticmethod
    def get_font(size: int):
        return pygame.font.Font(Theme.FONT_NAME, size)

def draw_rounded_rect(surface, color, rect, radius, border_width=0, border_color=None):
    if not isinstance(rect, pygame.Rect):
        rect = pygame.Rect(rect)
        
    if rect.width < 2 * radius: radius = rect.width // 2
    if rect.height < 2 * radius: radius = rect.height // 2
    if radius < 0: radius = 0

    pygame.draw.rect(surface, color, rect, 0, border_radius=radius)

    if border_width > 0:
        border_c = border_color
        if border_color is None:
            border_c = pygame.Color(
                max(0, color.r - 40), max(0, color.g - 40), max(0, color.b - 40)
            )
        pygame.draw.rect(surface, border_c, rect, border_width, border_radius=radius)
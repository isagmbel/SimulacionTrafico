# simulacion_trafico_engine/ui/theme.py
import pygame
import random
import os 
from typing import Any, Optional

ENGINE_ROOT_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_PATH = os.path.join(ENGINE_ROOT_PATH, "assets")

COCHES_HORIZONTALES_PATH = os.path.join(ASSETS_PATH, "cocheshorizontales")
COCHES_VERTICALES_PATH = os.path.join(ASSETS_PATH, "cochesverticales")
MAIN_MENU_ASSETS_PATH = os.path.join(ASSETS_PATH, "mainmenu")


class Theme:
    # ... (COLORES y FUENTES se mantienen igual que en la última versión) ...
    COLOR_BACKGROUND = pygame.Color("#2E3440") # Usado por MainMenu, y como fallback
    COLOR_ROAD = pygame.Color("#4C566A")     # Ya no se usa para dibujar carreteras si el mapa es una imagen
    COLOR_LINE = pygame.Color("#D8DEE9")     # Ya no se usa para dibujar líneas si el mapa es una imagen
    COLOR_TEXT_ON_DARK = pygame.Color("#ECEFF4")
    COLOR_INFO_PANEL_BG = pygame.Color("#434C5E") 
    COLOR_INFO_PANEL_BORDER = pygame.Color("#5E81AC")
    COLOR_TEXT_ON_INFO_PANEL = pygame.Color("#D8DEE9") 
    COLOR_INFO_PANEL_BG_COLLAPSED = pygame.Color("#5E81AC") 
    COLOR_INFO_PANEL_BORDER_COLLAPSED = pygame.Color("#4C566A")
    COLOR_GRASS = pygame.Color("#9AB990") # Ya no se usa para el fondo del mapa si es una imagen
    VEHICLE_COLORS = [ 
        pygame.Color("#BF616A"), pygame.Color("#A3BE8C"), pygame.Color("#EBCB8B"),
        pygame.Color("#B48EAD"), pygame.Color("#81A1C1"), pygame.Color("#D08770") ]
    TL_RED = pygame.Color("#BF616A"); TL_YELLOW = pygame.Color("#EBCB8B")
    TL_GREEN = pygame.Color("#A3BE8C"); TL_OFF = pygame.Color("#434C5E") 
    TL_HOUSING = pygame.Color("#3B4252")
    BORDER_RADIUS = 8; BORDER_WIDTH = 2
    BORDER_RADIUS_SMALL = 4; BORDER_WIDTH_SMALL = 1

    FONT_NAME = None 
    FONT_SIZE_NORMAL = 18
    FONT_SIZE_LARGE = 22
    FONT_SIZE_SMALL = 14
    # --- FIN COLORES y FUENTES ---

    # --- RUTAS DE ASSETS ---
    MAIN_MENU_BG_PATH = os.path.join(MAIN_MENU_ASSETS_PATH, "RushHourBG.PNG")
    MAIN_MENU_TEXT_PATH = os.path.join(MAIN_MENU_ASSETS_PATH, "RushHourText.PNG")

    GAME_MAP_BACKGROUND_PATH = os.path.join(ASSETS_PATH, "mapa.PNG") # Asumiendo que mapa.PNG está en /assets/


    VEHICLE_IMAGE_PATHS = [
        os.path.join(COCHES_HORIZONTALES_PATH, "IMG_6805.PNG"),
        os.path.join(COCHES_HORIZONTALES_PATH, "IMG_6806.PNG"),
        os.path.join(COCHES_HORIZONTALES_PATH, "IMG_6807.PNG"),
        os.path.join(COCHES_HORIZONTALES_PATH, "IMG_6808.PNG"),
    ]
    # --- FIN RUTAS DE ASSETS ---
    
    @staticmethod
    def get_vehicle_color() -> pygame.Color: 
        return random.choice(Theme.VEHICLE_COLORS)

    @staticmethod
    def get_vehicle_image_path() -> str: 
        if not Theme.VEHICLE_IMAGE_PATHS:
            print("CRITICAL: No vehicle image paths defined in Theme.VEHICLE_IMAGE_PATHS.")
            return Theme.VEHICLE_IMAGE_PATHS[0] if Theme.VEHICLE_IMAGE_PATHS else ""
        return random.choice(Theme.VEHICLE_IMAGE_PATHS)

    @staticmethod
    def get_font(size: int) -> pygame.font.Font:
        try:
            return pygame.font.Font(Theme.FONT_NAME, size)
        except pygame.error:
            return pygame.font.SysFont(None, size) 

# ... (función draw_rounded_rect, si todavía la usas para algo como InfoPanel) ...
def draw_rounded_rect(surface: pygame.Surface, color: pygame.Color, rect: Any, radius: int, border_width: int = 0, border_color: Optional[pygame.Color] = None):
    if not isinstance(rect, pygame.Rect):
        try: current_rect = pygame.Rect(rect)
        except TypeError: pygame.draw.rect(surface, color, rect); return 
    else: current_rect = rect
    if radius < 0: radius = 0
    max_r_w = current_rect.width // 2 if current_rect.width > 0 else 0
    max_r_h = current_rect.height // 2 if current_rect.height > 0 else 0
    if current_rect.width <= 0 or current_rect.height <= 0 : return
    eff_r = min(radius, max_r_w, max_r_h) if not (current_rect.width < 2 * radius or current_rect.height < 2 * radius) else min(max_r_w, max_r_h)
    if eff_r < 0: eff_r = 0
    try:
        pygame.draw.rect(surface, color, current_rect, 0, border_radius=eff_r)
        if border_width > 0:
            bc = border_color or pygame.Color(max(0,color.r-40) if color.r>40 else min(255,color.r+40), max(0,color.g-40) if color.g>40 else min(255,color.g+40), max(0,color.b-40) if color.b>40 else min(255,color.b+40))
            pygame.draw.rect(surface, bc, current_rect, border_width, border_radius=eff_r)
    except pygame.error: 
        pygame.draw.rect(surface, color, current_rect, 0)
        if border_width > 0 and (border_color or color): pygame.draw.rect(surface, border_color or color, current_rect, border_width)
# simulacion_trafico_engine/ui/theme.py
import pygame
import random
import os 
from typing import Any, Optional, List

# --- Definición de Rutas Base para Assets ---
# Se asume que la carpeta 'assets' está dentro de 'simulacion_trafico_engine'
ENGINE_ROOT_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_PATH = os.path.join(ENGINE_ROOT_PATH, "assets")

# Subdirectorios específicos dentro de 'assets'
COCHES_HORIZONTALES_PATH = os.path.join(ASSETS_PATH, "cocheshorizontales")
COCHES_VERTICALES_PATH = os.path.join(ASSETS_PATH, "cochesverticales")
MAIN_MENU_ASSETS_PATH = os.path.join(ASSETS_PATH, "mainmenu")

class Theme:
    """
    Clase central para definir todos los aspectos visuales y temáticos de la simulación,
    incluyendo colores, fuentes y rutas a assets gráficos.
    """

    # --- Paleta de Colores y UI General ---
    COLOR_BACKGROUND = pygame.Color("#2E3440")               # Fondo general oscuro (ej. para menú)
    COLOR_TEXT_ON_DARK = pygame.Color("#2E3440")             # Texto oscuro para usar sobre fondos claros (ej. panel rosa)
    
    # Colores para el Panel de Información (cuando está expandido o colapsado)
    INFO_PANEL_PINK_BG = pygame.Color("#FBCFE8")             # Fondo rosa pastel para el panel
    INFO_PANEL_PINK_BORDER = pygame.Color("#F472B6")         # Borde rosa más intenso para el panel
    COLOR_INFO_PANEL_BG = INFO_PANEL_PINK_BG                 # Color de fondo del panel expandido
    COLOR_INFO_PANEL_BORDER = INFO_PANEL_PINK_BORDER         # Color del borde del panel expandido
    COLOR_TEXT_ON_INFO_PANEL = COLOR_TEXT_ON_DARK            # Color del texto dentro del panel
    COLOR_INFO_PANEL_BG_COLLAPSED = INFO_PANEL_PINK_BG       # Fondo del panel cuando está colapsado (tab)
    COLOR_INFO_PANEL_BORDER_COLLAPSED = INFO_PANEL_PINK_BORDER # Borde del panel colapsado

    # Colores de Fallback para vehículos (si no cargan las imágenes)
    VEHICLE_COLORS_FALLBACK = [ 
        pygame.Color("#BF616A"), pygame.Color("#A3BE8C"), pygame.Color("#EBCB8B"),
        pygame.Color("#B48EAD"), pygame.Color("#81A1C1"), pygame.Color("#D08770") 
    ]

    # Colores para los Semáforos
    TL_RED = pygame.Color("#FF4136")                         # Rojo brillante para semáforo
    TL_YELLOW = pygame.Color("#FFDC00")                      # Amarillo brillante para semáforo
    TL_GREEN = pygame.Color("#2ECC40")                       # Verde brillante para semáforo
    TL_OFF = pygame.Color("#606060")                         # Gris para luz de semáforo apagada
    TL_HOUSING = pygame.Color("#777777")                     # Gris para la carcasa del semáforo

    # --- Parámetros de Bordes y Radios ---
    BORDER_RADIUS = 8                                        # Radio de borde para elementos grandes
    BORDER_WIDTH = 2                                         # Ancho de borde para elementos grandes
    BORDER_RADIUS_SMALL = 4                                  # Radio de borde para elementos pequeños (ej. tab del panel)
    BORDER_WIDTH_SMALL = 1                                   # Ancho de borde para elementos pequeños
    
    # --- Definiciones de Fuentes ---
    FONT_NAME = None                                         # Nombre del archivo de fuente (None para la por defecto de Pygame)
    FONT_SIZE_NORMAL = 18                                    # Tamaño de fuente normal
    FONT_SIZE_LARGE = 22                                     # Tamaño de fuente grande
    FONT_SIZE_SMALL = 14                                     # Tamaño de fuente pequeño

    # --- Rutas a Assets Gráficos ---
    # Menú Principal
    MAIN_MENU_BG_PATH = os.path.join(MAIN_MENU_ASSETS_PATH, "RushHourBG.PNG")
    MAIN_MENU_TEXT_PATH = os.path.join(MAIN_MENU_ASSETS_PATH, "RushHourText.PNG")
    # Mapa de Simulación
    GAME_MAP_BACKGROUND_PATH = os.path.join(ASSETS_PATH, "mapa.PNG")
    
    # Vehículos (se llenan dinámicamente al cargar la clase)
    VEHICLE_HORIZONTAL_IMAGE_PATHS: List[str] = []
    try:
        if os.path.exists(COCHES_HORIZONTALES_PATH):
            VEHICLE_HORIZONTAL_IMAGE_PATHS = [
                os.path.join(COCHES_HORIZONTALES_PATH, f) 
                for f in os.listdir(COCHES_HORIZONTALES_PATH) 
                if f.upper().endswith(".PNG") and os.path.isfile(os.path.join(COCHES_HORIZONTALES_PATH, f))
            ]
        if not VEHICLE_HORIZONTAL_IMAGE_PATHS:
            print(f"ADVERTENCIA: No se encontraron archivos PNG en {COCHES_HORIZONTALES_PATH}")
    except FileNotFoundError:
        print(f"ADVERTENCIA: Directorio no encontrado: {COCHES_HORIZONTALES_PATH}")
    except Exception as e:
        print(f"Error listando imágenes de vehículos horizontales: {e}")

    VEHICLE_VERTICAL_IMAGE_PATHS: List[str] = []
    try:
        if os.path.exists(COCHES_VERTICALES_PATH):
            VEHICLE_VERTICAL_IMAGE_PATHS = [
                os.path.join(COCHES_VERTICALES_PATH, f)
                for f in os.listdir(COCHES_VERTICALES_PATH) 
                if f.upper().endswith(".PNG") and os.path.isfile(os.path.join(COCHES_VERTICALES_PATH, f))
            ]
        if not VEHICLE_VERTICAL_IMAGE_PATHS:
            print(f"ADVERTENCIA: No se encontraron archivos PNG en {COCHES_VERTICALES_PATH}")
    except FileNotFoundError:
        print(f"ADVERTENCIA: Directorio no encontrado: {COCHES_VERTICALES_PATH}")
    except Exception as e:
        print(f"Error listando imágenes de vehículos verticales: {e}")
    
    # --- Métodos Estáticos Auxiliares ---
    @staticmethod
    def get_vehicle_color() -> pygame.Color:
        """Devuelve un color aleatorio de la paleta de fallback para vehículos."""
        return random.choice(Theme.VEHICLE_COLORS_FALLBACK)

    @staticmethod
    def get_vehicle_image_path(direction: str) -> str:
        """
        Devuelve una ruta aleatoria a un asset de vehículo según la dirección.
        Args:
            direction (str): La dirección de movimiento del vehículo ("left", "right", "up", "down").
        Returns:
            str: Ruta al archivo de imagen del vehículo. Devuelve cadena vacía si no se encuentran assets.
        """
        target_list = None
        if direction in ["left", "right"]:
            target_list = Theme.VEHICLE_HORIZONTAL_IMAGE_PATHS
            if not target_list:
                print("CRÍTICO: No hay rutas de imágenes para vehículos horizontales disponibles.")
                return "" 
        elif direction in ["up", "down"]:
            target_list = Theme.VEHICLE_VERTICAL_IMAGE_PATHS
            if not target_list:
                print("CRÍTICO: No hay rutas de imágenes para vehículos verticales disponibles.")
                return ""
        else: # Fallback para dirección desconocida
            print(f"ADVERTENCIA: Dirección desconocida '{direction}' para selección de imagen de vehículo. Usando horizontal por defecto.")
            target_list = Theme.VEHICLE_HORIZONTAL_IMAGE_PATHS
            if not target_list: 
                print("CRÍTICO: No hay rutas de imágenes horizontales (por defecto) disponibles.")
                return ""
        
        if not target_list: # Si después de todo, la lista está vacía
             print("CRÍTICO: La lista de imágenes de vehículos seleccionada está vacía.")
             return ""

        return random.choice(target_list)

    @staticmethod
    def get_font(size: int) -> pygame.font.Font:
        """
        Obtiene un objeto pygame.font.Font del tamaño especificado.
        Usa Theme.FONT_NAME si está definido, sino la fuente por defecto del sistema.
        """
        try:
            return pygame.font.Font(Theme.FONT_NAME, size)
        except pygame.error: # Si FONT_NAME es None o no se encuentra
            return pygame.font.SysFont(None, size) # Usa la fuente por defecto de Pygame

# --- Función Utilitaria de Dibujo ---
def draw_rounded_rect(surface: pygame.Surface, color: pygame.Color, rect: Any, 
                      radius: int, border_width: int = 0, 
                      border_color: Optional[pygame.Color] = None):
    """
    Dibuja un rectángulo con esquinas redondeadas.
    Args:
        surface: La superficie de Pygame donde dibujar.
        color: El color de relleno del rectángulo.
        rect: Un objeto pygame.Rect o una tupla/lista compatible con Rect (x, y, w, h).
        radius: El radio de las esquinas redondeadas.
        border_width: Ancho del borde (0 para sin borde).
        border_color: Color del borde (opcional, se calcula uno por defecto si no se provee).
    """
    current_rect: pygame.Rect
    if not isinstance(rect, pygame.Rect):
        try: 
            current_rect = pygame.Rect(rect)
        except TypeError: # Fallback si `rect` no es compatible
            pygame.draw.rect(surface, color, rect) 
            return 
    else: 
        current_rect = rect

    if radius < 0: radius = 0
    
    # Asegurar que el radio no sea más grande que la mitad del lado más corto
    max_radius_width = current_rect.width // 2 if current_rect.width > 0 else 0
    max_radius_height = current_rect.height // 2 if current_rect.height > 0 else 0
    
    # No dibujar si el rectángulo no tiene área
    if current_rect.width <= 0 or current_rect.height <= 0: 
        return

    # Si el radio es demasiado grande para el rectángulo, ajústalo al máximo posible
    # o dibuja un rectángulo normal si el radio efectivo sería 0 o menos.
    if current_rect.width < 2 * radius or current_rect.height < 2 * radius:
        effective_radius = min(max_radius_width, max_radius_height)
    else:
        effective_radius = min(radius, max_radius_width, max_radius_height)
    
    if effective_radius < 0: effective_radius = 0 # Doble chequeo

    try:
        # Dibuja el relleno
        pygame.draw.rect(surface, color, current_rect, 0, border_radius=effective_radius)

        # Dibuja el borde si es necesario
        if border_width > 0:
            # Determina el color del borde
            actual_border_color = border_color
            if actual_border_color is None: # Genera un color de borde por defecto si no se especifica
                actual_border_color = pygame.Color(
                    max(0, color.r - 40) if color.r > 40 else min(255, color.r + 40),
                    max(0, color.g - 40) if color.g > 40 else min(255, color.g + 40),
                    max(0, color.b - 40) if color.b > 40 else min(255, color.b + 40)
                )
            pygame.draw.rect(surface, actual_border_color, current_rect, border_width, border_radius=effective_radius)
    except pygame.error as e: 
        # Fallback a un rectángulo sin redondear si pygame.draw.rect con border_radius falla
        # print(f"Error dibujando rectángulo redondeado (rect: {current_rect}, radio: {effective_radius}): {e}. Dibujando normal.")
        pygame.draw.rect(surface, color, current_rect, 0) # Relleno
        if border_width > 0 and (border_color or color): # Borde (usa border_color si existe, sino el color de relleno)
             pygame.draw.rect(surface, border_color if border_color else color, current_rect, border_width)
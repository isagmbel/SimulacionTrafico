# simulacion_trafico_engine/ui/theme.py
import pygame

class Theme:
    # Pastel Palette
    COLOR_BACKGROUND = pygame.Color("#2E3440")  # Nord Polar Night (Dark Blue-Gray)
    COLOR_ROAD = pygame.Color("#4C566A")      # Nord Polar Night (Lighter Blue-Gray)
    COLOR_LINE = pygame.Color("#D8DEE9")      # Nord Snow Storm (Off-White)
    COLOR_TEXT = pygame.Color("#ECEFF4")      # Nord Snow Storm (Lightest Gray)
    
    COLOR_INFO_PANEL_BG = pygame.Color("#88C0D0") # Nord Frost (Light Blue/Turquoise)
    COLOR_INFO_PANEL_BORDER = pygame.Color("#5E81AC") # Nord Frost (Darker Blue)
    
    # Vehicle Colors (Pastel selection)
    VEHICLE_COLORS = [
        pygame.Color("#BF616A"), # Nord Aurora (Red)
        pygame.Color("#A3BE8C"), # Nord Aurora (Green)
        pygame.Color("#EBCB8B"), # Nord Aurora (Yellow)
        pygame.Color("#B48EAD"), # Nord Aurora (Purple)
        pygame.Color("#81A1C1"), # Nord Frost (Blue)
    ]

    # Traffic Light Colors
    TL_RED = pygame.Color("#BF616A") # Nord Aurora Red
    TL_YELLOW = pygame.Color("#EBCB8B") # Nord Aurora Yellow
    TL_GREEN = pygame.Color("#A3BE8C") # Nord Aurora Green
    TL_OFF = pygame.Color("#434C5E") # Nord Polar Night (Medium Gray)
    TL_HOUSING = pygame.Color("#3B4252") # Nord Polar Night (Darker Gray)

    # Sizes and Styles
    BORDER_RADIUS = 5
    BORDER_WIDTH = 2
    INFO_PANEL_WIDTH_RATIO = 0.25 # 25% of screen width

    FONT_NAME = None # Use default pygame font
    FONT_SIZE_NORMAL = 20
    FONT_SIZE_LARGE = 24
    FONT_SIZE_SMALL = 16

    @staticmethod
    def get_vehicle_color():
        import random
        return random.choice(Theme.VEHICLE_COLORS)

    @staticmethod
    def get_font(size: int):
        return pygame.font.Font(Theme.FONT_NAME, size)

# Helper for rounded rects - place in theme.py or a utils.py
def draw_rounded_rect(surface, color, rect, radius, border_width=0, border_color=None):
    """Draws a rectangle with rounded corners.
    `radius` argument is the radius of the corners.
    `border_width` if > 0, draws a border of this width.
    `border_color` color of the border. If None, uses main color darkened.
    """
    # Ensure rect is valid for drawing with radius
    if rect.width < 2 * radius: radius = rect.width // 2
    if rect.height < 2 * radius: radius = rect.height // 2
    if radius < 0: radius = 0 # Prevent negative radius


    # Main filled rect
    pygame.draw.rect(surface, color, rect, 0, border_radius=radius)

    if border_width > 0:
        if border_color is None:
            # Create a slightly darker color for the border if not specified
            border_c = pygame.Color(
                max(0, color.r - 40),
                max(0, color.g - 40),
                max(0, color.b - 40)
            )
        else:
            border_c = border_color
        
        # Draw the border using the same rect and radius, but with a width
        pygame.draw.rect(surface, border_c, rect, border_width, border_radius=radius)
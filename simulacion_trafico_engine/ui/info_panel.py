# simulacion_trafico_engine/ui/info_panel.py
import pygame
from typing import List, Callable, Dict, Tuple, Any # Tipos necesarios
from .theme import Theme, draw_rounded_rect # Importar draw_rounded_rect de Theme

class InfoPanel:
    """
    Panel de información que muestra estadísticas de la simulación.
    Puede ser expandido o colapsado por el usuario (ej. con la tecla TAB o click).
    Se posiciona en una esquina de la pantalla de simulación.
    """
    def __init__(self, base_screen_width: int, base_screen_height: int, 
                 metrics_provider_func: Callable[[], Dict[str, Any]]):
        """
        Inicializa el panel de información.
        Args:
            base_screen_width (int): Ancho de la pantalla principal sobre la que se dibujará el panel.
            base_screen_height (int): Alto de la pantalla principal.
            metrics_provider_func (Callable[[], Dict[str, Any]]): Una función que, al ser llamada,
                                                                  devuelve un diccionario con las métricas
                                                                  actuales de la simulación.
        """
        # --- Dimensiones y Posicionamiento del Panel ---
        self.panel_width_expanded: int = 300     # Ancho del panel cuando está completamente visible.
        self.panel_height_expanded: int = 300    # Alto máximo del panel cuando está visible.
        self.panel_tab_width: int = 100          # Ancho del "tab" o botón cuando el panel está colapsado.
        self.panel_tab_height: int = 40          # Alto del "tab" o botón.
        
        self.margin: int = 10  # Margen desde los bordes de la pantalla.

        # Rectángulo para el panel expandido (posición y tamaño)
        self.expanded_rect = pygame.Rect(
            base_screen_width - self.panel_width_expanded - self.margin, 
            self.margin, 
            self.panel_width_expanded, 
            self.panel_height_expanded
        )
        # Rectángulo para el tab del panel colapsado
        self.collapsed_rect = pygame.Rect(
            base_screen_width - self.panel_tab_width - self.margin, 
            self.margin,
            self.panel_tab_width,
            self.panel_tab_height
        )
        
        self.is_expanded: bool = False # El panel inicia en estado colapsado.

        # --- Carga de Fuentes desde el Tema ---
        self.font_normal = Theme.get_font(Theme.FONT_SIZE_NORMAL)
        self.font_large = Theme.get_font(Theme.FONT_SIZE_LARGE)
        self.font_small = Theme.get_font(Theme.FONT_SIZE_SMALL)
        self.font_tab = Theme.get_font(Theme.FONT_SIZE_SMALL) # Fuente específica para el texto del tab.
        
        # --- Datos y Configuración de Contenido ---
        self.metrics_provider_func: Callable[[], Dict[str, Any]] = metrics_provider_func
        self.padding: int = 15                # Relleno interno para el contenido del panel.
        self.line_spacing_small: int = 4      # Espaciado vertical entre líneas de texto pequeño.
        self.line_spacing_normal: int = 7     # Espaciado vertical entre líneas de texto normal.
        self.section_spacing: int = 15        # Espaciado vertical entre diferentes secciones de información.

        # --- Colores del Tema para el Panel ---
        self.text_color_on_panel: pygame.Color = Theme.COLOR_TEXT_ON_INFO_PANEL
        self.tab_text_color: pygame.Color = Theme.COLOR_TEXT_ON_DARK # O un color específico para el texto del tab.

    def toggle_expansion(self):
        """Cambia el estado del panel entre expandido y colapsado."""
        self.is_expanded = not self.is_expanded

    def handle_event(self, event: pygame.event.Event, mouse_pos: Tuple[int, int]) -> bool:
        """
        Maneja eventos de Pygame, específicamente clicks del ratón, para el panel.
        Permite al usuario expandir o colapsar el panel haciendo click en el área del tab.
        Args:
            event (pygame.event.Event): El evento de Pygame a procesar.
            mouse_pos (Tuple[int, int]): La posición actual del ratón (x, y).
        Returns:
            bool: True si el panel manejó el evento (ej. un click en su área), False en caso contrario.
        """
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1: # Solo procesar clicks del botón izquierdo del ratón
                # Determinar el área clickeable actual: el tab si está colapsado,
                # o la cabecera del panel (con altura de tab) si está expandido.
                if self.is_expanded:
                    # Si está expandido, la parte superior del panel (con la altura del tab) actúa como "botón" para colapsar
                    clickable_header_rect = pygame.Rect(
                        self.expanded_rect.x, self.expanded_rect.y, 
                        self.expanded_rect.width, self.panel_tab_height 
                    )
                    if clickable_header_rect.collidepoint(mouse_pos):
                        self.toggle_expansion()
                        return True # Evento manejado
                else: # Si está colapsado, el propio tab es el área clickeable
                    if self.collapsed_rect.collidepoint(mouse_pos):
                        self.toggle_expansion()
                        return True # Evento manejado
        return False # El evento no fue relevante para el panel

    def _render_multiline_text(self, surface: pygame.Surface, text_lines: List[str], 
                               font: pygame.font.Font, color: pygame.Color, 
                               start_x: int, start_y: int, max_width: int) -> int:
        """
        Renderiza una lista de cadenas de texto, ajustando palabras a nuevas líneas
        si exceden el `max_width` especificado.
        Args:
            surface: La superficie de Pygame donde dibujar el texto.
            text_lines: Una lista de cadenas, cada una representando una entrada de texto.
            font: El objeto pygame.font.Font a usar.
            color: El color del texto.
            start_x: Coordenada X inicial para la primera línea.
            start_y: Coordenada Y inicial para la primera línea.
            max_width: Ancho máximo permitido para una línea de texto antes de ajustarla.
        Returns:
            int: La coordenada Y final después de renderizar todo el texto.
        """
        current_y = start_y
        for line_text_entry in text_lines: # Cada `line_text_entry` puede necesitar múltiples líneas visuales
            words = line_text_entry.split(' ')
            sub_lines_for_this_entry: List[str] = [] 
            current_sub_line_text = ""
            for word in words:
                # Probar si añadir la palabra actual excede el ancho máximo
                test_line = current_sub_line_text + word + " "
                if font.size(test_line)[0] < max_width:
                    current_sub_line_text = test_line # La palabra cabe, añadirla a la sub-línea actual
                else: 
                    # La palabra no cabe, terminar la sub-línea actual y empezar una nueva con esta palabra
                    sub_lines_for_this_entry.append(current_sub_line_text.strip())
                    current_sub_line_text = word + " " 
            sub_lines_for_this_entry.append(current_sub_line_text.strip()) # Añadir la última sub-línea

            # Renderizar cada sub-línea generada para la entrada de texto actual
            for sub_line_to_render in sub_lines_for_this_entry:
                # Verificar si hay suficiente espacio vertical para dibujar la siguiente línea
                if current_y + font.get_height() > self.expanded_rect.bottom - self.padding:
                    return current_y # No hay más espacio, detener renderizado
                
                line_surface = font.render(sub_line_to_render, True, color)
                surface.blit(line_surface, (start_x, current_y))
                current_y += line_surface.get_height() + self.line_spacing_small # Mover a la siguiente posición Y
        return current_y

    def draw(self, surface: pygame.Surface, gui_metrics: Dict[str, Any]):
        """
        Dibuja el panel de información (expandido o colapsado) en la superficie dada.
        Args:
            surface (pygame.Surface): La superficie principal de Pygame donde se dibujará el panel.
            gui_metrics (Dict[str, Any]): Un diccionario con métricas específicas de la GUI
                                          (ej. FPS, conteo de vehículos).
        """
        if self.is_expanded:
            # --- Dibujar Panel Expandido ---
            draw_rounded_rect(surface, Theme.COLOR_INFO_PANEL_BG, self.expanded_rect, 
                              Theme.BORDER_RADIUS, Theme.BORDER_WIDTH, Theme.COLOR_INFO_PANEL_BORDER)

            # Obtener métricas de simulación actualizadas a través de la función proveedora
            sim_metrics = self.metrics_provider_func()
            
            # Posicionamiento inicial del contenido dentro del panel
            y_offset = self.expanded_rect.top + self.padding
            content_x = self.expanded_rect.left + self.padding
            content_max_width = self.expanded_rect.width - (2 * self.padding) # Ancho disponible para texto

            # Título del panel
            title_surface = self.font_large.render("Stats", True, self.text_color_on_panel)
            surface.blit(title_surface, (content_x, y_offset))
            y_offset += title_surface.get_height() + self.section_spacing // 2 # Espacio después del título

            # Lista de estadísticas a mostrar
            stats_to_display = [
                f"Vehicles: {sim_metrics.get('current_vehicle_count', 0)} / {gui_metrics.get('max_vehicles', 'N/A')}",
                f"FPS: {gui_metrics.get('actual_fps', 0.0):.1f} (T: {gui_metrics.get('target_fps', 'N/A')})",
                f"Sim Step: {sim_metrics.get('simulation_time_steps', 0)}",
                f"Avg Speed: {sim_metrics.get('average_vehicle_speed_px_frame', 0.0):.1f} px/f",
                f"Wait (s): {sim_metrics.get('total_vehicle_wait_time_seconds', 0.0):.1f}",
                f"Lights: {sim_metrics.get('traffic_light_changes', 0)}"
            ]
            # Renderizar cada estadística
            for stat_text in stats_to_display:
                # Evitar que el texto se salga del panel si no hay más espacio vertical
                if y_offset + self.font_normal.get_height() > self.expanded_rect.bottom - self.padding: 
                    break 
                stat_surface = self.font_normal.render(stat_text, True, self.text_color_on_panel)
                surface.blit(stat_surface, (content_x, y_offset))
                y_offset += stat_surface.get_height() + self.line_spacing_normal
            
            y_offset += self.section_spacing # Espacio antes de la sección de controles

            # Sección de Controles (solo si hay suficiente espacio vertical)
            controls_title_height = self.font_normal.get_height() + self.line_spacing_normal // 2
            # Estimar altura necesaria para 3 líneas de instrucciones de control
            controls_lines_height_approx = (self.font_small.get_height() + self.line_spacing_small) * 3 
            
            if y_offset + controls_title_height + controls_lines_height_approx < self.expanded_rect.bottom - self.padding:
                instructions_title_surface = self.font_normal.render("Controls:", True, self.text_color_on_panel)
                surface.blit(instructions_title_surface, (content_x, y_offset))
                y_offset += controls_title_height # Mover Y después del título de controles

                instructions_lines = [
                    "SPACE: Spawn Vehicle",
                    "ESC: Menu/Quit",
                    "TAB: Toggle Stats" 
                ]
                # Usar _render_multiline_text para manejar el ajuste de texto si es necesario
                self._render_multiline_text(surface, instructions_lines, self.font_small, 
                                            self.text_color_on_panel, 
                                            content_x, y_offset, content_max_width)
        else:
            # --- Dibujar Panel Colapsado (como un Tab o Botón) ---
            draw_rounded_rect(surface, Theme.COLOR_INFO_PANEL_BG_COLLAPSED, self.collapsed_rect, 
                              Theme.BORDER_RADIUS_SMALL, Theme.BORDER_WIDTH_SMALL, 
                              Theme.COLOR_INFO_PANEL_BORDER_COLLAPSED)
            
            tab_text_surface = self.font_tab.render("Stats (TAB)", True, self.tab_text_color)
            tab_text_rect = tab_text_surface.get_rect(center=self.collapsed_rect.center)
            surface.blit(tab_text_surface, tab_text_rect)
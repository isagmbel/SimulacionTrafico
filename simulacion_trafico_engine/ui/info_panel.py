# simulacion_trafico_engine/ui/info_panel.py
import pygame
from .theme import Theme, draw_rounded_rect

class InfoPanel:
    def __init__(self, screen_width: int, screen_height: int, metrics_provider_func):
        self.screen_height = screen_height
        self.panel_width = int(screen_width * Theme.INFO_PANEL_WIDTH_RATIO)
        self.panel_x = screen_width - self.panel_width
        
        self.rect = pygame.Rect(self.panel_x, 0, self.panel_width, self.screen_height)
        
        self.font_normal = Theme.get_font(Theme.FONT_SIZE_NORMAL)
        self.font_large = Theme.get_font(Theme.FONT_SIZE_LARGE)
        self.font_small = Theme.get_font(Theme.FONT_SIZE_SMALL)
        
        self.metrics_provider_func = metrics_provider_func
        self.padding = 20
        self.line_spacing_small = 5
        self.line_spacing_normal = 8
        self.section_spacing = 25

        self.text_color_on_panel = Theme.COLOR_TEXT_ON_INFO_PANEL # Using specific theme color

    def _render_multiline_text(self, surface, text_lines, font, color, start_x, start_y):
        current_y = start_y
        for line in text_lines:
            line_surf = font.render(line, True, color)
            surface.blit(line_surf, (start_x, current_y))
            current_y += line_surf.get_height() + self.line_spacing_small
        return current_y

    def draw(self, surface: pygame.Surface, gui_metrics: dict):
        draw_rounded_rect(surface, Theme.COLOR_INFO_PANEL_BG, self.rect, Theme.BORDER_RADIUS,
                          Theme.BORDER_WIDTH, Theme.COLOR_INFO_PANEL_BORDER)

        metrics = self.metrics_provider_func()
        y_offset = self.padding

        title_surf = self.font_large.render("Simulation Stats", True, self.text_color_on_panel)
        surface.blit(title_surf, (self.panel_x + self.padding, y_offset))
        y_offset += title_surf.get_height() + self.section_spacing

        stats = [
            f"Vehicles: {metrics.get('current_vehicle_count', 0)} / {gui_metrics.get('max_vehicles', 'N/A')}",
            f"FPS: {gui_metrics.get('actual_fps', 0.0):.1f} (Target: {gui_metrics.get('target_fps', 'N/A')})",
            f"Sim Step: {metrics.get('simulation_time_steps', 0)}",
            f"Avg Speed: {metrics.get('average_vehicle_speed_px_frame', 0.0):.2f} px/f",
            f"Pending Spawns: {gui_metrics.get('pending_spawns', 0)}",
            f"Total Wait (s): {metrics.get('total_vehicle_wait_time_seconds', 0.0):.1f}",
            f"Light Changes: {metrics.get('traffic_light_changes', 0)}"
        ]
        for stat_text in stats:
            stat_surf = self.font_normal.render(stat_text, True, self.text_color_on_panel)
            surface.blit(stat_surf, (self.panel_x + self.padding, y_offset))
            y_offset += stat_surf.get_height() + self.line_spacing_normal
        
        y_offset += self.section_spacing / 2

        description_lines = [
            "Motor de simulación de tráfico",
            "en tiempo real con Pygame y Asyncio."
        ]
        y_offset = self._render_multiline_text(surface, description_lines, self.font_small, 
                                              self.text_color_on_panel, 
                                              self.panel_x + self.padding, y_offset)
        y_offset += self.section_spacing

        instructions_title_surf = self.font_normal.render("Controls:", True, self.text_color_on_panel)
        surface.blit(instructions_title_surf, (self.panel_x + self.padding, y_offset))
        y_offset += instructions_title_surf.get_height() + self.line_spacing_normal

        instructions_lines = [
            "Press SPACE to spawn a vehicle.",
            "Press ESC to quit."
        ]
        y_offset = self._render_multiline_text(surface, instructions_lines, self.font_small, 
                                              self.text_color_on_panel, 
                                              self.panel_x + self.padding, y_offset)
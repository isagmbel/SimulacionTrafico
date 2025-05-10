# simulacion_trafico_engine/ui/info_panel.py
import pygame
from .theme import Theme, draw_rounded_rect # Assuming theme.py is in the same ui directory

class InfoPanel:
    def __init__(self, screen_width: int, screen_height: int, metrics_provider_func):
        self.screen_height = screen_height
        self.panel_width = int(screen_width * Theme.INFO_PANEL_WIDTH_RATIO)
        self.panel_x = screen_width - self.panel_width
        
        self.rect = pygame.Rect(self.panel_x, 0, self.panel_width, self.screen_height)
        
        self.font_normal = Theme.get_font(Theme.FONT_SIZE_NORMAL)
        self.font_large = Theme.get_font(Theme.FONT_SIZE_LARGE)
        
        self.metrics_provider_func = metrics_provider_func # Function to get metrics dict
        self.padding = 20

    def draw(self, surface: pygame.Surface, gui_metrics: dict):
        # Draw Panel Background (using helper for rounded rect)
        draw_rounded_rect(surface, Theme.COLOR_INFO_PANEL_BG, self.rect, Theme.BORDER_RADIUS,
                          Theme.BORDER_WIDTH, Theme.COLOR_INFO_PANEL_BORDER)

        # Metrics from GUI (passed in)
        metrics = self.metrics_provider_func() # Call the function to get latest metrics

        y_offset = self.padding

        title_surf = self.font_large.render("Simulation Stats", True, Theme.COLOR_TEXT)
        surface.blit(title_surf, (self.panel_x + self.padding, y_offset))
        y_offset += title_surf.get_height() + self.padding

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
            stat_surf = self.font_normal.render(stat_text, True, Theme.COLOR_TEXT)
            surface.blit(stat_surf, (self.panel_x + self.padding, y_offset))
            y_offset += stat_surf.get_height() + 5 # Small spacing
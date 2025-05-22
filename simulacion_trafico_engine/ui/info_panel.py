# simulacion_trafico_engine/ui/info_panel.py
import pygame
from .theme import Theme, draw_rounded_rect

class InfoPanel:
    def __init__(self, base_screen_width: int, base_screen_height: int, metrics_provider_func):
        # Panel dimensions - can be fixed or relative
        self.panel_width = 300  # Fixed width
        self.panel_height_expanded = 350 # Max height when expanded
        self.panel_height_collapsed = 40 # Height of the tab/button when collapsed
        
        self.base_screen_width = base_screen_width # The actual simulation area width
        self.base_screen_height = base_screen_height

        # Position in the top-right corner of the simulation area
        self.margin = 10 
        self.expanded_rect = pygame.Rect(
            self.base_screen_width - self.panel_width - self.margin, 
            self.margin, 
            self.panel_width, 
            self.panel_height_expanded
        )
        self.collapsed_rect = pygame.Rect( # Tab/Button
            self.base_screen_width - (self.panel_width // 3) - self.margin, # Make tab smaller
            self.margin,
            self.panel_width // 3, # Smaller width for tab
            self.panel_height_collapsed
        )
        
        self.is_expanded = False # Start collapsed

        self.font_normal = Theme.get_font(Theme.FONT_SIZE_NORMAL)
        self.font_large = Theme.get_font(Theme.FONT_SIZE_LARGE)
        self.font_small = Theme.get_font(Theme.FONT_SIZE_SMALL)
        self.font_tab = Theme.get_font(Theme.FONT_SIZE_SMALL) # For the tab text
        
        self.metrics_provider_func = metrics_provider_func
        self.padding = 15 # Reduced padding
        self.line_spacing_small = 4
        self.line_spacing_normal = 7
        self.section_spacing = 20

        self.text_color_on_panel = Theme.COLOR_TEXT_ON_INFO_PANEL
        self.tab_text_color = Theme.COLOR_TEXT_ON_DARK # Or a specific tab text color

    def toggle_expansion(self):
        self.is_expanded = not self.is_expanded

    def handle_event(self, event: pygame.event.Event, mouse_pos: tuple) -> bool:
        """
        Handles events for the info panel, specifically for toggling.
        Returns True if the event was handled by the panel (e.g., click on tab).
        """
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1: # Left click
                current_tab_rect = self.collapsed_rect if not self.is_expanded else self.expanded_rect.copy()
                current_tab_rect.height = self.panel_height_collapsed # Click area is always the tab height
                
                # If expanded, the "tab" area is the top part of the expanded panel
                if self.is_expanded:
                    clickable_header_rect = pygame.Rect(self.expanded_rect.x, self.expanded_rect.y, self.expanded_rect.width, self.panel_height_collapsed)
                    if clickable_header_rect.collidepoint(mouse_pos):
                        self.toggle_expansion()
                        return True
                elif self.collapsed_rect.collidepoint(mouse_pos): # If collapsed, click the tab itself
                    self.toggle_expansion()
                    return True
        return False

    def _render_multiline_text(self, surface, text_lines, font, color, start_x, start_y, max_width):
        current_y = start_y
        for line in text_lines:
            words = line.split(' ')
            lines_for_this_entry = []
            current_line_text = ""
            for word in words:
                test_line = current_line_text + word + " "
                if font.size(test_line)[0] < max_width:
                    current_line_text = test_line
                else:
                    lines_for_this_entry.append(current_line_text.strip())
                    current_line_text = word + " "
            lines_for_this_entry.append(current_line_text.strip())

            for l in lines_for_this_entry:
                if current_y + font.get_height() > self.expanded_rect.bottom - self.padding: # Stop if overflowing
                    return current_y 
                line_surf = font.render(l, True, color)
                surface.blit(line_surf, (start_x, current_y))
                current_y += line_surf.get_height() + self.line_spacing_small
        return current_y

    def draw(self, surface: pygame.Surface, gui_metrics: dict):
        if self.is_expanded:
            # Draw expanded panel
            draw_rounded_rect(surface, Theme.COLOR_INFO_PANEL_BG, self.expanded_rect, Theme.BORDER_RADIUS,
                              Theme.BORDER_WIDTH, Theme.COLOR_INFO_PANEL_BORDER)

            metrics = self.metrics_provider_func()
            y_offset = self.expanded_rect.top + self.padding
            content_x = self.expanded_rect.left + self.padding
            content_max_width = self.expanded_rect.width - 2 * self.padding


            title_surf = self.font_large.render("Stats", True, self.text_color_on_panel)
            surface.blit(title_surf, (content_x, y_offset))
            y_offset += title_surf.get_height() + self.section_spacing // 2

            stats = [
                f"Vehicles: {metrics.get('current_vehicle_count', 0)} / {gui_metrics.get('max_vehicles', 'N/A')}",
                f"FPS: {gui_metrics.get('actual_fps', 0.0):.1f} (T: {gui_metrics.get('target_fps', 'N/A')})", # Shorter target
                f"Sim Step: {metrics.get('simulation_time_steps', 0)}",
                f"Avg Speed: {metrics.get('average_vehicle_speed_px_frame', 0.0):.1f}px/f", # Shorter
                # f"Pending Spawns: {gui_metrics.get('pending_spawns', 0)}", # Can be verbose
                f"Wait (s): {metrics.get('total_vehicle_wait_time_seconds', 0.0):.1f}", # Shorter
                f"Lights: {metrics.get('traffic_light_changes', 0)}" # Shorter
            ]
            for stat_text in stats:
                if y_offset + self.font_normal.get_height() > self.expanded_rect.bottom - self.padding: break
                stat_surf = self.font_normal.render(stat_text, True, self.text_color_on_panel)
                surface.blit(stat_surf, (content_x, y_offset))
                y_offset += stat_surf.get_height() + self.line_spacing_normal
            
            y_offset += self.section_spacing / 2

            # Controls only if space permits
            if y_offset + self.font_normal.get_height() + (self.font_small.get_height() + self.line_spacing_small) * 2 < self.expanded_rect.bottom - self.padding:
                instructions_title_surf = self.font_normal.render("Controls:", True, self.text_color_on_panel)
                surface.blit(instructions_title_surf, (content_x, y_offset))
                y_offset += instructions_title_surf.get_height() + self.line_spacing_normal // 2

                instructions_lines = [
                    "SPACE: Spawn Vehicle",
                    "ESC: Menu/Quit",
                    "TAB: Toggle Stats" # New instruction
                ]
                y_offset = self._render_multiline_text(surface, instructions_lines, self.font_small, 
                                                    self.text_color_on_panel, 
                                                    content_x, y_offset, content_max_width)
        else:
            # Draw collapsed tab/button
            draw_rounded_rect(surface, Theme.COLOR_INFO_PANEL_BG_COLLAPSED, self.collapsed_rect, Theme.BORDER_RADIUS_SMALL,
                              Theme.BORDER_WIDTH_SMALL, Theme.COLOR_INFO_PANEL_BORDER_COLLAPSED)
            tab_surf = self.font_tab.render("Stats (TAB)", True, self.tab_text_color)
            tab_rect = tab_surf.get_rect(center=self.collapsed_rect.center)
            surface.blit(tab_surf, tab_rect)
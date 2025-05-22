# simulacion_trafico_engine/ui/main_gui.py
import pygame
import asyncio
from typing import List, Dict, Optional, Any, TYPE_CHECKING

# Importaciones de componentes del motor de simulación
# from simulacion_trafico_engine.core.vehicle import Vehicle  # No se usa directamente aquí, pero sí en ZoneNode
# from simulacion_trafico_engine.core.traffic_light import TrafficLight # No se usa directamente aquí
# from simulacion_trafico_engine.core.zone_map import ZoneMap # No se usa directamente aquí

# Importaciones de componentes de UI de este paquete
from .theme import Theme 
from .info_panel import InfoPanel
from .main_menu import MainMenu 

if TYPE_CHECKING:
    # Para type hinting sin causar importaciones circulares en tiempo de ejecución
    from simulacion_trafico_engine.distribution.rabbitclient import RabbitMQClient
    from simulacion_trafico_engine.performance.metrics import TrafficMetrics
    from simulacion_trafico_engine.node.zone_node import ZoneNode

class MainGUI:
    """
    Clase principal para la interfaz gráfica de usuario (GUI) de la simulación.
    Gestiona los diferentes estados de la GUI (menú, simulación), el renderizado,
    y el bucle de eventos de Pygame.
    """

    # --- Estados de la GUI ---
    STATE_MENU = 0
    STATE_SIMULATION = 1

    def __init__(self, city_config: Dict,
                 metrics_client: Optional['TrafficMetrics'] = None):
        """
        Inicializa la GUI principal.
        Args:
            city_config (Dict): Configuración de la ciudad/simulación (ej. dimensiones del mapa).
            metrics_client (Optional[TrafficMetrics]): Cliente para registrar y obtener métricas.
        """
        self.city_config = city_config
        
        # --- Configuración de Dimensiones de la Ventana ---
        # La ventana se ajusta a las dimensiones globales del mapa definidas en la configuración.
        self.map_render_width = city_config["global_map_width"]
        self.map_render_height = city_config["global_map_height"]
        
        # --- Inicialización de Pygame ---
        pygame.init()
        pygame.font.init() # Esencial para poder usar fuentes
        self.screen = pygame.display.set_mode((self.map_render_width, self.map_render_height))
        pygame.display.set_caption("Rush Hour") # Título de la ventana
        
        self.running = True  # Controla el bucle principal de la GUI
        self.fps = 30        # Frames por segundo objetivo
        self.actual_fps = float(self.fps) # FPS real, calculado en cada frame

        # --- Componentes de la GUI ---
        self.metrics_client = metrics_client
        # Panel de información (inicia colapsado)
        self.info_panel = InfoPanel(self.map_render_width, self.map_render_height, self._get_sim_metrics)
        # Nodos de zona (se registran externamente)
        self.zone_nodes: Dict[str, 'ZoneNode'] = {} 
        # Estado inicial de la GUI: Menú Principal
        self.game_state = MainGUI.STATE_MENU
        # Instancia del Menú Principal
        self.main_menu = MainMenu(self.map_render_width, self.map_render_height)

        # --- Carga del Fondo del Mapa de Simulación ---
        self.game_map_background_image: Optional[pygame.Surface] = None
        try:
            # Cargar la imagen definida en Theme
            raw_game_map_bg = pygame.image.load(Theme.GAME_MAP_BACKGROUND_PATH).convert()
            # Escalarla a las dimensiones de la pantalla si no coincide
            if raw_game_map_bg.get_size() != (self.map_render_width, self.map_render_height):
                self.game_map_background_image = pygame.transform.scale(
                    raw_game_map_bg, (self.map_render_width, self.map_render_height)
                )
            else:
                self.game_map_background_image = raw_game_map_bg
        except pygame.error as e:
            print(f"ERROR: Cargando imagen de fondo del mapa '{Theme.GAME_MAP_BACKGROUND_PATH}': {e}")
            # self.game_map_background_image permanece None, se usará un color de fallback en render()

    def register_zone_node(self, node: 'ZoneNode'):
        """Registra un nodo de zona para que la GUI pueda dibujarlo."""
        self.zone_nodes[node.zone_id] = node

    def _get_sim_metrics(self) -> dict:
        """Función proveedora para que InfoPanel obtenga las métricas de simulación."""
        if self.metrics_client:
            return self.metrics_client.get_metrics() 
        return {} # Devuelve diccionario vacío si no hay cliente de métricas

    def handle_events(self):
        """Maneja los eventos de Pygame (teclado, ratón, cierre de ventana)."""
        mouse_pos = pygame.mouse.get_pos()
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT: 
                self.running = False # Termina el bucle principal
            
            # Si estamos en la simulación, el panel de info puede manejar el evento primero (para su toggle)
            if self.game_state == MainGUI.STATE_SIMULATION:
                if self.info_panel.handle_event(event, mouse_pos):
                    continue # Si el panel manejó el evento, no procesar más para este evento

            # Manejo de eventos según el estado actual de la GUI
            if self.game_state == MainGUI.STATE_MENU:
                action = self.main_menu.handle_event(event, mouse_pos)
                if action == MainMenu.ACTION_START_SIM:
                    self.game_state = MainGUI.STATE_SIMULATION
                    # Opcional: resetear contador de pasos de simulación al iniciar
                    if self.metrics_client: self.metrics_client.metrics_data["simulation_time_steps"] = 0 
                elif action == MainMenu.ACTION_QUIT:
                    self.running = False
            
            elif self.game_state == MainGUI.STATE_SIMULATION:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE: # ESC en simulación vuelve al menú
                        self.game_state = MainGUI.STATE_MENU 
                    elif event.key == pygame.K_SPACE: # ESPACIO para spawnear vehículo manualmente
                        if self.zone_nodes:
                            try: # Intenta spawnear en la primera zona disponible
                                node_id_to_spawn_in = list(self.zone_nodes.keys())[0] 
                                target_node = self.zone_nodes.get(node_id_to_spawn_in)
                                if target_node: target_node.trigger_manual_spawn()
                            except IndexError: # Si no hay zonas registradas
                                print("ADVERTENCIA: No hay zonas para spawnear vehículo manualmente.")
                    elif event.key == pygame.K_TAB: # TAB para mostrar/ocultar panel de info
                        self.info_panel.toggle_expansion()

    def render(self):
        """Renderiza la GUI según el estado actual (menú o simulación)."""
        if self.game_state == MainGUI.STATE_MENU:
            self.main_menu.draw(self.screen)
        elif self.game_state == MainGUI.STATE_SIMULATION:
            # 1. Dibujar el fondo del mapa del juego
            if self.game_map_background_image:
                self.screen.blit(self.game_map_background_image, (0,0))
            else: # Fallback si la imagen del mapa no cargó
                fallback_map_color = Theme.COLOR_BACKGROUND # Un color de fondo genérico
                if hasattr(Theme, 'COLOR_GRASS'): fallback_map_color = Theme.COLOR_GRASS
                self.screen.fill(fallback_map_color) 
            
            # 2. Dibujar elementos de cada zona (actualmente solo semáforos)
            for node in self.zone_nodes.values():
                node.draw_zone_elements(self.screen) # Pasa la pantalla principal
            
            # 3. Dibujar vehículos (se dibujan encima del fondo y semáforos)
            for node in self.zone_nodes.values():
                for vehicle in node.get_drawable_vehicles():
                    vehicle.draw(self.screen) # Vehicle.draw usa coordenadas globales
            
            # 4. Dibujar el panel de información (encima de todo)
            # Recopilar métricas específicas de la GUI para el panel
            active_vehicle_count = sum(len(node.get_drawable_vehicles()) for node in self.zone_nodes.values())
            total_max_vehicles_estimate = sum(node.max_vehicles_in_zone for node in self.zone_nodes.values())
            total_pending_spawns = 0
            if self.zone_nodes:
                 total_pending_spawns = sum(node.get_pending_spawn_count() for node in self.zone_nodes.values())

            gui_panel_metrics = {
                 "max_vehicles": f"~{total_max_vehicles_estimate}", 
                 "actual_fps": self.actual_fps, "target_fps": self.fps,
                 "pending_spawns": total_pending_spawns, 
                 "current_vehicle_count": active_vehicle_count 
            }
            self.info_panel.draw(self.screen, gui_panel_metrics)
        
        pygame.display.flip() # Actualizar toda la pantalla

    async def run_gui_loop(self):
        """Bucle principal asíncrono de la GUI."""
        loop = asyncio.get_running_loop()
        target_frame_duration = 1.0 / self.fps
        simulation_active_in_gui = False # Para rastrear si la simulación está visible

        while self.running:
            frame_start_time = loop.time()
            
            self.handle_events() 
            if not self.running: break # Salir si self.running se puso a False
            
            # Lógica para iniciar/detener el conteo de pasos de simulación en métricas
            if self.game_state == MainGUI.STATE_SIMULATION:
                if not simulation_active_in_gui and self.metrics_client: 
                    self.metrics_client.log_event("Vista de simulación iniciada.")
                simulation_active_in_gui = True
                if self.metrics_client: self.metrics_client.simulation_step_start()
            else: # Estamos en el menú
                if simulation_active_in_gui and self.metrics_client: 
                     self.metrics_client.log_event("Vista de simulación pausada/detenida (menú).")
                simulation_active_in_gui = False

            self.render() # Dibujar el estado actual
            
            if self.game_state == MainGUI.STATE_SIMULATION and self.metrics_client:
                self.metrics_client.simulation_step_end()

            # Control de FPS
            elapsed_time = loop.time() - frame_start_time
            sleep_time = target_frame_duration - elapsed_time
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            
            # Calcular FPS real
            final_frame_time = loop.time() - frame_start_time
            self.actual_fps = 1.0 / final_frame_time if final_frame_time > 0 else float('inf')
        
        pygame.quit() # Limpiar Pygame al salir
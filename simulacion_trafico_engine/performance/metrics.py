# simulacion_trafico_engine/performance/metrics.py
import logging
import json
import os
import time # Para time.monotonic() en el cálculo de tiempos de espera
from datetime import datetime # Para timestamps en nombres de archivo
from typing import Dict, Any, List, Optional # Tipos estándar

# --- Integración Opcional con Prometheus ---
# Intenta importar las librerías de Prometheus. Si no están disponibles,
# se definen clases dummy para que el resto del código no falle y la funcionalidad
# de Prometheus simplemente se deshabilite.
try:
    from prometheus_client import Counter, Gauge, start_http_server, CollectorRegistry
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Definición de clases dummy si prometheus_client no está instalado
    class Counter: 
        def __init__(self, *args, **kwargs): pass
        def inc(self, amount: float = 1): pass
    class Gauge:
        def __init__(self, *args, **kwargs): pass
        def set(self, value: float): pass
        def inc(self, amount: float = 1): pass
        def dec(self, amount: float = 1): pass
    class CollectorRegistry: pass # No necesita métodos dummy para este uso
    def start_http_server(*args, **kwargs): pass # Función dummy

class TrafficMetrics:
    """
    Clase responsable de recolectar, gestionar y exportar métricas de la simulación de tráfico.
    Puede registrar eventos como spawns de vehículos, cambios en semáforos, tiempos de espera, etc.
    Soporta la salida de métricas a archivos JSON, logs de texto, y opcionalmente a un servidor Prometheus.
    """

    def __init__(self, output_dir: str = "metrics_output", 
                 enable_prometheus: bool = False, prometheus_port: int = 8000):
        """
        Inicializa el sistema de métricas.
        Args:
            output_dir (str, optional): Directorio donde se guardarán los archivos de log y JSON de métricas.
                                        Por defecto es "metrics_output".
            enable_prometheus (bool, optional): Si es True, intenta habilitar la exportación de métricas a Prometheus.
                                                Requiere que `prometheus_client` esté instalado. Por defecto es False.
            prometheus_port (int, optional): Puerto en el que el servidor HTTP de Prometheus escuchará si está habilitado.
                                             Por defecto es 8000.
        """
        # --- Configuración del Directorio de Salida y Archivo de Log ---
        self.output_dir: str = output_dir
        if not os.path.exists(self.output_dir): # Crear directorio si no existe
            try:
                os.makedirs(self.output_dir)
            except OSError as e:
                print(f"ERROR: No se pudo crear el directorio de salida de métricas '{self.output_dir}': {e}")
                # Considerar un fallback o lanzar una excepción si el directorio es crítico.

        # Configurar el archivo de log con un timestamp para unicidad.
        self.log_file: str = os.path.join(self.output_dir, f"simulation_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        
        # Limpiar handlers de logging existentes para evitar duplicados si se reinicializa.
        # Esto es útil en entornos de desarrollo o pruebas donde el módulo puede recargarse.
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        # Configurar el logging básico para escribir a archivo.
        logging.basicConfig(filename=self.log_file, level=logging.INFO,
                            format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

        # --- Inicialización de Datos de Métricas Internas ---
        # Diccionario principal para almacenar los contadores y valores de las métricas.
        self.metrics_data: Dict[str, Any] = {
            "simulation_start_time_iso": datetime.now().isoformat(),
            "vehicle_spawn_count": 0,
            "vehicle_despawn_count": 0,
            "current_vehicle_count": 0,
            "average_vehicle_speed_px_frame": 0.0,
            "total_vehicle_wait_time_seconds": 0.0,
            "simulation_time_steps": 0,
            "traffic_light_changes": 0,
        }
        # Acumuladores temporales para calcular la velocidad promedio por frame/step.
        self.vehicle_speeds_sum_current_frame: float = 0.0
        self.vehicle_count_current_frame_for_speed: int = 0
        # Diccionario para rastrear el tiempo de inicio de espera de cada vehículo.
        # Clave: vehicle_id (str), Valor: tiempo monotónico de inicio de espera (float).
        self.vehicle_wait_times_start: Dict[str, float] = {} 

        # --- Configuración Opcional de Prometheus ---
        self.enable_prometheus: bool = enable_prometheus and PROMETHEUS_AVAILABLE
        if self.enable_prometheus:
            self.registry = CollectorRegistry() # Registro para las métricas de Prometheus.
            # Definición de las métricas de Prometheus (Contadores y Gauges).
            self.prom_vehicle_spawn_count = Counter('traffic_vehicle_spawn_total', 'Total de vehículos generados', registry=self.registry)
            self.prom_vehicle_despawn_count = Counter('traffic_vehicle_despawn_total', 'Total de vehículos eliminados', registry=self.registry)
            self.prom_current_vehicle_count = Gauge('traffic_current_vehicles', 'Número actual de vehículos en simulación', registry=self.registry)
            self.prom_average_vehicle_speed = Gauge('traffic_average_vehicle_speed_px_frame', 'Velocidad promedio de vehículos (píxeles/frame)', registry=self.registry)
            self.prom_traffic_light_changes = Counter('traffic_light_changes_total', 'Total de cambios de estado de semáforos', registry=self.registry)
            self.prom_total_wait_time = Gauge('traffic_total_vehicle_wait_seconds', 'Tiempo total de espera acumulado por los vehículos (segundos)', registry=self.registry)
            
            try: # Intentar iniciar el servidor HTTP para Prometheus.
                start_http_server(prometheus_port, registry=self.registry)
                self.log_event(f"Servidor de métricas Prometheus iniciado en el puerto {prometheus_port}")
            except Exception as e: 
                self.log_event(f"Fallo al iniciar el servidor Prometheus en el puerto {prometheus_port}: {e}", "error")
                self.enable_prometheus = False # Deshabilitar si no se puede iniciar.
        
        self.log_event(f"Cliente TrafficMetrics inicializado. Logs en: {self.log_file}")

    # --- Sección: Registro de Eventos y Métricas ---
    def log_event(self, message: str, level: str = "info"):
        """
        Registra un mensaje en el archivo de log y lo imprime en la consola.
        Args:
            message (str): El mensaje a registrar.
            level (str, optional): Nivel de logging ("info", "warning", "error"). Por defecto "info".
        """
        if level.lower() == "info": logging.info(message)
        elif level.lower() == "warning": logging.warning(message)
        elif level.lower() == "error": logging.error(message)
        else: logging.log(logging.INFO, f"[{level.upper()}] {message}") # Nivel desconocido, loguear como INFO
        
        # También imprimir en consola para visibilidad inmediata.
        print(f"[{level.upper() if level in ['info', 'warning', 'error'] else 'LOG'}] {message}")

    def vehicle_spawned(self, vehicle_id: str):
        """Registra el evento de un vehículo generado (spawn)."""
        self.metrics_data["vehicle_spawn_count"] += 1
        self._update_current_vehicle_count() # Actualizar conteo actual.
        if self.enable_prometheus: self.prom_vehicle_spawn_count.inc()
        # self.log_event(f"Vehículo {vehicle_id} generado.") # Puede ser muy verboso, opcional.

    def vehicle_despawned(self, vehicle_id: str):
        """Registra el evento de un vehículo eliminado (despawn)."""
        self.metrics_data["vehicle_despawn_count"] += 1
        self._update_current_vehicle_count()
        # Si el vehículo estaba esperando y es eliminado, finalizar su tiempo de espera.
        if vehicle_id in self.vehicle_wait_times_start:
            self.vehicle_stopped_waiting(vehicle_id) 
        if self.enable_prometheus: self.prom_vehicle_despawn_count.inc()
        # self.log_event(f"Vehículo {vehicle_id} eliminado.") # Puede ser verboso.
    
    def _update_current_vehicle_count(self):
        """Método privado para actualizar el contador de vehículos actualmente en la simulación."""
        count = self.metrics_data["vehicle_spawn_count"] - self.metrics_data["vehicle_despawn_count"]
        self.metrics_data["current_vehicle_count"] = count
        if self.enable_prometheus: self.prom_current_vehicle_count.set(count)

    def traffic_light_changed(self, light_id: str, new_state: str):
        """Registra un cambio de estado en un semáforo."""
        self.metrics_data["traffic_light_changes"] += 1
        if self.enable_prometheus: self.prom_traffic_light_changes.inc()
        # self.log_event(f"Semáforo {light_id} cambió a {new_state}.") # Puede ser verboso.

    def vehicle_started_waiting(self, vehicle_id: str):
        """Registra el inicio del tiempo de espera para un vehículo (ej. en semáforo rojo)."""
        if vehicle_id not in self.vehicle_wait_times_start: # Solo registrar si no estaba ya esperando.
            self.vehicle_wait_times_start[vehicle_id] = time.monotonic() # Usar tiempo monotónico para duraciones.

    def vehicle_stopped_waiting(self, vehicle_id: str):
        """Registra el fin del tiempo de espera para un vehículo y acumula la duración."""
        if vehicle_id in self.vehicle_wait_times_start:
            wait_duration = time.monotonic() - self.vehicle_wait_times_start[vehicle_id]
            self.metrics_data["total_vehicle_wait_time_seconds"] += wait_duration
            if self.enable_prometheus: 
                self.prom_total_wait_time.set(self.metrics_data["total_vehicle_wait_time_seconds"])
            del self.vehicle_wait_times_start[vehicle_id] # Eliminar entrada para evitar doble conteo.

    def accumulate_vehicle_speed(self, speed: float):
        """Acumula la velocidad de un vehículo en el frame/step actual para calcular el promedio."""
        self.vehicle_speeds_sum_current_frame += speed
        self.vehicle_count_current_frame_for_speed += 1

    # --- Sección: Gestión de Pasos de Simulación ---
    def simulation_step_start(self):
        """
        Se llama al inicio de cada paso/frame de simulación.
        Resetea acumuladores por frame.
        """
        self.vehicle_speeds_sum_current_frame = 0.0
        self.vehicle_count_current_frame_for_speed = 0

    def simulation_step_end(self):
        """
        Se llama al final de cada paso/frame de simulación.
        Incrementa el contador de pasos y calcula métricas agregadas como la velocidad promedio.
        """
        self.metrics_data["simulation_time_steps"] += 1
        self._update_current_vehicle_count() # Asegurar que el conteo de vehículos esté actualizado.
        
        # Calcular velocidad promedio para este paso.
        if self.vehicle_count_current_frame_for_speed > 0:
            avg_speed = self.vehicle_speeds_sum_current_frame / self.vehicle_count_current_frame_for_speed
            self.metrics_data["average_vehicle_speed_px_frame"] = avg_speed
            if self.enable_prometheus: self.prom_average_vehicle_speed.set(avg_speed)
        else: # Si no hubo vehículos para promediar velocidad.
            self.metrics_data["average_vehicle_speed_px_frame"] = 0.0
            if self.enable_prometheus: self.prom_average_vehicle_speed.set(0.0)

    # --- Sección: Acceso y Exportación de Métricas ---
    def get_metrics(self) -> Dict[str, Any]:
        """Devuelve una copia del diccionario de métricas actual."""
        return self.metrics_data.copy()

    def save_metrics_to_file(self, filename_suffix: str = ""):
        """
        Guarda el estado actual de las métricas en un archivo JSON.
        Args:
            filename_suffix (str, optional): Sufijo para añadir al nombre del archivo (antes del timestamp).
                                             Por defecto es una cadena vacía.
        """
        # Asegurar que se contabilicen los tiempos de espera de vehículos que aún están esperando
        # cuando la simulación termina. Esto podría no ser perfectamente preciso si la simulación
        # termina abruptamente, pero es un mejor esfuerzo.
        for v_id in list(self.vehicle_wait_times_start.keys()): # Usar list() para poder modificar el dict.
             self.vehicle_stopped_waiting(v_id)

        # Actualizar el tiempo de finalización de la simulación en los datos de métricas.
        self.metrics_data["simulation_end_time_iso"] = datetime.now().isoformat()

        # Construir la ruta completa del archivo de salida.
        filepath = os.path.join(
            self.output_dir, 
            f"sim_metrics_{filename_suffix}{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.metrics_data, f, indent=4) # Usar indent=4 para un JSON legible.
            self.log_event(f"Métricas guardadas en: {filepath}")
        except Exception as e:
            self.log_event(f"Error guardando métricas en archivo '{filepath}': {e}", "error")

    def close(self):
        """
        Cierra el cliente de métricas. Principalmente guarda las métricas finales.
        """
        self.save_metrics_to_file("final_") # Sufijo "final_" para el archivo de cierre.
        self.log_event("Cliente TrafficMetrics cerrado. Métricas finales guardadas.")
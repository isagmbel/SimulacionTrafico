# performance/metrics.py
import logging
import json
import os
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

# Optional: prometheus_client integration
try:
    from prometheus_client import Counter, Gauge, start_http_server, CollectorRegistry
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Define dummy classes if prometheus_client is not available, so type hints don't break
    class Counter: pass
    class Gauge: pass


class TrafficMetrics:
    def __init__(self, output_dir: str = "metrics_output", 
                 enable_prometheus: bool = False, prometheus_port: int = 8000):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        self.log_file = os.path.join(self.output_dir, f"simulation_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        # Remove any existing handlers before adding a new one to avoid duplicate logs if re-initialized
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        logging.basicConfig(filename=self.log_file, level=logging.INFO,
                            format='%(asctime)s - %(levelname)s - %(message)s')

        self.metrics_data: Dict[str, Any] = {
            "vehicle_spawn_count": 0,
            "vehicle_despawn_count": 0,
            "current_vehicle_count": 0,
            "average_vehicle_speed_px_frame": 0.0,
            "total_vehicle_wait_time_seconds": 0.0,
            "simulation_time_steps": 0,
            "traffic_light_changes": 0,
        }
        self.vehicle_speeds_sum_current_frame: float = 0.0
        self.vehicle_count_current_frame_for_speed: int = 0
        self.vehicle_wait_times_start: Dict[str, float] = {} # vehicle_id: start_wait_time (monotonic)

        self.enable_prometheus = enable_prometheus and PROMETHEUS_AVAILABLE
        if self.enable_prometheus:
            self.registry = CollectorRegistry()
            self.prom_vehicle_spawn_count = Counter('traffic_vehicle_spawn_total', 'Total vehicles spawned', registry=self.registry)
            self.prom_vehicle_despawn_count = Counter('traffic_vehicle_despawn_total', 'Total vehicles despawned', registry=self.registry)
            self.prom_current_vehicle_count = Gauge('traffic_current_vehicles', 'Current vehicles in simulation', registry=self.registry)
            self.prom_average_vehicle_speed = Gauge('traffic_average_vehicle_speed_px_frame', 'Avg speed (pixels/frame)', registry=self.registry)
            self.prom_traffic_light_changes = Counter('traffic_light_changes_total', 'Total traffic light changes', registry=self.registry)
            self.prom_total_wait_time = Gauge('traffic_total_vehicle_wait_seconds', 'Total wait time for vehicles', registry=self.registry)
            try:
                start_http_server(prometheus_port, registry=self.registry)
                self.log_event(f"Prometheus metrics server started on port {prometheus_port}")
            except Exception as e: # Catch specific OSError if port is in use, etc.
                self.log_event(f"Failed to start Prometheus server on port {prometheus_port}: {e}", "error")
                self.enable_prometheus = False
        
        self.log_event("TrafficMetrics initialized.")

    def log_event(self, message: str, level: str = "info"):
        if level == "info": logging.info(message)
        elif level == "warning": logging.warning(message)
        elif level == "error": logging.error(message)
        print(f"[{level.upper()}] {message}") # Console output

    def vehicle_spawned(self, vehicle_id: str):
        self.metrics_data["vehicle_spawn_count"] += 1
        self._update_current_vehicle_count()
        if self.enable_prometheus: self.prom_vehicle_spawn_count.inc()
        self.log_event(f"Vehicle {vehicle_id} spawned.")

    def vehicle_despawned(self, vehicle_id: str):
        self.metrics_data["vehicle_despawn_count"] += 1
        self._update_current_vehicle_count()
        if vehicle_id in self.vehicle_wait_times_start: # Clear wait time if despawned while waiting
            self.vehicle_stopped_waiting(vehicle_id) # Record final wait
            del self.vehicle_wait_times_start[vehicle_id]
        if self.enable_prometheus: self.prom_vehicle_despawn_count.inc()
        self.log_event(f"Vehicle {vehicle_id} despawned.")
    
    def _update_current_vehicle_count(self):
        count = self.metrics_data["vehicle_spawn_count"] - self.metrics_data["vehicle_despawn_count"]
        self.metrics_data["current_vehicle_count"] = count
        if self.enable_prometheus: self.prom_current_vehicle_count.set(count)


    def traffic_light_changed(self, light_id: str, new_state: str):
        self.metrics_data["traffic_light_changes"] += 1
        if self.enable_prometheus: self.prom_traffic_light_changes.inc()
        self.log_event(f"Traffic light {light_id} changed to {new_state}")

    def vehicle_started_waiting(self, vehicle_id: str):
        if vehicle_id not in self.vehicle_wait_times_start:
            self.vehicle_wait_times_start[vehicle_id] = time.monotonic()
            # self.log_event(f"Vehicle {vehicle_id} started waiting.") # Can be noisy

    def vehicle_stopped_waiting(self, vehicle_id: str):
        if vehicle_id in self.vehicle_wait_times_start:
            wait_duration = time.monotonic() - self.vehicle_wait_times_start[vehicle_id]
            self.metrics_data["total_vehicle_wait_time_seconds"] += wait_duration
            # self.log_event(f"Vehicle {vehicle_id} stopped waiting after {wait_duration:.2f}s.") # Can be noisy
            if self.enable_prometheus: self.prom_total_wait_time.set(self.metrics_data["total_vehicle_wait_time_seconds"])
            del self.vehicle_wait_times_start[vehicle_id] # Remove after processing

    def accumulate_vehicle_speed(self, speed: float):
        self.vehicle_speeds_sum_current_frame += speed
        self.vehicle_count_current_frame_for_speed += 1

    def simulation_step_start(self):
        # Reset per-frame accumulators
        self.vehicle_speeds_sum_current_frame = 0.0
        self.vehicle_count_current_frame_for_speed = 0

    def simulation_step_end(self):
        self.metrics_data["simulation_time_steps"] += 1
        self._update_current_vehicle_count() # Ensure count is up-to-date
        
        if self.vehicle_count_current_frame_for_speed > 0:
            avg_speed = self.vehicle_speeds_sum_current_frame / self.vehicle_count_current_frame_for_speed
            self.metrics_data["average_vehicle_speed_px_frame"] = avg_speed
            if self.enable_prometheus: self.prom_average_vehicle_speed.set(avg_speed)
        else:
            self.metrics_data["average_vehicle_speed_px_frame"] = 0.0
            if self.enable_prometheus: self.prom_average_vehicle_speed.set(0.0)


    def get_metrics(self) -> Dict[str, Any]:
        return self.metrics_data.copy()

    def save_metrics_to_file(self, filename_suffix: str = ""):
        # Ensure all vehicles that were waiting but simulation ends, have their wait time accounted for
        # This might not be perfectly accurate if sim ends abruptly
        for v_id in list(self.vehicle_wait_times_start.keys()):
             self.vehicle_stopped_waiting(v_id)

        filepath = os.path.join(self.output_dir, f"sim_metrics_{filename_suffix}{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        try:
            with open(filepath, 'w') as f:
                json.dump(self.metrics_data, f, indent=4)
            self.log_event(f"Metrics saved to {filepath}")
        except Exception as e:
            self.log_event(f"Error saving metrics to file: {e}", "error")

    def close(self):
        self.save_metrics_to_file("final_")
        self.log_event("TrafficMetrics closed. Final metrics saved.")
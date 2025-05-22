# simulacion_trafico_engine/orchestrator.py
import asyncio
import json
import os
import sys # Though not directly used here, good to keep if sub-functions might need it
import traceback
from typing import Dict, List, Optional

from .node.zone_node import ZoneNode
from .ui.main_gui import MainGUI
from .distribution.rabbitclient import RabbitMQClient
from .performance.metrics import TrafficMetrics

async def _run_single_zone_node_simulation(node: ZoneNode):
    """Helper async function to run simulation for a single ZoneNode."""
    try:
        await node.setup_rabbitmq_subscriptions()
        while node.is_running:
            await node.update_tick()
            # Adjust sleep time for desired simulation speed vs. GUI responsiveness
            # 1/60 or 1/30 are common for simulation ticks if GUI runs at 30 FPS
            await asyncio.sleep(1 / 30) # e.g., 30 simulation steps per second
    except asyncio.CancelledError:
        print(f"[Orchestrator] ZoneNode {node.zone_id} task cancelled.")
    except Exception as e:
        print(f"[Orchestrator] ERROR in ZoneNode {node.zone_id} simulation: {e}")
        traceback.print_exc()
    finally:
        node.stop() # Ensure node is stopped on exit or error

class SimulationOrchestrator:
    def __init__(self, config_filename: str = "city_layout.json"):
        self.config_filename = config_filename
        self.city_config: Optional[Dict] = None
        self.rabbit_client: Optional[RabbitMQClient] = None
        self.metrics_client: Optional[TrafficMetrics] = None
        self.main_gui: Optional[MainGUI] = None
        self.zone_nodes: List[ZoneNode] = []
        self.node_simulation_tasks: List[asyncio.Task] = []

    async def _load_config(self) -> bool:
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # Up one level to project root for config
        config_path = os.path.join(script_dir, "config", self.config_filename)
        
        if not os.path.exists(config_path):
            print(f"CRITICAL ERROR: Config not found: {config_path}")
            return False
        try:
            with open(config_path, 'r') as f:
                self.city_config = json.load(f)
            print(f"City config '{self.city_config.get('city_name', 'Unnamed City')}' loaded from {config_path}.")
            return True
        except Exception as e:
            print(f"CRITICAL ERROR: Loading config {config_path}: {e}")
            return False

    async def _initialize_rabbitmq(self) -> bool:
        if not self.city_config: return False
        
        self.rabbit_client = RabbitMQClient(
            exchange_name=self.city_config.get("rabbitmq_exchange", "city_traffic_exchange")
        )
        try:
            await self.rabbit_client.connect_async()
            print("[Orchestrator] RabbitMQ client connected successfully.")
            return True
        except Exception as e:
            print(f"[Orchestrator] WARNING: Failed to connect to RabbitMQ: {e}. Migrations might not work.")
            # Decide if RabbitMQ is critical for startup. If so, return False.
            # For now, let's allow continuing without it, but migrations will fail.
            return True # Or False if critical

    def _initialize_metrics(self):
        self.metrics_client = TrafficMetrics(output_dir="metrics_output") # Consider making dir configurable

    def _initialize_gui(self):
        if not self.city_config or not self.metrics_client: return False
        self.main_gui = MainGUI(self.city_config, self.metrics_client)
        return True

    def _initialize_zone_nodes(self) -> bool:
        if not self.city_config or not self.rabbit_client or not self.metrics_client or not self.main_gui:
            print("[Orchestrator] CRITICAL: Cannot initialize zone nodes due to missing components.")
            return False

        self.zone_nodes = []
        for zone_conf in self.city_config.get("zones", []):
            if not all(k in zone_conf for k in ["id", "bounds"]):
                print(f"WARNING: Skipping invalid zone config: {zone_conf}")
                continue
            
            node = ZoneNode(
                zone_id=zone_conf["id"],
                zone_config=zone_conf,
                rabbit_client=self.rabbit_client,
                metrics_client=self.metrics_client,
                global_city_config=self.city_config
            )
            self.zone_nodes.append(node)
            self.main_gui.register_zone_node(node)
        
        if not self.zone_nodes:
            print("CRITICAL ERROR: No valid zones loaded from config.")
            return False
        return True

    async def setup(self) -> bool:
        """Sets up all components of the simulation."""
        if not await self._load_config(): return False
        if not await self._initialize_rabbitmq(): 
            # Consider if this should be a hard stop
            pass 
        self._initialize_metrics()
        if not self._initialize_gui(): return False
        if not self._initialize_zone_nodes(): return False
        
        print("[Orchestrator] All components initialized successfully.")
        return True

    async def run(self):
        """Runs the main simulation loop."""
        if not self.main_gui or not self.zone_nodes:
            print("[Orchestrator] CRITICAL: Simulation cannot run, setup failed or not called.")
            return

        # Create tasks for each zone node simulation
        self.node_simulation_tasks = [
            asyncio.create_task(_run_single_zone_node_simulation(node))
            for node in self.zone_nodes
        ]
        # Create task for the GUI loop
        gui_task = asyncio.create_task(self.main_gui.run_gui_loop())

        try:
            # Wait for the GUI task to complete (e.g., user closes the window)
            await gui_task
        except asyncio.CancelledError:
            print("[Orchestrator] GUI task was cancelled.")
        except Exception as e:
            print(f"[Orchestrator] Error during GUI execution: {e}")
            traceback.print_exc()
        finally:
            await self._shutdown()

    async def _shutdown(self):
        """Handles the graceful shutdown of simulation components."""
        print("[Orchestrator] Shutdown initiated...")

        # Stop all zone nodes
        for node in self.zone_nodes:
            node.stop() # Sets node.is_running to False

        # Wait for node simulation tasks to finish or timeout
        if self.node_simulation_tasks:
            try:
                # Give a timeout for nodes to finish their current tick and exit their loops
                done, pending = await asyncio.wait(
                    self.node_simulation_tasks, 
                    timeout=5.0, 
                    return_when=asyncio.ALL_COMPLETED
                )
                for task in pending:
                    task.cancel() # Cancel any tasks that didn't finish in time
                    print(f"[Orchestrator] ZoneNode task {task.get_name()} cancelled on shutdown.")
                # Await cancelled tasks to allow them to process CancelledError
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)

            except asyncio.TimeoutError:
                print("[Orchestrator] Node shutdown timed out. Some nodes might not have stopped cleanly.")
            except Exception as e:
                print(f"[Orchestrator] Error during node simulation task shutdown: {e}")
        
        # Disconnect RabbitMQ
        if self.rabbit_client and self.rabbit_client.async_connection and \
           not self.rabbit_client.async_connection.is_closed:
            try:
                await self.rabbit_client.disconnect_async()
                print("[Orchestrator] RabbitMQ client disconnected.")
            except Exception as e:
                print(f"[Orchestrator] Error disconnecting RabbitMQ: {e}")
        
        # Close metrics (e.g., save final data)
        if self.metrics_client:
            try:
                self.metrics_client.close()
                print("[Orchestrator] Metrics client closed.")
            except Exception as e:
                print(f"[Orchestrator] Error closing metrics client: {e}")

        print("[Orchestrator] Shutdown complete.")
# main.py (Project Root)
import asyncio
import json
import os
import sys
from typing import Dict, List

from simulacion_trafico_engine.node.zone_node import ZoneNode
from simulacion_trafico_engine.ui.main_gui import MainGUI
from simulacion_trafico_engine.distribution.rabbitclient import RabbitMQClient
from simulacion_trafico_engine.performance.metrics import TrafficMetrics

async def run_zone_node_simulation(node: ZoneNode):
    try:
        # --- AÑADIDO: Configurar suscripciones RabbitMQ para el nodo ---
        await node.setup_rabbitmq_subscriptions()
        # --- FIN AÑADIDO ---
        while node.is_running:
            await node.update_tick()
            await asyncio.sleep(1/30) 
    except asyncio.CancelledError:
        print(f"[Orchestrator] ZoneNode {node.zone_id} task cancelled.")
    except Exception as e:
        print(f"[Orchestrator] ERROR in ZoneNode {node.zone_id} simulation: {e}")
        import traceback
        traceback.print_exc()
    finally:
        node.stop()

async def main_orchestrator():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config", "city_layout.json")
    if not os.path.exists(config_path):
        print(f"CRITICAL ERROR: Config not found: {config_path}"); return
    try:
        with open(config_path, 'r') as f: city_config = json.load(f)
    except Exception as e:
        print(f"CRITICAL ERROR: Loading config {config_path}: {e}"); return
    print(f"City config '{city_config.get('city_name', 'City')}' loaded.")

    rabbit_client = RabbitMQClient(
        exchange_name=city_config.get("rabbitmq_exchange", "city_traffic_exchange") # Usar config o default
    )
    # --- CONECTAR RABBITMQ ANTES DE CREAR NODOS QUE LO USAN ---
    try:
        await rabbit_client.connect_async()
        print("[Orchestrator] RabbitMQ client connected successfully.")
    except Exception as e:
        print(f"[Orchestrator] CRITICAL: Failed to connect to RabbitMQ: {e}. Simulation cannot proceed with migrations.")
        # Podrías decidir salir o continuar sin funcionalidad de migración.
        # Por ahora, continuaremos, pero las migraciones no funcionarán.
        # return # Descomentar para salir si RabbitMQ es esencial desde el inicio.
    # --- FIN CONEXIÓN RABBITMQ ---

    metrics_client = TrafficMetrics(output_dir="metrics_output")
    main_gui = MainGUI(city_config, metrics_client)
    zone_nodes: List[ZoneNode] = []

    for zone_conf in city_config.get("zones", []):
        # ... (validación de zona_conf como antes) ...
        if not all(k in zone_conf for k in ["id", "bounds"]): # Adjacencies es opcional para el borde
            print(f"WARNING: Skipping zone config: {zone_conf}")
            continue
        node = ZoneNode(zone_conf["id"], zone_conf, rabbit_client, metrics_client, city_config)
        zone_nodes.append(node)
        main_gui.register_zone_node(node)

    if not zone_nodes: print("CRITICAL ERROR: No zones loaded."); return

    node_simulation_tasks = [asyncio.create_task(run_zone_node_simulation(node)) for node in zone_nodes]
    gui_task = asyncio.create_task(main_gui.run_gui_loop())

    try:
        await gui_task 
    except asyncio.CancelledError: print("[Orchestrator] GUI task cancelled.")
    finally:
        print("[Orchestrator] Shutdown initiated...")
        for node in zone_nodes: node.stop()
        try:
            await asyncio.wait_for(asyncio.gather(*node_simulation_tasks, return_exceptions=True), timeout=5.0)
        except asyncio.TimeoutError: print("[Orchestrator] Node shutdown timeout.")
        except Exception as e: print(f"[Orchestrator] Node shutdown error: {e}")
        
        if rabbit_client.async_connection and not rabbit_client.async_connection.is_closed:
            await rabbit_client.disconnect_async()
        if metrics_client: metrics_client.close()
        print("[Orchestrator] Shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main_orchestrator())
    except KeyboardInterrupt: print("\n[Orchestrator] Simulation interrupted.")
    except Exception as e:
        print(f"[Orchestrator] Top-level error: {e}"); import traceback; traceback.print_exc()
    finally: print("[Orchestrator] Program exiting.")
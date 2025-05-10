#!/usr/bin/env python3
"""
Traffic Simulation Main Module
"""
import asyncio
import os
import sys


from simulacion_trafico_engine.ui.gui import GUI # MODIFIED
from simulacion_trafico_engine.distribution.rabbitclient import RabbitMQClient # MODIFIED
from simulacion_trafico_engine.performance.metrics import TrafficMetrics # MODIFIED

async def main_async_entrypoint():
    rabbit_client = RabbitMQClient(
        host=os.getenv("RABBITMQ_HOST", "localhost"),
        port=int(os.getenv("RABBITMQ_PORT", "5672")),
        username=os.getenv("RABBITMQ_USER", "guest"),
        password=os.getenv("RABBITMQ_PASS", "guest"),
        exchange_name="traffic_sim_exchange"
    )
    try:
        await rabbit_client.connect_async()
        print("Async connection to RabbitMQ established.")
    except Exception as e:
        print(f"Initial async connection to RabbitMQ failed: {e}. Client will attempt to connect on first use.")

    # Ensure the output_dir for metrics is correctly relative to where main.py is.
    # If main.py is at the project root, "metrics_output" will create it there.
    metrics = TrafficMetrics(
        output_dir="metrics_output",
        enable_prometheus=False,
        prometheus_port=8001
    )

    simulation_gui = GUI(
        width=1280, height=720, fps=30,
        rabbit_client=rabbit_client,
        metrics_client=metrics
    )

    try:
        await simulation_gui.run()
    finally:
        if rabbit_client and rabbit_client.async_connection and not rabbit_client.async_connection.is_closed:
            await rabbit_client.disconnect_async()
            print("Async connection to RabbitMQ closed.")
        if metrics:
            metrics.close()
        print("Simulation shutdown complete.")

if __name__ == "__main__":
    if sys.platform == "win32" and sys.version_info >= (3, 8):
        pass

    try:
        asyncio.run(main_async_entrypoint())
    except KeyboardInterrupt:
        print("\nSimulation interrupted by user.")
    except Exception as e:
        print(f"Unhandled critical error in main: {e}")
        import traceback
        traceback.print_exc()
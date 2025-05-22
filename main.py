# main.py (Project Root)
import asyncio
import traceback # Keep for top-level exception handling

# orchestrator
from simulacion_trafico_engine.orchestrator import SimulationOrchestrator

async def main():
    """
    Main entry point for the simulation.
    Initializes and runs the SimulationOrchestrator.
    """
    orchestrator = SimulationOrchestrator(config_filename="city_layout.json")
    
    if await orchestrator.setup():
        await orchestrator.run()
    else:
        print("[Main] Failed to set up the simulation. Exiting.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Main] Simulation interrupted by user (KeyboardInterrupt).")
    except Exception as e:
        print(f"[Main] A top-level error occurred: {e}")
        traceback.print_exc()
    finally:
        print("[Main] Program exiting.")
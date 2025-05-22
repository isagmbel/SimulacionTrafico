# main.py (Punto de entrada principal de la simulación)
import asyncio
import traceback # Para imprimir trazas de error detalladas en caso de excepciones no esperadas

# Importar el orquestador de la simulación desde el motor
from simulacion_trafico_engine.orchestrator import SimulationOrchestrator

async def main():
    """
    Función asíncrona principal que configura y ejecuta la simulación.
    Crea una instancia de SimulationOrchestrator, la configura, y si tiene éxito,
    ejecuta la simulación.
    """
    print("[Main] Iniciando Simulador de Tráfico Rush Hour...")
    
    # Crear una instancia del orquestador.
    # Se puede pasar el nombre del archivo de configuración si es diferente al por defecto.
    orchestrator = SimulationOrchestrator(config_filename="city_layout.json")
    
    # Intentar configurar todos los componentes de la simulación.
    if await orchestrator.setup():
        # Si la configuración fue exitosa, ejecutar la simulación.
        # El control se cederá aquí hasta que la simulación (GUI) termine.
        await orchestrator.run()
    else:
        # Si la configuración falló, informar y salir.
        print("[Main] Falló la configuración de la simulación. El programa terminará.")

if __name__ == "__main__":
    
    try:
        # Ejecutar la corutina main()
        asyncio.run(main())
    except KeyboardInterrupt:
        # Manejar la interrupción por teclado (Ctrl+C) de forma ordenada.
        print("\n[Main] Simulación interrumpida por el usuario (Ctrl+C).")
    except Exception as e:
        # Capturar cualquier otra excepción no manejada a alto nivel.
        print(f"[Main] Ocurrió un error de alto nivel no esperado: {e}")
        traceback.print_exc() # Imprimir la traza completa del error.
    finally:
        # Este bloque se ejecuta siempre, incluso si hay errores o interrupciones.
        print("[Main] Programa terminando.")
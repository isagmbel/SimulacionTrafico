# simulacion_trafico_engine/orchestrator.py
import asyncio
import json
import os
import traceback # Para imprimir trazas de error detalladas
from typing import Dict, List, Optional, Any # Any añadido para city_config

# Importaciones de componentes del motor de simulación
from .node.zone_node import ZoneNode
from .ui.main_gui import MainGUI
from .distribution.rabbitclient import RabbitMQClient
from .performance.metrics import TrafficMetrics

async def _run_single_zone_node_simulation(node: ZoneNode):
    """
    Función auxiliar asíncrona para ejecutar el bucle de simulación de un único ZoneNode.
    Incluye la configuración de suscripciones RabbitMQ y el manejo de excepciones.
    Args:
        node (ZoneNode): El nodo de zona para el cual ejecutar la simulación.
    """
    try:
        # Configurar las suscripciones de RabbitMQ para el nodo antes de iniciar el bucle.
        await node.setup_rabbitmq_subscriptions()
        
        # Bucle principal del nodo: se ejecuta mientras el nodo esté activo.
        while node.is_running:
            await node.update_tick() # Realizar un paso de simulación del nodo.
            # Pausa breve para ceder control y mantener la tasa de simulación deseada.
            # 1/30 implica aproximadamente 30 ticks de simulación por segundo.
            await asyncio.sleep(1 / 30) 
    except asyncio.CancelledError:
        # Manejar la cancelación de la tarea del nodo (ej. durante el apagado).
        print(f"[Orchestrator] Tarea del ZoneNode {node.zone_id} cancelada.")
    except Exception as e:
        # Capturar y registrar cualquier otra excepción que ocurra en la simulación del nodo.
        print(f"[Orchestrator] ERROR en la simulación del ZoneNode {node.zone_id}: {e}")
        traceback.print_exc() # Imprimir la traza completa del error.
    finally:
        # Asegurar que el nodo se detenga (is_running = False) al finalizar o en caso de error.
        node.stop()

class SimulationOrchestrator:
    """
    Clase principal que orquesta la configuración, ejecución y apagado de la simulación de tráfico.
    Gestiona la carga de configuración, la inicialización de componentes (RabbitMQ, GUI, Nodos de Zona, Métricas),
    y el ciclo de vida de las tareas asíncronas de la simulación.
    """
    def __init__(self, config_filename: str = "city_layout.json"):
        """
        Inicializa el orquestador.
        Args:
            config_filename (str, optional): Nombre del archivo de configuración JSON.
                                             Por defecto es "city_layout.json".
        """
        self.config_filename: str = config_filename
        self.city_config: Optional[Dict[str, Any]] = None # Configuración cargada de JSON.
        self.rabbit_client: Optional[RabbitMQClient] = None # Cliente para RabbitMQ.
        self.metrics_client: Optional[TrafficMetrics] = None # Cliente para métricas.
        self.main_gui: Optional[MainGUI] = None             # Interfaz gráfica principal.
        self.zone_nodes: List[ZoneNode] = []                # Lista de nodos de zona activos.
        self.node_simulation_tasks: List[asyncio.Task] = [] # Tareas asyncio para cada nodo.

    async def _load_config(self) -> bool:
        """
        Carga la configuración de la ciudad desde el archivo JSON especificado.
        El archivo de configuración se espera en una carpeta 'config' en la raíz del proyecto.
        Returns:
            bool: True si la configuración se cargó con éxito, False en caso contrario.
        """
        # Determinar la ruta al archivo de configuración.
        # Se asume que 'orchestrator.py' está en 'simulacion_trafico_engine/',
        # y 'config/' está en el directorio padre (raíz del proyecto).
        current_script_path = os.path.dirname(os.path.abspath(__file__))
        project_root_path = os.path.dirname(current_script_path)
        config_path = os.path.join(project_root_path, "config", self.config_filename)
        
        if not os.path.exists(config_path):
            print(f"ERROR CRÍTICO: Archivo de configuración no encontrado en: {config_path}")
            return False
        try:
            with open(config_path, 'r', encoding='utf-8') as f: # Especificar encoding es buena práctica
                self.city_config = json.load(f)
            print(f"Configuración de ciudad '{self.city_config.get('city_name', 'Ciudad Sin Nombre')}' cargada desde {config_path}.")
            return True
        except json.JSONDecodeError as e:
            print(f"ERROR CRÍTICO: Error decodificando JSON en {config_path}: {e}")
            return False
        except Exception as e:
            print(f"ERROR CRÍTICO: Cargando configuración {config_path}: {e}")
            return False

    async def _initialize_rabbitmq(self) -> bool:
        """
        Inicializa y conecta el cliente RabbitMQ.
        La configuración de RabbitMQ (ej. nombre del exchange) se toma de self.city_config.
        Returns:
            bool: True si la conexión fue exitosa o si se decide continuar a pesar de un fallo.
                  False si la conexión falla y se considera crítica para el inicio.
        """
        if not self.city_config: 
            print("ERROR: No se puede inicializar RabbitMQ sin configuración de ciudad cargada.")
            return False
        
        self.rabbit_client = RabbitMQClient(
            exchange_name=self.city_config.get("rabbitmq_exchange", "city_traffic_exchange") # Usar config o default
        )
        try:
            await self.rabbit_client.connect_async()
            print("[Orquestador] Cliente RabbitMQ conectado exitosamente.")
            return True
        except Exception as e:
            # Advertir sobre el fallo pero permitir que la simulación continúe si RabbitMQ no es estrictamente esencial
            # para todas las funcionalidades desde el inicio (ej. si las migraciones son opcionales).
            print(f"[Orquestador] ADVERTENCIA: Fallo al conectar con RabbitMQ: {e}. Las migraciones podrían no funcionar.")
            # Para un error crítico, se podría hacer 'return False' aquí.
            return True # Permitir continuar; ajustar si RabbitMQ es mandatorio.

    def _initialize_metrics(self):
        """Inicializa el cliente de métricas."""
        # La ruta de salida de las métricas podría ser configurable.
        self.metrics_client = TrafficMetrics(output_dir="metrics_output")

    def _initialize_gui(self) -> bool:
        """
        Inicializa la interfaz gráfica principal (MainGUI).
        Requiere que self.city_config y self.metrics_client estén ya inicializados.
        Returns:
            bool: True si la GUI se inicializó con éxito, False en caso contrario.
        """
        if not self.city_config or not self.metrics_client: 
            print("ERROR: No se puede inicializar la GUI sin configuración de ciudad o cliente de métricas.")
            return False
        self.main_gui = MainGUI(self.city_config, self.metrics_client)
        return True

    def _initialize_zone_nodes(self) -> bool:
        """
        Inicializa los nodos de zona (ZoneNode) basados en la configuración de la ciudad.
        Cada nodo se registra con la GUI.
        Requiere que varios componentes (config, rabbit, metrics, gui) estén inicializados.
        Returns:
            bool: True si al menos un nodo de zona se cargó con éxito, False en caso contrario.
        """
        if not self.city_config or not self.rabbit_client or \
           not self.metrics_client or not self.main_gui:
            print("[Orquestador] ERROR CRÍTICO: No se pueden inicializar nodos de zona debido a componentes faltantes.")
            return False

        self.zone_nodes = [] # Limpiar lista por si se llama múltiples veces (aunque no debería)
        for zone_conf in self.city_config.get("zones", []):
            # Validar configuración básica de la zona
            if not all(k in zone_conf for k in ["id", "bounds"]):
                print(f"ADVERTENCIA: Saltando configuración de zona inválida: {zone_conf}")
                continue
            
            node = ZoneNode(
                zone_id=zone_conf["id"],
                zone_config=zone_conf,
                rabbit_client=self.rabbit_client, # Pasar cliente RabbitMQ
                metrics_client=self.metrics_client, # Pasar cliente de métricas
                global_city_config=self.city_config # Pasar configuración global
            )
            self.zone_nodes.append(node)
            self.main_gui.register_zone_node(node) # Registrar nodo en la GUI
        
        if not self.zone_nodes:
            print("ERROR CRÍTICO: No se cargaron zonas válidas desde la configuración.")
            return False
        print(f"[Orquestador] {len(self.zone_nodes)} nodo(s) de zona inicializado(s).")
        return True

    async def setup(self) -> bool:
        """
        Configura todos los componentes necesarios para la simulación.
        Este método debe llamarse antes de `run()`.
        Returns:
            bool: True si toda la configuración fue exitosa, False si algún paso crítico falló.
        """
        print("[Orquestador] Iniciando configuración de la simulación...")
        if not await self._load_config(): return False
        if not await self._initialize_rabbitmq(): 
            # Decidir aquí si la simulación PUEDE continuar sin RabbitMQ.
            # Si es esencial, se debería retornar False.
            print("[Orquestador] Continuando sin conexión RabbitMQ completamente funcional.")
            pass 
        self._initialize_metrics()
        if not self._initialize_gui(): return False # GUI es esencial
        if not self._initialize_zone_nodes(): return False # Nodos de zona son esenciales
        
        print("[Orquestador] Todos los componentes inicializados exitosamente.")
        return True

    async def run(self):
        """
        Ejecuta el bucle principal de la simulación.
        Lanza tareas asíncronas para la GUI y para cada nodo de zona.
        Espera a que la GUI termine (ej. el usuario cierra la ventana) antes de proceder al apagado.
        """
        if not self.main_gui or not self.zone_nodes:
            print("[Orquestador] ERROR CRÍTICO: La simulación no puede ejecutarse. Falló la configuración o no se llamó a setup().")
            return

        print("[Orquestador] Iniciando bucles de simulación y GUI...")
        # Crear tareas asíncronas para la simulación de cada nodo de zona.
        self.node_simulation_tasks = [
            asyncio.create_task(_run_single_zone_node_simulation(node), name=f"SimTask-{node.zone_id}")
            for node in self.zone_nodes
        ]
        # Crear tarea asíncrona para el bucle de la GUI.
        gui_task = asyncio.create_task(self.main_gui.run_gui_loop(), name="GUITask")

        try:
            # Esperar a que la tarea de la GUI complete. 
            # Esto ocurre cuando MainGUI.run_gui_loop() termina (ej. self.running = False).
            await gui_task
        except asyncio.CancelledError:
            print("[Orquestador] Tarea de la GUI cancelada.")
        except Exception as e: # Capturar otras excepciones de la GUI
            print(f"[Orquestador] Error durante la ejecución de la GUI: {e}")
            traceback.print_exc()
        finally:
            # Asegurar que el proceso de apagado se ejecute siempre.
            await self._shutdown()

    async def _shutdown(self):
        """
        Maneja el apagado ordenado de todos los componentes de la simulación.
        Detiene los nodos de zona, espera a que sus tareas terminen, y cierra conexiones.
        """
        print("[Orquestador] Iniciando proceso de apagado...")

        # 1. Señalizar a todos los nodos de zona que deben detenerse.
        for node in self.zone_nodes:
            node.stop() # Esto debería hacer que node.is_running sea False.

        # 2. Esperar a que las tareas de simulación de los nodos terminen.
        if self.node_simulation_tasks:
            print(f"[Orquestador] Esperando a que {len(self.node_simulation_tasks)} tareas de nodos finalicen...")
            try:
                # Esperar a que todas las tareas completen o se alcance el timeout.
                done, pending = await asyncio.wait(
                    self.node_simulation_tasks, 
                    timeout=5.0, # Timeout de 5 segundos para el apagado de nodos.
                    return_when=asyncio.ALL_COMPLETED
                )
                # Cancelar cualquier tarea de nodo que no haya terminado a tiempo.
                for task in pending:
                    task.cancel()
                    print(f"[Orquestador] Tarea de ZoneNode {task.get_name()} cancelada por timeout durante apagado.")
                # Esperar a que las tareas canceladas procesen la CancelledError.
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)

            except asyncio.TimeoutError: # Esto no debería ocurrir con asyncio.wait y return_when=ALL_COMPLETED
                print("[Orquestador] Timeout esperando el apagado de los nodos.")
            except Exception as e:
                print(f"[Orquestador] Error durante el apagado de tareas de nodos: {e}")
        
        # 3. Desconectar el cliente RabbitMQ si está conectado.
        if self.rabbit_client and self.rabbit_client.async_connection and \
           not self.rabbit_client.async_connection.is_closed:
            try:
                await self.rabbit_client.disconnect_async()
                print("[Orquestador] Cliente RabbitMQ desconectado.")
            except Exception as e:
                print(f"[Orquestador] Error desconectando RabbitMQ: {e}")
        
        # 4. Cerrar el cliente de métricas (ej. para guardar datos finales).
        if self.metrics_client:
            try:
                self.metrics_client.close()
                # El log de "Metrics client closed" ya se hace dentro de TrafficMetrics.close()
            except Exception as e:
                print(f"[Orquestador] Error cerrando cliente de métricas: {e}")

        print("[Orquestador] Proceso de apagado completado.")
# Motor de Simulación de Tráfico en Tiempo Real

Este proyecto es una simulación de tráfico en tiempo real que gestiona el flujo de vehículos en un mapa con semáforos y carreteras. El motor es capaz de simular hasta 20 vehículos moviéndose en una intersección, respetando los semáforos y gestionando la generación de vehículos de manera aleatoria.

### Repositorio en GitHub:
```
https://github.com/isagmbel/SimulacionTrafico
```

### Características:
- Simulación de tráfico en un mapa con dos carreteras horizontales y verticales.
- 16 semáforos que controlan el flujo de tráfico en las intersecciones.
- Hasta 20 vehículos generados aleatoriamente en el mapa.
- Los vehículos reaccionan a los semáforos y se mueven de acuerdo con la simulación.
- La simulación se ejecuta en tiempo real con un límite de FPS para asegurar un rendimiento adecuado.

## Requisitos

Para ejecutar este proyecto, necesitas tener instalado lo siguiente:

- Python 3.x
- Pygame (para la visualización y manejo de gráficos)

### Instalación de dependencias

1. **Clonar el repositorio**:
   ```bash
   git clone https://github.com/isagmbel/SimulacionTrafico
   cd SimulacionTrafico
   ```

2. **Crear un entorno virtual** (opcional pero recomendado):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # En Windows usa: venv\Scripts\activate
   ```

3. **Instalar los requisitos**:
   Asegúrate de que tienes los requisitos de Python necesarios instalados:
   ```bash
   pip install -r requirements.txt
   ```

   Esto instalará todas las dependencias necesarias, como `pygame` y otras librerías que pueda necesitar el proyecto.

## Ejecución

Para ejecutar la simulación, simplemente ejecuta el siguiente comando en tu terminal:

```bash
python main.py
```

Esto abrirá una ventana gráfica con la simulación de tráfico. Puedes interactuar con la simulación presionando las siguientes teclas:

- **ESPACIO**: Genera un nuevo vehículo (hasta un máximo de 20).
- **ESC**: Cierra la simulación.

## Estructura del proyecto

```
SimulacionTrafico/
│
├── environment/            # Contiene la lógica del entorno y los objetos (vehículos, semáforos, etc.)
│   ├── Vehicle.py          # Clase para representar los vehículos
│   ├── TrafficLight.py     # Clase para representar los semáforos
│   └── Map.py              # Clase que representa el mapa y la simulación del tráfico
│
├── ui/                     # Contiene la interfaz gráfica del usuario
│   ├── gui.py              # Clase principal de la interfaz gráfica (usando pygame)
│
├── distribution/           # Contiene componentes relacionados con la distribución de datos
│   └── rabbitclient.py     # Cliente RabbitMQ para la comunicación distribuida
│
├── performance/            # Contiene componentes relacionados con el rendimiento y métricas
│   └── metrics.py          # Lógica para la recolección de métricas del rendimiento
│
├── requirements.txt        # Lista de dependencias necesarias
└── README.md               # Info
```

## Contribuciones

Las contribuciones son bienvenidas. Si encuentras un bug o deseas agregar una nueva característica, por favor abre un _issue_ o envía un _pull request_.

## Licencia

Este proyecto está bajo la Licencia MIT. Consulta el archivo `LICENSE` para más detalles.

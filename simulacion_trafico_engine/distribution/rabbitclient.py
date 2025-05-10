import pika
import json
import asyncio
from aio_pika import connect_robust, Message, ExchangeType
from typing import Dict, Any, Callable, List, Optional

class RabbitMQClient:
    """
    Client for handling RabbitMQ connections and communications for the traffic simulation.
    Supports both synchronous and asynchronous operations.
    """
    def __init__(self, host: str = "localhost", port: int = 5672, 
                 username: str = "guest", password: str = "guest", 
                 exchange_name: str = "traffic_exchange"):
        """
        Initialize the RabbitMQ client.
        
        Args:
            host: RabbitMQ server host
            port: RabbitMQ server port
            username: RabbitMQ username
            password: RabbitMQ password
            exchange_name: Name of the exchange to use
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.exchange_name = exchange_name
        
        # Sync connection
        self.connection = None
        self.channel = None
        
        # Async connection
        self.async_connection = None
        self.async_channel = None
        self.async_exchange = None
        
        # Callback handlers
        self.message_handlers = {}
        
    def connect(self) -> None:
        """Establish a synchronous connection to RabbitMQ server."""
        if self.connection is None or self.connection.is_closed:
            credentials = pika.PlainCredentials(self.username, self.password)
            parameters = pika.ConnectionParameters(
                host=self.host,
                port=self.port,
                credentials=credentials
            )
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            
            # Declare exchange
            self.channel.exchange_declare(
                exchange=self.exchange_name,
                exchange_type='topic',
                durable=True
            )
            
            print(f"Connected to RabbitMQ at {self.host}:{self.port}")
    
    async def connect_async(self) -> None:
        """Establish an asynchronous connection to RabbitMQ server."""
        if self.async_connection is None or self.async_connection.is_closed:
            self.async_connection = await connect_robust(
                host=self.host,
                port=self.port,
                login=self.username,
                password=self.password
            )
            self.async_channel = await self.async_connection.channel()
            self.async_exchange = await self.async_channel.declare_exchange(
                name=self.exchange_name,
                type=ExchangeType.TOPIC,
                durable=True
            )
            
            print(f"Async connected to RabbitMQ at {self.host}:{self.port}")
    
    def disconnect(self) -> None:
        """Close the synchronous connection."""
        if self.connection and self.connection.is_open:
            self.connection.close()
            print("Disconnected from RabbitMQ")
    
    async def disconnect_async(self) -> None:
        """Close the asynchronous connection."""
        if self.async_connection and not self.async_connection.is_closed:
            await self.async_connection.close()
            print("Async disconnected from RabbitMQ")
    
    def publish(self, routing_key: str, message: Dict[str, Any]) -> None:
        """
        Publish a message synchronously to the exchange with the specified routing key.
        
        Args:
            routing_key: Routing key for the message
            message: Message data to send (will be converted to JSON)
        """
        if self.channel is None:
            self.connect()
            
        json_message = json.dumps(message)
        self.channel.basic_publish(
            exchange=self.exchange_name,
            routing_key=routing_key,
            body=json_message.encode(),
            properties=pika.BasicProperties(
                content_type='application/json',
                delivery_mode=2  # persistent message
            )
        )
    
    async def publish_async(self, routing_key: str, message: Dict[str, Any]) -> None:
        """
        Publish a message asynchronously to the exchange with the specified routing key.
        
        Args:
            routing_key: Routing key for the message
            message: Message data to send (will be converted to JSON)
        """
        if self.async_exchange is None:
            await self.connect_async()
            
        json_message = json.dumps(message)
        await self.async_exchange.publish(
            Message(
                body=json_message.encode(),
                content_type='application/json',
                delivery_mode=2  # persistent message
            ),
            routing_key=routing_key
        )
    
    def subscribe(self, queue_name: str, routing_keys: List[str], 
                 callback: Callable, auto_ack: bool = True) -> None:
        """
        Subscribe to messages with the specified routing keys.
        
        Args:
            queue_name: Name of the queue to create/use
            routing_keys: List of routing key patterns to subscribe to
            callback: Function to call when a message is received
            auto_ack: Whether to automatically acknowledge messages
        """
        if self.channel is None:
            self.connect()
        
        # Declare queue
        self.channel.queue_declare(queue=queue_name, durable=True)
        
        # Bind queue to exchange with routing keys
        for key in routing_keys:
            self.channel.queue_bind(
                exchange=self.exchange_name,
                queue=queue_name,
                routing_key=key
            )
        
        # Store callback for this queue
        self.message_handlers[queue_name] = callback
        
        # Start consuming
        self.channel.basic_consume(
            queue=queue_name,
            on_message_callback=lambda ch, method, properties, body: self._process_message(
                callback, ch, method, properties, body
            ),
            auto_ack=auto_ack
        )
        
        print(f"Subscribed to {routing_keys} on queue {queue_name}")
    
    async def subscribe_async(self, queue_name: str, routing_keys: List[str], 
                            callback: Callable) -> None:
        """
        Subscribe to messages asynchronously with the specified routing keys.
        
        Args:
            queue_name: Name of the queue to create/use
            routing_keys: List of routing key patterns to subscribe to
            callback: Async function to call when a message is received
        """
        if self.async_channel is None:
            await self.connect_async()
        
        # Declare queue
        queue = await self.async_channel.declare_queue(
            name=queue_name,
            durable=True
        )
        
        # Bind queue to exchange with routing keys
        for key in routing_keys:
            await queue.bind(
                exchange=self.exchange_name,
                routing_key=key
            )
        
        # Start consuming
        await queue.consume(callback)
        
        print(f"Async subscribed to {routing_keys} on queue {queue_name}")
    
    def _process_message(self, callback: Callable, ch, method, properties, body: bytes) -> None:
        """Process and decode a received message."""
        try:
            message = json.loads(body.decode())
            callback(message, method.routing_key)
        except Exception as e:
            print(f"Error processing message: {e}")
    
    def start_consuming(self) -> None:
        """Start consuming messages (blocking)."""
        if self.channel is None:
            self.connect()
            
        try:
            print("Starting to consume messages. To exit press CTRL+C")
            self.channel.start_consuming()
        except KeyboardInterrupt:
            self.channel.stop_consuming()
            self.disconnect()
    
    async def process_traffic_data(self, vehicle_data: Dict[str, Any], 
                                  routing_key: str = "traffic.vehicles") -> None:
        """
        Process and publish traffic simulation data.
        
        Args:
            vehicle_data: Dictionary of vehicle data to publish
            routing_key: Routing key for the message
        """
        await self.publish_async(routing_key, vehicle_data)

    def send_vehicle_position(self, vehicle_id: str, x: float, y: float, 
                             direction: str, speed: float) -> None:
        """
        Send vehicle position update.
        
        Args:
            vehicle_id: Unique identifier of the vehicle
            x, y: Position coordinates
            direction: Movement direction
            speed: Current speed
        """
        message = {
            "vehicle_id": vehicle_id,
            "position": {"x": x, "y": y},
            "direction": direction,
            "speed": speed,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        self.publish("traffic.vehicle.position", message)
    
    def send_traffic_light_status(self, light_id: str, state: str, 
                                position: Dict[str, float], orientation: str) -> None:
        """
        Send traffic light status update.
        
        Args:
            light_id: Unique identifier of the traffic light
            state: Current state (green, yellow, red)
            position: Position coordinates
            orientation: Light orientation
        """
        message = {
            "light_id": light_id,
            "state": state,
            "position": position,
            "orientation": orientation,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        self.publish("traffic.light.status", message)
    
    def send_simulation_metrics(self, metrics: Dict[str, Any]) -> None:
        """
        Send simulation metrics.
        
        Args:
            metrics: Dictionary of simulation metrics
        """
        metrics["timestamp"] = asyncio.get_event_loop().time()
        self.publish("traffic.simulation.metrics", metrics)


# Example usage
async def example_async_usage():
    # Create client
    client = RabbitMQClient()
    
    # Connect
    await client.connect_async()
    
    # Publish a message
    await client.publish_async(
        "traffic.test", 
        {"message": "Hello from traffic simulation!"}
    )
    
    # Define a message handler
    async def message_handler(message, routing_key):
        print(f"Received message: {message} with routing key: {routing_key}")
    
    # Subscribe to messages
    await client.subscribe_async(
        "test_queue", 
        ["traffic.test"], 
        message_handler
    )
    
    # Wait for a bit to receive messages
    await asyncio.sleep(5)
    
    # Disconnect
    await client.disconnect_async()

if __name__ == "__main__":
    # Example of synchronous usage
    client = RabbitMQClient()
    client.connect()
    client.publish("traffic.test", {"message": "Sync test message"})
    client.disconnect()
    
    # Example of asynchronous usage
    asyncio.run(example_async_usage())
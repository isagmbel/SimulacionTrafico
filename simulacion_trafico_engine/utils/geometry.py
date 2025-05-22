# simulacion_trafico_engine/utils/geometry.py
import pygame
from typing import Tuple # Para type hints si se añaden métodos que devuelvan tuplas

class Point:
    """
    Representa un punto 2D con coordenadas x e y.
    """
    def __init__(self, x: float, y: float):
        """
        Inicializa un nuevo objeto Point.
        Args:
            x (float): La coordenada x del punto.
            y (float): La coordenada y del punto.
        """
        self.x: float = x
        self.y: float = y

    def __repr__(self) -> str:
        """Devuelve una representación de cadena del punto."""
        return f"Point(x={self.x}, y={self.y})"

    def to_tuple(self) -> Tuple[float, float]:
        """Convierte el punto a una tupla (x, y)."""
        return (self.x, self.y)

class Rect:
    """
    Representa un rectángulo 2D definido por su esquina superior izquierda (x, y),
    ancho y alto.
    Internamente, puede usar un pygame.Rect para algunas operaciones de colisión.
    """
    def __init__(self, x: float, y: float, width: float, height: float):
        """
        Inicializa un nuevo objeto Rect.
        Args:
            x (float): Coordenada x de la esquina superior izquierda.
            y (float): Coordenada y de la esquina superior izquierda.
            width (float): Ancho del rectángulo.
            height (float): Alto del rectángulo.
        """
        self.x: float = x
        self.y: float = y
        self.width: float = width
        self.height: float = height
        
        # Crear un pygame.Rect para aprovechar sus métodos de colisión y utilidad.
        # Se usan enteros para pygame.Rect, se puede considerar redondear o truncar.
        self.pygame_rect: pygame.Rect = pygame.Rect(int(x), int(y), int(width), int(height))

    @property
    def left(self) -> float: return self.x
    @property
    def right(self) -> float: return self.x + self.width
    @property
    def top(self) -> float: return self.y
    @property
    def bottom(self) -> float: return self.y + self.height
    @property
    def centerx(self) -> float: return self.x + self.width / 2
    @property
    def centery(self) -> float: return self.y + self.height / 2
    @property
    def center(self) -> Tuple[float, float]: return (self.centerx, self.centery)
    @property
    def topleft(self) -> Tuple[float, float]: return (self.x, self.y)
    @property
    def topright(self) -> Tuple[float, float]: return (self.right, self.y)
    @property
    def bottomleft(self) -> Tuple[float, float]: return (self.x, self.bottom)
    @property
    def bottomright(self) -> Tuple[float, float]: return (self.right, self.bottom)


    def contains_point(self, point: Point) -> bool:
        """
        Comprueba si el punto dado está contenido dentro de este rectángulo.
        Args:
            point (Point): El punto a comprobar.
        Returns:
            bool: True si el punto está dentro del rectángulo, False en caso contrario.
        """
        # Delega la comprobación de colisión al pygame.Rect interno.
        return self.pygame_rect.collidepoint(point.x, point.y)

    def colliderect(self, other_rect: 'Rect') -> bool:
        """
        Comprueba si este rectángulo colisiona con otro rectángulo.
        Args:
            other_rect (Rect): El otro rectángulo con el que comprobar la colisión.
        Returns:
            bool: True si los rectángulos colisionan, False en caso contrario.
        """
        return self.pygame_rect.colliderect(other_rect.pygame_rect)

    def __repr__(self) -> str:
        """Devuelve una representación de cadena del rectángulo."""
        return f"Rect(x={self.x}, y={self.y}, width={self.width}, height={self.height})"
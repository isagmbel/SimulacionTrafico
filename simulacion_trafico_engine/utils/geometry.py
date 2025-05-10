# simulacion_trafico_engine/utils/geometry.py
import pygame

class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

class Rect: # Similar a pygame.Rect pero podría tener más semántica
    def __init__(self, x, y, width, height):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.pygame_rect = pygame.Rect(x, y, width, height)

    def contains_point(self, point: Point) -> bool:
        return self.pygame_rect.collidepoint(point.x, point.y)
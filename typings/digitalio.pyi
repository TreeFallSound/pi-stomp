from typing import Any
from enum import Enum

class Direction(Enum):
    INPUT = 0
    OUTPUT = 1

class DigitalInOut:
    direction: Direction
    value: bool
    def __init__(self, pin: Any) -> None: ...

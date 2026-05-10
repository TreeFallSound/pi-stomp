from typing import Any
from adafruit_rgb_display import Display

class ILI9341(Display):
    def __init__(self, spi: Any, *, cs: Any, dc: Any, rst: Any = None, baudrate: int = 24000000, **kwargs: Any) -> None: ...

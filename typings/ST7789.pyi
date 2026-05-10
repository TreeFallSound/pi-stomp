from typing import Any
from PIL.Image import Image

BG_SPI_CS_BACK: int
BG_SPI_CS_FRONT: int

class ST7789:
    width: int
    height: int
    def __init__(
        self,
        port: int,
        cs: int,
        dc: int,
        backlight: int,
        width: int = 240,
        height: int = 240,
        rotation: int = 0,
        spi_speed_hz: int = 80000000,
        **kwargs: Any,
    ) -> None: ...
    def display(self, image: Image) -> None: ...

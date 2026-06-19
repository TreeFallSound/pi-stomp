from typing import Any, Callable
from PIL.Image import Image

class Display:
    width: int
    height: int
    rotation: int
    spi_device: Any
    dc_pin: Any
    _X_START: int
    _Y_START: int
    _COLUMN_SET: int
    _PAGE_SET: int
    _RAM_WRITE: int
    _block: Callable[..., Any]
    def image(self, img: Image) -> None: ...
    def fill(self, color: int) -> None: ...
    def _encode_pos(self, x: int, y: int) -> bytes: ...

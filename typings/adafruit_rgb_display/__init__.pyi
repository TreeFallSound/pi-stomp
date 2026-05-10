from typing import Any
from PIL.Image import Image

class Display:
    width: int
    height: int
    rotation: int
    def image(self, img: Image) -> None: ...

from typing import Any
from adafruit_rgb_display import Display

class DisplaySPI(Display):
    @staticmethod
    def _block(disp: Display, x0: int, y0: int, x1: int, y1: int, data: Any = None) -> None: ...

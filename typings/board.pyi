from typing import Any

class Pin: ...

SCL: Pin
SDA: Pin
D1: Pin
D5: Pin
D6: Pin
D13: Pin
CE0: Pin
CE1: Pin

def SPI() -> Any: ...
def I2C() -> Any: ...

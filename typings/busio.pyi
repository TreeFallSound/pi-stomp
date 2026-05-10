from typing import Any

class I2C:
    def __init__(self, scl: Any, sda: Any) -> None: ...

class SPI:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

from typing import Any

class AnalogIn:
    value: int
    voltage: float
    def __init__(self, mcp: Any, *pins: int) -> None: ...

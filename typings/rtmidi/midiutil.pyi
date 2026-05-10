from typing import Any
from rtmidi._rtmidi import MidiIn, MidiOut

__all__ = (
    "get_api_from_environment",
    "list_available_ports",
    "list_input_ports",
    "list_output_ports",
    "open_midiinput",
    "open_midioutput",
    "open_midiport",
)

def get_api_from_environment(api: Any = ...) -> Any: ...
def list_available_ports(ports: Any = ..., midiio: Any = ...) -> None: ...
def list_input_ports(api: Any = ...) -> None: ...
def list_output_ports(api: Any = ...) -> None: ...
def open_midiport(
    port: Any = ...,
    type_: Any = ...,
    api: Any = ...,
    use_virtual: Any = ...,
    interactive: Any = ...,
    client_name: Any = ...,
    port_name: Any = ...,
) -> tuple[MidiIn | MidiOut, str]: ...
def open_midiinput(
    port: Any = ...,
    api: Any = ...,
    use_virtual: Any = ...,
    interactive: Any = ...,
    client_name: Any = ...,
    port_name: Any = ...,
) -> tuple[MidiIn, str]: ...
def open_midioutput(
    port: Any = ...,
    api: Any = ...,
    use_virtual: Any = ...,
    interactive: Any = ...,
    client_name: Any = ...,
    port_name: Any = ...,
) -> tuple[MidiOut, str]: ...

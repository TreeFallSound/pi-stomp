"""Dispatch real input events through the handler, mirroring the hardware → sink
path. Replaces the retired ``universal_encoder_select`` / ``universal_encoder_sw``
shims so tests exercise the same ``handler.handle`` cascade the device uses."""

import time

import common.token as Token
from pistomp.input.event import EncoderEvent, SwitchEvent, SwitchEventKind


def nav_encoder(handler):
    for e in handler.hardware.encoders:
        if e.type == Token.NAV:
            return e
    raise AssertionError("handler has no NAV encoder")


def nav_step(handler, d: int) -> None:
    """Dispatch a NAV-encoder rotation of ``d`` detents."""
    handler.handle(EncoderEvent(controller=nav_encoder(handler), rotations=d))


def nav_click(handler, *, long: bool = False) -> None:
    """Dispatch a NAV-encoder button press (``long=True`` for a long-press)."""
    kind = SwitchEventKind.LONGPRESS if long else SwitchEventKind.PRESS
    handler.handle(SwitchEvent(controller=nav_encoder(handler), kind=kind, timestamp=time.monotonic()))

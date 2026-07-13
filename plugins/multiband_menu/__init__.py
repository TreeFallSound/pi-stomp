"""Reusable arc-ring grid window for low-band-count multi-band plugins.

``MultibandWindow`` is a thin subclass of ``ParameterWindow`` that sources
slots from ``build_slots()`` (the subclass contract). ``ParamSlot`` is an
alias of ``PinnedParam`` so existing subclasses keep working unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence

from modalapi.plugin_customization import PinnedParam as ParamSlot
from plugins.parameter_window import ParameterWindow, ParamSlotWidget

__all__ = ["MultibandWindow", "ParamSlot", "ParamSlotWidget"]


class MultibandWindow(ParameterWindow):
    """Windowed arc-ring grid for up to ~10 parameters.

    Subclasses provide the parameter slots via ``build_slots()``. The window
    manages selection (Nav), drawing, and Tweak1 edits of the selected ring.
    """

    # ── subclass contract ──────────────────────────────────────────────────

    def build_slots(self) -> Sequence[ParamSlot]:
        raise NotImplementedError

    # ── ParameterWindow override ───────────────────────────────────────────

    def _heuristic_slots(self) -> list[ParamSlot]:
        # MultibandWindow subclasses always override build_slots, so this
        # should never be called. Defensive fallback.
        return super()._heuristic_slots()

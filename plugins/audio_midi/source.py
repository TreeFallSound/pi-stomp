"""Synthetic reactive param source for the Audio & MIDI menu.

The Audio & MIDI menu edits the audiocard's global EQ (5 bands) and
input/output levels — there is no backing ``Plugin``. Per
``docs/audio-midi-menu.md`` §4.1 these are modelled as synthetic reactive
``Parameter``s so the menu reuses ``PluginPanel``'s entire param machinery
(coalescing, subscribe→dirty→apply_state, edit_symbol's ParameterSteps math)
instead of bespoke commit callbacks.

The source satisfies ``common.param_source.ParamSource`` structurally:
``parameters``, ``instance_id``, ``set_param_value`` (the write side —
commits to the audiocard), ``subscribe`` (fans out over the synthetic
parameters). It does **not** implement ``BypassSource`` — the audio menu
has no bypass, so the reactive core's bypass/reset paths no-op and the
footer omits Bypass/Reset (§4.2).

Symbols are the audiocard's ALSA mixer names (``MASTER``, ``CAPTURE_VOLUME``,
``EQ_1``..``EQ_5``), so the existing ``audio_parameter_commit`` write path
matches exactly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from common.parameter import Parameter, PortInfo, Symbol
from plugins.audio_midi.band_spec import BAND_SPECS

if TYPE_CHECKING:
    from pistomp.audiocard import Audiocard
    from pistomp.hardware import Hardware

# instance_id for the synthetic source. ``_flush_param_queue`` keys the
# WebSocket send on this; ``_send_param`` is overridden to no-op (no
# mod-host instance), so the value is purely diagnostic.
INSTANCE_ID = "audio_midi"

# Range mirror of modhandler._create_audio_parameter / bind_volume_encoder.
_IN_GAIN_RANGE = (-19.75, 12.0)
_OUT_VOL_RANGE = (-25.75, 6.0)
_EQ_BAND_RANGE = (-10.50, 12.0)


def _make_param(name: str, symbol: Symbol, value: float, lo: float, hi: float) -> Parameter:
    info: PortInfo = {
        "shortName": name,
        "symbol": str(symbol),
        "ranges": {"minimum": lo, "maximum": hi, "default": 0.0},
    }
    p = Parameter(info, value, None, INSTANCE_ID)
    p.unit_symbol = "dB"
    return p


class AudioMidiParamSource:
    """Reactive bundle of the audiocard params the Audio & MIDI menu edits.

    Created fresh each time the menu opens (the audiocard values may have
    drifted via alsamixer, so we re-read on construction). ``set_param_value``
    is the single write path — it writes the audiocard and mirrors the value
    into the ``Parameter`` (which fires the reactive subscription → the open
    panel's ``_model_dirty`` → ``apply_state``).
    """

    def __init__(self, audiocard: "Audiocard", hardware: "Hardware | None") -> None:
        self._audiocard = audiocard
        self._hardware = hardware
        self.instance_id: str = INSTANCE_ID
        self.parameters: dict[Symbol, Parameter] = {}
        self._unsubs: list[Callable[[], None]] = []
        self._build()

    def _read(self, symbol: Symbol, lo: float, hi: float) -> float:
        v = self._audiocard.get_volume_parameter(str(symbol))
        return max(lo, min(hi, float(v)))

    def _build(self) -> None:
        ac = self._audiocard
        if ac.CAPTURE_VOLUME is not None:
            in_gain = self._read(Symbol(ac.CAPTURE_VOLUME), *_IN_GAIN_RANGE)
            self.parameters[Symbol(ac.CAPTURE_VOLUME)] = _make_param(
                "Input Gain", Symbol(ac.CAPTURE_VOLUME), in_gain, *_IN_GAIN_RANGE
            )
        if ac.MASTER is not None:
            out_vol = self._read(Symbol(ac.MASTER), *_OUT_VOL_RANGE)
            self.parameters[Symbol(ac.MASTER)] = _make_param(
                "Output Volume", Symbol(ac.MASTER), out_vol, *_OUT_VOL_RANGE
            )
        # 5-band DAC EQ — symbols match the ALSA mixer names (DAC EQ1..5),
        # which is what GraphicBandSpec.gain_sym carries. Gated on DAC_EQ
        # being present (IQaudIO Codec only); other cards skip the bands.
        if ac.DAC_EQ is not None:
            for band in BAND_SPECS:
                val = self._read(band.gain_sym, *_EQ_BAND_RANGE)
                self.parameters[band.gain_sym] = _make_param(band.name, band.gain_sym, val, *_EQ_BAND_RANGE)

    def set_param_value(self, symbol: Symbol, value: float) -> None:
        # Commit to the audiocard (the single hardware writer for these),
        # then mirror into the reactive Parameter so observers fire.
        self._audiocard.set_volume_parameter(str(symbol), value)
        if self._audiocard.CAPTURE_VOLUME is not None and symbol == Symbol(self._audiocard.CAPTURE_VOLUME):
            if self._hardware is not None:
                # Input-gain changes require VU recalibration, mirroring the
                # legacy audio_parameter_commit path.
                self._hardware.recalibrateVU_gain(value)
        p = self.parameters.get(symbol)
        if p is not None:
            p.value = value

    def subscribe(self, cb: Callable[[Parameter], None]) -> Callable[[], None]:
        unsubs = [p.subscribe(cb) for p in self.parameters.values()]
        def _unsub() -> None:
            for u in unsubs:
                u()
        return _unsub
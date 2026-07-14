"""Ports that duplicate :bypass but carry no LV2 metadata to catch them by.

`common.parameter.is_hidden_port` handles every port that declares itself — a
`notOnGUI` property, or one of the `HIDDEN_DESIGNATIONS`. That covers 197 of the
5913 control-input ports on the device. The ones below declare nothing: they are
author-rolled bypass/enable switches, named by convention alone, and only a
per-URI table can find them. Symbol names are worthless as a global rule — "on"
is a redundant bypass in Calf Reverb and a real control elsewhere.

Hiding is a display exclusion, not a deletion: the `Parameter` stays in
`plugin.parameters`, so MIDI bindings, snapshots and echo reconciliation are
unaffected.
"""

from __future__ import annotations

from common.parameter import Symbol
from plugins.customization import hide_params

_BYPASS = frozenset({Symbol("bypass")})
_ON = frozenset({Symbol("on")})
_ACTIVE = frozenset({Symbol("active")})
_POWER = frozenset({Symbol("power")})
_ONOFF = frozenset({Symbol("onoff")})

hide_params(
    "http://calf.sourceforge.net/plugins/BassEnhancer",
    "http://calf.sourceforge.net/plugins/CompensationDelay",
    "http://calf.sourceforge.net/plugins/Compressor",
    "http://calf.sourceforge.net/plugins/Crusher",
    "http://calf.sourceforge.net/plugins/EnvelopeFilter",
    "http://calf.sourceforge.net/plugins/Equalizer5Band",
    "http://calf.sourceforge.net/plugins/Exciter",
    "http://calf.sourceforge.net/plugins/Filter",
    "http://calf.sourceforge.net/plugins/Gate",
    "http://calf.sourceforge.net/plugins/MonoCompressor",
    "http://calf.sourceforge.net/plugins/Pulsator",
    "http://calf.sourceforge.net/plugins/Saturator",
    "http://github.com/blablack/deteriorate-lv2/downsampler_mono",
    "http://github.com/blablack/deteriorate-lv2/downsampler_stereo",
    "http://github.com/blablack/deteriorate-lv2/granulator_mono",
    "http://github.com/blablack/deteriorate-lv2/granulator_stereo",
    "http://invadarecords.com/plugins/lv2/compressor/mono",
    "http://invadarecords.com/plugins/lv2/compressor/stereo",
    "http://invadarecords.com/plugins/lv2/delay/mono",
    "http://invadarecords.com/plugins/lv2/delay/sum",
    "http://invadarecords.com/plugins/lv2/erreverb/mono",
    "http://invadarecords.com/plugins/lv2/erreverb/sum",
    "http://invadarecords.com/plugins/lv2/filter/hpf/mono",
    "http://invadarecords.com/plugins/lv2/filter/hpf/stereo",
    "http://invadarecords.com/plugins/lv2/filter/lpf/mono",
    "http://invadarecords.com/plugins/lv2/filter/lpf/stereo",
    "http://invadarecords.com/plugins/lv2/input",
    "http://invadarecords.com/plugins/lv2/tube/mono",
    "http://invadarecords.com/plugins/lv2/tube/stereo",
    symbols=_BYPASS,
)

hide_params(
    "http://calf.sourceforge.net/plugins/Flanger",
    "http://calf.sourceforge.net/plugins/MultiChorus",
    "http://calf.sourceforge.net/plugins/Phaser",
    "http://calf.sourceforge.net/plugins/Reverb",
    "http://calf.sourceforge.net/plugins/VintageDelay",
    symbols=_ON,
)

hide_params(
    "http://home.gna.org/lv2vocoder/1",
    "http://invadarecords.com/plugins/lv2/testtone",
    symbols=_ACTIVE,
)

hide_params(
    "http://moddevices.com/plugins/caps/AmpVTS",
    "urn:juce:TalReverb3",
    symbols=_POWER,
)

hide_params(
    "http://gareus.org/oss/lv2/midifilter#velocityscale",
    symbols=_ONOFF,
)

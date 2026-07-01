"""Live compressor gain-reduction meter, backed by a JACK subprocess.

A ``GrMeterClient`` spawns ``python -m pistomp.compmeter``, which opens a JACK
client, taps the compressor instance's input and output audio ports, and writes
a small telemetry frame (input dB, output dB, derived gain reduction dB) into
shared memory. The panel reads it lock-free on the LCD tick — same pattern as
``pistomp.tuner``.

Gain reduction is derived from the audio, not the plugin's ``gr`` output port:
``GR ≈ in_db + makeup_db − out_db`` (clamped ≥ 0), since the compressor's output
is ``input · comp_gain · makeup``. It is a metering approximation, not exact.
"""

from modalapi.plugin import Plugin


def _plugin(instance_id: str, name: str | None = None) -> Plugin:
    info = {"name": name} if name is not None else None
    return Plugin(instance_id, {}, info)


def test_shorter_name_wins():
    p = _plugin("StompBox_fuzz", "Fuzz")
    assert p.display_name == "Fuzz"


def test_longer_name_loses():
    # "C* Noisegate - Attenuate noise..." is longer than "Noisegate"
    p = _plugin("Noisegate", "C* Noisegate - Attenuate noise resident in silence")
    assert p.display_name == "Noisegate"


def test_mono_id_uses_name():
    p = _plugin("mono", "Invada Compressor (mono)")
    assert p.display_name == "Invada Compressor (mono)"


def test_mono_with_suffix_uses_name():
    p = _plugin("mono_1", "TinyGain Mono")
    assert p.display_name == "TinyGain Mono"


def test_stereo_id_uses_name():
    p = _plugin("stereo_2", "Some Stereo Reverb")
    assert p.display_name == "Some Stereo Reverb"


def test_underscores_stripped():
    p = _plugin("StompBox_fuzz", "Fuzz")
    assert "_" not in p.display_name


def test_no_info_falls_back_to_instance_id():
    p = _plugin("valve")
    assert p.display_name == "valve"


def test_equal_length_keeps_instance_id():
    # same length → instance_id wins (not shorter)
    p = _plugin("mixer", "Mixer")
    assert p.display_name == "mixer"


def test_internal_number_not_stripped():
    # ts9sim has a number mid-name; should not trigger mono/stereo rule
    p = _plugin("ts9sim", "TS9 Simulator")
    assert p.display_name == "ts9sim"


def test_internal_number_with_suffix():
    # trailing _1 stripped for the check, but internal 9 is preserved in instance_id
    p = _plugin("ts9sim_1", "TS9 Simulator")
    assert p.display_name == "ts9sim1"

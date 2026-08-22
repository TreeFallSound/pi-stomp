"""Regression net for the version 1 config format.

Guards two things: every shipped template still parses, and the external-MIDI
routing surface (per-control `midi_port` plus the `external_midi` block) is
accepted when well-formed and rejected when malformed.
"""

import glob

import pytest
from jsonschema import Draft202012Validator

from pistomp.config import ConfigError, json_schema, load_cfg_from_file, parse

TEMPLATES = sorted(glob.glob("setup/config_templates/default_config*.yml"))


def _parse(cfg):
    return parse(cfg, "<test>")


def test_generated_schema_is_well_formed():
    Draft202012Validator.check_schema(json_schema())


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: p.rsplit("/", 1)[-1])
def test_shipped_template_parses(path):
    load_cfg_from_file(path)


def test_midi_port_and_external_midi_accepted():
    _parse({
        "hardware": {
            "version": 3.0,
            "midi": {"channel": 14},
            "footswitches": [
                {"id": 0, "midi_CC": 60, "midi_port": "Source Audio C4 Synth", "midi_channel": 0}
            ],
            "analog_controllers": [
                {"adc_input": 5, "id": 0, "midi_CC": 75, "midi_port": "HX Stomp", "midi_channel": 0,
                 "type": "EXPRESSION"}
            ],
            "encoders": [
                {"id": 1, "midi_CC": 70, "midi_port": "Source Audio C4 Synth", "midi_channel": 0}
            ],
            "external_midi": {
                "enabled": True,
                "send_delay_ms": 10,
                "messages": {
                    "Source Audio C4 Synth": [[0xB0, 0x66, 0x00]],
                    "HX Stomp": [[0xC0, 0x00]],
                },
            },
        }
    })


def test_non_string_midi_port_rejected():
    with pytest.raises(ConfigError):
        _parse({"hardware": {"encoders": [{"id": 1, "midi_port": 5, "midi_channel": 0}]}})


def test_unknown_key_rejected():
    with pytest.raises(ConfigError):
        _parse({"hardware": {"footswitches": [{"id": 0, "colour": "Red"}]}})


def test_entry_without_id_rejected():
    with pytest.raises(ConfigError):
        _parse({"hardware": {"footswitches": [{"midi_CC": 60}]}})


def test_midi_cc_out_of_range_rejected():
    with pytest.raises(ConfigError):
        _parse({"hardware": {"footswitches": [{"id": 0, "midi_CC": 200}]}})


@pytest.mark.parametrize("section,entry", [
    ("footswitches", {"id": 0, "midi_CC": 60, "midi_port": "Source Audio C4 Synth"}),
    ("analog_controllers", {"adc_input": 5, "id": 0, "midi_CC": 75, "midi_port": "HX Stomp"}),
    ("encoders", {"id": 1, "midi_CC": 70, "midi_port": "Source Audio C4 Synth"}),
])
def test_midi_port_without_midi_channel_rejected(section, entry):
    with pytest.raises(ConfigError):
        _parse({"hardware": {section: [entry]}})


@pytest.mark.parametrize("section,entry", [
    ("footswitches", {"id": 0, "adc_input": 0, "midi_CC": 60}),
    ("analog_controllers", {"adc_input": 5, "id": 0, "midi_CC": 75}),
    ("encoders", {"id": 1, "midi_CC": 70}),
])
def test_midi_channel_not_required_without_midi_port(section, entry):
    """midi_channel is only needed with midi_port; the common case stays untouched."""
    _parse({"hardware": {section: [entry]}})


def _fs_cfg(longpress):
    return {"hardware": {"footswitches": [{"id": 0, "midi_CC": 60, "longpress": longpress}]}}


@pytest.mark.parametrize("longpress", [
    {"midi_CC": 64},
    {"preset": "UP"},
    {"preset": 2},
    {"pedalboard": "DOWN"},
    "next_snapshot",
    ["next_snapshot", "toggle_bypass"],
    "toggle_tuner_enable",
    "next_pedalboard",
    "previous_pedalboard",
    ["previous_snapshot", "previous_pedalboard"],
    None,
])
def test_longpress_form_valid(longpress):
    _parse(_fs_cfg(longpress))


@pytest.mark.parametrize("longpress", [
    {"midi_CC": "foo"},
    {"midi_CC": 64, "preset": "UP"},
    {},
    {"pedalboard": "SIDEWAYS"},
    {"bogus": 1},
    "not_a_handler_name",
    ["next_snapshot", "not_a_handler_name"],
])
def test_longpress_form_invalid(longpress):
    with pytest.raises(ConfigError):
        _parse(_fs_cfg(longpress))


def test_explicit_null_clears_overlay_sections():
    from pistomp.config.adapt_v1 import adapt
    from pistomp.config.schema_v1 import merge

    base = _parse({
        "hardware": {
            "version": 3.0,
            "midi": {"channel": 14},
            "footswitches": [{"id": 0, "adc_input": 0, "midi_CC": 60}],
            "encoders": [{"id": 1, "midi_CC": 70}],
            "analog_controllers": [{"id": 2, "adc_input": 0, "midi_CC": 75}],
            "external_midi": {"enabled": True, "messages": {"dev": [[0xC0, 1]]}},
        },
        "blend_snapshots": [{"name": "Blend", "input_id": 0, "stops": [0, 1]}],
    })
    overlay = _parse({
        "hardware": {
            "footswitches": None,
            "encoders": None,
            "analog_controllers": None,
            "external_midi": None,
        },
        "blend_snapshots": None,
    })

    effective = adapt(merge(base, overlay))

    assert effective.footswitches == ()
    assert effective.encoders == ()
    assert effective.analog_controls == ()
    assert effective.external_midi.get("enabled") is False
    assert effective.external_midi.get("messages") == {}
    assert effective.blend_snapshots == []

"""Schema regression net for pistomp/config.py (S1: external_midi / midi_port).

Guards two things: every shipped template stays schema-valid, and the
external-MIDI routing surface (per-control `midi_port` + the `external_midi`
block) is both accepted when well-formed and rejected when malformed.
"""

import glob

import pytest
import yaml
from jsonschema import Draft4Validator, exceptions, validate

from pistomp.config import schema

TEMPLATES = sorted(glob.glob("setup/config_templates/default_config*.yml"))


def test_schema_is_well_formed():
    Draft4Validator.check_schema(schema)


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: p.rsplit("/", 1)[-1])
def test_shipped_template_validates(path):
    with open(path) as fh:
        cfg = yaml.safe_load(fh)
    validate(instance=cfg, schema=schema)


def test_midi_port_and_external_midi_accepted():
    cfg = {
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
    }
    validate(instance=cfg, schema=schema)


def test_non_string_midi_port_rejected():
    cfg = {
        "hardware": {
            "version": 3.0,
            "midi": {"channel": 14},
            "encoders": [{"id": 1, "midi_port": 5, "midi_channel": 0}],
        }
    }
    with pytest.raises(exceptions.ValidationError):
        validate(instance=cfg, schema=schema)


@pytest.mark.parametrize("section,entry", [
    ("footswitches", {"id": 0, "midi_CC": 60, "midi_port": "Source Audio C4 Synth"}),
    ("analog_controllers", {"adc_input": 5, "id": 0, "midi_CC": 75, "midi_port": "HX Stomp"}),
    ("encoders", {"id": 1, "midi_CC": 70, "midi_port": "Source Audio C4 Synth"}),
])
def test_midi_port_without_midi_channel_rejected(section, entry):
    cfg = {
        "hardware": {
            "version": 3.0,
            "midi": {"channel": 14},
            section: [entry],
        }
    }
    with pytest.raises(exceptions.ValidationError):
        validate(instance=cfg, schema=schema)


@pytest.mark.parametrize("section,entry", [
    ("footswitches", {"id": 0, "adc_input": 0, "midi_CC": 60}),
    ("analog_controllers", {"adc_input": 5, "id": 0, "midi_CC": 75}),
    ("encoders", {"id": 1, "midi_CC": 70}),
])
def test_midi_channel_not_required_without_midi_port(section, entry):
    """midi_channel is only required alongside midi_port; the common no-external-routing case must stay untouched."""
    cfg = {
        "hardware": {
            "version": 3.0,
            "midi": {"channel": 14},
            section: [entry],
        }
    }
    validate(instance=cfg, schema=schema)

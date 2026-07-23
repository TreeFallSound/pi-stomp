# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

import logging
import os
from typing import Any

import yaml
from jsonschema import validate
from jsonschema import exceptions

data_dir = '/home/pistomp/data/config'

DEFAULT_CONFIG_FILE = "default_config.yml"

schema = {
  "$schema": "http://json-schema.org/draft-04/schema#",
  "type": "object",
  "properties": {
    "hardware": {
      "type": "object",
      "properties": {
        "version": {
          "type": "number"
        },
        "midi": {
          "type": "object",
          "properties": {
            "channel": {
              "type": "integer",
              "minimum": 1,
              "maximum": 16
            }
          },
          "required": [
            "channel"
          ]
        },
        "footswitches": {
          "type": "array",
            "uniqueItems": True,
            "items": {
            "type": "object",
            "properties": {
              "bypass": {
                "enum": ["LEFT", "RIGHT", "LEFT_RIGHT"]
              },
              "adc_input": {
                "type": "integer"
              },
              "color": {
                "type": "string"
              },
              "debounce_input": {
                "type": "integer"
              },
              "disable": {
                "type": "boolean",
                "description": "Disable this footswitch entirely or per-pedalboard (disabled=True)"
              },
              "gpio_input": {
                "type": "integer"
              },
              "gpio_output": {
                "type": "integer"
              },
              "id": {
                "type": "integer"
              },
              "ledstrip_position": {
                "type": "integer"
              },
              "longpress": {
                "oneOf": [
                  {
                    "type": "string",
                    "enum": ["next_snapshot", "previous_snapshot", "toggle_bypass", "set_mod_tap_tempo", "toggle_tap_tempo_enable", "toggle_tuner_enable"]
                  },
                  {
                    "type": "array",
                    "items": {
                      "type": "string",
                      "enum": ["next_snapshot", "previous_snapshot", "toggle_bypass", "set_mod_tap_tempo", "toggle_tap_tempo_enable", "toggle_tuner_enable"]
                    }
                  },
                  {
                    "type": "object",
                    "additionalProperties": False,
                    "minProperties": 1,
                    "maxProperties": 1,
                    "properties": {
                      "midi_CC": {"type": "integer", "minimum": 0, "maximum": 127},
                      "preset": {
                        "oneOf": [
                          {"type": "integer"},
                          {"type": "string", "enum": ["UP", "DOWN"]}
                        ]
                      },
                      "pedalboard": {"type": "string", "enum": ["UP", "DOWN"]}
                    }
                  }
                ]
              },
              "midi_CC": {
                "type": "integer"
              },
              "midi_port": {
                "type": "string",
                "description": "Send MIDI to this external port instead of the virtual MIDI Through port; falls back to virtual if the device is unavailable (must match a port in external_midi)"
              },
              "midi_channel": {
                "type": "integer",
                "minimum": 0,
                "maximum": 15,
                "description": "Override MIDI channel for this footswitch; required when midi_port is set, since external devices rarely share the hardware default channel"
              },
              "preset": {
                "oneOf": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "string",
                    "enum": ["UP", "DOWN"]
                  }
                ]
              },
              "tap_tempo": {
                "enum": ["set_mod_tap_tempo"]
              }
            },
            "required": [
              "id",
            ],
            "dependencies": {
              "midi_port": ["midi_channel"]
            }
          }
        },
        "analog_controllers": {
          "type": "array",
          "uniqueItems": True,
          "items": {
            "type": "object",
            "properties": {
              "adc_input": {
                "type": "integer"
              },
              "id": {
                "type": "integer"
              },
              "midi_CC": {
                "type": "integer"
              },
              "midi_port": {
                "type": "string",
                "description": "Send MIDI to this external port instead of the virtual MIDI Through port; falls back to virtual if the device is unavailable (must match a port in external_midi)"
              },
              "midi_channel": {
                "type": "integer",
                "minimum": 0,
                "maximum": 15,
                "description": "Override MIDI channel for this controller; required when midi_port is set, since external devices rarely share the hardware default channel"
              },
              "threshold": {
                "type": "integer",
                "minimum": 0,
                "maximum": 127
              },
              "type": {
                "enum": ["KNOB", "EXPRESSION"]
              },
              "autosync": {
                "type": "boolean"
              }
            },
            "required": [
              "adc_input",
              "midi_CC"
            ],
            "dependencies": {
              "midi_port": ["midi_channel"]
            }
          }
        },
        "encoders": {
          "type": "array",
          "uniqueItems": True,
          "items": {
            "type": "object",
            "properties": {
              "id": {
                "type": "integer"
              },
              "midi_CC": {
                "type": "integer"
              },
              "midi_port": {
                "type": "string",
                "description": "Send MIDI to this external port instead of the virtual MIDI Through port; falls back to virtual if the device is unavailable (must be the device name)"
              },
              "midi_channel": {
                "type": "integer",
                "minimum": 0,
                "maximum": 15,
                "description": "Override MIDI channel for this encoder; required when midi_port is set, since external devices rarely share the hardware default channel"
              },
              "type": {
                "enum": ["KNOB", "VOLUME"]
              },
              "longpress": {
                "type": "string"
              }
            },
            "required": [
              "id"
            ],
            "dependencies": {
              "midi_port": ["midi_channel"]
            }
          }
        },
        "external_midi": {
          "type": "object",
          "properties": {
            "enabled": {
              "type": "boolean"
            },
            "send_delay_ms": {
              "type": "integer",
              "minimum": 0
            },
            "messages": {
              "type": "object",
              "additionalProperties": {
                "type": "array",
                "items": {
                  "type": "array",
                  "items": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 255
                  }
                }
              }
            }
          }
        }
      },
      "required": [
        "version",
        "midi",
      ]
    }
  },
  "required": [
    "hardware"
  ]
}

def load_cfg_from_file(path):
    """Load and validate a config from an explicit file path."""
    with open(path, 'r') as ymlfile:
        cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)
    try:
        validate(instance=cfg, schema=schema)
    except exceptions.SchemaError as e:
        logging.error("Badly formatted schema in: %s %s" % (os.path.basename(path), e.message))
    except exceptions.ValidationError as e:
        logging.error("Config file error in: %s\n%s\n%s" % (path, e.schema_path, e.message))
    return cfg

def load_default_cfg() -> dict[str, Any]:
    # Read the default config file - should only need to read once per session
    default_config_file = os.path.join(data_dir, DEFAULT_CONFIG_FILE)
    with open(default_config_file, 'r') as ymlfile:
        cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)

        # Now validate.  Error message if problem found but it won't be fatal
        try:
            validate(instance=cfg, schema=schema)
        except exceptions.SchemaError as e:
            msg = ("Badly formatted schema in: %s %s" % (os.path.basename(__file__), e.message))
            logging.error(msg)
        except exceptions.ValidationError as e:
            msg = ("Config file error in: %s\n%s\n%s" % (default_config_file, e.schema_path, e.message))
            logging.error(msg)

        return cfg

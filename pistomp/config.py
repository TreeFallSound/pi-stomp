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
import sys

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
                "type": "boolean"
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
                "type" : ["array", "string"],
                "items" : {
                  "type" : "string",
                  "enum" : ["next_snapshot", "previous_snapshot", "toggle_bypass", "set_mod_tap_tempo", "toggle_tap_tempo_enable"]
                }
              },
              "midi_CC": {
                "type": "integer"
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
            ]
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
              "midi_CC": {
                "type": "integer"
              },
              "threshold": {
                "type": "integer",
                "minimum": 0,
                "maximum": 127
              },
              "type": {
                "enum": ["KNOB", "EXPRESSION"]
              }
            },
            "required": [
              "adc_input",
              "midi_CC"
            ]
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
              "type": {
                "enum": ["KNOB", "VOLUME"]
              },
              "longpress": {
                "type": "string"
              }
            },
            "required": [
              "id"
            ]
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

def load_default_cfg():
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

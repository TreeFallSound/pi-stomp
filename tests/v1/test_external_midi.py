"""External controllers must render in the v1 mono analog-assignments zone."""

import common.token as Token


def test_external_analog_assignments_render(v1_system, snapshot):
    v1_system.handler.lcd.draw_analog_assignments(
        {
            "0:75": {Token.CATEGORY: "External", Token.TYPE: Token.KNOB, Token.ID: 3,
                     "port_name": "c4", "midi_cc": 75},
            "0:76": {Token.CATEGORY: "External", Token.TYPE: Token.EXPRESSION, Token.ID: 4,
                     "port_name": "hx", "midi_cc": 76},
        }
    )
    snapshot()

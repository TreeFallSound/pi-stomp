"""Verify that plugin bypass states are synced from MOD after pedalboard load.

On boot, LILV parses the TTL bundle which stores the "Default" snapshot's bypass
values.  If MOD is actually running a different snapshot (e.g. tremolo is engaged
in "TremDly" but bypassed in "Default"), the initial LILV values are wrong.
set_current_pedalboard() must call preset_change_plugin_update() to reconcile.
"""

from unittest.mock import MagicMock

from tests.types import SystemFixture


def test_v3_bypass_synced_from_mod_on_pedalboard_load(v3_system: SystemFixture, make_plugin):
    """After set_current_pedalboard(), plugin bypass reflects MOD state, not LILV defaults."""
    handler = v3_system.handler
    hw = v3_system.hw
    mock_get = v3_system.mock_get

    assert handler.current

    # Plugin parsed from TTL as bypassed (Default snapshot), but MOD says it's active
    plugin = make_plugin("tremolo", bypassed=True)
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    assert plugin.is_bypassed(), "sanity check: plugin starts bypassed (LILV default)"

    def get_side_effect(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "pi_stomp_get" in url and "/:bypass" in url:
            resp.text = "false"
        elif "snapshot/list" in url:
            resp.text = '{"0": "Default", "1": "TremDly"}'
        elif "snapshot/name" in url:
            resp.text = '{"name": "TremDly"}'
        else:
            resp.text = "{}"
        return resp

    mock_get.side_effect = get_side_effect

    pb = handler.pedalboards[list(handler.pedalboards.keys())[0]]
    handler.set_current_pedalboard(pb)

    assert not plugin.is_bypassed(), "plugin should reflect MOD state (engaged), not LILV default (bypassed)"

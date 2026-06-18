"""Integration tests for the pistomp-stamp stamping protocol.

Verifies that ``pistomp-stamp stamp`` is called at the exact right times and
*not* called when it shouldn't be.  Only the v1 (Mod) handler stamps; v2/v3
(Modhandler) delegates pedalboard-change detection to poll_modui_changes().
"""

from unittest.mock import patch, MagicMock

import pistomp.switchstate as switchstate

from tests.types import SystemFixtureLegacy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stamp_calls(mock_run):
    return [c for c in mock_run.call_args_list if c.args and c.args[0][:2] == ["pistomp-stamp", "stamp"]]


def _assert_stamp_called(mock_run, times: int = 1):
    calls = _stamp_calls(mock_run)
    assert len(calls) == times, (
        f"Expected {times} pistomp-stamp call(s), got {len(calls)}. All subprocess.run calls: {mock_run.call_args_list}"
    )


def _assert_stamp_not_called(mock_run):
    calls = _stamp_calls(mock_run)
    assert not calls, f"Unexpected pistomp-stamp call(s): {calls}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStampOnPedalboardChange:
    """pistomp-stamp stamp must be called whenever a pedalboard change
    completes successfully."""

    def test_stamp_called_on_pedalboard_change(self, v1_system: SystemFixtureLegacy):
        handler = v1_system.handler
        with patch("modalapi.mod.subprocess.run") as mock_run:
            handler.pedalboard_change()
        _assert_stamp_called(mock_run, times=1)

    def test_stamp_called_on_top_encoder_select(self, v1_system: SystemFixtureLegacy):
        handler = v1_system.handler
        handler.selected_pedalboard_index = 1
        handler.top_encoder_mode = type(handler.top_encoder_mode).PEDALBOARD_SELECTED
        with patch("modalapi.mod.subprocess.run") as mock_run:
            handler.top_encoder_sw(switchstate.Value.RELEASED)
        _assert_stamp_called(mock_run, times=1)

    def test_no_stamp_on_mod_host_failure(self, v1_system: SystemFixtureLegacy):
        """Stamp must NOT be called when mod-host returns non-200 — stamp
        means 'I know this works' and a failed load is not known-good."""
        handler = v1_system.handler
        with (
            patch("modalapi.mod.subprocess.run") as mock_run,
            patch("modalapi.mod.req.get") as mock_get,
            patch("modalapi.mod.req.post") as mock_post,
        ):

            def fail_response(*args, **kwargs):
                resp = MagicMock()
                resp.status_code = 500
                resp.text = "{}"
                return resp

            mock_get.side_effect = fail_response
            mock_post.side_effect = fail_response
            handler.pedalboard_change()
        _assert_stamp_not_called(mock_run)

    def test_stamp_exception_is_caught(self, v1_system: SystemFixtureLegacy):
        handler = v1_system.handler
        with patch("modalapi.mod.subprocess.run", side_effect=FileNotFoundError("no binary")):
            handler.pedalboard_change()


class TestNoStampOnSetCurrentPedalboard:
    """pistomp-stamp stamp must NOT be called when set_current_pedalboard()
    is called directly (e.g. on startup when last.json already has a bundle)."""

    def test_no_stamp_on_direct_set(self, v1_system: SystemFixtureLegacy):
        handler = v1_system.handler
        pb = handler.pedalboards["/path/to/rig.pedalboard"]
        with patch("modalapi.mod.subprocess.run") as mock_run:
            handler.set_current_pedalboard(pb)
        _assert_stamp_not_called(mock_run)

    def test_no_stamp_on_load_pedalboards(self, v1_system: SystemFixtureLegacy):
        handler = v1_system.handler
        with patch("modalapi.mod.subprocess.run") as mock_run:
            handler.load_pedalboards()
        _assert_stamp_not_called(mock_run)


class TestStampNotCalledOnNonChangeOperations:
    """Operations that don't change the pedalboard must not trigger a stamp."""

    def test_no_stamp_on_preset_change(self, v1_system: SystemFixtureLegacy):
        handler = v1_system.handler
        with patch("modalapi.mod.subprocess.run") as mock_run:
            handler.preset_change()
        _assert_stamp_not_called(mock_run)

    def test_no_stamp_on_bypass_toggle(self, v1_system: SystemFixtureLegacy):
        handler = v1_system.handler
        with patch("modalapi.mod.subprocess.run") as mock_run:
            handler.toggle_plugin_bypass()
        _assert_stamp_not_called(mock_run)

    def test_no_stamp_on_parameter_value_change(self, v1_system: SystemFixtureLegacy):
        handler = v1_system.handler
        with patch("modalapi.mod.subprocess.run") as mock_run:
            handler.parameter_value_change(0, lambda: None)
        _assert_stamp_not_called(mock_run)

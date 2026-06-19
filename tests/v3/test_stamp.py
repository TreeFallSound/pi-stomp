"""Integration tests for the pistomp-stamp stamping protocol — v3 (Modhandler).

v3 stamps inside ``poll_modui_changes()`` when MOD-UI writes a new
``last.json`` and the pedalboard actually changes.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from tests.types import SystemFixture


def _stamp_calls(mock_run):
    return [c for c in mock_run.call_args_list if c.args and c.args[0][:2] == ["pistomp-stamp", "stamp"]]


def _assert_stamp_called(mock_run, times: int = 1):
    calls = _stamp_calls(mock_run)
    assert len(calls) == times, (
        f"Expected {times} pistomp-stamp call(s), got {len(calls)}. "
        f"All subprocess.run calls: {mock_run.call_args_list}"
    )


def _assert_stamp_not_called(mock_run):
    calls = _stamp_calls(mock_run)
    assert not calls, f"Unexpected pistomp-stamp call(s): {calls}"


class TestStampOnPedalboardChange:
    """pistomp-stamp stamp must be called when poll_modui_changes() detects
    a pedalboard change via last.json."""

    def test_stamp_called_on_modui_change(self, v3_system: SystemFixture, make_plugin):
        handler = v3_system.handler
        mock_get = v3_system.mock_get

        pb2 = handler.pedalboards["/path/to/new.pedalboard"]
        pb2.plugins = [make_plugin("fuzz", category="Distortion")]

        def get_side_effect(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.text = (
                json.dumps({"0": "Default"})
                if "snapshot/list" in url
                else json.dumps({"name": "Default"})
                if "snapshot/name" in url
                else "{}"
            )
            return resp

        mock_get.side_effect = get_side_effect

        last_json = Path(handler.data_dir) / "last.json"
        last_json.write_text(json.dumps({"pedalboard": "/path/to/new.pedalboard"}))
        os.utime(last_json, (9999, 9999))

        with patch("modalapi.modhandler.subprocess.run") as mock_run:
            handler.poll_modui_changes()

        _assert_stamp_called(mock_run, times=1)

    def test_no_stamp_without_change(self, v3_system: SystemFixture):
        """poll_modui_changes() must NOT stamp when last.json hasn't changed."""
        handler = v3_system.handler

        with patch("modalapi.modhandler.subprocess.run") as mock_run:
            handler.poll_modui_changes()

        _assert_stamp_not_called(mock_run)

    def test_no_stamp_on_same_pedalboard(self, v3_system: SystemFixture):
        """poll_modui_changes() must NOT stamp when last.json points to the
        same pedalboard already loaded."""
        handler = v3_system.handler

        last_json = Path(handler.data_dir) / "last.json"
        last_json.write_text(json.dumps({"pedalboard": "/path/to/rig.pedalboard"}))
        os.utime(last_json, (9999, 9999))

        with patch("modalapi.modhandler.subprocess.run") as mock_run:
            handler.poll_modui_changes()

        _assert_stamp_not_called(mock_run)


class TestNoStampOnSetCurrentPedalboard:
    """pistomp-stamp stamp must NOT be called when set_current_pedalboard()
    is called directly."""

    def test_no_stamp_on_direct_set(self, v3_system: SystemFixture):
        handler = v3_system.handler
        pb = handler.pedalboards["/path/to/rig.pedalboard"]
        with patch("modalapi.modhandler.subprocess.run") as mock_run:
            handler.set_current_pedalboard(pb)
        _assert_stamp_not_called(mock_run)

    def test_no_stamp_on_load_pedalboards(self, v3_system: SystemFixture):
        handler = v3_system.handler
        with patch("modalapi.modhandler.subprocess.run") as mock_run:
            handler.load_pedalboards()
        _assert_stamp_not_called(mock_run)


class TestStampNotCalledOnNonChangeOperations:
    """Operations that don't change the pedalboard must not trigger a stamp."""

    def test_no_stamp_on_preset_change(self, v3_system: SystemFixture):
        handler = v3_system.handler
        with patch("modalapi.modhandler.subprocess.run") as mock_run:
            handler.preset_change(0)
        _assert_stamp_not_called(mock_run)

    def test_no_stamp_on_system_info_load(self, v3_system: SystemFixture):
        handler = v3_system.handler
        with patch("modalapi.modhandler.subprocess.run") as mock_run:
            handler.system_info_load()
        _assert_stamp_not_called(mock_run)

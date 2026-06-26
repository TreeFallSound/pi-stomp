"""Unit tests for pistomp/nam/routing.py — JACK connection save/restore."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, call, patch

import pytest

import pistomp.nam.routing as routing


# Sample jack_lsp -c output: port name on its own line, connections indented.
_LSP_PLAYBACK2 = "system:playback_2\n   mod-host:out_0\n   mod-host:out_1\n"
_LSP_CAPTURE2 = "system:capture_2\n   mod-host:in_0\n"
_LSP_EMPTY = "system:playback_2\n"


def _lsp_side_effect(playback_out, capture_out):
    """Return a side_effect that dispatches by port name."""

    def side_effect(cmd, **kwargs):
        port = cmd[-1]
        if port == routing.FX_SEND_PORT:
            return playback_out
        if port == routing.FX_RETURN_PORT:
            return capture_out
        return ""

    return side_effect


class TestSnapshot:
    def test_returns_pairs_for_both_ports(self):
        with patch("subprocess.check_output") as mock_lsp:
            mock_lsp.side_effect = _lsp_side_effect(_LSP_PLAYBACK2, _LSP_CAPTURE2)
            saved = routing.snapshot()

        assert ("mod-host:out_0", routing.FX_SEND_PORT) in saved
        assert ("mod-host:out_1", routing.FX_SEND_PORT) in saved
        assert (routing.FX_RETURN_PORT, "mod-host:in_0") in saved
        assert len(saved) == 3

    def test_empty_ports_returns_empty(self):
        with patch("subprocess.check_output") as mock_lsp:
            mock_lsp.side_effect = _lsp_side_effect(_LSP_EMPTY, _LSP_EMPTY)
            saved = routing.snapshot()
        assert saved == []

    def test_lsp_failure_returns_empty(self):
        with patch("subprocess.check_output", side_effect=FileNotFoundError("jack_lsp")):
            saved = routing.snapshot()
        assert saved == []


class TestClear:
    def test_disconnects_all_fx_loop_connections(self):
        with (
            patch("subprocess.check_output") as mock_lsp,
            patch("subprocess.call") as mock_call,
        ):
            mock_lsp.side_effect = _lsp_side_effect(_LSP_PLAYBACK2, _LSP_CAPTURE2)
            routing.clear()

        # playback_2 has 2 sources → 2 disconnects; capture_2 has 1 dest → 1 disconnect
        calls = mock_call.call_args_list
        cmd_lists = [c[0][0] for c in calls]
        assert ["jack_disconnect", "mod-host:out_0", routing.FX_SEND_PORT] in cmd_lists
        assert ["jack_disconnect", "mod-host:out_1", routing.FX_SEND_PORT] in cmd_lists
        assert ["jack_disconnect", routing.FX_RETURN_PORT, "mod-host:in_0"] in cmd_lists

    def test_no_connections_is_no_op(self):
        with (
            patch("subprocess.check_output") as mock_lsp,
            patch("subprocess.call") as mock_call,
        ):
            mock_lsp.side_effect = _lsp_side_effect(_LSP_EMPTY, _LSP_EMPTY)
            routing.clear()
        mock_call.assert_not_called()


class TestRestore:
    def test_reconnects_all_saved_pairs(self):
        saved = [
            ("mod-host:out_0", routing.FX_SEND_PORT),
            (routing.FX_RETURN_PORT, "mod-host:in_0"),
        ]
        with patch("subprocess.call") as mock_call:
            routing.restore(saved)

        cmd_lists = [c[0][0] for c in mock_call.call_args_list]
        assert ["jack_connect", "mod-host:out_0", routing.FX_SEND_PORT] in cmd_lists
        assert ["jack_connect", routing.FX_RETURN_PORT, "mod-host:in_0"] in cmd_lists

    def test_empty_saved_is_no_op(self):
        with patch("subprocess.call") as mock_call:
            routing.restore([])
        mock_call.assert_not_called()


class TestRoundTrip:
    def test_snapshot_clear_restore_cycle(self):
        """Saved connections from snapshot are exactly what restore reconnects."""
        with patch("subprocess.check_output") as mock_lsp:
            mock_lsp.side_effect = _lsp_side_effect(_LSP_PLAYBACK2, _LSP_CAPTURE2)
            saved = routing.snapshot()

        with patch("subprocess.call") as mock_call:
            routing.restore(saved)

        reconnected = {tuple(c[0][0][1:]) for c in mock_call.call_args_list}
        expected = {
            ("mod-host:out_0", routing.FX_SEND_PORT),
            ("mod-host:out_1", routing.FX_SEND_PORT),
            (routing.FX_RETURN_PORT, "mod-host:in_0"),
        }
        assert reconnected == expected

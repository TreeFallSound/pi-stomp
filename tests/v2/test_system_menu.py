"""v2-specific system menu behaviour."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from tests.types import SystemFixture


def _fake_completed(stdout: str = "", stderr: str = "") -> MagicMock:
    """A CompletedProcess-like MagicMock for subprocess.run."""
    cp = MagicMock()
    cp.stdout = stdout
    cp.stderr = stderr
    return cp


def _patch_expanded(handler, expanded: bool):
    marker = Path(handler.homedir + "/.git/EXPANDED")
    real_exists = Path.exists

    def _exists(self):
        if self == marker:
            return expanded
        return real_exists(self)

    return patch("pathlib.Path.exists", side_effect=_exists, autospec=True)


def test_system_info_load(v2_system: SystemFixture):
    """On v2 (relay present), system_info_load reads bypass from the relay, not the audiocard."""
    handler = v2_system.handler
    hw = v2_system.hw
    hw.relay = MagicMock()
    hw.relay.get.return_value = False  # relay not engaged → bypass enabled
    handler.audiocard = MagicMock()
    handler.audiocard.get_switch_parameter.return_value = True

    with _patch_expanded(handler, False), \
         patch("subprocess.check_output", return_value=b"v1.0.0-abc\n"), \
         patch("subprocess.run", return_value=_fake_completed("", "")):
        handler.system_info_load()

    assert handler.software_version == "v1.0.0-abc"
    assert handler.eq_status is True
    hw.relay.get.assert_called_once()
    handler.audiocard.get_bypass_left.assert_not_called()
    handler.audiocard.get_bypass_right.assert_not_called()


def test_system_info_load_dpkg_clean(v2_system: SystemFixture):
    """No EXPANDED marker: dpkg --verify clean → bare version, no asterisk."""
    handler = v2_system.handler
    hw = v2_system.hw
    hw.relay = MagicMock()
    hw.relay.get.return_value = False
    handler.audiocard = MagicMock()
    handler.audiocard.get_switch_parameter.return_value = True

    with _patch_expanded(handler, False), \
         patch("subprocess.check_output", return_value=b"1.2.3\n"), \
         patch("subprocess.run", return_value=_fake_completed("", "")) as mock_run:
        handler.system_info_load()

    assert handler.software_version == "1.2.3"
    verify_calls = [c for c in mock_run.call_args_list if c.args and c.args[0][:3] == ["dpkg", "--verify", "pi-stomp"]]
    assert len(verify_calls) == 1


def test_system_info_load_dpkg_drifted(v2_system: SystemFixture):
    """No EXPANDED marker: dpkg --verify reports drift → version + '*'."""
    handler = v2_system.handler
    hw = v2_system.hw
    hw.relay = MagicMock()
    hw.relay.get.return_value = False
    handler.audiocard = MagicMock()
    handler.audiocard.get_switch_parameter.return_value = True

    verify_out = "??5?????? /opt/pistomp/pi-stomp/modalapi/modhandler.py\n"

    with _patch_expanded(handler, False), \
         patch("subprocess.check_output", return_value=b"1.2.3\n"), \
         patch("subprocess.run", return_value=_fake_completed(verify_out, "")):
        handler.system_info_load()

    assert handler.software_version == "1.2.3*"


def test_system_info_load_git_clean(v2_system: SystemFixture):
    """EXPANDED marker present: git describe runs, clean tree → rich version."""
    handler = v2_system.handler
    hw = v2_system.hw
    hw.relay = MagicMock()
    hw.relay.get.return_value = False
    handler.audiocard = MagicMock()
    handler.audiocard.get_switch_parameter.return_value = True

    with _patch_expanded(handler, True), \
         patch("subprocess.check_output", return_value=b"v3.0.4-224-gd392af1\n"):
        handler.system_info_load()

    assert handler.software_version == "v3.0.4-224-gd392af1\n"


def test_system_info_load_git_dirty(v2_system: SystemFixture):
    """EXPANDED marker present: git describe --dirty=* appends '*' on drift."""
    handler = v2_system.handler
    hw = v2_system.hw
    hw.relay = MagicMock()
    hw.relay.get.return_value = False
    handler.audiocard = MagicMock()
    handler.audiocard.get_switch_parameter.return_value = True

    with _patch_expanded(handler, True), \
         patch("subprocess.check_output", return_value=b"v3.0.4-224-gd392af1*\n"):
        handler.system_info_load()

    assert handler.software_version == "v3.0.4-224-gd392af1*\n"
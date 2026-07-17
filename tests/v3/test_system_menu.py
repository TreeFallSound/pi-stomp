"""v3-specific system menu behaviour."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from tests.types import SystemFixture


def _fake_completed(stdout: str = "", stderr: str = "") -> MagicMock:
    """A CompletedProcess-like MagicMock for subprocess.run."""
    cp = MagicMock()
    cp.stdout = stdout
    cp.stderr = stderr
    return cp


def _setup(handler):
    handler.audiocard = MagicMock()
    handler.audiocard.get_switch_parameter.return_value = True
    handler.audiocard.get_bypass_left.return_value = False
    handler.audiocard.get_bypass_right.return_value = True


def _patch_expanded(handler, expanded: bool):
    """Patch Path.exists so only the EXPANDED marker check returns `expanded`.

    All other Path.exists calls (e.g. build_file) fall through to the real
    filesystem.
    """
    marker = Path(handler.homedir + "/.git/EXPANDED")
    real_exists = Path.exists

    def _exists(self):
        if self == marker:
            return expanded
        return real_exists(self)

    return patch("pathlib.Path.exists", side_effect=_exists, autospec=True)


def test_system_info_load(v3_system: SystemFixture):
    """On v3 (no relay), system_info_load reads bypass state from the audiocard.

    Default (no EXPANDED marker): dpkg path runs, returns bare version.
    """
    handler = v3_system.handler
    _setup(handler)

    with (
        _patch_expanded(handler, False),
        patch("subprocess.check_output", return_value=b"v1.0.0-abc\n"),
        patch("subprocess.run", return_value=_fake_completed("", "")),
    ):
        handler.system_info_load()

    assert handler.software_version == "v1.0.0-abc"
    assert handler.eq_status is True
    assert handler.bypass_left is False
    assert handler.bypass_right is True


def test_system_info_load_dpkg_clean(v3_system: SystemFixture):
    """No EXPANDED marker: dpkg --verify clean → bare version, no asterisk."""
    handler = v3_system.handler
    _setup(handler)

    with (
        _patch_expanded(handler, False),
        patch("subprocess.check_output", return_value=b"1.2.3\n"),
        patch("subprocess.run", return_value=_fake_completed("", "")) as mock_run,
    ):
        handler.system_info_load()

    handler._drift_check.join()
    assert handler.software_version == "1.2.3"
    assert handler.get_software_version() == "1.2.3"
    verify_calls = [c for c in mock_run.call_args_list if c.args and c.args[0][:3] == ["dpkg", "--verify", "pi-stomp"]]
    assert len(verify_calls) == 1


def test_system_info_load_dpkg_drifted(v3_system: SystemFixture):
    """No EXPANDED marker: dpkg --verify reports drift → version + '*'."""
    handler = v3_system.handler
    _setup(handler)

    verify_out = "??5?????? /opt/pistomp/pi-stomp/modalapi/modhandler.py\n"

    with (
        _patch_expanded(handler, False),
        patch("subprocess.check_output", return_value=b"1.2.3\n"),
        patch("subprocess.run", return_value=_fake_completed(verify_out, "")),
    ):
        handler.system_info_load()

    handler._drift_check.join()
    assert handler.software_version == "1.2.3"
    assert handler.get_software_version() == "1.2.3*"


def test_system_info_load_git_clean(v3_system: SystemFixture):
    """EXPANDED marker present: git describe runs, clean tree → rich version."""
    handler = v3_system.handler
    _setup(handler)

    with _patch_expanded(handler, True), patch("subprocess.check_output", return_value=b"v3.0.4-224-gd392af1\n"):
        handler.system_info_load()

    assert handler.software_version == "v3.0.4-224-gd392af1\n"


def test_system_info_load_git_dirty(v3_system: SystemFixture):
    """EXPANDED marker present: git describe --dirty=* appends '*' on drift."""
    handler = v3_system.handler
    _setup(handler)

    with _patch_expanded(handler, True), patch("subprocess.check_output", return_value=b"v3.0.4-224-gd392af1*\n"):
        handler.system_info_load()

    assert handler.software_version == "v3.0.4-224-gd392af1*\n"

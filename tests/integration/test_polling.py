"""poll_system_info() and poll_lcd_updates() — handler-level polling logic."""

import subprocess
from unittest.mock import patch

from tests.types import SystemFixture


def test_poll_system_info(modhandler_system: SystemFixture):
    """poll_system_info() parses systemctl + vcgencmd output into handler state."""
    handler = modhandler_system.handler

    def sub_output(cmd, **kwargs):
        if cmd[0] == "systemctl":
            return b"SystemState=running"
        if "get_throttled" in cmd:
            return b"throttled=0x0"
        if "measure_temp" in cmd:
            return b"temp=45.2'C"
        return b""

    with patch("subprocess.check_output", side_effect=sub_output):
        handler.poll_system_info()

    assert handler.SystemState == "running"
    assert handler.throttled == "0x0"
    assert handler.temperature == "45.2'C"


def test_poll_system_info_subprocess_failure(modhandler_system: SystemFixture):
    """poll_system_info() sets state to 'unknown' when subprocess calls fail."""
    handler = modhandler_system.handler

    with patch("subprocess.check_output", side_effect=subprocess.CalledProcessError(1, "vcgencmd")):
        handler.poll_system_info()

    assert handler.SystemState == "unknown"
    assert handler.throttled == "unknown"
    assert handler.temperature == "unknown"


def test_poll_lcd_updates(modhandler_system: SystemFixture):
    """poll_lcd_updates() calls through without raising."""
    handler = modhandler_system.handler
    handler.poll_lcd_updates()
    assert handler.lcd is not None

"""Bootstrap fixtures for emulator tests.

Mirrors tests/integration/conftest.py's patch set but routed at the emulator
entrypoints (modalapi.mod.AsyncWebSocketBridge, modalapi.modhandler.AsyncWebSocketBridge,
modalapi.wifi.WifiManager).  Drives pygame headlessly via SDL_VIDEODRIVER=dummy."""

import json
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

import common.token as Token


@pytest.fixture(autouse=True)
def _restore_global_pygame_state():
    """Re-init pygame and drop cached fonts after each emulator test.

    Emulator teardown quits pygame — hardware `cleanup()` (the clean-exit path
    exercised by test_bootstrap) and the window-close tests both call
    `pygame_quit()`. That invalidates every `Font` cached in the Config
    singleton ("freetype module quit since freetype font created") for the rest
    of the session, breaking later suites. Restoring state here contains the
    teardown to the suite that causes it rather than leaking it process-wide.
    """
    yield
    from uilib.config import Config
    from uilib.pygame_init import init as pygame_init

    pygame_init()
    if Config._instance is not None:
        # Cleared, not rebuilt: Config().__init__ re-adds defaults on next use.
        Config._instance.fonts = {}


def _mod_get(url, **_):
    resp = MagicMock()
    resp.status_code = 200
    if "pedalboard/list" in url:
        resp.text = json.dumps(
            [
                {Token.TITLE: "Emu Rig", Token.BUNDLE: "/path/to/emu.pedalboard"},
            ]
        )
    elif "snapshot/list" in url:
        resp.text = json.dumps({"0": "Clean"})
    elif "snapshot/name" in url:
        resp.text = json.dumps({"name": "Clean"})
    else:
        resp.text = "{}"
    return resp


def _mod_post(*_, **__):
    resp = MagicMock()
    resp.status_code = 200
    resp.text = "{}"
    return resp


def _reset_singletons():
    # Modhandler / Mod stash their single instance under a name-mangled attr.
    try:
        from modalapi.modhandler import Modhandler

        setattr(Modhandler, "_Modhandler__single", None)
    except Exception:
        pass
    try:
        from modalapi.mod import Mod

        setattr(Mod, "_Mod__single", None)
    except Exception:
        pass


@pytest.fixture
def emulator_env(tmp_path, monkeypatch):
    """Patches + env so emulator.bootstrap.bootstrap_emulator() runs offline."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    _reset_singletons()

    with ExitStack() as stack:
        mock_get = stack.enter_context(patch("pistomp.httpclient.get", side_effect=_mod_get))
        mock_post = stack.enter_context(patch("pistomp.httpclient.post", side_effect=_mod_post))
        stack.enter_context(patch("modalapi.pedalboard.Pedalboard.hydrate"))
        stack.enter_context(patch("modalapi.mod.AsyncWebSocketBridge"))
        stack.enter_context(patch("modalapi.modhandler.AsyncWebSocketBridge"))
        stack.enter_context(patch("emulator.mod.AsyncWebSocketBridge"))
        stack.enter_context(patch("emulator.modhandler.AsyncWebSocketBridge"))
        # MIDI device may not exist on CI; force the bootstrap's except branch.
        stack.enter_context(patch("emulator.bootstrap.open_midioutput", side_effect=RuntimeError("no midi")))
        yield {"get": mock_get, "post": mock_post, "tmp_path": tmp_path}

    _reset_singletons()

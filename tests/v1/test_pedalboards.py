"""Pedalboard switching via the v1 (Mod) encoder state machines and LCD menu.

The LCD menu calls handler.pedalboard_change(pedalboard) with the chosen board.
Before the fix, mod.py's pedalboard_change() took no argument and silently used
selected_pedalboard_index, so the menu could load the wrong board.

The encoder tests also confirm the full encoder→load_bundle integration path.
"""

import pistomp.switchstate as switchstate
from modalapi.mod import TopEncoderMode, UniversalEncoderMode
from tests.types import SystemFixtureLegacy


def _load_bundle_url(mock_post):
    calls = [c for c in mock_post.call_args_list if "load_bundle" in c.args[0]]
    assert calls, "no load_bundle POST found"
    return calls[0].args[1]["bundlepath"]


def test_v1_pedalboard_change_loads_passed_board_not_selected_index(v1_system: SystemFixtureLegacy, get_urls):
    """pedalboard_change(pb) loads pb regardless of selected_pedalboard_index.

    This is the regression the fix addressed: the LCD menu passes the chosen
    pedalboard as an argument; the old no-arg form ignored it and used
    selected_pedalboard_index, potentially loading the wrong board.
    """
    handler = v1_system.handler
    mock_post = v1_system.mock_post

    # Index deliberately left at 0 (first board) to expose the old bug
    handler.selected_pedalboard_index = 0
    target_pb = handler.pedalboard_list[1]  # second board: /path/to/new.pedalboard

    handler.pedalboard_change(target_pb)

    assert _load_bundle_url(mock_post) == "/path/to/new.pedalboard"
    assert handler.current.pedalboard.bundle == "/path/to/new.pedalboard"


def test_v1_top_encoder_pedalboard_change(v1_system: SystemFixtureLegacy, get_urls):
    """Top encoder: PEDALBOARD_SELECTED + RELEASED fires load_bundle for the selected board."""
    handler = v1_system.handler
    mock_post = v1_system.mock_post

    handler.selected_pedalboard_index = 1  # second board: /path/to/new.pedalboard
    handler.top_encoder_mode = TopEncoderMode.PEDALBOARD_SELECTED

    handler.top_encoder_sw(switchstate.Value.RELEASED)

    assert _load_bundle_url(mock_post) == "/path/to/new.pedalboard"
    assert handler.current.pedalboard.bundle == "/path/to/new.pedalboard"


def test_v1_universal_encoder_pedalboard_change(v1_system: SystemFixtureLegacy, get_urls):
    """Universal encoder: PEDALBOARD_SELECT + RELEASED fires load_bundle for the selected board."""
    handler = v1_system.handler
    mock_post = v1_system.mock_post

    handler.selected_pedalboard_index = 1  # second board: /path/to/new.pedalboard
    handler.universal_encoder_mode = UniversalEncoderMode.PEDALBOARD_SELECT

    handler.universal_encoder_sw(switchstate.Value.RELEASED)

    assert _load_bundle_url(mock_post) == "/path/to/new.pedalboard"
    assert handler.current.pedalboard.bundle == "/path/to/new.pedalboard"

import os
from unittest.mock import patch

import pytest

from uilib.animated_image import AnimatedImageWidget
from uilib.box import Box


IMAGES = os.path.join(os.path.dirname(__file__), "..", "images")
STATIC = os.path.join(IMAGES, "wifi_gray.png")
FRAMES = [os.path.join(IMAGES, f"wifi_processing_{i}.png") for i in range(1, 4)]


def make_widget(frame_paths=FRAMES):
    return AnimatedImageWidget(
        static_path=STATIC, frame_paths=frame_paths, box=Box.xywh(0, 0, 20, 20)
    )


def test_tick_on_stopped_widget_is_noop():
    w = make_widget()
    with patch.object(w, "refresh") as mock_refresh:
        w.tick()
        w.tick()
    mock_refresh.assert_not_called()


def test_play_then_tick_advances_and_refreshes():
    w = make_widget()
    w.play()
    with patch.object(w, "refresh") as mock_refresh:
        w.tick()
        assert w.image is w._frames[1]
        w.tick()
        assert w.image is w._frames[2]
    assert mock_refresh.call_count == 2


def test_tick_wraps_around():
    w = make_widget()
    w.play()
    for _ in range(len(FRAMES)):
        w.tick()
    # After n ticks of n frames, idx wraps to 0
    assert w._frame_idx == 0
    assert w.image is w._frames[0]


def test_stop_same_path_does_not_refresh():
    w = make_widget()
    with patch.object(w, "refresh") as mock_refresh:
        w.stop(STATIC)
    mock_refresh.assert_not_called()
    assert not w.is_playing


def test_stop_different_path_refreshes_once():
    w = make_widget()
    with patch.object(w, "refresh") as mock_refresh:
        w.stop(os.path.join(IMAGES, "wifi_silver.png"))
    mock_refresh.assert_called_once()


def test_play_twice_is_noop():
    w = make_widget()
    w.play()
    w._frame_idx = 2
    w.play()  # second call must not reset
    assert w._frame_idx == 2


def test_empty_frames_tick_is_safe_even_when_playing():
    w = make_widget(frame_paths=())
    w.play()
    with patch.object(w, "refresh") as mock_refresh:
        w.tick()
    mock_refresh.assert_not_called()


def test_mismatched_frame_size_raises():
    bad = os.path.join(IMAGES, "wifi_silver.png")  # same size, so use a deliberately mismatched one
    # Find some other image that differs in size
    from PIL import Image
    base_size = Image.open(STATIC).size
    # Search for a differently-sized image
    other = None
    for fname in os.listdir(IMAGES):
        p = os.path.join(IMAGES, fname)
        if not fname.lower().endswith(".png"):
            continue
        try:
            if Image.open(p).size != base_size:
                other = p
                break
        except Exception:
            continue
    if other is None:
        pytest.skip("no differently-sized image available to test mismatch")
    with pytest.raises(ValueError):
        AnimatedImageWidget(
            static_path=STATIC, frame_paths=[other], box=Box.xywh(0, 0, 20, 20)
        )


def test_replace_img_path_equality_guard():
    w = make_widget()
    with patch.object(w, "refresh") as mock_refresh:
        w.replace_img(STATIC)  # same as ctor path
    mock_refresh.assert_not_called()

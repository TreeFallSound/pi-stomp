import os
from unittest.mock import patch

from PIL import Image

from uilib.box import Box
from uilib.image import ImageWidget


IMAGES = os.path.join(os.path.dirname(__file__), "..", "images")
GRAY = os.path.join(IMAGES, "wifi_gray.png")
SILVER = os.path.join(IMAGES, "wifi_silver.png")


def make_widget(image: str | Image.Image = GRAY):
    return ImageWidget(image=image, box=Box.xywh(0, 0, 20, 20))


def test_construct_from_path_opens_image():
    w = make_widget(GRAY)
    assert isinstance(w.image, Image.Image)
    assert w._image_path == GRAY


def test_construct_from_pil_image_uses_it_directly():
    img = Image.open(GRAY)
    w = make_widget(img)
    assert w.image is img
    assert w._image_path is None


def test_replace_img_same_path_is_noop():
    w = make_widget(GRAY)
    original = w.image
    with patch.object(w, "refresh") as mock_refresh:
        w.replace_img(GRAY)
    mock_refresh.assert_not_called()
    assert w.image is original


def test_replace_img_different_path_loads_and_refreshes():
    w = make_widget(GRAY)
    with patch.object(w, "refresh") as mock_refresh:
        w.replace_img(SILVER)
    mock_refresh.assert_called_once()
    assert w._image_path == SILVER


def test_replace_img_with_pil_image_swaps_and_clears_path():
    w = make_widget(GRAY)
    new_img = Image.open(SILVER)
    with patch.object(w, "refresh") as mock_refresh:
        w.replace_img(new_img)
    mock_refresh.assert_called_once()
    assert w.image is new_img
    assert w._image_path is None


def test_replace_img_with_same_pil_image_is_noop():
    img = Image.open(GRAY)
    w = make_widget(img)
    with patch.object(w, "refresh") as mock_refresh:
        w.replace_img(img)
    mock_refresh.assert_not_called()


def test_replace_path_after_pil_swap_reloads_even_if_path_matches_prior():
    """After a PIL.Image swap, _image_path is cleared, so re-supplying the
    original path must actually reload (not be skipped by the same-path guard)."""
    w = make_widget(GRAY)
    w.replace_img(Image.open(SILVER))  # clears _image_path
    with patch.object(w, "refresh") as mock_refresh:
        w.replace_img(GRAY)
    mock_refresh.assert_called_once()
    assert w._image_path == GRAY

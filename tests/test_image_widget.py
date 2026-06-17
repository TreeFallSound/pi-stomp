import os
from unittest.mock import patch

import pygame

from uilib.box import Box
from uilib.image import ImageWidget, load_surface


IMAGES = os.path.join(os.path.dirname(__file__), "..", "images")
GRAY = os.path.join(IMAGES, "wifi_gray.png")
SILVER = os.path.join(IMAGES, "wifi_silver.png")


def make_widget(image: str | pygame.Surface = GRAY):
    return ImageWidget(image=image, box=Box.xywh(0, 0, 20, 20))


def test_construct_from_path_loads_surface():
    w = make_widget(GRAY)
    assert isinstance(w.image, pygame.Surface)
    assert w._image_path == GRAY


def test_construct_from_surface_uses_it_directly():
    surf = load_surface(GRAY)
    w = make_widget(surf)
    assert w.image is surf
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


def test_replace_img_with_surface_swaps_and_clears_path():
    w = make_widget(GRAY)
    new_surf = load_surface(SILVER)
    with patch.object(w, "refresh") as mock_refresh:
        w.replace_img(new_surf)
    mock_refresh.assert_called_once()
    assert w.image is new_surf
    assert w._image_path is None


def test_replace_img_with_same_surface_is_noop():
    surf = load_surface(GRAY)
    w = make_widget(surf)
    with patch.object(w, "refresh") as mock_refresh:
        w.replace_img(surf)
    mock_refresh.assert_not_called()


def test_replace_path_after_surface_swap_reloads_even_if_path_matches_prior():
    """After a Surface swap, _image_path is cleared, so re-supplying the
    original path must actually reload (not be skipped by the same-path guard)."""
    w = make_widget(GRAY)
    w.replace_img(load_surface(SILVER))  # clears _image_path
    with patch.object(w, "refresh") as mock_refresh:
        w.replace_img(GRAY)
    mock_refresh.assert_called_once()
    assert w._image_path == GRAY

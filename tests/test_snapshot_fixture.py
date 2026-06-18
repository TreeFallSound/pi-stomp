"""
Tests for assert_snapshot: correctness of dirty-rect reporting and basic
performance of the numpy diff path.
"""

import timeit

import numpy as np
import pygame
import pytest

from tests.conftest import assert_snapshot


W, H = 320, 240


def _solid(color: tuple[int, int, int]) -> pygame.Surface:
    s = pygame.Surface((W, H))
    s.fill(color)
    return s


def _with_rect(base_color, rect_color, rect) -> pygame.Surface:
    """Solid surface with a filled rectangle drawn on top."""
    s = _solid(base_color)
    pygame.draw.rect(s, rect_color, rect)
    return s


# ---------------------------------------------------------------------------
# Correctness
# ---------------------------------------------------------------------------


def test_identical_surfaces_pass(tmp_path, monkeypatch):
    monkeypatch.setattr("tests.conftest._SNAPSHOT_DIR", tmp_path)
    surf = _solid((10, 20, 30))
    assert_snapshot(surf, "identical", update=True)  # write baseline
    assert_snapshot(surf, "identical", update=False)  # must pass


def test_mismatch_reports_dirty_rect(tmp_path, monkeypatch):
    monkeypatch.setattr("tests.conftest._SNAPSHOT_DIR", tmp_path)
    baseline = _solid((0, 0, 0))
    assert_snapshot(baseline, "dirty", update=True)

    # Single changed pixel at (10, 20)
    changed = _solid((0, 0, 0))
    changed.set_at((10, 20), (255, 0, 0))

    with pytest.raises(AssertionError) as exc:
        assert_snapshot(changed, "dirty", update=False)
    msg = str(exc.value)
    assert "(10, 20)-(10, 20)" in msg
    assert "[1x1px]" in msg


def test_mismatch_rect_spans_full_changed_region(tmp_path, monkeypatch):
    monkeypatch.setattr("tests.conftest._SNAPSHOT_DIR", tmp_path)

    baseline = _solid((0, 0, 0))
    assert_snapshot(baseline, "region", update=True)

    # Change a 40x30 block starting at (50, 60)
    changed = _with_rect((0, 0, 0), (128, 64, 32), pygame.Rect(50, 60, 40, 30))

    with pytest.raises(AssertionError) as exc:
        assert_snapshot(changed, "region", update=False)
    msg = str(exc.value)
    assert "(50, 60)-(89, 89)" in msg
    assert "[40x30px]" in msg


def test_full_screen_change_reports_full_rect(tmp_path, monkeypatch):
    monkeypatch.setattr("tests.conftest._SNAPSHOT_DIR", tmp_path)
    assert_snapshot(_solid((0, 0, 0)), "full", update=True)

    with pytest.raises(AssertionError) as exc:
        assert_snapshot(_solid((255, 255, 255)), "full", update=False)
    msg = str(exc.value)
    assert f"(0, 0)-({W - 1}, {H - 1})" in msg
    assert f"[{W}x{H}px]" in msg


# ---------------------------------------------------------------------------
# Benchmark: dirty-rect diff on a 320×240 surface
# ---------------------------------------------------------------------------


def _run_diff(a_buf: bytes, b_buf: bytes):
    """Replicate the numpy path from assert_snapshot."""
    a = np.frombuffer(a_buf, dtype=np.uint8).reshape(H, W, 3)
    b = np.frombuffer(b_buf, dtype=np.uint8).reshape(H, W, 3)
    diff = np.any(a != b, axis=2)
    ys, xs = np.where(diff)
    return int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())


def test_benchmark_dirty_rect(tmp_path):
    """Dirty-rect diff on a full 320x240 frame must complete in < 5 ms on average."""
    a_surf = _solid((0, 0, 0))
    b_surf = _with_rect((0, 0, 0), (255, 128, 0), pygame.Rect(100, 80, 120, 60))
    a_buf = pygame.image.tobytes(a_surf, "RGB")
    b_buf = pygame.image.tobytes(b_surf, "RGB")

    n = 200
    elapsed = timeit.timeit(lambda: _run_diff(a_buf, b_buf), number=n)
    avg_ms = elapsed / n * 1000
    print(f"\ndirty-rect diff avg: {avg_ms:.3f} ms over {n} runs")
    assert avg_ms < 5.0, f"diff too slow: {avg_ms:.3f} ms"

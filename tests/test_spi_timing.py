import pytest

from uilib.spi_timing import (
    DEFAULT_PROFILE,
    DEFAULT_SOURCE_HZ,
    PUSH_PROFILE,
    SPI_SOURCE_HZ,
    actual_spi_hz,
    push_profile,
    spi_source_hz,
    transfer_ms,
)

PI3 = 400_000_000  # v2 — BCM2837 VPU core clock
PI5 = 200_000_000  # v3 — RP1 CLK_SYS


@pytest.mark.parametrize(
    "requested, expected_hz",
    [
        # Measured on a Pi 3A+ (docs/spi_lcd_timing_pi3.md): every achievable
        # clock is 400 MHz / even divisor.
        (12_500_000, 12_500_000),  # cdiv 32
        (20_000_000, 20_000_000),  # cdiv 20
        (25_000_000, 25_000_000),  # cdiv 16
        (28_571_428, 25_000_000),  # cdiv 15 -> 16
        (33_333_333, 400_000_000 / 14),  # cdiv 13 -> 14
        (40_000_000, 40_000_000),  # cdiv 10
        (44_444_444, 40_000_000),  # cdiv 9 -> 10
        (50_000_000, 50_000_000),  # cdiv 8 (production)
        (57_142_857, 50_000_000),  # cdiv 7 -> 8
        (80_000_000, 400_000_000 / 6),  # cdiv 5 -> 6
        (99_000_000, 400_000_000 / 6),  # cdiv 5 -> 6
        (100_000_000, 100_000_000),  # cdiv 4 — garbles the ILI9341
    ],
)
def test_pi3_divisor_rule(requested, expected_hz):
    assert actual_spi_hz(requested, PI3) == pytest.approx(expected_hz)


def test_pi3_one_hertz_below_a_divisor_point_costs_a_full_step():
    # 400e6 / 6 == 66_666_666.67, so 66_666_666 rounds the divisor to 7 -> 8.
    assert actual_spi_hz(66_666_666, PI3) == pytest.approx(50_000_000)
    assert actual_spi_hz(66_666_667, PI3) == pytest.approx(400_000_000 / 6)


@pytest.mark.parametrize(
    "requested, expected_hz",
    [
        (81_000_000, 50_000_000),  # BAUDR 3 -> 4
        (50_000_000, 50_000_000),  # BAUDR 4
        (99_000_000, 50_000_000),  # BAUDR 3 -> 4
        (100_000_000, 100_000_000),  # BAUDR 2
    ],
)
def test_pi5_divisor_rule(requested, expected_hz):
    assert actual_spi_hz(requested, PI5) == pytest.approx(expected_hz)


def test_pi5_cannot_reach_66mhz_but_pi3_can():
    # 200/6 needs BAUDR 3 (odd); 400/6 is even, so v2 out-runs v3 here.
    assert actual_spi_hz(70_000_000, PI5) == pytest.approx(50_000_000)
    assert actual_spi_hz(70_000_000, PI3) == pytest.approx(400_000_000 / 6)


def test_actual_never_exceeds_request():
    for source in (PI3, PI5):
        for requested in range(1_000_000, 100_000_000, 997_000):
            assert actual_spi_hz(requested, source) <= requested


def test_divisor_floors_at_two():
    assert actual_spi_hz(10_000_000_000, PI3) == pytest.approx(PI3 / 2)


def test_rejects_nonpositive():
    with pytest.raises(ValueError):
        actual_spi_hz(0, PI3)


def test_source_from_device_tree(monkeypatch, tmp_path):
    dt = tmp_path / "compatible"
    dt.write_bytes(b"raspberrypi,3-model-b-plus\0brcm,bcm2837\0")
    monkeypatch.setattr("uilib.spi_timing._DT_COMPATIBLE", dt)
    assert spi_source_hz() == PI3


def test_source_defaults_when_device_tree_absent(monkeypatch, tmp_path):
    monkeypatch.setattr("uilib.spi_timing._DT_COMPATIBLE", tmp_path / "nope")
    assert spi_source_hz() == DEFAULT_SOURCE_HZ


def test_source_defaults_on_unknown_soc(monkeypatch, tmp_path):
    dt = tmp_path / "compatible"
    dt.write_bytes(b"acme,widget\0")
    monkeypatch.setattr("uilib.spi_timing._DT_COMPATIBLE", dt)
    assert spi_source_hz() == DEFAULT_SOURCE_HZ


def test_every_known_soc_has_a_push_profile():
    # push_profile() indexes PUSH_PROFILE with whatever soc_key() returns, and
    # soc_key() answers from SPI_SOURCE_HZ. A SoC in one dict but not the other
    # is a KeyError on that board and nowhere else.
    assert SPI_SOURCE_HZ.keys() == PUSH_PROFILE.keys()


def test_pi3_push_costs_more_than_pi5(tmp_path, monkeypatch):
    # The CPU-bound terms are why the profile is per-SoC at all: an A53 pack is
    # ~7x an A76's, and treating them alike over-admits inline pushes on v2.
    dt = tmp_path / "compatible"

    dt.write_bytes(b"brcm,bcm2837\0")
    monkeypatch.setattr("uilib.spi_timing._DT_COMPATIBLE", dt)
    pi3 = push_profile()

    dt.write_bytes(b"brcm,bcm2712\0")
    pi5 = push_profile()

    assert pi3.pipeline_ms_per_px > 5 * pi5.pipeline_ms_per_px
    assert pi3.fixed_ms > pi5.fixed_ms


def test_unknown_soc_on_a_real_board_gets_the_slow_profile(tmp_path, monkeypatch):
    # A Pi 2, or a Pi 6 we've never benched: guessing Pi 5's costs here would
    # over-admit inline pushes and stall the poll loop.
    dt = tmp_path / "compatible"
    dt.write_bytes(b"brcm,bcm9999\0")
    monkeypatch.setattr("uilib.spi_timing._DT_COMPATIBLE", dt)
    assert push_profile() == PUSH_PROFILE["brcm,bcm2837"]


def test_off_device_gets_the_default_profile(tmp_path, monkeypatch):
    # No device tree at all (mac, emulator, CI) — pair with DEFAULT_SOURCE_HZ.
    monkeypatch.setattr("uilib.spi_timing._DT_COMPATIBLE", tmp_path / "absent")
    assert push_profile() == DEFAULT_PROFILE


def test_transfer_ms_scales_with_clock():
    slow = transfer_ms(76800, 50_000_000)
    fast = transfer_ms(76800, 400_000_000 / 6)
    assert slow > fast
    # Wire time dominates a full frame: 66.67 MHz should be meaningfully cheaper.
    # The floor is the pure wire ratio, 50/66.67 = 0.75; the CPU-bound terms are
    # what hold it above that, so this tracks the host's push profile.
    assert fast / slow == pytest.approx(0.76, abs=0.03)

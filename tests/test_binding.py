"""Native libmgba binding checks — gated on availability.

The compiled binding requires `brew install mgba` + `python -m game._mgba_build`;
loading a core additionally requires a real ROM at ROM_PATH (copyrighted, never
in CI). Each test skips cleanly when its prerequisite is absent, so this file is
safe to run everywhere while still exercising the binding where possible.
"""
import os
import pytest

try:
    from game import _mgba_native  # noqa: F401
    HAVE_BINDING = True
except Exception:
    HAVE_BINDING = False

from config import ROM_PATH

binding = pytest.mark.skipif(not HAVE_BINDING, reason="binding not built (python -m game._mgba_build)")
rom = pytest.mark.skipif(not os.path.isfile(ROM_PATH), reason=f"ROM not present at {ROM_PATH}")


@binding
def test_binding_exposes_expected_symbols():
    from game._mgba_native import lib
    for name in ("pycore_load", "pycore_read8", "pycore_set_keys",
                 "pycore_run_frame", "pycore_screenshot", "pycore_video_ptr",
                 "pycore_load_save", "pycore_reset"):
        assert hasattr(lib, name), f"missing binding symbol {name}"


@binding
@rom
def test_loads_leafgreen_and_reads_header():
    from game.mgba_core import NativeMGBAClient
    m = NativeMGBAClient(show_window=False)
    assert m.verify_connection()
    assert m.get_game_code() == "AGB-BPGE"
    assert m.get_game_title() == "POKEMON LEAF"


@binding
@rom
def test_framebuffer_size_matches_gba():
    from game.mgba_core import NativeMGBAClient
    m = NativeMGBAClient(show_window=False)
    m.tick(2)
    assert len(m.framebuffer()) == 240 * 160 * 4


@binding
@rom
def test_reset_reboots_without_crashing():
    from game.mgba_core import NativeMGBAClient
    m = NativeMGBAClient(show_window=False)
    m.tick(120)                 # advance into the boot sequence
    m.reset()                   # power-cycle
    m.tick(2)
    # ROM header is still readable after a reset (core is alive and re-booting).
    assert m.get_game_code() == "AGB-BPGE"


@binding
@rom
def test_load_save_returns_bool(tmp_path):
    from game.mgba_core import NativeMGBAClient
    m = NativeMGBAClient(show_window=False)
    # mGBA opens the cartridge save (creating it if absent) and reports success.
    result = m.load_save(str(tmp_path / "fresh.sav"))
    assert result is True
    m.reset()  # load-then-reset is the intended "Continue" sequence; must not crash
    m.tick(2)
    assert m.get_game_code() == "AGB-BPGE"

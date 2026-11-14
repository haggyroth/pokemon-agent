"""Live tests: drive the REAL ROM through the native libmgba binding.

They are skipped automatically when the binding, the ROM, or the fixtures are missing (so CI, which has
no ROM, just skips them). Run locally with:

    python -m pytest tests/live -v

Fixtures live in `saves/live/` (gitignored — ROM-derived). See tests/live/README.md for what each one is.
"""
import os
import sys
from pathlib import Path

import pytest

# Force a headless, text-only run BEFORE any project module (config reads .env at import — a developer's
# SHOW_WINDOW=true would otherwise open a paced window and make these tests crawl).
os.environ.update(USE_VISION="false", SHOW_WINDOW="false", MGBA_BACKEND="native")
os.environ.pop("START_FROM_STATE", None)
os.environ.pop("RESUME", None)

ROOT = Path(__file__).resolve().parents[2]
LIVE_DIR = Path(os.environ.get("LIVE_DIR", ROOT / "saves" / "live"))
ROM = Path(os.path.expanduser(os.environ.get("ROM_PATH", "~/mgba-http/Pokemon_LeafGreen.gba")))


@pytest.fixture(scope="session")
def rt(tmp_path_factory):
    """One emulator runtime for the whole live session (booting takes a few seconds)."""
    if not ROM.exists():
        pytest.skip(f"ROM not found at {ROM}")
    sav = LIVE_DIR / "work.sav"
    if not sav.exists():
        pytest.skip(f"fixture {sav} missing — see tests/live/README.md")
    try:
        import game.mgba_core as mgba_core   # needs the compiled cffi binding
    except Exception as e:      # ImportError / OSError when libmgba isn't built
        pytest.skip(f"native binding unavailable: {e}")
    # tests/conftest.py imports config (→ .env) before this file runs, so a developer's SHOW_WINDOW=true
    # is already baked in: override the module constants directly. A paced window makes tests crawl.
    mgba_core.SHOW_WINDOW = False
    os.environ["START_FROM_SAVE"] = str(sav)
    sys.path.insert(0, str(ROOT))
    import main
    tmp = tmp_path_factory.mktemp("live")
    runtime = main.build_runtime(ltm_path=str(tmp / "ltm.json"), journal_path=str(tmp / "j.jsonl"),
                                 verbose=False)
    if runtime is None:
        pytest.skip("emulator runtime could not be built")
    return runtime


@pytest.fixture
def live(rt):
    """Per-test handle: `live.load('threemon')` restores a fixture state; helpers from harness.py."""
    from live.harness import Live
    return Live(rt, LIVE_DIR)

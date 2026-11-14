"""The viewer decouples emulation pacing from presentation (the 1x/turbo stutter on macOS)."""
import time

from game.viewer import PygameViewer


def _viewer(fps=0, present_hz=60):
    v = PygameViewer.__new__(PygameViewer)
    v.min_frame_dt = (1.0 / fps) if fps > 0 else 0.0
    v.present_dt = 1.0 / present_hz
    v._deadline, v._last_present, v._pending, v._skipped, v._closed = None, 0.0, False, 0, False
    v.draws = 0

    def draw(buf, now):
        v.draws += 1
        v._pending = False
        v._last_present = time.perf_counter()
    v._draw = draw
    v._pump = lambda: None
    return v


def test_uncapped_emulation_presents_at_most_present_hz():
    v = _viewer(fps=0)
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 0.2:
        v.render(b"")                      # an emulator running flat out
    assert v.draws <= 0.2 * 60 + 2 and v._skipped > 100 and v._pending


def test_flush_shows_the_newest_frame_once_after_skips():
    v = _viewer(fps=0)
    v.render(b"")                           # presents (first frame)
    v.render(b"")                           # skipped: too soon
    assert v._pending
    before = v.draws
    v.flush(b"")
    v.flush(b"")                            # nothing pending any more
    assert v.draws == before + 1 and not v._pending


def test_paced_playback_holds_the_requested_speed_not_the_display_rate():
    v = _viewer(fps=600)                    # 10x real time, fast to test
    t0 = time.perf_counter()
    for _ in range(120):
        v.render(b"")
    dt = time.perf_counter() - t0
    assert 0.17 <= dt <= 0.45, dt           # ≈ 120 frames / 600 fps = 0.2 s


def test_closed_viewer_is_inert():
    v = _viewer()
    v._closed = True
    v.render(b"")
    v.flush(b"")
    assert v.draws == 0

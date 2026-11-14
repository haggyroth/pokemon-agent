"""Live pygame window for watching the native backend play.

The native emulator is headless, so this reads libmgba's framebuffer directly
each frame and blits it to a scaled window. Because the game only advances when
the agent runs frames, the window is smooth during actions/animations and holds
the last frame still while the LLM is thinking.

Playback is paced to `VIEWER_FPS` so it's watchable: while the window is open,
`render()` sleeps so emulated frames are presented at up to VIEWER_FPS (default
120 ≈ 2× real GBA speed) instead of the emulator's raw multi-hundred-fps burst,
which flashed by incomprehensibly. This pacing only happens when a window exists —
headless runs never construct a viewer, so real (unwatched) runs stay full speed.

Closing the window (or pressing Esc) tears the window down but does NOT stop the
run — the agent keeps playing headless. This is deliberate: a backgrounded pygame
window on macOS gets spurious QUIT events, and it used to raise a KeyboardInterrupt
that killed long runs ~minutes in. To stop the run, Ctrl-C the terminal.
"""
import time
from config import VIEWER_SCALE, VIEWER_FPS


class PygameViewer:
    def __init__(self, width: int, height: int,
                 scale: int = VIEWER_SCALE, fps: int = VIEWER_FPS, present_hz: int = 60):
        import pygame  # imported lazily so headless runs never need pygame
        self._pg = pygame
        self.w, self.h = width, height
        self.scale = scale
        self.min_frame_dt = (1.0 / fps) if fps > 0 else 0.0
        self.present_dt = 1.0 / max(1, present_hz)
        self._deadline = None         # pacing schedule (see render)
        self._last_present = 0.0
        self._pending = False         # frames emulated since the last present
        self._skipped = 0
        self._closed = False

        pygame.init()
        pygame.display.set_caption("Pokemon LeafGreen — LLM Agent")
        self.screen = pygame.display.set_mode((width * scale, height * scale))

    def render(self, buf) -> None:
        """buf: a bytes-like RGBX framebuffer (w*h*4). No-op once the window has been closed (the run continues
        headless).

        Emulation speed and what you SEE are decoupled:
          * `VIEWER_FPS` paces emulated frames against a running deadline (60 ≈ real time, 120 ≈ 2×,
            0 = uncapped). Pacing sleeps only; it never depends on the display.
          * the window is only PRESENTED at most `present_hz` times a second (default 60). The old code
            presented every emulated frame, and on macOS `display.flip()` blocks on the display refresh while
            the window is visible — capping the emulator at ~1× — but returns instantly when the window is
            occluded or in Mission Control — letting it run at ~50×. That was the 1×/turbo stutter.
        """
        if self._closed:
            return
        now = time.perf_counter()
        if self.min_frame_dt > 0:
            if self._deadline is None or now - self._deadline > 0.25:
                self._deadline = now                  # (re)sync after a pause, e.g. the LLM thinking
            self._deadline += self.min_frame_dt
            wait = self._deadline - now
            if wait > 0:
                time.sleep(wait)                      # pace the emulator so motion is watchable
                now = time.perf_counter()
        if now - self._last_present < self.present_dt:
            self._pending = True                      # emulated, not drawn: flush() shows it when idle
            self._skipped += 1
            if self._skipped % 64 == 0:
                self._pump()                          # keep the window responsive between presents
            return
        self._draw(buf, now)

    def flush(self, buf) -> None:
        """Present the newest frame if frames were skipped since the last present — called when emulation is
        about to stop advancing (e.g. before waiting on the LLM) so the window never shows a stale frame."""
        if self._closed or not self._pending:
            return
        self._draw(buf, time.perf_counter())

    def _draw(self, buf, now) -> None:
        self._pending = False
        pg = self._pg
        # Interpret the raw RGBX bytes as a surface. .convert() remaps it to the
        # display's native pixel format — without it, scaling straight into the
        # display surface reinterprets the channels and colors come out wrong.
        frame = pg.image.frombuffer(buf, (self.w, self.h), "RGBX").convert()
        scaled = pg.transform.scale(frame, self.screen.get_size())
        self.screen.blit(scaled, (0, 0))
        pg.display.flip()
        # Stamp AFTER flip(): on macOS it blocks for the display refresh while the window is visible. Stamping
        # before it made the next frame due the instant flip() returned, i.e. one flip per emulated frame (~1×).
        self._last_present = time.perf_counter()
        self._pump()

    def _pump(self) -> None:
        for event in self._pg.event.get():
            if event.type == self._pg.QUIT or (
                    event.type == self._pg.KEYDOWN and event.key == self._pg.K_ESCAPE):
                # Close the window but DON'T raise — a spurious QUIT (common when
                # the process is backgrounded on macOS) must not kill the run. The
                # run continues headless; Ctrl-C the terminal to actually stop.
                self.close()
                self._closed = True
                return

    def close(self) -> None:
        try:
            self._pg.display.quit()
            self._pg.quit()
        except Exception:
            pass

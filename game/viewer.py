"""Live pygame window for watching the native backend play.

The native emulator is headless, so this reads libmgba's framebuffer directly
each frame and blits it to a scaled window. Because the game only advances when
the agent runs frames, the window is smooth during actions/animations and holds
the last frame still while the LLM is thinking.

Playback is paced to `VIEWER_FPS` so it's watchable at roughly game speed rather
than the emulator's raw multi-hundred-fps burst.

Closing the window (or pressing Esc) tears the window down but does NOT stop the
run — the agent keeps playing headless. This is deliberate: a backgrounded pygame
window on macOS gets spurious QUIT events, and it used to raise a KeyboardInterrupt
that killed long runs ~minutes in. To stop the run, Ctrl-C the terminal.
"""
import time
from config import VIEWER_SCALE, VIEWER_FPS


class PygameViewer:
    def __init__(self, width: int, height: int,
                 scale: int = VIEWER_SCALE, fps: int = VIEWER_FPS):
        import pygame  # imported lazily so headless runs never need pygame
        self._pg = pygame
        self.w, self.h = width, height
        self.scale = scale
        self.min_frame_dt = (1.0 / fps) if fps > 0 else 0.0
        self._last = 0.0
        self._closed = False

        pygame.init()
        pygame.display.set_caption("Pokemon LeafGreen — LLM Agent")
        self.screen = pygame.display.set_mode((width * scale, height * scale))

    def render(self, buf) -> None:
        """buf: a bytes-like RGBX framebuffer (w*h*4). Blit, scale, present.
        No-op once the window has been closed (the run continues headless).

        `VIEWER_FPS` caps the DISPLAY refresh rate by frame-SKIPPING — if too little
        wall-clock time has passed since the last actual draw, we skip this frame
        entirely and return immediately. Crucially this does NOT sleep, so the
        emulator keeps running at full speed (grind/battles run thousands of frames;
        drawing every one throttled the whole run). fps=0 draws every frame."""
        if self._closed:
            return
        if self.min_frame_dt > 0:
            now = time.perf_counter()
            if now - self._last < self.min_frame_dt:
                return   # too soon to redraw — skip, don't slow the emulator
            self._last = now
        pg = self._pg
        # Interpret the raw RGBX bytes as a surface. .convert() remaps it to the
        # display's native pixel format — without it, scaling straight into the
        # display surface reinterprets the channels and colors come out wrong.
        frame = pg.image.frombuffer(buf, (self.w, self.h), "RGBX").convert()
        scaled = pg.transform.scale(frame, self.screen.get_size())
        self.screen.blit(scaled, (0, 0))
        pg.display.flip()
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

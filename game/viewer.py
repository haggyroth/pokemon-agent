"""Live pygame window for watching the native backend play.

The native emulator is headless, so this reads libmgba's framebuffer directly
each frame and blits it to a scaled window. Because the game only advances when
the agent runs frames, the window is smooth during actions/animations and holds
the last frame still while the LLM is thinking.

Playback is paced to `VIEWER_FPS` so it's watchable at roughly game speed rather
than the emulator's raw multi-hundred-fps burst. Closing the window raises
KeyboardInterrupt so main.py exits cleanly (saving progress).
"""
import time
from config import VIEWER_SCALE, VIEWER_FPS


class ViewerClosed(KeyboardInterrupt):
    """Raised when the user closes the window — treated as a clean stop."""


class PygameViewer:
    def __init__(self, width: int, height: int,
                 scale: int = VIEWER_SCALE, fps: int = VIEWER_FPS):
        import pygame  # imported lazily so headless runs never need pygame
        self._pg = pygame
        self.w, self.h = width, height
        self.scale = scale
        self.min_frame_dt = (1.0 / fps) if fps > 0 else 0.0
        self._last = 0.0

        pygame.init()
        pygame.display.set_caption("Pokemon LeafGreen — LLM Agent")
        self.screen = pygame.display.set_mode((width * scale, height * scale))
        # Small source surface we blit the raw framebuffer into, then scale up.
        self.surface = pygame.Surface((width, height))

    def render(self, buf) -> None:
        """buf: a bytes-like RGBX framebuffer (w*h*4). Blit, scale, present."""
        pg = self._pg
        # Interpret the raw RGBX bytes as a surface (ignores the pad byte).
        frame = pg.image.frombuffer(buf, (self.w, self.h), "RGBX")
        pg.transform.scale(frame, self.screen.get_size(), self.screen)
        pg.display.flip()
        self._pump()
        self._pace()

    def _pump(self) -> None:
        for event in self._pg.event.get():
            if event.type == self._pg.QUIT:
                self.close()
                raise ViewerClosed()
            if (event.type == self._pg.KEYDOWN
                    and event.key == self._pg.K_ESCAPE):
                self.close()
                raise ViewerClosed()

    def _pace(self) -> None:
        if self.min_frame_dt <= 0:
            return
        now = time.perf_counter()
        wait = self.min_frame_dt - (now - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.perf_counter()

    def close(self) -> None:
        try:
            self._pg.display.quit()
            self._pg.quit()
        except Exception:
            pass

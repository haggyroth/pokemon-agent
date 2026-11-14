"""Per-skill frame budget + no-progress detector.

A deterministic skill (grind, go_to, catch, ...) drives the emulator for many thousands of frames
without the LLM in the loop, so a bug in it can spin for as long as it likes: the 2026-11-13 run died
inside one `train_party()` call that ran 26 minutes with zero model calls. The wall-time limit
(MAX_WALL_S) is only checked between model calls and can't see that.

`FrameWatchdog` counts the frames a skill advances (the emulator calls `advance(n)` from its frame
stepper) and raises `SkillBudgetExceeded` when EITHER the skill has run past its hard frame cap, OR a
progress signature (map, position, party levels, foe HP, ... — whatever `probe()` returns) has not
changed for `stall_frames`. Frames, not wall time, so it behaves the same headless and under the
paced viewer window.

`SkillBudgetExceeded` is a BaseException on purpose: skills are full of `except Exception` fallbacks
and must not be able to swallow it. The tool dispatcher catches it and turns it into a message.
"""
from __future__ import annotations


class SkillBudgetExceeded(BaseException):
    def __init__(self, reason: str, frames: int, stalled: bool):
        super().__init__(reason)
        self.reason, self.frames, self.stalled = reason, frames, stalled


class FrameWatchdog:
    def __init__(self, max_frames: int, stall_frames: int, probe=None, check_every: int = 600):
        self.max_frames, self.stall_frames = max_frames, stall_frames
        self.probe, self.check_every = probe, check_every
        self.frames = 0
        self._since = 0           # frames since the last progress check
        self._still = 0           # consecutive frames the signature has been unchanged
        self._last = object()
        self.armed = True

    def advance(self, n: int) -> None:
        if not self.armed:
            return
        self.frames += n
        self._since += n
        if self.frames > self.max_frames:
            self._trip(f"ran {self._mins(self.frames)} of game time (limit {self._mins(self.max_frames)})", False)
        if self.probe is not None and self._since >= self.check_every:
            self._check()

    def _check(self) -> None:
        try:
            sig = self.probe()
        except Exception:
            self._since = 0                # an unreadable probe says nothing: only the hard cap applies
            return
        if sig == self._last:
            self._still += self._since
        else:
            self._still, self._last = 0, sig
        self._since = 0
        if self._still >= self.stall_frames:
            self._trip(f"no progress for {self._mins(self._still)} of game time", True)

    def _trip(self, reason: str, stalled: bool) -> None:
        self.armed = False                 # raise once; cleanup code must be free to run frames
        raise SkillBudgetExceeded(reason, self.frames, stalled)

    @staticmethod
    def _mins(frames: int) -> str:
        s = frames / 60
        return f"{s / 60:.1f} min" if s >= 90 else f"{s:.0f} s"

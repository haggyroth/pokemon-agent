"""Emulator checkpoints so a cancelled / stuck run can be resumed instead of restarted (#185 item 2).

Written under the run's log directory:  logs/runs/<ts>/checkpoints/
  ckpt_<step>_<ctx>.ss1        rolling — the newest `keep` are retained
  badge<N>_<step>.ss1          permanent — one per new badge
  latest.json                  {path, step, tag, time, meta} — what `RESUME=latest` loads

`save_fn(path) -> bool` is the emulator's state saver (native backend only). All I/O is best-effort:
a checkpoint failure must never break a run.
"""
from __future__ import annotations

import json
import time
from pathlib import Path


class CheckpointManager:
    def __init__(self, directory, save_fn, every_ticks: int = 20, keep: int = 5):
        self.dir = Path(directory)
        self.save_fn, self.every, self.keep = save_fn, every_ticks, keep
        self._last_step = -10**9
        self._badges = None
        self._rolling: list[Path] = []

    def maybe(self, step: int, badges: int, ctx: str = "", meta: dict | None = None) -> Path | None:
        """Call once per decision tick. Saves on a new badge (permanent) or every `every_ticks`."""
        if self._badges is None:
            self._badges = badges
        if badges > self._badges:
            self._badges = badges
            return self.save(f"badge{badges}_{step:05d}", step, meta, permanent=True)
        if self.every > 0 and step - self._last_step >= self.every:
            return self.save(f"ckpt_{step:05d}_{ctx or 'x'}", step, meta)
        return None

    def save(self, tag: str, step: int, meta: dict | None = None, permanent: bool = False) -> Path | None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            path = self.dir / f"{tag}.ss1"
            if not self.save_fn(str(path)):
                return None
            self._last_step = step
            if not permanent:
                self._rolling.append(path)
                while len(self._rolling) > self.keep:
                    self._rolling.pop(0).unlink(missing_ok=True)
            (self.dir / "latest.json").write_text(json.dumps(
                {"path": str(path), "step": step, "tag": tag, "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                 "meta": meta or {}}, indent=2, default=str))
            return path
        except Exception:
            return None


def find_latest(runs_root) -> dict | None:
    """Newest checkpoint across every run under `runs_root` (by latest.json mtime), or None."""
    best, best_t = None, -1.0
    for lj in Path(runs_root).glob("*/checkpoints/latest.json"):
        try:
            info = json.loads(lj.read_text())
            if Path(info["path"]).exists() and lj.stat().st_mtime > best_t:
                best, best_t = info, lj.stat().st_mtime
        except Exception:
            continue
    return best

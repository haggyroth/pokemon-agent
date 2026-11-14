"""Per-run structured trace (JSONL) for post-hoc analysis.

One directory per run: ``logs/runs/<YYYYmmdd-HHMMSS>/`` containing
  run.jsonl   one JSON object per line: {"t": secs-since-start, "kind": ..., ...}
  meta.json   config snapshot written at start, result summary written at end

Event kinds: ``start``, ``tick`` (observation + state), ``llm`` (one completion:
tokens, reasoning, requested tool calls), ``tool`` (name, args, result, seconds,
state snapshot), ``end``. Writes are flushed per line so a crash or Ctrl-C keeps
everything. All I/O is best-effort: logging must never break a run.
"""
from __future__ import annotations

import json
import time
from pathlib import Path


class NullRunLog:
    """Do-nothing log (default, and used by the eval harness / tests)."""
    path: Path | None = None

    def event(self, kind: str, **fields) -> None:
        pass

    def write_meta(self, **fields) -> None:
        pass

    def close(self) -> None:
        pass


class RunLog(NullRunLog):
    def __init__(self, root: Path | str, stamp: str | None = None):
        stamp = stamp or time.strftime("%Y%m%d-%H%M%S")
        self.dir = Path(root) / stamp
        self.t0 = time.time()
        self._f = None
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            self._f = open(self.dir / "run.jsonl", "a", buffering=1)
        except OSError:
            self._f = None
        self.path = self.dir / "run.jsonl"
        self._meta: dict = {}

    def event(self, kind: str, **fields) -> None:
        if self._f is None:
            return
        try:
            rec = {"t": round(time.time() - self.t0, 2), "kind": kind, **fields}
            self._f.write(json.dumps(rec, default=str, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def write_meta(self, **fields) -> None:
        self._meta.update(fields)
        try:
            (self.dir / "meta.json").write_text(
                json.dumps(self._meta, indent=2, default=str))
        except Exception:
            pass

    def close(self) -> None:
        try:
            if self._f:
                self._f.close()
        except Exception:
            pass
        self._f = None

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from config import JOURNAL_PATH

@dataclass
class BattleRecord:
    timestamp: str;  location: str;  enemy_name: str;  enemy_level: int
    player_lead: str;  outcome: str;  turns: int
    moves_used: list[str];  hp_remaining_pct: float;  reward: float;  notes: str

class BattleJournal:
    def __init__(self, path=None):
        # path overrides the default battles.jsonl — the eval harness isolates it
        # so scenario battles don't pollute the real journal.
        self.path = Path(path or JOURNAL_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, record: BattleRecord):
        with open(self.path, "a") as f:
            f.write(json.dumps(asdict(record)) + "\n")

    def _all(self) -> list[BattleRecord]:
        if not self.path.exists():
            return []
        records = []
        with open(self.path) as f:
            for line in f:
                if line.strip():
                    try: records.append(BattleRecord(**json.loads(line)))
                    except Exception: pass
        return records

    def get_loss_lessons(self, enemy_name: str, n: int = 3) -> str:
        losses = [r for r in self._all() if r.enemy_name == enemy_name and r.outcome == "loss"]
        if not losses:
            return ""
        lines = [f"Past losses against {enemy_name}:"]
        for r in losses[-n:]:
            lines.append(f"  - Turn {r.turns}: led {r.player_lead}, "
                         f"used {', '.join(r.moves_used) or 'unknown'}. {r.notes}")
        return "\n".join(lines)

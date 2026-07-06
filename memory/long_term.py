import copy
import json
from pathlib import Path
from config import PROGRESS_PATH

DEFAULTS = {
    "session_count": 0,   "badges_earned": 0,
    "gyms_beaten": [],    "pokemon_caught": 0,
    "towns_visited": [],  "milestones": [],
    "notes": [],          "starter": None,
    "total_battles": 0,   "battles_won": 0,
    "battles_lost": 0,    "total_reward": 0.0,
}

class LongTermMemory:
    def __init__(self):
        self.path = Path(PROGRESS_PATH)
        self.data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            with open(self.path) as f:
                saved = json.load(f)
            # deepcopy so absent keys don't alias DEFAULTS' mutable lists
            data = {**copy.deepcopy(DEFAULTS), **saved}
            # Strip keys removed from the schema (e.g. key_items_obtained).
            # Keeps the file from accumulating dead fields across schema changes.
            data = {k: v for k, v in data.items() if k in DEFAULTS}
            # Fix type mismatches from old schema versions.
            if not isinstance(data.get("pokemon_caught"), int):
                old = data.get("pokemon_caught")
                data["pokemon_caught"] = len(old) if isinstance(old, list) else 0
            return data
        return copy.deepcopy(DEFAULTS)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=2)

    def add_badge(self, gym_name: str):
        if gym_name not in self.data["gyms_beaten"]:
            self.data["gyms_beaten"].append(gym_name)
            self.data["badges_earned"] = len(self.data["gyms_beaten"])
            self.save()

    def reconcile_badges_from_ram(self, badge_bits: int) -> list[str]:
        """Fold the game's badge bitmask (the authoritative save state) into LTM.

        LTM is a *monotonic* mirror for reward/milestone tracking: we adopt any
        badge RAM shows that LTM is missing, but never remove one — game RAM can
        legitimately regress when the agent load_state()s to retry a gym, and we
        must not un-earn milestones. This never writes game RAM.

        Returns the milestone names newly adopted (for logging).
        """
        from knowledge.leafgreen_data import badges_in_bitmask
        adopted: list[str] = []
        changed = False
        for _bit, leader, milestone in badges_in_bitmask(badge_bits):
            if leader and leader not in self.data["gyms_beaten"]:
                self.data["gyms_beaten"].append(leader)
                self.data["badges_earned"] = len(self.data["gyms_beaten"])
                changed = True
            if milestone and milestone not in self.data["milestones"]:
                self.data["milestones"].append(milestone)
                adopted.append(milestone)
                changed = True
        if changed:
            self.save()
        return adopted

    def add_milestone(self, name: str, note: str = "") -> bool:
        if name in self.data["milestones"]:
            return False
        self.data["milestones"].append(name)
        if note:
            self.data["notes"].append(f"{name}: {note}")
        self.save()
        return True

    def add_town(self, town_name: str) -> bool:
        if town_name in self.data["towns_visited"]:
            return False
        self.data["towns_visited"].append(town_name)
        self.save()
        return True

    def new_session(self):
        self.data["session_count"] += 1
        self.save()

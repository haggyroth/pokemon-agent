import copy
import json
import os
from datetime import datetime
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
    def __init__(self, path=None):
        # path overrides the default progress.json — the eval harness points it at
        # a scratch file so a scenario never mutates the real long-term memory.
        self.path = Path(path or PROGRESS_PATH)
        self.data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                with open(self.path) as f:
                    saved = json.load(f)
            except (json.JSONDecodeError, ValueError, OSError) as e:
                # A truncated/corrupt progress file must never crash startup.
                # Rename it aside (preserving forensics) and start from DEFAULTS.
                # This is the recovery path for a crash mid-save() before the
                # atomic-write fix; kept as belt-and-braces afterward.
                bak = self.path.with_name(
                    f"{self.path.name}.corrupt-"
                    f"{datetime.now().strftime('%Y%m%d-%H%M%S')}.bak")
                try:
                    os.replace(self.path, bak)
                    print(f"[long_term] WARNING: {self.path.name} was corrupt ({e}); "
                          f"moved to {bak.name}, starting fresh.")
                except OSError:
                    print(f"[long_term] WARNING: {self.path.name} was corrupt ({e}) "
                          f"and could not be renamed; starting fresh.")
                return copy.deepcopy(DEFAULTS)
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
        # Atomic write: serialize to a sibling temp file, fsync, then os.replace
        # (atomic on POSIX and Windows). A crash/interrupt mid-write can never
        # leave a truncated progress.json — the old file survives until the
        # rename completes. progress.json is the only cross-session memory and
        # save() runs often (every milestone/town/battle end), so a partial write
        # here previously corrupted it (logs/progress.json.corrupted.bak).
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.tmp")
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

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

    def reconcile_badges_authoritative(self, badge_bits: int) -> dict:
        """Sync LTM's badge state to EXACTLY match the live save's bitmask — adopting
        badges the save has that LTM is missing AND dropping any LTM claims that the
        save does NOT back up. Use ONLY at STARTUP: a journal from a prior run can get
        ahead of the cartridge you're now testing with, and the agent then deadlocks
        (it thinks a gym is beaten, heads for the next town, but the game's guard NPC
        blocks it and marches it back to the un-beaten gym). Non-gym milestones
        (starter_chosen, …) are untouched. Returns {'adopted': [...], 'dropped': [...]}.

        Mid-session, keep using the monotonic reconcile_badges_from_ram so a
        load_state() retry (RAM regresses) never un-earns a real badge.
        """
        from knowledge.leafgreen_data import badges_in_bitmask, BADGE_BIT_MILESTONE
        live = badges_in_bitmask(badge_bits)
        live_leaders = [leader for _b, leader, _m in live if leader]
        live_milestones = {m for _b, _l, m in live if m}
        gym_milestones = set(BADGE_BIT_MILESTONE.values())

        adopted: list[str] = []
        dropped: list[str] = []
        # Drop gym progress the cartridge doesn't back up.
        for leader in list(self.data["gyms_beaten"]):
            if leader not in live_leaders:
                self.data["gyms_beaten"].remove(leader)
                dropped.append(leader)
        for ms in list(self.data["milestones"]):
            if ms in gym_milestones and ms not in live_milestones:
                self.data["milestones"].remove(ms)
                dropped.append(ms)
        # Adopt anything the cartridge has that we're missing.
        for _b, leader, ms in live:
            if leader and leader not in self.data["gyms_beaten"]:
                self.data["gyms_beaten"].append(leader)
                adopted.append(leader)
            if ms and ms not in self.data["milestones"]:
                self.data["milestones"].append(ms)
                adopted.append(ms)
        self.data["badges_earned"] = len(self.data["gyms_beaten"])
        if adopted or dropped:
            self.save()
        return {"adopted": adopted, "dropped": dropped}

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

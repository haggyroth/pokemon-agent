from dataclasses import dataclass

SHAPED = {
    "trainer_win": 1.0, "gym_leader_win": 10.0, "elite_four_win": 15.0,
    "champion_win": 50.0, "new_badge": 5.0, "new_town": 2.0,
    "caught_new": 1.0, "level_up": 0.5, "key_item": 2.0,
    "party_faint": -1.0, "loss": -2.0,
}
SPARSE = {
    "gym_leader_win": 10.0, "elite_four_win": 15.0,
    "champion_win": 100.0, "new_badge": 10.0,
    "party_faint": -0.5, "loss": -1.0,
}

@dataclass
class RewardEvent:
    label: str; value: float

class RewardTracker:
    def __init__(self, shaped: bool = True):
        self.shaped  = shaped
        self.table   = SHAPED if shaped else SPARSE
        self.total   = 0.0
        self.history: list[RewardEvent] = []

    def reward(self, event: str) -> float:
        v = self.table.get(event, 0.0)
        self.total += v
        self.history.append(RewardEvent(event, v))
        return v

    def anneal_to_sparse(self):
        self.shaped = False
        self.table  = SPARSE

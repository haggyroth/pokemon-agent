from dataclasses import dataclass, field
from enum import Enum, auto
import time


class GameContext(Enum):
    TRANSITIONING = auto()
    IN_BATTLE     = auto()
    DIALOG_OPEN   = auto()
    IN_MENU       = auto()
    OVERWORLD     = auto()
    UNKNOWN       = auto()


@dataclass
class PokemonStatus:
    slot: int
    level: int
    current_hp: int
    max_hp: int
    status: str           # "healthy" | "burned" | "paralyzed" | etc.
    species_id: int = 0   # 0 until Tier 2 decryption implemented
    species_name: str = ""
    move_ids: list[int] = field(default_factory=lambda: [0]*4)
    move_names: list[str] = field(default_factory=lambda: [""]*4)
    pp: list[int] = field(default_factory=lambda: [0]*4)

    @property
    def hp_percent(self) -> float:
        return self.current_hp / self.max_hp if self.max_hp > 0 else 0.0

    @property
    def is_fainted(self) -> bool:
        return self.current_hp == 0


@dataclass
class GameState:
    context:       GameContext
    badges:        int          # popcount of badge_bits (0–8), for display
    badge_bits:    int          # raw u8 bitmask from 0x02025968, for bitwise diff
    party:         list[PokemonStatus]
    party_count:   int
    map_bank:      int
    map_id:        int
    player_x:      int
    player_y:      int
    screen_fading: bool
    timestamp:     float = field(default_factory=time.time)


@dataclass
class StateDiff:
    badges_changed:     bool = False
    hp_changed:         list[int] = field(default_factory=list)
    level_changed:      list[int] = field(default_factory=list)
    moves_changed:      list[int] = field(default_factory=list)
    party_size_changed: bool = False
    battle_started:     bool = False
    battle_ended:       bool = False
    context_changed:    bool = False
    notes:              list[str] = field(default_factory=list)

    @property
    def anything_changed(self) -> bool:
        return any([
            self.badges_changed, self.hp_changed, self.level_changed,
            self.moves_changed, self.party_size_changed,
            self.battle_started, self.battle_ended, self.context_changed,
        ])


def active_party_member(party: list[PokemonStatus], slot: int) -> PokemonStatus | None:
    """Return the party member at `slot`, clamped to a valid entry.

    Used at battle end to record the Pokémon that was actually fighting (tracked
    as the last slot to take damage) rather than always the lead. Falls back to
    the lead if `slot` is out of range, or None for an empty party.
    """
    if not party:
        return None
    if 0 <= slot < len(party):
        return party[slot]
    return party[0]

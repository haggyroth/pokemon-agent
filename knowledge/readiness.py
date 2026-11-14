"""Readiness assessment (pure): what a good Pokémon player would sort out BEFORE walking on.

The agent drifted into "go_to everything": travel tools were so convenient that healing, PP, catching and
levelling the whole team were only done when something broke. This module turns the party's actual state into
a short prioritised to-do list that is (a) shown to the model every overworld tick and (b) used by go_to as a
pre-flight check for the things that must not be skipped (hurt party, out of attack PP).
"""
from dataclasses import dataclass

from knowledge.leafgreen_data import GYMS, GYM_ACE_LEVEL
from knowledge.party import attack_pp, can_attack, lagging_mons

HURT_FRACTION = 0.5        # any member below this → heal
LEAD_FRACTION = 0.6        # the lead matters more
MIN_TEAM = 4               # below this, keep catching
MIN_BALLS, MIN_POTIONS = 5, 3


@dataclass(frozen=True)
class Need:
    level: str      # "must" | "should"
    code: str       # heal | shop | catch | train | level
    text: str


def next_gym_target(gyms_beaten) -> tuple[str, int] | None:
    """(leader, recommended lead level) for the next gym still owed: one level under its ace."""
    beaten = set(gyms_beaten or [])
    nxt = next((g for g in GYMS if g["leader"] not in beaten), None)
    if nxt is None:
        return None
    return nxt["leader"], max(5, GYM_ACE_LEVEL.get(nxt["leader"], 20) - 1)


def assess(party, balls: int = 0, potions: int = 0, money: int = 0, gyms_beaten=(), dex=None) -> list[Need]:
    needs: list[Need] = []
    if not party:
        return needs
    alive = [p for p in party if p.current_hp > 0]
    hurt = [p for p in party if p.max_hp and p.current_hp / p.max_hp < HURT_FRACTION]
    lead = party[0]
    why = []
    if lead.max_hp and lead.current_hp / lead.max_hp < LEAD_FRACTION:
        why.append(f"{lead.nickname or lead.species_name} is at {lead.current_hp}/{lead.max_hp} HP")
    elif hurt:
        why.append(f"{len(hurt)} Pokémon below half HP")
    if any(p.current_hp == 0 for p in party):
        why.append("a Pokémon has fainted")
    strikers = [p for p in alive if can_attack(p)]
    best = max(strikers, key=lambda p: (p.level, attack_pp(p)), default=None)
    if alive and best is None:
        why.append("no Pokémon has attacking PP left")
    elif best is not None and attack_pp(best) <= 2:
        why.append(f"{best.nickname or best.species_name} is almost out of attack PP")
    if why:
        needs.append(Need("must", "heal", "heal() at a Pokémon Center (HP and PP): " + "; ".join(why)))

    if (balls < MIN_BALLS or potions < MIN_POTIONS) and money >= 500:
        short = [f"{n} ({have}/{want})" for n, have, want in
                 (("Poké Balls", balls, MIN_BALLS), ("Potions", potions, MIN_POTIONS)) if have < want]
        needs.append(Need("should", "shop", f"shop() — low on {', '.join(short)} and you have ¥{money}"))

    if len(party) < MIN_TEAM:
        needs.append(Need("should", "catch",
                          f"only {len(party)} Pokémon — catch more: wild encounters in tall grass "
                          "(grind() catches worthwhile ones automatically; or weaken one with use_move, then catch())"))

    lag = lagging_mons(party)
    if lag:
        top = max(p.level for p in party)
        names = ", ".join(f"{p.nickname or p.species_name} L{p.level}" for _, p in lag)
        needs.append(Need("should", "train", f"{names} trail the top L{top} by >25% — grind() with no level trains them"))

    tgt = next_gym_target(gyms_beaten)
    top_level = max((p.level for p in party), default=0)
    if tgt and top_level < tgt[1]:
        needs.append(Need("should", "level", f"{tgt[0]}'s gym is next (ace L{GYM_ACE_LEVEL.get(tgt[0], '?')}): "
                                             f"your best is L{top_level} — grind({tgt[1]}) first"))
    if dex and dex[0] < 151 and not blocking(needs) and balls >= 3:
        needs.append(Need("should", "dex", f"Pokédex {dex[0]}/151 caught ({dex[1]} seen) — a SECONDARY goal: also catch "
                                           "species you don't own yet (a full party sends them to the PC box). Beating "
                                           "the game stays the main objective."))
    return needs


def blocking(needs) -> list[Need]:
    return [n for n in needs if n.level == "must"]


def render(needs) -> str:
    """Compact block for the observation ('' when all is well)."""
    if not needs:
        return ""
    lines = [("⛔ " if n.level == "must" else "• ") + n.text for n in needs]
    return "READINESS — sort these out before travelling on (go_to is only for travel; it won't do them):\n" + "\n".join(lines)

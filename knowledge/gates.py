"""Story / capability gates the router must respect (pure data + logic; no I/O).

A gate says "entering this map needs X". go_to asks `unmet_gates(route, have)` BEFORE walking, so it can
pick another route or tell the model what to get first (instead of marching into a locked road, a
Snorlax, a guard or open water and stalling). Requirements are stable facts of the game; the hint
says where to get the thing."""
from dataclasses import dataclass

# key item ids (pokefirered constants/items.h)
SILPH_SCOPE, POKE_FLUTE, SECRET_KEY, CARD_KEY, TEA, BICYCLE = 359, 350, 351, 355, 369, 360
# HM move id -> (name, badge bit index that lets you use it in the field)
HM_BADGE = {"Cut": (15, 1), "Fly": (19, 2), "Strength": (70, 3), "Surf": (57, 4), "Flash": (148, 0)}


@dataclass(frozen=True)
class Req:
    kind: str            # "key_item" | "hm" | "badges" | "flag"
    value: object        # item id | HM name | badge count | world-map flag
    hint: str
    alt_flag: int | None = None   # satisfied if this system flag is set (e.g. already visited)


MAP_GATES: dict[tuple[int, int], list[Req]] = {
    (1, 94): [Req("key_item", SILPH_SCOPE,
                  "Pokémon Tower 7F is blocked by ghosts until you have the Silph Scope "
                  "(Celadon Rocket Hideout B4F, beat Giovanni's grunts there).")],
    (3, 10): [Req("key_item", TEA,
                  "Saffron City's gate guards want Tea (a drink from the Celadon Mansion roof / "
                  "Game Corner area). Once you've visited Saffron you can Fly there.",
                  alt_flag=0x89A)],
    (3, 30): [Req("key_item", POKE_FLUTE,
                  "A Snorlax blocks Route 12 — you need the Poké Flute (Mr. Fuji, Lavender Town, "
                  "after rescuing him from the Pokémon Tower).")],
    (3, 34): [Req("key_item", POKE_FLUTE,
                  "A Snorlax blocks Route 16 — you need the Poké Flute (Mr. Fuji, Lavender Town).")],
    (3, 8): [Req("hm", "Surf", "Cinnabar Island is across the sea: teach Surf (HM03 from the Safari "
                 "Zone) to a Pokémon, then use_hm('Surf') / go_to.")],
    (3, 37): [Req("hm", "Surf", "Route 19 is open water — you need Surf.")],
    (3, 38): [Req("hm", "Surf", "Route 20 is open water — you need Surf.")],
    (1, 83): [Req("hm", "Surf", "Seafoam Islands needs Surf (and Strength for its boulders).")],
    (1, 39): [Req("hm", "Strength", "Victory Road's boulders need Strength (HM04, Safari Zone).")],
    (3, 41): [Req("badges", 8, "Route 23's checkpoints only let you through with all 8 badges.")],
}


def unmet_gates(route, satisfied) -> list[tuple[int, Req]]:
    """[(step index, Req)] for every step of `route` that enters a gated map whose requirement
    `satisfied(req)` rejects. `route` is route_to()'s step list (dest node = step[2])."""
    out = []
    for i, step in enumerate(route or []):
        dest = tuple(step[2][:2])
        for req in MAP_GATES.get(dest, []):
            if not satisfied(req):
                out.append((i, req))
    return out

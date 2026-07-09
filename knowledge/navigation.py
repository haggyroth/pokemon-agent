from __future__ import annotations
from pathlib import Path
from game.state import GameState
from config import PROJECT_ROOT

MAP_NAMES: dict[tuple[int, int], str] = {
    # Group 3 — Towns and Routes
    (3, 0):  "Pallet Town",
    (3, 1):  "Viridian City",
    (3, 2):  "Pewter City",
    (3, 3):  "Cerulean City",
    (3, 4):  "Lavender Town",
    (3, 5):  "Vermilion City",
    (3, 6):  "Celadon City",
    (3, 7):  "Fuchsia City",
    (3, 8):  "Cinnabar Island",
    (3, 9):  "Indigo Plateau",
    (3, 10): "Saffron City",
    (3, 19): "Route 1",
    (3, 20): "Route 2",
    (3, 21): "Route 3",
    (3, 22): "Route 4",
    (3, 23): "Route 5",
    (3, 24): "Route 6",
    (3, 25): "Route 7",
    (3, 26): "Route 8",
    (3, 27): "Route 9",
    (3, 28): "Route 10",
    (3, 29): "Route 11",
    (3, 30): "Route 12",
    (3, 31): "Route 13",
    (3, 32): "Route 14",
    (3, 33): "Route 15",
    (3, 34): "Route 16",
    (3, 35): "Route 17 (Cycling Road)",
    (3, 36): "Route 18",
    (3, 37): "Route 19",
    (3, 38): "Route 20",
    (3, 39): "Route 21",
    (3, 40): "Route 22",
    (3, 41): "Route 23",
    (3, 42): "Route 24",
    (3, 43): "Route 25",
    # Group 1 — Dungeons
    (1, 0):  "Viridian Forest",
    (1, 1):  "Mt. Moon 1F",
    (1, 2):  "Mt. Moon B1F",
    (1, 3):  "Mt. Moon B2F",
    (1, 4):  "S.S. Anne (exterior)",
    (1, 39): "Victory Road 1F",
    (1, 40): "Victory Road 2F",
    (1, 41): "Victory Road 3F",
    (1, 42): "Rocket Hideout B1F",
    (1, 43): "Rocket Hideout B2F",
    (1, 44): "Rocket Hideout B3F",
    (1, 45): "Rocket Hideout B4F",
    (1, 47): "Silph Co. 1F",
    (1, 48): "Silph Co. 2F",
    (1, 63): "Safari Zone (Center)",
    (1, 64): "Safari Zone (East)",
    (1, 65): "Safari Zone (North)",
    (1, 66): "Safari Zone (West)",
    (1, 72): "Cerulean Cave 1F",
    (1, 81): "Rock Tunnel 1F",
    (1, 82): "Rock Tunnel B1F",
    (1, 83): "Seafoam Islands 1F",
    (1, 88): "Pokemon Tower 1F",
    (1, 89): "Pokemon Tower 2F",
    (1, 90): "Pokemon Tower 3F",
    (1, 91): "Pokemon Tower 4F",
    (1, 92): "Pokemon Tower 5F",
    (1, 93): "Pokemon Tower 6F",
    (1, 94): "Pokemon Tower 7F",
}

DIRECTION_BUTTON: dict[str, str] = {
    "N": "Up", "S": "Down", "E": "Right", "W": "Left"
}

# Each entry: (min_badges, objective, navigation_hint, travel_direction)
# travel_direction is the primary compass bearing (N/S/E/W) for this story segment,
# or None when the next step is local (inside a city/dungeon with no single bearing).
# This is a rough guide — local detours through gates and buildings are expected.
STORY_PATH: list[tuple[int, str, str, str | None]] = [
    (0, "Choose your starter from Prof. Oak's lab in Pallet Town",
     "Go north from Pallet Town → Route 1 → Viridian City → keep going north on Route 2 through Viridian Forest → Pewter City. Fight trainers to level up.",
     "N"),

    (0, "Defeat Brock (Rock type) at Pewter City Gym — use Grass or Water moves",
     "Pewter City Gym is in the north-west of Pewter City. Bulbasaur's Vine Whip is 2× effective.",
     "N"),

    (1, "Head to Cerulean City and defeat Misty (Water type) — use Grass or Electric moves",
     "From Pewter, go east on Route 3, through Mt. Moon (two floors), exit onto Route 4, then north to Cerulean City.",
     "E"),

    (2, "Get HM01 Cut from the S.S. Anne in Vermilion City, then defeat Lt. Surge (Electric)",
     "From Cerulean, go south on Route 5/6 to Vermilion City. Board S.S. Anne for Cut. Gym: use Ground moves — Diglett's Cave is Route 2 south of Pewter.",
     "S"),

    (3, "Reach Lavender Town via Rock Tunnel, then go to Celadon City for Gym 4",
     "From Cerulean go east on Route 9/10 to Rock Tunnel (bring Repels — it is dark without Flash). After tunnel go south to Lavender Town, then west on Route 8/7 to Celadon City.",
     "E"),

    (3, "Defeat Erika (Grass type) at Celadon City Gym — use Fire, Ice, Flying, or Poison",
     "Celadon Gym is in the west side of Celadon City. Also get TM26 Earthquake and Game Corner TMs (Thunderbolt/Ice Beam/Flamethrower) while here.",
     "W"),

    (4, "Clear the Rocket Hideout under the Game Corner in Celadon to get the Silph Scope",
     "Enter the Game Corner (north of Celadon City). Find the hidden switch behind a poster for the Hideout entrance. Defeat Giovanni on B4F to get the Silph Scope.",
     None),

    (4, "Go to Lavender Town and clear Pokemon Tower to rescue Mr. Fuji",
     "Pokemon Tower is the tall building in Lavender Town. You need the Silph Scope to reveal Ghost-type enemies. Defeat Rocket Grunts on each floor. Mr. Fuji is on 7F.",
     "E"),

    (4, "Get the Poke Flute from Mr. Fuji in Lavender Town to wake the Snorlax",
     "Mr. Fuji gives you the Poke Flute after rescue. Use it on the Snorlax blocking Route 12 (south of Lavender) or Route 16 (west of Celadon).",
     None),

    (4, "Go to Saffron City — clear Silph Co. and defeat Sabrina (Psychic type)",
     "Saffron is east of Celadon. Clear Silph Co. (11 floors, find the teleporters to reach Giovanni on 11F) then challenge Sabrina's Gym. Use Bug moves (2×) or Dark-type attackers with high SpAtk.",
     "E"),

    (5, "Defeat Koga (Poison type) at Fuchsia City Gym",
     "Fuchsia is south of Celadon via Cycling Road (Route 17) or south of Lavender via Routes 12-15. Bring Antidotes and Full Heals — Koga uses Toxic and Smokescreen. Ground/Psychic moves are effective.",
     "S"),

    (5, "Get HM03 Surf and HM04 Strength from the Safari Zone warden in Fuchsia",
     "The Safari Zone is in the north part of Fuchsia City. Find the warden's house (east side of Fuchsia). He gives Surf and Strength after you find his Gold Teeth in the Safari Zone (far west area).",
     None),

    (6, "Surf to Cinnabar Island and defeat Blaine (Fire type)",
     "Surf south from Fuchsia (Route 19/20) to reach Cinnabar Island. The Gym is in the south-east of the island. Use Water moves — any Surf user works fine.",
     "S"),

    (7, "Return to Viridian City and defeat Giovanni (Ground type) at Gym 8",
     "Fly or walk north from Pallet Town to Viridian City. Giovanni's Gym is in the north-west. Use Water, Grass, or Ice moves. Ice Beam is essential for Rhydon.",
     "N"),

    (8, "Head to the Pokemon League via Route 23 and Victory Road",
     "From Viridian City, go north on Route 22 then Route 23 (need all 8 badges for the checkpoints). Navigate Victory Road (3 floors, need Strength for boulders). Then train to level 50–55 before challenging the Elite Four.",
     "N"),

    (8, "Defeat the Elite Four: Lorelei (Ice), Bruno (Fighting), Agatha (Ghost), Lance (Dragon), then Champion Gary",
     "Save before each trainer. Lorelei: Electric/Rock/Fighting. Bruno: Psychic/Flying. Agatha: Ground/Psychic. Lance: Ice Beam is critical — Dragonite survives most other moves. Gary: bring Ice Beam for Rhydon, Psychic for Fighting-types.",
     "N"),
]


def get_travel_direction(state: GameState) -> str | None:
    """Return the current compass bearing (N/S/E/W) or None if no clear direction."""
    badges = state.badges
    matching = [d for (m, _o, _h, d) in STORY_PATH if badges >= m]
    return matching[-1] if matching else None


# ── Phase derivation ─────────────────────────────────────────────────────────
# A phase is a short string capturing the current story context.
# Derived from (badges, milestones) each tick — never persisted.

def derive_phase(state: GameState, milestones: list[str]) -> str:
    b = state.badges
    m = set(milestones)
    if b == 0:
        if "starter_chosen" not in m:
            return "start_choose_starter"
        if "delivered_oaks_parcel" not in m:
            return "deliver_oaks_parcel"
        return "pre_brock"
    if b == 1:
        return "post_brock_heading_east"
    if b == 2:
        return "post_misty_heading_south"
    if b == 3:
        if "got_cut" not in m:
            return "post_surge_need_cut"
        return "post_surge_heading_east"
    if b == 4:
        if "got_silph_scope" not in m:
            return "post_erika_need_silph_scope"
        if "got_poke_flute" not in m:
            return "post_silph_scope_clear_tower"
        return "post_flute_heading_south"
    if b == 5:
        if "got_surf" not in m:
            return "post_koga_need_surf"
        return "post_surf_to_saffron_or_cinnabar"
    if b == 6:
        return "post_sabrina_to_cinnabar"
    if b == 7:
        return "post_blaine_to_viridian"
    return "post_giovanni_to_league"


# ── Route guide ──────────────────────────────────────────────────────────────
# Per-map, per-phase step-by-step guidance. Falls back to STORY_PATH hint
# when no entry exists. Phase-keyed so Pewter says different things before
# vs. after Brock.

ROUTE_GUIDE: dict[tuple[int, int], dict[str, str]] = {
    (3, 0): {  # Pallet Town
        "start_choose_starter": "You're home in Pallet. Walk NORTH into the tall grass — Prof. Oak stops you and leads you to his lab. Choose Bulbasaur (leftmost ball). Gary will battle you right after.",
        "deliver_oaks_parcel":  "Head NORTH to Route 1, through Viridian City Pokemart. Talk to the clerk to receive Oak's Parcel, then return SOUTH to Pallet and give it to Oak.",
    },
    (3, 19): {  # Route 1
        "start_choose_starter":  "Go NORTH through grass to Viridian City. Fight wild Pokemon for levels.",
        "deliver_oaks_parcel":   "Continue NORTH to Viridian Pokemart, or SOUTH back to Pallet once you have the Parcel.",
        "pre_brock":             "Continue NORTH to Viridian, then Route 2.",
    },
    (3, 1): {  # Viridian City
        "deliver_oaks_parcel":  "Enter the Pokemart (blue roof, central). Talk to the clerk for Oak's Parcel, then head SOUTH to Pallet.",
        "pre_brock":            "Heal at the Pokemon Center (red roof). Head NORTH onto Route 2 → Viridian Forest → Pewter City. The Gym here is LOCKED until you have 7 badges.",
        "post_blaine_to_viridian": "The Gym here is NOW open. It's in the NW — Giovanni uses Ground types, bring Water/Grass/Ice.",
        "post_giovanni_to_league": "Head NORTH on Route 22 → Route 23 → Victory Road → Indigo Plateau.",
    },
    (3, 20): {  # Route 2
        "pre_brock": "Go NORTH. The Viridian Forest entrance is on the west side — enter and navigate north through the maze to reach Pewter City.",
    },
    (1, 0): {  # Viridian Forest
        "pre_brock": "Navigate NORTH through the maze. Fight bug trainers for easy XP. Catch a Pikachu if you see one (rare). Exit at the north gate onto Route 2 north → Pewter.",
    },
    (3, 2): {  # Pewter City
        "pre_brock":             "Gym is NORTH-WEST (gray building with spikes). Brock uses Geodude L12 and Onix L14 — Vine Whip 2HKOs both. Heal at the Pokemon Center (SE) and stock Potions at the Mart before entering.",
        "post_brock_heading_east": "Exit Pewter EAST through the gate onto Route 3. Mt. Moon is at the east end of Route 3.",
    },
    (3, 21): {  # Route 3
        "post_brock_heading_east": "Travel EAST. Fight trainers (lots of easy XP here). Pokemon Center at the east end before Mt. Moon. A salesman sells Magikarp — skip it.",
    },
    (1, 1): {  # Mt. Moon 1F
        "post_brock_heading_east": "Navigate through the cave. Staircase down to B1F is in the NW. On B1F/B2F fight Rocket grunts and exit on the far side. Grab Moon Stones if you see them. Exit leads to Route 4 near Cerulean.",
    },
    (3, 22): {  # Route 4
        "post_brock_heading_east": "Short route. Go EAST into Cerulean City. Pokemon Center is right at the entrance.",
    },
    (3, 3): {  # Cerulean City
        "post_brock_heading_east": "Gym is in the CENTER (blue roof). Misty's Starmie L21 is dangerous — use Bulbasaur's Vine Whip. Heal and stock Super Potions first. There's also a Rocket near the house NW with a TM — talk to the kid afterward for Dig TM.",
        "post_misty_heading_south": "Exit SOUTH onto Route 5 toward Vermilion City. Underground Path links to Route 6.",
    },
    (3, 23): {  # Route 5
        "post_misty_heading_south": "Go SOUTH. A Day Care is here (optional). Continue SOUTH through the gate to Route 6.",
    },
    (3, 24): {  # Route 6
        "post_misty_heading_south": "Continue SOUTH into Vermilion City.",
    },
    (3, 5): {  # Vermilion City
        "post_misty_heading_south": "Board the S.S. Anne (dock in SE) — fight through trainers to reach the Captain's cabin, he gives you HM01 Cut. Then challenge Lt. Surge's Gym (center-north). Surge uses Electric — catch Diglett from Diglett's Cave (Route 2 north of Pewter) if you need a Ground counter. Solve the trash-can switch puzzle to reach him.",
        "post_surge_need_cut":     "If you didn't get Cut from S.S. Anne, the ship has left — you're stuck. Cut is needed to progress east via Route 9.",
        "post_surge_heading_east": "Exit NORTH back to Cerulean, then head EAST via Route 9 (a tree blocks the path — use Cut).",
    },
    (3, 4): {  # Lavender Town
        "post_surge_heading_east":      "Small town. Pokemon Tower is here but you need the Silph Scope (from Celadon Rocket Hideout) to clear it. Continue WEST on Route 8 → Route 7 → Celadon City for Gym 4.",
        "post_silph_scope_clear_tower": "Go to the Pokemon Tower (tall building, center). Climb floors fighting ghost Rockets. Mr. Fuji is rescued on 7F — he gives you the Poke Flute.",
        "post_flute_heading_south":     "Exit SOUTH onto Route 12. A Snorlax blocks the path — use the Poke Flute. Continue SOUTH to Fuchsia via Routes 12-15.",
    },
    (3, 6): {  # Celadon City
        "post_surge_heading_east":      "Gym is in the WEST (gray building). Erika uses Grass — Flying/Fire/Ice moves win. Before the Gym, visit Game Corner (north center) to find the Rocket Hideout entrance (talk to the poster-Rocket, press the switch). Clear Rocket Hideout B1F-B4F to get Silph Scope from Giovanni.",
        "post_erika_need_silph_scope":  "Enter the Game Corner (north, pink building). Find the Rocket Grunt in the back; press the poster switch to open the Hideout. Clear 4 basement floors — Giovanni is on B4F and drops the Silph Scope.",
        "post_silph_scope_clear_tower": "Head EAST via Route 7 → Route 8 → Lavender Town. Use the Silph Scope in Pokemon Tower.",
    },
    (3, 10): {  # Saffron City
        "post_flute_heading_south":        "The city is occupied by Rockets — most buildings are blocked. You need to clear Silph Co. to unlock Sabrina's Gym. But first head to Fuchsia for Surf.",
        "post_surf_to_saffron_or_cinnabar": "Enter Silph Co. (tall building, center-west). 11 floors, teleporter maze. Fight Gary on 7F, Giovanni on 11F. You get Lapras (free gift) and TM Earthquake. Then challenge Sabrina's Gym (east).",
    },
    (3, 7): {  # Fuchsia City
        "post_flute_heading_south":        "Gym is in the CENTER-SOUTH (Koga — Poison). Before the Gym, visit the Safari Zone (north entrance) — find Gold Teeth for the Warden (east house), he gives you HM03 Surf and HM04 Strength.",
        "post_koga_need_surf":             "Enter Safari Zone (north), find Gold Teeth in far-west area, give to Warden (east house) for Surf + Strength HMs. Then Surf south to Cinnabar Island.",
        "post_surf_to_saffron_or_cinnabar": "Exit SOUTH and SURF down Route 19-20 to Cinnabar Island. Or fly to Saffron and clear Silph Co.",
    },
    (3, 8): {  # Cinnabar Island
        "post_surf_to_saffron_or_cinnabar": "Gym is in the SE. Blaine uses Fire — bring any Water user (your Surf Pokemon works). You'll need Key from Pokemon Mansion (west building) to enter the Gym — navigate the Mansion to find it.",
        "post_sabrina_to_cinnabar":         "Same as above: Key from Pokemon Mansion (west), then Gym in SE. Surf users destroy Blaine.",
    },
}


def get_route_guidance(state: GameState, milestones: list[str]) -> str:
    """Return 2-5 line guidance for the current (map, phase). Falls back to
    STORY_PATH badge-gated hint when no specific entry exists."""
    map_key = (state.map_bank, state.map_id)
    phase    = derive_phase(state, milestones)

    # Indoors, the outdoor route ("go north to Route 1") is unreachable until you
    # leave the building — lead with the exit instead of the town-level objective.
    if infer_building_type(state.map_bank, state.map_id) == "interior":
        return "\n".join([
            f"Current location: indoors (map {state.map_bank}/{state.map_id})",
            f"Phase: {phase}",
            "You are INSIDE a building. Leave it first: walk onto a door/exit tile "
            "(see 'Exits' in the observation), then resume the route outside.",
        ])

    location = MAP_NAMES.get(map_key, f"unknown area (bank={state.map_bank}, id={state.map_id})")
    lines = [f"Current location: {location}", f"Phase: {phase}"]

    specific = ROUTE_GUIDE.get(map_key, {}).get(phase)
    if specific:
        lines.append(specific)
    else:
        badges = state.badges
        matching = [(o, h, d) for (m, o, h, d) in STORY_PATH if badges >= m]
        ahead    = [o           for (m, o, _h, _d) in STORY_PATH if m > badges]
        if matching:
            obj, hint, direction = matching[-1]
            lines.append(f"Objective: {obj}")
            lines.append(f"Route: {hint}")
            if direction:
                lines.append(f"Travel direction: {direction} — generally press {DIRECTION_BUTTON[direction]}")
        if ahead:
            lines.append(f"After that: {ahead[0]}")

    return "\n".join(lines)


# ── Building-interior knowledge ──────────────────────────────────────────────
# Generic per-building-type advice for when the agent is indoors.

# Only "interior" is reachable: infer_building_type() cannot distinguish
# Center/Mart/Gym from the (bank, id) alone, and building interiors aren't in
# MAP_NAMES. Center/Mart/Gym visual identification is covered by the system
# prompt's screenshot guidance instead. (Per-map overrides live in BUILDING_DETAIL.)
BUILDING_TYPE_GUIDE: dict[str, str] = {
    "interior": "You're INDOORS. To exit, walk to the DOORMAT (usually on the SOUTH wall) and step down off it onto the outdoor tile.",
}

# Story-critical interior overrides. Keyed on (map_bank, map_id).
BUILDING_DETAIL: dict[tuple[int, int], str] = {
    (1, 47): "Silph Co. 1F: Receptionist at the desk. Take the ELEVATOR or STAIRS up — you need to reach higher floors via teleporter pads. Gary battle is on 7F, Giovanni on 11F. Exit is SOUTH.",
    (1, 42): "Rocket Hideout B1F: Navigate the rotating-floor puzzle. Stairs down are to the WEST. Goal is B4F where Giovanni drops the Silph Scope.",
    (1, 45): "Rocket Hideout B4F: Giovanni is here. Defeat him for Silph Scope. Lift key is required — get it on B2F from a grunt.",
    (1, 88): "Pokemon Tower 1F: Stairs up in NE corner. Need Silph Scope to see ghost enemies. Climb to 7F for Mr. Fuji.",
    (1, 94): "Pokemon Tower 7F: Defeat the Rocket grunts holding Mr. Fuji. He gives you the Poke Flute after rescue.",
}


# ── Map images (overhead reference maps) ─────────────────────────────────────
# Filenames live under knowledge/maps/. Keyed on (map_bank, map_id) to match
# the live state. Only includes maps where the bank/id pairing is verified
# from the existing MAP_NAMES table — anything ambiguous is omitted rather
# than guessed wrong.

_MAPS_DIR = PROJECT_ROOT / "knowledge" / "maps"

MAP_IMAGES: dict[tuple[int, int], str] = {
    # Group 3 — Towns
    (3, 0):  "pallet-town-gba-map.png",
    (3, 1):  "viridian-city-gba-map.png",
    (3, 2):  "pewter-city-gba-map.png",
    (3, 3):  "cerulean-city-gba-map.png",
    (3, 4):  "lavender-town-gba-map.png",
    (3, 5):  "vermilion-city-gba-map.png",
    (3, 6):  "celadon-city-gba-map.png",
    (3, 7):  "fuchsia-city-gba-map.png",
    (3, 8):  "cinnabar-island-gba-map.png",
    (3, 10): "saffron-city-gba-map.png",
    # Group 3 — Routes 1..25
    (3, 19): "route-01-gba-map.png",
    (3, 20): "route-02-gba-map.png",
    (3, 21): "route-03-gba-map.png",
    (3, 22): "route-04-gba-map.png",
    (3, 23): "route-05-gba-map.png",
    (3, 24): "route-06-gba-map.png",
    (3, 25): "route-07-gba-map.png",
    (3, 26): "route-08-gba-map.png",
    (3, 27): "route-09-gba-map.png",
    (3, 28): "route-10-gba-map.png",
    (3, 29): "route-11-gba-map.png",
    (3, 30): "route-12-gba-map.png",
    (3, 32): "route-14-gba-map.png",
    (3, 33): "route-15-gba-map.png",
    (3, 34): "route-16-gba-map.png",
    (3, 35): "route-17-gba-map.png",
    (3, 36): "route-18-gba-map.png",
    (3, 37): "route-19-gba-map.png",
    (3, 38): "route-20-gba-map.png",
    (3, 39): "route-21-gba-map.png",
    (3, 40): "route-22-gba-map.png",
    (3, 41): "route-23-gba-map.png",
    (3, 42): "route-24-gba-map.png",
    (3, 43): "route-25-gba-map.png",
    # Group 1 — Dungeons
    (1, 0):  "viridian-forest-gba-map.png",
    (1, 1):  "mt-moon-1f-gba-map.png",
    (1, 2):  "mt-moon-b1f-gba-map.png",
    (1, 3):  "mt-moon-b2f-gba-map.png",
    (1, 4):  "ss-anne-1f-gba-map.png",
    (1, 39): "victory-road-1f-gba-map.png",
    (1, 40): "victory-road-2f-gba-map.png",
    (1, 41): "victory-road-b1f-gba-map.png",
    (1, 42): "rocket-hideout-b1f-gba-map.png",
    (1, 43): "rocket-hideout-b2f-gba-map.png",
    (1, 44): "rocket-hideout-b3f-gba-map.png",
    (1, 45): "rocket-hideout-b4f-gba-map.png",
    (1, 47): "silph-co-01f-gba-map.png",
    (1, 48): "silph-co-02f-gba-map.png",
    (1, 63): "safari-zone-center-area-gba-map.png",
    (1, 64): "safari-zone-area-1-gba-map.png",
    (1, 65): "safari-zone-area-2-gba-map.png",
    (1, 66): "safari-zone-area-3-gba-map.png",
    (1, 72): "cerulean-cave-1f-gba-map.png",
    (1, 81): "rock-tunnel-1f-gba-map.png",
    (1, 82): "rock-tunnel-b1f-gba-map.png",
    (1, 83): "seafoam-islands-1f-gba-map.png",
    (1, 88): "pokemon-tower-1f-gba-map.png",
    (1, 89): "pokemon-tower-2f-gba-map.png",
    (1, 90): "pokemon-tower-3f-gba-map.png",
    (1, 91): "pokemon-tower-4f-gba-map.png",
    (1, 92): "pokemon-tower-5f-gba-map.png",
    (1, 93): "pokemon-tower-6f-gba-map.png",
    (1, 94): "pokemon-tower-7f-gba-map.png",
}


def get_map_image_path(bank: int, id: int) -> Path | None:
    """Return absolute path to the overhead reference map for this (bank, id), or None."""
    fname = MAP_IMAGES.get((bank, id))
    if not fname:
        return None
    p = _MAPS_DIR / fname
    return p if p.exists() else None


def infer_building_type(bank: int, id: int) -> str | None:
    """Return a building-type key for BUILDING_TYPE_GUIDE, or None if outdoor/dungeon."""
    if bank == 3:           # Outdoor towns and routes
        return None
    if bank == 1:           # Dungeons — handled by STORY_PATH direction hints
        return None
    return "interior"       # Anything else: give a generic indoor hint


def get_building_guidance(bank: int, id: int) -> str | None:
    """Specific override if present, else generic type guide, else None."""
    if (bank, id) in BUILDING_DETAIL:
        return BUILDING_DETAIL[(bank, id)]
    t = infer_building_type(bank, id)
    return BUILDING_TYPE_GUIDE.get(t) if t else None

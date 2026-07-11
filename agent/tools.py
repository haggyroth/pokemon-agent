# Canonical GBA buttons plus the synonyms models actually emit. The observation
# labels tiles by compass (N/S/E/W), so the model routinely asks for "West" or
# "N" — accept those instead of erroring and wasting a step.
_BUTTON_ALIASES = {
    "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    "north": "Up", "south": "Down", "east": "Right", "west": "Left",
    "n": "Up", "s": "Down", "e": "Right", "w": "Left",
    "a": "A", "b": "B", "l": "L", "r": "R",
    "select": "Select", "start": "Start",
}


def normalize_button(name: str) -> str:
    """Map a button name (incl. compass synonyms like 'West'/'N') to a canonical
    GBA button. Unknown names pass through unchanged so the backend still raises a
    clear 'invalid button' error rather than this masking a typo silently."""
    if not isinstance(name, str):
        return name
    return _BUTTON_ALIASES.get(name.strip().lower(), name)


TOOLS = [
    {"type": "function", "function": {
        "name": "press_button",
        "description": "Press a GBA button. Use for menus, battle, and movement. "
                       "For movement, Up/Down/Left/Right map to North/South/West/East.",
        "parameters": {"type": "object", "properties": {
            "button": {"type": "string",
                       "enum": ["A","B","Start","Select","Up","Down","Left","Right","L","R"]},
            "times": {"type": "integer", "default": 1, "minimum": 1, "maximum": 10},
        }, "required": ["button"]},
    }},
    {"type": "function", "function": {
        "name": "walk_to",
        "description": "Walk the player to tile (x, y) on the CURRENT map. Finds a "
                       "path around walls/obstacles automatically and moves there — "
                       "use this for overworld navigation instead of pressing "
                       "direction buttons one at a time. To leave a building, walk_to "
                       "a door/exit tile. Stops early if the map changes (you crossed "
                       "an edge or entered a door) or the target can't be reached.",
        "parameters": {"type": "object", "properties": {
            "x": {"type": "integer"},
            "y": {"type": "integer"},
        }, "required": ["x", "y"]},
    }},
    {"type": "function", "function": {
        "name": "go_to_map",
        "description": "Leave the current map by crossing a seamless connection on the "
                       "given edge (see 'Map edges' in the observation). Walks to the "
                       "opening on that edge and steps across into the adjacent map. "
                       "direction is North/South/East/West. Use this to travel between "
                       "towns and routes.",
        "parameters": {"type": "object", "properties": {
            "direction": {"type": "string",
                          "enum": ["North", "South", "East", "West"]},
        }, "required": ["direction"]},
    }},
    {"type": "function", "function": {
        "name": "go_to",
        "description": "Travel to a named map ('Pewter City', 'Route 1') OR a waypoint "
                       "('Pokemon Center', 'Mart', 'Gym'), auto-routing across map "
                       "connections and building/cave doors — it finds the route and "
                       "walks/crosses each step for you. Waypoints go to the nearest one. "
                       "It AUTO-FLEES wild battles along the way so travelling through a "
                       "route/forest/cave is one call (the fast way through Viridian "
                       "Forest). It stops — call again to resume — on a TRAINER battle "
                       "(win it first), when your HP gets low (heal() first), or if the "
                       "way is blocked. The main overworld travel tool.",
        "parameters": {"type": "object", "properties": {
            "destination": {"type": "string",
                            "description": "Map name (e.g. 'Viridian City') or waypoint "
                                           "('Pokemon Center', 'Mart', 'Gym')."},
        }, "required": ["destination"]},
    }},
    {"type": "function", "function": {
        "name": "challenge_leader",
        "description": "Start the battle with the Gym Leader. Call this when you're "
                       "inside the gym and ready (healed, save_state'd) — it walks up "
                       "to the Leader and talks to them to begin the fight. Then "
                       "attack with use_move (e.g. Vine Whip vs Brock).",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "heal",
        "description": "Fully restore the party's HP (and cure status) at a Pokémon "
                       "Center. Travels to the nearest Center if you're not already "
                       "inside, walks to Nurse Joy, and completes the heal for you. "
                       "Call this when your lead/party HP is low (e.g. below ~40%) and "
                       "you are NOT in a battle. Resumable if a wild battle interrupts "
                       "the trip — just call it again.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "shop",
        "description": "Restock supplies at a Poké Mart. Travels to the nearest Mart "
                       "if needed, walks to the clerk, and BUYS the recommended items "
                       "for you — Poké Balls, Potions/healing, and status cures — at "
                       "par levels that scale with your badge count (it upgrades to "
                       "Super/Hyper Potions and Great/Ultra Balls as you progress), "
                       "spending only what you can afford. Call it when the 'Bag:' line "
                       "shows you're low on Balls or Potions and you're not in a battle. "
                       "The MART line in the observation shows the exact recommendation.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "use_move",
        "description": "In battle, use one of your lead Pokémon's moves by name. Drives "
                       "the battle menu for you — advances intro/result text, opens FIGHT, "
                       "selects the move, and confirms it. Prefer this over press_button "
                       "for attacking. Pick the move from the 'Your moves' list.",
        "parameters": {"type": "object", "properties": {
            "move": {"type": "string", "description": "Exact move name, e.g. 'Tackle'."},
        }, "required": ["move"]},
    }},
    {"type": "function", "function": {
        "name": "grind",
        "description": "Level up your lead Pokémon by grinding wild battles. Stand in "
                       "TALL GRASS (a route or Viridian Forest) and call grind(level) — "
                       "it wanders to trigger wild battles and auto-fights each one for "
                       "you until your lead reaches the target level (no need to fight "
                       "them one at a time yourself). Use it to prepare for a gym, e.g. "
                       "grind(13) so Bulbasaur learns Vine Whip before Brock. It pauses "
                       "if HP gets low (then heal() and grind again).",
        "parameters": {"type": "object", "properties": {
            "level": {"type": "integer", "description": "target lead level, e.g. 13"},
        }, "required": ["level"]},
    }},
    {"type": "function", "function": {
        "name": "flee_battle",
        "description": "Run away from a WILD battle to keep moving. Use when you're "
                       "just travelling through a route/forest/cave and don't need "
                       "the fight, or when your HP is low and you'd rather escape "
                       "than risk fainting. Drives the RUN option for you. You "
                       "CANNOT flee a trainer battle (win or switch instead); the "
                       "escape can occasionally fail, so it may take a couple of "
                       "tries.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "catch",
        "description": "Throw a Poké Ball at the WILD Pokémon you're battling to add it "
                       "to your team. Opens the Bag, switches to the Poké Balls pocket, "
                       "and throws a ball for you. Best after you've weakened the foe "
                       "with use_move (low HP — or a status like sleep/paralysis — "
                       "greatly raises the catch rate); it may break free, so you can "
                       "catch() again. Use it on wild Pokémon that would help your team "
                       "(a new species, a good type). You can't catch a trainer's "
                       "Pokémon. Needs Poké Balls (buy them with shop()).",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "read_game_state",
        "description": "Read current game state: party HP, battle status, badges, location.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "save_state",
        "description": "Save state to a slot. Call before gym leaders and Elite Four.",
        "parameters": {"type": "object", "properties": {
            "slot": {"type": "integer", "default": 0},
        }},
    }},
    {"type": "function", "function": {
        "name": "load_state",
        "description": "Load a save state. Used after a loss.",
        "parameters": {"type": "object", "properties": {
            "slot": {"type": "integer", "default": 0},
        }},
    }},
    {"type": "function", "function": {
        "name": "wait_frames",
        "description": "Wait N frames (60fps). Use during animations and transitions.",
        "parameters": {"type": "object", "properties": {
            "frames": {"type": "integer"},
        }, "required": ["frames"]},
    }},
    {"type": "function", "function": {
        "name": "record_milestone",
        "description": (
            "Record a story milestone permanently to long-term memory. "
            "Call IMMEDIATELY after the triggering event. Valid names: "
            "starter_chosen, delivered_oaks_parcel, got_cut, got_flash, "
            "cleared_rock_tunnel, got_silph_scope, rescued_mr_fuji, got_poke_flute, "
            "got_surf, got_strength, woke_snorlax_12, woke_snorlax_16. "
            "Do NOT use this for gym wins — those are auto-detected."
        ),
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"},
            "note": {"type": "string", "default": ""},
        }, "required": ["name"]},
    }},
]

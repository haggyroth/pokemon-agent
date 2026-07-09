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
        "description": "Travel toward a named map (e.g. 'Viridian City', 'Route 1'). If "
                       "it's directly connected to the current map, crosses to it; "
                       "otherwise tells you the adjacent maps so you can head that way "
                       "one step at a time. Friendlier than go_to_map when you know the "
                       "destination name.",
        "parameters": {"type": "object", "properties": {
            "destination": {"type": "string", "description": "Map name, e.g. 'Viridian City'."},
        }, "required": ["destination"]},
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
        "name": "set_opponent",
        "description": (
            "Tell the agent which Pokémon you are currently facing in battle. "
            "Read the opponent's name from the battle screenshot and call this ONCE "
            "at the start of each new battle. This unlocks type-effectiveness "
            "analysis for your moves."
        ),
        "parameters": {"type": "object", "properties": {
            "species": {"type": "string",
                        "description": "Opponent Pokémon name exactly as shown (e.g. 'GEODUDE', 'STARMIE')"},
        }, "required": ["species"]},
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

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
        "name": "switch_pokemon",
        "description": "In battle, switch your active Pokémon to another party member "
                       "(by species name, e.g. 'Pidgey', or 1-based slot number). Drives "
                       "the party menu and confirms the swap. Switching costs your turn "
                       "(the opponent gets a free hit), so use it to bring in a "
                       "type-favorable Pokémon or save one that's low — not casually. "
                       "Needs a team of 2+ (build one with catch()). Can be used more than "
                       "once per battle.",
        "parameters": {"type": "object", "properties": {
            "target": {"type": "string",
                       "description": "Party member to send in: a species name or a 1-based slot."},
        }, "required": ["target"]},
    }},
    {"type": "function", "function": {
        "name": "use_item",
        "description": "In battle, use a Bag item on your ACTIVE Pokémon — a Potion "
                       "(or Super/Hyper/Max Potion) to restore HP, or a status cure "
                       "(Antidote, Paralyze Heal, Awakening, Burn Heal, Ice Heal, Full "
                       "Heal). Drives the Bag → Items pocket → item → your lead for you, "
                       "and confirms it worked. Using an item spends your turn, so heal "
                       "when your lead is low rather than risking a faint. Check the "
                       "'Bag:' line for what you have. OUTSIDE battle it works too: opens "
                       "Start → Bag, uses the item on the Pokémon that needs it (or the "
                       "`target` you name — species or 1-based slot), and also handles "
                       "Revive and Repel. Free actions out of battle: heal a hurt mon here "
                       "instead of walking to a Pokémon Center.",
        "parameters": {"type": "object", "properties": {
            "item": {"type": "string",
                     "description": "Item name, e.g. 'Potion', 'Super Potion', 'Antidote', "
                                    "'Revive', 'Repel'."},
            "target": {"type": "string",
                       "description": "Optional (field use): species name or 1-based party "
                                      "slot. Omit to auto-pick whoever needs it."},
        }, "required": ["item"]},
    }},
    {"type": "function", "function": {
        "name": "pick_up_items",
        "description": "Collect the item balls (Poké Balls sitting on the ground) visible "
                       "on the current map. Walks up to each, faces it, and picks it up for "
                       "you — free items like Potions, Antidotes, Poké Balls, and TMs. Call "
                       "it whenever the observation's 'Items on the ground:' line lists a "
                       "ball, before leaving the area. Overworld only.",
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
        "description": "Level up by fighting wild Pokémon in tall grass (auto-fights every battle, and "
                       "heals itself at a Pokémon Center when HP or attack PP runs low, then walks "
                       "back — one call does a lot of work). Two modes: grind(level=13) raises your "
                       "LEAD to L13 (e.g. before Brock so Bulbasaur has Vine Whip); grind() with NO "
                       "level BALANCES the team — every Pokémon should be within ~15% of your highest "
                       "(top L18 → nobody under L16), because weak backups can't carry a gym, a "
                       "dungeon or a forced switch. In balance mode the lowest lagging Pokémon is "
                       "sent in first for the XP and a strong teammate finishes tough fights. "
                       "Evolutions complete automatically. Use grind() after catching new Pokémon "
                       "and before gyms/dungeons.",
        "parameters": {"type": "object", "properties": {
            "level": {"type": "integer",
                      "description": "target LEAD level, e.g. 13. Omit (or 0) to balance the whole team."},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "teach_move",
        "description": "Teach a TM or HM move to a party Pokémon via the TM Case (Start → Bag → Key "
                       "Items → TM CASE → the TM → USE → Pokémon). `tm` is 'TM09', 'HM01', or the "
                       "move name ('Cut', 'Giga Drain'). `pokemon` (species or 1-based slot) is "
                       "optional — otherwise each party member is tried in order until one can learn "
                       "it. If it already knows 4 moves it forgets `forget` (a move name) or, by "
                       "default, a safe one (a status move / the weakest attack — never an HM move or "
                       "its last attack). Confirms the move shows up. Teach Cut/Surf/Strength/"
                       "Flash/Fly HMs this way, then use_hm.",
        "parameters": {"type": "object", "properties": {
            "tm": {"type": "string", "description": "e.g. 'HM01', 'TM09', 'Surf'"},
            "pokemon": {"type": "string", "description": "optional species name or 1-based slot"},
            "forget": {"type": "string", "description": "optional move to replace when full"},
        }, "required": ["tm"]},
    }},
    {"type": "function", "function": {
        "name": "fly_to",
        "description": "Fly to a town you have already visited (needs a Pokémon that knows Fly + the "
                       "Thunder Badge, and you must be outdoors). Opens the party menu, picks Fly and "
                       "steers the map cursor to the town. Towns: Pallet, Viridian, Pewter, Cerulean, "
                       "Lavender, Vermilion, Celadon, Fuchsia, Cinnabar, Saffron, Indigo Plateau. A "
                       "fast way back to a Pokémon Center / gym instead of walking.",
        "parameters": {"type": "object", "properties": {
            "town": {"type": "string"},
        }, "required": ["town"]},
    }},
    {"type": "function", "function": {
        "name": "use_hm",
        "description": "Use a field HM: Surf (starts surfing at the nearest shore — then walk_to / "
                       "go_to_map cross water), Cut (nearest cut tree), Rock Smash (rock), "
                       "Strength (boulder; then walk into it to push). A Pokémon in your party must "
                       "know the move and you need its badge. walk_to also starts Surf by itself "
                       "when only water blocks the route.",
        "parameters": {"type": "object", "properties": {
            "move": {"type": "string", "enum": ["Surf", "Cut", "Rock Smash", "Strength", "Flash"]},
        }, "required": ["move"]},
    }},
    {"type": "function", "function": {
        "name": "open_menu",
        "description": "Open a Start-menu entry and land on its screen: Pokemon (party), "
                       "Bag, Pokedex, Player (trainer card), Save, Option, or Exit. Moves "
                       "the Start-menu cursor for you and confirms the screen opened. "
                       "Then navigate inside with press_button; close_menus() exits.",
        "parameters": {"type": "object", "properties": {
            "menu": {"type": "string",
                     "enum": ["Pokemon", "Bag", "Pokedex", "Player", "Save", "Option", "Exit"]},
        }, "required": ["menu"]},
    }},
    {"type": "function", "function": {
        "name": "answer_prompt",
        "description": "Answer an open YES/NO box (e.g. 'Would you like to save?', shop or "
                       "NPC questions). Waits for the box to take input, sets the cursor, "
                       "and confirms. Not for battle menus.",
        "parameters": {"type": "object", "properties": {
            "answer": {"type": "string", "enum": ["yes", "no"]},
        }, "required": ["answer"]},
    }},
    {"type": "function", "function": {
        "name": "advance_dialog",
        "description": "Press A through NPC/sign/system dialogue until it finishes or a "
                       "choice (Yes/No / menu) needs your decision. Safer than mashing A.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "close_menus",
        "description": "Back out of every open menu, prompt and dialogue with B until you "
                       "are on the free field again. Use when stuck in a menu.",
        "parameters": {"type": "object", "properties": {}},
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
                       "Pokémon. Needs Poké Balls (buy them with shop()). ALWAYS pass a "
                       "`nickname` — you invent it, so make it memorable and a bit funny (a pun on "
                       "the species or its moves, a pop-culture or food reference, a dramatic or "
                       "grumpy title); never just the species name or a number, and no two team "
                       "members alike. Max 10 characters; letters, digits, space . , ! ? only "
                       "(typed on the naming screen for you).",
        "parameters": {"type": "object", "properties": {
            "nickname": {"type": "string",
                         "description": "name YOU invent for this catch — inventive/funny, max 10 chars, "
                                        "not the species name. Omit only to skip naming."},
        }},
    }},
    {"type": "function", "function": {
        "name": "enter_name",
        "description": "Type a name on the naming screen when one is open (a nickname, or "
                       "the player/rival name in a new game) and confirm it. Types key by "
                       "key, switching UPPER/lower/symbol pages and verifying every letter.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "letters, digits, space . , ! ?"},
        }, "required": ["name"]},
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

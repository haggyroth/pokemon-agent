# Pure game data for Pokemon LeafGreen (FireRed/LeafGreen US v1.0).
# No I/O. Zero imports. All data sourced from CLAUDE.md.

# ── Gyms ──────────────────────────────────────────────────────────────────────
# badge_bit: the bit index in the BADGES bitmask (0x02025968)
# bit 0=Brock, 1=Misty, 2=Surge, 3=Erika, 4=Koga, 5=Sabrina, 6=Blaine, 7=Giovanni

GYMS: list[dict] = [
    {
        "number": 1, "leader": "Brock", "city": "Pewter City",
        "type": "Rock", "badge": "Boulder Badge", "badge_bit": 0,
        "key_threat": "Geodude L12, Onix L14",
        "counter": "Grass or Water. Vine Whip wins.",
    },
    {
        "number": 2, "leader": "Misty", "city": "Cerulean City",
        "type": "Water", "badge": "Cascade Badge", "badge_bit": 1,
        "key_threat": "Starmie L21 (has Recover)",
        "counter": "Grass or Electric. Hit fast — Recover stalls.",
    },
    {
        "number": 3, "leader": "Lt. Surge", "city": "Vermilion City",
        "type": "Electric", "badge": "Thunder Badge", "badge_bit": 2,
        "key_threat": "Raichu L24",
        "counter": "Ground. Diglett from Diglett's Cave trivializes.",
    },
    {
        "number": 4, "leader": "Erika", "city": "Celadon City",
        "type": "Grass", "badge": "Rainbow Badge", "badge_bit": 3,
        "key_threat": "Vileplume L29 (Sleep Powder)",
        "counter": "Fire/Ice/Flying/Poison. Lum Berry blocks sleep.",
    },
    {
        "number": 5, "leader": "Koga", "city": "Fuchsia City",
        "type": "Poison", "badge": "Soul Badge", "badge_bit": 4,
        "key_threat": "Weezing L43 (Self-Destruct)",
        "counter": "Ground or Psychic. Bring Antidotes + Full Heals.",
    },
    {
        "number": 6, "leader": "Sabrina", "city": "Saffron City",
        "type": "Psychic", "badge": "Marsh Badge", "badge_bit": 5,
        "key_threat": "Alakazam L43",
        "counter": "Bug (2x). Dark moves only if high SpAtk. Ghost is immune, not 2x.",
    },
    {
        "number": 7, "leader": "Blaine", "city": "Cinnabar Island",
        "type": "Fire", "badge": "Volcano Badge", "badge_bit": 6,
        "key_threat": "Arcanine L47",
        "counter": "Water. Any Surf user. Requires Surf HM to reach.",
    },
    {
        "number": 8, "leader": "Giovanni", "city": "Viridian City",
        "type": "Ground", "badge": "Earth Badge", "badge_bit": 7,
        "key_threat": "Rhydon L50",
        "counter": "Water/Grass/Ice. Ice Beam for Rhydon.",
    },
]

# ── Elite Four ────────────────────────────────────────────────────────────────

ELITE_FOUR: list[dict] = [
    {"trainer": "Lorelei", "type": "Ice", "key_threat": "Lapras L60",
     "counter": "Electric, Rock, Fighting"},
    {"trainer": "Bruno",   "type": "Fighting", "key_threat": "Machamp L58",
     "counter": "Psychic, Flying"},
    {"trainer": "Agatha",  "type": "Ghost", "key_threat": "Gengar L58",
     "counter": "Ground, Psychic"},
    {"trainer": "Lance",   "type": "Dragon", "key_threat": "Dragonite L62",
     "counter": "Ice Beam is critical. Dragonite survives most else."},
    {"trainer": "Gary",    "type": "Mixed", "key_threat": "Alakazam + Rhydon + starter counter",
     "counter": "Ice Beam for Rhydon; Psychic for Fighting; counter Gary's starter."},
]

# ── HM Requirements ───────────────────────────────────────────────────────────

HM_REQUIREMENTS: dict[str, dict] = {
    "Cut":      {"hm": "HM01", "required_for": "optional tree shortcuts",
                 "location": "S.S. Anne, Vermilion"},
    "Fly":      {"hm": "HM02", "required_for": "fast travel",
                 "location": "Route 16 house (need Cut)"},
    "Surf":     {"hm": "HM03", "required_for": "all water routes — required for Gym 7",
                 "location": "Safari Zone warden quest (Gold Teeth)"},
    "Strength": {"hm": "HM04", "required_for": "boulders in caves — required for Victory Road",
                 "location": "Safari Zone warden quest (Gold Teeth)"},
    "Flash":    {"hm": "HM05", "required_for": "Rock Tunnel navigation (optional)",
                 "location": "Route 2 Oak's aide"},
}

# ── Milestones (closed vocabulary the LLM and auto-detect both use) ───────────

MILESTONES: tuple[str, ...] = (
    "starter_chosen", "delivered_oaks_parcel",
    "beat_brock", "got_cut", "beat_misty",
    "beat_surge", "got_flash", "cleared_rock_tunnel",
    "got_silph_scope", "rescued_mr_fuji", "got_poke_flute",
    "beat_erika", "beat_koga", "beat_sabrina", "beat_blaine", "beat_giovanni",
    "got_surf", "got_strength",
    "woke_snorlax_12", "woke_snorlax_16",
)

# Map badge bit index (0..7) → auto-emitted milestone name
BADGE_BIT_MILESTONE: dict[int, str] = {
    0: "beat_brock",    1: "beat_misty",   2: "beat_surge",  3: "beat_erika",
    4: "beat_koga",     5: "beat_sabrina", 6: "beat_blaine", 7: "beat_giovanni",
}


def badges_in_bitmask(badge_bits: int) -> list[tuple[int, str | None, str | None]]:
    """Decode a BADGES bitmask into (bit, gym_leader, milestone_name) for each
    set bit. leader/milestone are None if a bit is unmapped. Pure — no I/O."""
    out = []
    for bit in range(8):
        if badge_bits & (1 << bit):
            gym = next((g for g in GYMS if g["badge_bit"] == bit), None)
            out.append((bit, gym["leader"] if gym else None, BADGE_BIT_MILESTONE.get(bit)))
    return out

# ── Key Items ─────────────────────────────────────────────────────────────────

KEY_ITEMS: list[dict] = [
    {"item": "Silph Scope",  "location": "Celadon Rocket Hideout B4F",
     "required_for": "Pokémon Tower (Lavender) — reveals ghost Pokemon"},
    {"item": "Poke Flute",   "location": "Mr. Fuji, Lavender Town",
     "required_for": "Wake Snorlax blocking Routes 12 and 16"},
    {"item": "Lapras",       "location": "Silph Co. (free gift, L25)",
     "note": "Only one available. Excellent Surf + Ice Beam user."},
    {"item": "TM26 Earthquake",  "location": "Silph Co.",
     "note": "Critical — Ground/Physical 100 power"},
    {"item": "TM13 Ice Beam",    "location": "Celadon Game Corner (4000 coins)",
     "note": "Critical — covers Dragon/Ground/Flying. Essential for Lance."},
    {"item": "TM24 Thunderbolt", "location": "Celadon Game Corner (4000 coins)"},
    {"item": "TM35 Flamethrower","location": "Celadon Game Corner (4000 coins)"},
    {"item": "TM29 Psychic",     "location": "Saffron City (man in house)"},
]

# ── Starter Recommendation ────────────────────────────────────────────────────

STARTER_RECOMMENDATION = "Bulbasaur"
STARTER_REASON = (
    "Trivializes Gyms 1 (Vine Whip vs Rock) and 2 (Vine Whip vs Water). "
    "Learns Sleep Powder for catching Pokémon. "
    "Gives the agent more time to learn navigation before difficulty spikes."
)

# ── Gen III damage category (CRITICAL — differs from Gen IV+) ─────────────────
# Determined by MOVE TYPE, not per-move.
# Physical types use Atk vs Def; Special types use SpAtk vs SpDef.

GEN3_CATEGORY: dict[str, str] = {
    "NOR": "Physical", "FIG": "Physical", "FLY": "Physical", "POI": "Physical",
    "GRD": "Physical", "ROC": "Physical", "BUG": "Physical", "GHO": "Physical",
    "STL": "Physical",
    "FIR": "Special",  "WAT": "Special",  "GRS": "Special",  "ELE": "Special",
    "ICE": "Special",  "PSY": "Special",  "DRG": "Special",  "DRK": "Special",
}

# ── Move name → type code ─────────────────────────────────────────────────────
# Covers moves commonly seen in LeafGreen playthroughs.

MOVE_TYPE: dict[str, str] = {
    # Normal
    "Tackle": "NOR", "Scratch": "NOR", "Pound": "NOR", "Growl": "NOR",
    "Tail Whip": "NOR", "Leer": "NOR", "String Shot": "NOR", "Smokescreen": "NOR",
    "Sand Attack": "NOR", "Sweet Scent": "NOR", "Scary Face": "NOR",
    "Constrict": "NOR", "Harden": "NOR", "Withdraw": "NOR", "Minimize": "NOR",
    "Amnesia": "NOR", "Softboiled": "NOR", "Splash": "NOR", "Conversion": "NOR",
    "Wrap": "NOR", "Bind": "NOR", "Quick Attack": "NOR", "Double-Edge": "NOR",
    "Body Slam": "NOR", "Hyper Beam": "NOR", "Return": "NOR", "Frustration": "NOR",
    "Slash": "NOR", "Swift": "NOR", "Pay Day": "NOR", "Headbutt": "NOR",
    "Skull Bash": "NOR", "Explosion": "NOR", "Self-Destruct": "NOR",
    "Double Team": "NOR", "Supersonic": "NOR", "Screech": "NOR",
    "Attract": "NOR", "Protect": "NOR", "Endure": "NOR", "Snore": "NOR",
    "Rest": "PSY",  # Rest is Psychic type move
    "Metronome": "NOR", "Tri Attack": "NOR", "Sharpen": "NOR",
    "Recover": "NOR", "Haze": "ICE",  # Haze is Ice
    "Agility": "PSY",  # Agility is Psychic type
    "Barrier": "PSY",  # Barrier is Psychic type
    "Mimic": "NOR", "Bide": "NOR", "Rage": "NOR", "Disable": "NOR",
    "Lick": "GHO", "Stomp": "NOR", "Cut": "NOR", "Strength": "NOR",
    "Flash": "NOR", "Rock Smash": "FIG",
    # Fighting
    "Karate Chop": "FIG", "Low Kick": "FIG", "Double Kick": "FIG",
    "Jump Kick": "FIG", "Hi Jump Kick": "FIG", "Rolling Kick": "FIG",
    "Counter": "FIG", "Seismic Toss": "FIG", "Submission": "FIG",
    "Superpower": "FIG", "Mach Punch": "FIG", "Cross Chop": "FIG",
    "Sky Uppercut": "FIG", "Focus Punch": "FIG", "Brick Break": "FIG",
    "Vital Throw": "FIG",
    # Flying
    "Wing Attack": "FLY", "Fly": "FLY", "Peck": "FLY", "Drill Peck": "FLY",
    "Mirror Move": "FLY", "Sky Attack": "FLY", "Aerial Ace": "FLY",
    "Hurricane": "FLY", "Gust": "FLY",
    # Poison
    "Poison Sting": "POI", "Acid": "POI", "Smog": "POI", "Sludge": "POI",
    "Sludge Bomb": "POI", "Toxic": "POI", "Poison Powder": "POI",
    "Stun Spore": "GRS",  # Stun Spore is Grass type
    "Sleep Powder": "GRS",  # Sleep Powder is Grass type
    "Leech Seed": "GRS",
    # Ground
    "Earthquake": "GRD", "Fissure": "GRD", "Dig": "GRD", "Mud-Slap": "GRD",
    "Magnitude": "GRD", "Bone Club": "GRD", "Bonemerang": "GRD",
    "Bone Rush": "GRD", "Sand Tomb": "GRD", "Mud Shot": "GRD",
    # Rock
    "Rock Throw": "ROC", "Rock Slide": "ROC", "Rock Blast": "ROC",
    "Rollout": "ROC", "Defense Curl": "NOR", "Ancient Power": "ROC",
    "Sandstorm": "ROC",
    # Bug
    "Leech Life": "BUG", "Pin Missile": "BUG", "X-Scissor": "BUG",
    "Twineedle": "BUG", "Fury Attack": "NOR",  # Fury Attack is Normal
    "Fury Swipes": "NOR",
    "Signal Beam": "BUG", "Silver Wind": "BUG",
    # Ghost  (Lick is defined once above in the Normal-move block)
    "Night Shade": "GHO", "Confuse Ray": "GHO",
    "Shadow Ball": "GHO", "Astonish": "GHO", "Grudge": "GHO",
    "Destiny Bond": "GHO", "Curse": "GHO",
    # Steel
    "Iron Tail": "STL", "Metal Claw": "STL", "Steel Wing": "STL",
    "Meteor Mash": "STL", "Magnet Bomb": "STL",
    # Fire
    "Ember": "FIR", "Flamethrower": "FIR", "Fire Blast": "FIR",
    "Fire Spin": "FIR", "Fire Punch": "FIR", "Flame Wheel": "FIR",
    "Overheat": "FIR",
    # Water
    "Water Gun": "WAT", "Bubble": "WAT", "Bubble Beam": "WAT",
    "Surf": "WAT", "Hydro Pump": "WAT", "Water Pulse": "WAT",
    "Waterfall": "WAT", "Clamp": "WAT", "Whirlpool": "WAT",
    "Crabhammer": "WAT", "Brine": "WAT",
    # Grass
    "Vine Whip": "GRS", "Razor Leaf": "GRS", "Solar Beam": "GRS",
    "Mega Drain": "GRS", "Absorb": "GRS", "Giga Drain": "GRS",
    "Bullet Seed": "GRS", "Frenzy Plant": "GRS",
    # Electric
    "Thunderbolt": "ELE", "Thunder": "ELE", "Thundershock": "ELE",
    "Thunder Wave": "ELE", "Thunder Punch": "ELE", "Spark": "ELE",
    "Discharge": "ELE", "Volt Tackle": "ELE", "Shock Wave": "ELE",
    # Ice
    "Ice Beam": "ICE", "Blizzard": "ICE", "Ice Punch": "ICE",
    "Powder Snow": "ICE", "Aurora Beam": "ICE", "Icy Wind": "ICE",
    "Sheer Cold": "ICE", "Hail": "ICE",
    # Psychic
    "Psychic": "PSY", "Psybeam": "PSY", "Confusion": "PSY",
    "Psywave": "PSY", "Future Sight": "PSY", "Dream Eater": "PSY",
    "Hypnosis": "PSY", "Meditate": "PSY", "Kinesis": "PSY",
    "Calm Mind": "PSY", "Extrasensory": "PSY",
    # Dragon
    "Dragon Rage": "DRG", "Dragon Breath": "DRG", "Outrage": "DRG",
    "Draco Meteor": "DRG", "Twister": "DRG",
    # Dark
    "Bite": "DRK", "Crunch": "DRK", "Faint Attack": "DRK",
    "Knock Off": "DRK", "Pursuit": "DRK", "Thief": "DRK",
    "Torment": "DRK", "Taunt": "DRK", "Snatch": "DRK",
}

# ── All 151 Kanto Pokémon species → types ─────────────────────────────────────
# Tuple of 1 or 2 type codes. Used to rate move effectiveness vs live opponents.

POKEMON_TYPES: dict[str, tuple[str, ...]] = {
    "BULBASAUR": ("GRS", "POI"), "IVYSAUR": ("GRS", "POI"), "VENUSAUR": ("GRS", "POI"),
    "CHARMANDER": ("FIR",),      "CHARMELEON": ("FIR",),     "CHARIZARD": ("FIR", "FLY"),
    "SQUIRTLE": ("WAT",),        "WARTORTLE": ("WAT",),      "BLASTOISE": ("WAT",),
    "CATERPIE": ("BUG",),        "METAPOD": ("BUG",),        "BUTTERFREE": ("BUG", "FLY"),
    "WEEDLE": ("BUG", "POI"),    "KAKUNA": ("BUG", "POI"),   "BEEDRILL": ("BUG", "POI"),
    "PIDGEY": ("NOR", "FLY"),    "PIDGEOTTO": ("NOR", "FLY"), "PIDGEOT": ("NOR", "FLY"),
    "RATTATA": ("NOR",),         "RATICATE": ("NOR",),
    "SPEAROW": ("NOR", "FLY"),   "FEAROW": ("NOR", "FLY"),
    "EKANS": ("POI",),           "ARBOK": ("POI",),
    "PIKACHU": ("ELE",),         "RAICHU": ("ELE",),
    "SANDSHREW": ("GRD",),       "SANDSLASH": ("GRD",),
    "NIDORAN F": ("POI",),       "NIDORINA": ("POI",),       "NIDOQUEEN": ("POI", "GRD"),
    "NIDORAN M": ("POI",),       "NIDORINO": ("POI",),       "NIDOKING": ("POI", "GRD"),
    "CLEFAIRY": ("NOR",),        "CLEFABLE": ("NOR",),
    "VULPIX": ("FIR",),          "NINETALES": ("FIR",),
    "JIGGLYPUFF": ("NOR",),      "WIGGLYTUFF": ("NOR",),
    "ZUBAT": ("POI", "FLY"),     "GOLBAT": ("POI", "FLY"),
    "ODDISH": ("GRS", "POI"),    "GLOOM": ("GRS", "POI"),    "VILEPLUME": ("GRS", "POI"),
    "PARAS": ("BUG", "GRS"),     "PARASECT": ("BUG", "GRS"),
    "VENONAT": ("BUG", "POI"),   "VENOMOTH": ("BUG", "POI"),
    "DIGLETT": ("GRD",),         "DUGTRIO": ("GRD",),
    "MEOWTH": ("NOR",),          "PERSIAN": ("NOR",),
    "PSYDUCK": ("WAT",),         "GOLDUCK": ("WAT",),
    "MANKEY": ("FIG",),          "PRIMEAPE": ("FIG",),
    "GROWLITHE": ("FIR",),       "ARCANINE": ("FIR",),
    "POLIWAG": ("WAT",),         "POLIWHIRL": ("WAT",),      "POLIWRATH": ("WAT", "FIG"),
    "ABRA": ("PSY",),            "KADABRA": ("PSY",),        "ALAKAZAM": ("PSY",),
    "MACHOP": ("FIG",),          "MACHOKE": ("FIG",),        "MACHAMP": ("FIG",),
    "BELLSPROUT": ("GRS", "POI"), "WEEPINBELL": ("GRS", "POI"), "VICTREEBEL": ("GRS", "POI"),
    "TENTACOOL": ("WAT", "POI"), "TENTACRUEL": ("WAT", "POI"),
    "GEODUDE": ("ROC", "GRD"),   "GRAVELER": ("ROC", "GRD"), "GOLEM": ("ROC", "GRD"),
    "PONYTA": ("FIR",),          "RAPIDASH": ("FIR",),
    "SLOWPOKE": ("WAT", "PSY"),  "SLOWBRO": ("WAT", "PSY"),
    "MAGNEMITE": ("ELE", "STL"), "MAGNETON": ("ELE", "STL"),
    "FARFETCHD": ("NOR", "FLY"), "DODUO": ("NOR", "FLY"),    "DODRIO": ("NOR", "FLY"),
    "SEEL": ("WAT",),            "DEWGONG": ("WAT", "ICE"),
    "GRIMER": ("POI",),          "MUK": ("POI",),
    "SHELLDER": ("WAT",),        "CLOYSTER": ("WAT", "ICE"),
    "GASTLY": ("GHO", "POI"),    "HAUNTER": ("GHO", "POI"),  "GENGAR": ("GHO", "POI"),
    "ONIX": ("ROC", "GRD"),
    "DROWZEE": ("PSY",),         "HYPNO": ("PSY",),
    "KRABBY": ("WAT",),          "KINGLER": ("WAT",),
    "VOLTORB": ("ELE",),         "ELECTRODE": ("ELE",),
    "EXEGGCUTE": ("GRS", "PSY"), "EXEGGUTOR": ("GRS", "PSY"),
    "CUBONE": ("GRD",),          "MAROWAK": ("GRD",),
    "HITMONLEE": ("FIG",),       "HITMONCHAN": ("FIG",),
    "LICKITUNG": ("NOR",),
    "KOFFING": ("POI",),         "WEEZING": ("POI",),
    "RHYHORN": ("GRD", "ROC"),   "RHYDON": ("GRD", "ROC"),
    "CHANSEY": ("NOR",),
    "TANGELA": ("GRS",),
    "KANGASKHAN": ("NOR",),
    "HORSEA": ("WAT",),          "SEADRA": ("WAT",),
    "GOLDEEN": ("WAT",),         "SEAKING": ("WAT",),
    "STARYU": ("WAT",),          "STARMIE": ("WAT", "PSY"),
    "MR. MIME": ("PSY",),        "MRMIME": ("PSY",),
    "SCYTHER": ("BUG", "FLY"),
    "JYNX": ("ICE", "PSY"),
    "ELECTABUZZ": ("ELE",),
    "MAGMAR": ("FIR",),
    "PINSIR": ("BUG",),
    "TAUROS": ("NOR",),
    "MAGIKARP": ("WAT",),        "GYARADOS": ("WAT", "FLY"),
    "LAPRAS": ("WAT", "ICE"),
    "DITTO": ("NOR",),
    "EEVEE": ("NOR",),           "VAPOREON": ("WAT",),
    "JOLTEON": ("ELE",),         "FLAREON": ("FIR",),
    "PORYGON": ("NOR",),
    "OMANYTE": ("ROC", "WAT"),   "OMASTAR": ("ROC", "WAT"),
    "KABUTO": ("ROC", "WAT"),    "KABUTOPS": ("ROC", "WAT"),
    "AERODACTYL": ("ROC", "FLY"),
    "SNORLAX": ("NOR",),
    "ARTICUNO": ("ICE", "FLY"),
    "ZAPDOS": ("ELE", "FLY"),
    "MOLTRES": ("FIR", "FLY"),
    "DRATINI": ("DRG",),         "DRAGONAIR": ("DRG",),      "DRAGONITE": ("DRG", "FLY"),
    "MEWTWO": ("PSY",),          "MEW": ("PSY",),
}

class Addr:
    # Party — read with /core/readrange
    # Note: PARTY_DATA confirmed at 0x02024284 by live decryption (Bulbasaur L6, Tackle+Growl).
    # There is no reliable separate party-count address; use level>0 at slot offset 0x54 instead.
    PARTY_DATA   = 0x02024284   # 600 bytes: 6 × 100-byte party structs

    # Progress
    BADGES       = 0x02025968   # u8 bitmask: popcount = badges earned
    # Bit order: bit 0=Brock, 1=Misty, 2=Surge, 3=Erika,
    #            4=Koga, 5=Sabrina, 6=Blaine, 7=Giovanni

    # Context detection — three-signal system (empirically verified via diagnostic):
    #
    #   OVERWORLD_FLAG (0x0202287C) u32:
    #     Non-zero (0x00410000) on overworld, 0 in battle and transition.
    #     Primary gate: if != 0 we are on the overworld.
    #
    #   SCREEN_FADE (0x03000F9C) u8:
    #     1 during BOTH screen-fade transitions AND active battle.
    #     Cannot be used alone to detect "transitioning" — only meaningful when
    #     OVERWORLD_FLAG is also non-zero (overworld fade).
    #
    #   SCRIPT_RAM byte[2] (0x03000EB2) u8:
    #     0x01 ONLY when it is the player's move-select turn — 0 during HP
    #     animations, move text, damage rolls, etc. NOT reliable for battle
    #     detection; only non-zero for a fraction of each battle turn.
    #
    # Detection logic in detect_context():
    #   OVERWORLD_FLAG != 0 → OVERWORLD (or TRANSITIONING if also fading)
    #   OVERWORLD_FLAG == 0, BATTLE_FLAGS != 0 → IN_BATTLE (stays set all battle)
    #   OVERWORLD_FLAG == 0, BATTLE_FLAGS == 0 → TRANSITIONING
    #
    # ⚠ IMPORTANT: BATTLE_FLAGS (gBattleTypeFlags) is NOT zeroed when a battle
    # ends and the player returns to the overworld.  It retains the last battle's
    # flags indefinitely.  Never check BATTLE_FLAGS without first confirming
    # OVERWORLD_FLAG == 0.  Checking BATTLE_FLAGS alone will give false positives
    # on every overworld frame after the first battle.
    OVERWORLD_FLAG = 0x0202287C   # u32: non-zero = on overworld; 0 in battle/transition
    BATTLE_FLAGS   = 0x02022880   # u32: gBattleTypeFlags — non-zero during battle, persists after
    SCREEN_FADE    = 0x03000F9C   # u8: 1 during fade AND during battle
    SCRIPT_RAM     = 0x03000EB0   # 74 bytes; byte[2] at 0x03000EB2 = 0x01 in battle

    # Map header — DataCrystal: "Current Map Header 0x02036DFC"
    # The struct MapHeader sits directly at this address (not a pointer to it).
    # First 4 bytes are the mapLayout ROM pointer (0x08xxxxxx).
    MAP_HEADER   = 0x02036DFC   # struct MapHeader in EWRAM

    # Map bank/id — these are in the save-warp block, reliable for current map
    MAP_BANK     = 0x02031DBC   # u8: current map bank
    MAP_ID       = 0x02031DBD   # u8: current map number

    # Live player tile coordinates — always indirect; the target block is
    # DMA-protected and its address changes on every map transition.
    # DataCrystal RAM map:
    #   [0x03005008]+0x000 = Camera X (2b) = player tile X
    #   [0x03005008]+0x002 = Camera Y (2b) = player tile Y
    #   [0x03005008]+0x004 = current map number (1b)
    #   [0x03005008]+0x005 = current map bank (1b)
    # read_player_pos() in memory_reader.py does: ptr=read32(PLAYER_PTR);
    # x=read16(ptr); y=read16(ptr+2).
    # DO NOT cache or store the resolved address — it drifts.
    PLAYER_PTR   = 0x03005008   # IRAM → DMA-protected map data block

    # Player sprite object (overworld, 36 bytes). Player is always OW slot 0.
    # Offsets within OW struct (from pokefirered decomp / DataCrystal):
    #   +0x1C, +0x20 = sub-tile pixel offsets (not tile coords — do not use for navigation)
    OW_PLAYER    = 0x02036E38   # struct OW[0], 36 bytes

    # ⚠ MEMORY.md correction: 0x0202402C is gFrameCount (frame counter),
    # NOT the enemy party data.  Do not read battle Pokémon from this address.
    # Enemy battle data lives in gBattleMons (unencrypted, 88 bytes/slot);
    # exact EWRAM address requires the pokefirered linker map — pending research.
    # ENEMY_PARTY  = 0x0202402C   # ← WRONG: this is gFrameCount


# Gen III character encoding (for nickname decoding)
GEN3_CHARSET: dict[int, str | None] = {
    0x00: " ",
    0xA1: "0", 0xA2: "1", 0xA3: "2", 0xA4: "3", 0xA5: "4",
    0xA6: "5", 0xA7: "6", 0xA8: "7", 0xA9: "8", 0xAA: "9",
    0xAB: "!", 0xAC: "?", 0xAD: ".", 0xAE: "-",
    0xBB: "A", 0xBC: "B", 0xBD: "C", 0xBE: "D", 0xBF: "E",
    0xC0: "F", 0xC1: "G", 0xC2: "H", 0xC3: "I", 0xC4: "J",
    0xC5: "K", 0xC6: "L", 0xC7: "M", 0xC8: "N", 0xC9: "O",
    0xCA: "P", 0xCB: "Q", 0xCC: "R", 0xCD: "S", 0xCE: "T",
    0xCF: "U", 0xD0: "V", 0xD1: "W", 0xD2: "X", 0xD3: "Y",
    0xD4: "Z",
    0xD5: "a", 0xD6: "b", 0xD7: "c", 0xD8: "d", 0xD9: "e",
    0xDA: "f", 0xDB: "g", 0xDC: "h", 0xDD: "i", 0xDE: "j",
    0xDF: "k", 0xE0: "l", 0xE1: "m", 0xE2: "n", 0xE3: "o",
    0xE4: "p", 0xE5: "q", 0xE6: "r", 0xE7: "s", 0xE8: "t",
    0xE9: "u", 0xEA: "v", 0xEB: "w", 0xEC: "x", 0xED: "y",
    0xEE: "z",
    0xFC: "\n", 0xFD: "[NAME]", 0xFE: "\n\n", 0xFF: None,
}


def decode_gen3_string(raw: bytes) -> str:
    chars = []
    for byte in raw:
        ch = GEN3_CHARSET.get(byte)
        if ch is None:
            break
        chars.append(ch)
    return "".join(chars)


# Full Gen I National Dex (1–151)
SPECIES_NAMES: dict[int, str] = {
    1: "Bulbasaur",    2: "Ivysaur",      3: "Venusaur",
    4: "Charmander",   5: "Charmeleon",   6: "Charizard",
    7: "Squirtle",     8: "Wartortle",    9: "Blastoise",
    10: "Caterpie",   11: "Metapod",     12: "Butterfree",
    13: "Weedle",     14: "Kakuna",      15: "Beedrill",
    16: "Pidgey",     17: "Pidgeotto",   18: "Pidgeot",
    19: "Rattata",    20: "Raticate",    21: "Spearow",
    22: "Fearow",     23: "Ekans",       24: "Arbok",
    25: "Pikachu",    26: "Raichu",      27: "Sandshrew",
    28: "Sandslash",  29: "Nidoran-F",   30: "Nidorina",
    31: "Nidoqueen",  32: "Nidoran-M",   33: "Nidorino",
    34: "Nidoking",   35: "Clefairy",    36: "Clefable",
    37: "Vulpix",     38: "Ninetales",   39: "Jigglypuff",
    40: "Wigglytuff", 41: "Zubat",       42: "Golbat",
    43: "Oddish",     44: "Gloom",       45: "Vileplume",
    46: "Paras",      47: "Parasect",    48: "Venonat",
    49: "Venomoth",   50: "Diglett",     51: "Dugtrio",
    52: "Meowth",     53: "Persian",     54: "Psyduck",
    55: "Golduck",    56: "Mankey",      57: "Primeape",
    58: "Growlithe",  59: "Arcanine",    60: "Poliwag",
    61: "Poliwhirl",  62: "Poliwrath",   63: "Abra",
    64: "Kadabra",    65: "Alakazam",    66: "Machop",
    67: "Machoke",    68: "Machamp",     69: "Bellsprout",
    70: "Weepinbell", 71: "Victreebel",  72: "Tentacool",
    73: "Tentacruel", 74: "Geodude",     75: "Graveler",
    76: "Golem",      77: "Ponyta",      78: "Rapidash",
    79: "Slowpoke",   80: "Slowbro",     81: "Magnemite",
    82: "Magneton",   83: "Farfetch'd",  84: "Doduo",
    85: "Dodrio",     86: "Seel",        87: "Dewgong",
    88: "Grimer",     89: "Muk",         90: "Shellder",
    91: "Cloyster",   92: "Gastly",      93: "Haunter",
    94: "Gengar",     95: "Onix",        96: "Drowzee",
    97: "Hypno",      98: "Krabby",      99: "Kingler",
    100: "Voltorb",  101: "Electrode",  102: "Exeggcute",
    103: "Exeggutor",104: "Cubone",     105: "Marowak",
    106: "Hitmonlee",107: "Hitmonchan", 108: "Lickitung",
    109: "Koffing",  110: "Weezing",    111: "Rhyhorn",
    112: "Rhydon",   113: "Chansey",    114: "Tangela",
    115: "Kangaskhan",116: "Horsea",    117: "Seadra",
    118: "Goldeen",  119: "Seaking",    120: "Staryu",
    121: "Starmie",  122: "Mr. Mime",   123: "Scyther",
    124: "Jynx",     125: "Electabuzz", 126: "Magmar",
    127: "Pinsir",   128: "Tauros",     129: "Magikarp",
    130: "Gyarados", 131: "Lapras",     132: "Ditto",
    133: "Eevee",    134: "Vaporeon",   135: "Jolteon",
    136: "Flareon",  137: "Porygon",    138: "Omanyte",
    139: "Omastar",  140: "Kabuto",     141: "Kabutops",
    142: "Aerodactyl",143: "Snorlax",   144: "Articuno",
    145: "Zapdos",   146: "Moltres",    147: "Dratini",
    148: "Dragonair",149: "Dragonite",  150: "Mewtwo",
    151: "Mew",
}


# All 354 Gen III moves (FireRed/LeafGreen)
MOVE_NAMES: dict[int, str] = {
    1:   "Pound",          2:   "Karate Chop",     3:   "Double Slap",
    4:   "Comet Punch",    5:   "Mega Punch",       6:   "Pay Day",
    7:   "Fire Punch",     8:   "Ice Punch",        9:   "Thunder Punch",
    10:  "Scratch",        11:  "Vise Grip",        12:  "Guillotine",
    13:  "Razor Wind",     14:  "Swords Dance",     15:  "Cut",
    16:  "Gust",           17:  "Wing Attack",      18:  "Whirlwind",
    19:  "Fly",            20:  "Bind",             21:  "Slam",
    22:  "Vine Whip",      23:  "Stomp",            24:  "Double Kick",
    25:  "Mega Kick",      26:  "Jump Kick",        27:  "Rolling Kick",
    28:  "Sand Attack",    29:  "Headbutt",         30:  "Horn Attack",
    31:  "Fury Attack",    32:  "Horn Drill",       33:  "Tackle",
    34:  "Body Slam",      35:  "Wrap",             36:  "Take Down",
    37:  "Thrash",         38:  "Double-Edge",      39:  "Tail Whip",
    40:  "Poison Sting",   41:  "Twineedle",        42:  "Pin Missile",
    43:  "Leer",           44:  "Bite",             45:  "Growl",
    46:  "Roar",           47:  "Sing",             48:  "Supersonic",
    49:  "Sonic Boom",     50:  "Disable",          51:  "Acid",
    52:  "Ember",          53:  "Flamethrower",     54:  "Mist",
    55:  "Water Gun",      56:  "Hydro Pump",       57:  "Surf",
    58:  "Ice Beam",       59:  "Blizzard",         60:  "Psybeam",
    61:  "Bubble Beam",    62:  "Aurora Beam",      63:  "Hyper Beam",
    64:  "Peck",           65:  "Drill Peck",       66:  "Submission",
    67:  "Low Kick",       68:  "Counter",          69:  "Seismic Toss",
    70:  "Strength",       71:  "Absorb",           72:  "Mega Drain",
    73:  "Leech Seed",     74:  "Growth",           75:  "Razor Leaf",
    76:  "Solar Beam",     77:  "Poison Powder",    78:  "Stun Spore",
    79:  "Sleep Powder",   80:  "Petal Dance",      81:  "String Shot",
    82:  "Dragon Rage",    83:  "Fire Spin",        84:  "Thunder Shock",
    85:  "Thunderbolt",    86:  "Thunder Wave",     87:  "Thunder",
    88:  "Rock Throw",     89:  "Earthquake",       90:  "Fissure",
    91:  "Dig",            92:  "Toxic",            93:  "Confusion",
    94:  "Psychic",        95:  "Hypnosis",         96:  "Meditate",
    97:  "Agility",        98:  "Quick Attack",     99:  "Rage",
    100: "Teleport",       101: "Night Shade",      102: "Mimic",
    103: "Screech",        104: "Double Team",      105: "Recover",
    106: "Harden",         107: "Minimize",         108: "Smokescreen",
    109: "Confuse Ray",    110: "Withdraw",         111: "Defense Curl",
    112: "Barrier",        113: "Light Screen",     114: "Haze",
    115: "Reflect",        116: "Focus Energy",     117: "Bide",
    118: "Metronome",      119: "Mirror Move",      120: "Self-Destruct",
    121: "Egg Bomb",       122: "Lick",             123: "Smog",
    124: "Sludge",         125: "Bone Club",        126: "Fire Blast",
    127: "Waterfall",      128: "Clamp",            129: "Swift",
    130: "Skull Bash",     131: "Spike Cannon",     132: "Constrict",
    133: "Amnesia",        134: "Kinesis",          135: "Soft-Boiled",
    136: "Hi Jump Kick",   137: "Glare",            138: "Dream Eater",
    139: "Poison Gas",     140: "Barrage",          141: "Leech Life",
    142: "Lovely Kiss",    143: "Sky Attack",       144: "Transform",
    145: "Bubble",         146: "Dizzy Punch",      147: "Spore",
    148: "Flash",          149: "Psywave",          150: "Splash",
    151: "Acid Armor",     152: "Crabhammer",       153: "Explosion",
    154: "Fury Swipes",    155: "Bonemerang",       156: "Rest",
    157: "Rock Slide",     158: "Hyper Fang",       159: "Sharpen",
    160: "Conversion",     161: "Tri Attack",       162: "Super Fang",
    163: "Slash",          164: "Substitute",       165: "Struggle",
    166: "Sketch",         167: "Triple Kick",      168: "Thief",
    169: "Spider Web",     170: "Mind Reader",      171: "Nightmare",
    172: "Flame Wheel",    173: "Snore",            174: "Curse",
    175: "Flail",          176: "Conversion 2",     177: "Aeroblast",
    178: "Cotton Spore",   179: "Reversal",         180: "Spite",
    181: "Powder Snow",    182: "Protect",          183: "Mach Punch",
    184: "Scary Face",     185: "Feint Attack",     186: "Sweet Kiss",
    187: "Belly Drum",     188: "Sludge Bomb",      189: "Mud-Slap",
    190: "Octazooka",      191: "Spikes",           192: "Zap Cannon",
    193: "Foresight",      194: "Destiny Bond",     195: "Perish Song",
    196: "Icy Wind",       197: "Detect",           198: "Bone Rush",
    199: "Lock-On",        200: "Outrage",          201: "Sandstorm",
    202: "Giga Drain",     203: "Endure",           204: "Charm",
    205: "Rollout",        206: "False Swipe",      207: "Swagger",
    208: "Milk Drink",     209: "Spark",            210: "Fury Cutter",
    211: "Steel Wing",     212: "Mean Look",        213: "Attract",
    214: "Sleep Talk",     215: "Heal Bell",        216: "Return",
    217: "Present",        218: "Frustration",      219: "Safeguard",
    220: "Pain Split",     221: "Sacred Fire",      222: "Magnitude",
    223: "Dynamic Punch",  224: "Megahorn",         225: "Dragon Breath",
    226: "Baton Pass",     227: "Encore",           228: "Pursuit",
    229: "Rapid Spin",     230: "Sweet Scent",      231: "Iron Tail",
    232: "Metal Claw",     233: "Vital Throw",      234: "Morning Sun",
    235: "Synthesis",      236: "Moonlight",        237: "Hidden Power",
    238: "Cross Chop",     239: "Twister",          240: "Rain Dance",
    241: "Sunny Day",      242: "Crunch",           243: "Mirror Coat",
    244: "Psych Up",       245: "Extreme Speed",    246: "Ancient Power",
    247: "Shadow Ball",    248: "Future Sight",     249: "Rock Smash",
    250: "Whirlpool",      251: "Beat Up",          252: "Fake Out",
    253: "Uproar",         254: "Stockpile",        255: "Spit Up",
    256: "Swallow",        257: "Heat Wave",        258: "Hail",
    259: "Torment",        260: "Flatter",          261: "Will-O-Wisp",
    262: "Memento",        263: "Facade",           264: "Focus Punch",
    265: "Smelling Salts", 266: "Follow Me",        267: "Nature Power",
    268: "Charge",         269: "Taunt",            270: "Helping Hand",
    271: "Trick",          272: "Role Play",        273: "Wish",
    274: "Assist",         275: "Ingrain",          276: "Superpower",
    277: "Magic Coat",     278: "Recycle",          279: "Revenge",
    280: "Brick Break",    281: "Yawn",             282: "Knock Off",
    283: "Endeavor",       284: "Eruption",         285: "Skill Swap",
    286: "Imprison",       287: "Refresh",          288: "Grudge",
    289: "Snatch",         290: "Secret Power",     291: "Dive",
    292: "Arm Thrust",     293: "Camouflage",       294: "Tail Glow",
    295: "Luster Purge",   296: "Mist Ball",        297: "Feather Dance",
    298: "Teeter Dance",   299: "Blaze Kick",       300: "Mud Sport",
    301: "Ice Ball",       302: "Needle Arm",       303: "Slack Off",
    304: "Hyper Voice",    305: "Poison Fang",      306: "Crush Claw",
    307: "Blast Burn",     308: "Hydro Cannon",     309: "Meteor Mash",
    310: "Astonish",       311: "Weather Ball",     312: "Aromatherapy",
    313: "Fake Tears",     314: "Air Cutter",       315: "Overheat",
    316: "Odor Sleuth",    317: "Rock Tomb",        318: "Silver Wind",
    319: "Metal Sound",    320: "Grass Whistle",    321: "Tickle",
    322: "Cosmic Power",   323: "Water Spout",      324: "Signal Beam",
    325: "Shadow Punch",   326: "Extrasensory",     327: "Sky Uppercut",
    328: "Sand Tomb",      329: "Sheer Cold",       330: "Muddy Water",
    331: "Bullet Seed",    332: "Aerial Ace",       333: "Icicle Spear",
    334: "Iron Defense",   335: "Block",            336: "Howl",
    337: "Dragon Claw",    338: "Frenzy Plant",     339: "Bulk Up",
    340: "Bounce",         341: "Mud Shot",         342: "Poison Tail",
    343: "Covet",          344: "Volt Tackle",      345: "Magical Leaf",
    346: "Water Sport",    347: "Calm Mind",        348: "Leaf Blade",
    349: "Dragon Dance",   350: "Rock Blast",       351: "Shock Wave",
    352: "Water Pulse",    353: "Doom Desire",      354: "Psycho Boost",
}

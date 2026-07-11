class Addr:
    # Party — read with /core/readrange
    # Note: PARTY_DATA confirmed at 0x02024284 by live decryption (Bulbasaur L6, Tackle+Growl).
    # There is no reliable separate party-count address; use level>0 at slot offset 0x54 instead.
    PARTY_DATA   = 0x02024284   # gPlayerParty: 600 bytes, 6 × 100-byte structs
    # gEnemyParty — same struct as gPlayerParty, 600 bytes immediately before it.
    # Fixed global (NOT DMA-relocated). slot 0 = the wild mon / trainer's active
    # lead. Verified live: (0x02024284 - 600) decodes to the wild encounter.
    ENEMY_PARTY  = 0x0202402C
    # gMoveSelectionCursor[gActiveBattler] — the FIGHT move-selection slot (0-3,
    # 2×2 grid: bit0=column, bit1=row). On A the game commits THIS value as the
    # chosen move (per pokefirered HandleInputChooseMove), so use_move writes the
    # target slot here then presses A. Verified live: writing it + an A edge, then
    # letting the turn resolve, drops exactly that move's PP. Single-battle scope
    # (player = battler 0). NOTE: the display var 4 bytes earlier (0x02023FF8) is
    # NOT the one A reads — must use this address.
    MOVE_CURSOR  = 0x02023FFC
    # gActionSelectionCursor[0] — the FIGHT/BAG/POKEMON/RUN action menu cursor,
    # the u8 array adjacent to the move cursor (this is the "red herring" seen
    # during use_move RE — it's the ACTION cursor, not the move one). Indices:
    # 0=FIGHT 1=BAG 2=POKEMON 3=RUN. flee_battle writes 3 then presses A.
    ACTION_CURSOR = 0x02023FF8
    ACTION_RUN    = 3
    # gBattlerControllerFuncs[0] — player battler's controller callback. Equals
    # CTRL_CHOOSE_MOVE while the FIGHT move menu is open, CTRL_CHOOSE_ACTION while
    # the FIGHT/BAG/POKEMON/RUN action menu is open (both live-verified).
    BATTLE_CTRL_FUNC   = 0x03004FE0
    CTRL_CHOOSE_MOVE   = 0x0802EA11   # HandleInputChooseMove — move menu is up
    CTRL_CHOOSE_ACTION = 0x08030611   # HandleInputChooseAction — action menu is up

    # Progress. Badges live in gSaveBlock1, which the game DMA-RELOCATES on every
    # map transition (verified live: base 0x202554c indoors → 0x20255a8 outdoors).
    # So the badge byte must be read via the live pointer (deref SAVEBLOCK1_PTR +
    # BADGES_OFFSET), NOT a fixed address — a fixed read drifts off the byte after
    # a warp and returns a neighbouring byte, which caused phantom badges.
    #
    # BADGES_OFFSET derivation (pokefirered global.h + constants/flags.h): badges
    # are SYS_FLAGS, stored in SaveBlock1.flags[] at struct offset 0xEE0.
    # FLAG_BADGE01_GET = SYS_FLAGS(0x800)+0x20 = 0x820, so the badge byte is
    # flags[0x820>>3] = 0xEE0 + 0x104 = 0xFE4, bit0=Boulder..bit7=Earth. (The old
    # 0x41C was wrong — it landed in the bag-items region, so read_badges returned
    # bag data and NO run ever registered a badge. Cross-checked: key items at
    # +0x3B8 matches this same struct base, confirming the offset frame.)
    BADGES       = 0x02026530   # canonical base(0x202554c)+0xFE4; reference only (do not read live)
    BADGES_OFFSET = 0xFE4       # + [SAVEBLOCK1_PTR] → badge bitmask (relocation-safe)
    # Bit order: bit 0=Brock, 1=Misty, 2=Surge, 3=Erika,
    #            4=Koga, 5=Sabrina, 6=Blaine, 7=Giovanni

    # Context detection — verified live via in-process libmgba (fix/detect-context).
    #
    #   gMain.callback2 (0x030030F4) u32 — the game's live "current screen"
    #   dispatcher, and the authoritative context gate:
    #     == CB2_OVERWORLD (0x080565B5) while the field system runs (free-roam,
    #        on-map dialog/scripts, field fades). Returns to this value when a
    #        battle ends — unlike the old flags, which persist after battle.
    #     == CB2_BATTLE    (0x08011101) for essentially the whole battle.
    #   SCREEN_FADE (0x03000F9C) u8: 1 while a menu is on screen OR during a fade;
    #     0 in plain free-roam. This is the reliable "something is over the field
    #     right now" signal — crucially it returns to 0 the instant a menu closes.
    #   MENU_OPEN   (0x03002415) u8: set when a field menu is/was open. It
    #     OVER-STAYS: after a full-screen menu (Pokédex/Bag/…) closes it can read 1
    #     back on the field. So it must never be used alone (that trapped the agent
    #     in a phantom IN_MENU) — pair it with SCREEN_FADE, which does clear.
    #   SCRIPT_RAM  (0x03000EB0): script-engine block; byte[0] != 0 while a map
    #     script runs (NPC dialog, signs, cutscenes), 0 in free-roam.
    #
    # detect_context():
    #   callback2 == CB2_BATTLE                        -> IN_BATTLE
    #   callback2 == CB2_OVERWORLD:                    (field: overlay menu/fade/dialog/roam)
    #       MENU_OPEN and SCREEN_FADE                  -> IN_MENU (Start/Save overlay)
    #       SCREEN_FADE                                -> TRANSITIONING (warp/map fade)
    #       SCRIPT_RAM[0] != 0                         -> DIALOG_OPEN
    #       else                                       -> OVERWORLD (stale MENU_OPEN lands here)
    #   otherwise:                                     (full-screen menu / warp / intro)
    #       MENU_OPEN                                  -> IN_MENU (Pokédex/Party/Bag/Option/…)
    #       else                                       -> TRANSITIONING
    #
    # ROM-version note: the CB2_* target addresses are specific to this LeafGreen
    # build (as are all addresses here); re-derive if OVERWORLD is misdetected.
    GMAIN_CALLBACK2 = 0x030030F4   # u32: gMain.callback2 — live screen dispatcher
    CB2_OVERWORLD   = 0x080565B5   # callback2 value while the field system is active
    CB2_BATTLE      = 0x08011101   # callback2 value during battle
    SCREEN_FADE     = 0x03000F9C   # u8: 1 while a menu is on screen OR mid-fade; clears when the menu closes
    SCRIPT_RAM      = 0x03000EB0   # script-engine block; byte[0] != 0 = map script running
    # Field-menu flag. Non-zero for EVERY field menu (Start, Bag, Party, Trainer
    # Card, Option, Save, Pokédex, …). BUT it OVER-STAYS: after a full-screen menu
    # closes it can still read 1 back on the field, so it is NOT a standalone gate
    # — detect_context() pairs it with SCREEN_FADE (which does clear) to avoid a
    # phantom IN_MENU. Never under-reports (always 1 while a menu is truly open).
    MENU_OPEN       = 0x03002415

    # gBattleTypeFlags (real one) — set at battle init, persists after. Verified
    # live: wild = 0x04 (IS_MASTER), trainer = 0x0C (IS_MASTER | TRAINER). Read at
    # battle START to classify the battle. Bit values per pokefirered.
    BATTLE_TYPE_FLAGS   = 0x02022B4C
    BATTLE_TYPE_TRAINER = 0x08   # gBattleTypeFlags & this != 0 → a trainer battle

    # Bag key-items pocket, inside gSaveBlock1 (deref SAVEBLOCK1_PTR — the block
    # is DMA-relocated, so always re-read the pointer). 30 slots × 4 bytes
    # (u16 item id + u16 encrypted qty); item IDs are cleartext, id 0 = empty.
    # Verified live: receiving the Town Map (id 361) filled a new slot here.
    SAVEBLOCK1_PTR   = 0x03005008
    KEY_ITEMS_OFFSET = 0x03B8
    KEY_ITEMS_SLOTS  = 30

    # Money + consumable bag pockets, inside gSaveBlock1 (deref SAVEBLOCK1_PTR).
    # FRLG XOR-obfuscates money and item QUANTITIES with gSaveBlock2->encryptionKey
    # (money ^ key32; quantity ^ (key & 0xFFFF)); item IDs are cleartext, id 0 =
    # empty. gSaveBlock2Ptr is the pointer right after gSaveBlock1Ptr. All offsets
    # and the pointer derived + verified live (money=$3080, 5 Poké Balls) against
    # the pokefirered global.h struct.
    SAVEBLOCK2_PTR       = 0x0300500C   # deref → gSaveBlock2
    ENCRYPTION_KEY_OFFSET = 0xF20       # + [SAVEBLOCK2_PTR] → u32 XOR key
    MONEY_OFFSET         = 0x290        # + [SAVEBLOCK1_PTR] → u32 money ^ key
    ITEMS_OFFSET         = 0x310        # Items pocket (42 slots × 4 bytes)
    ITEMS_SLOTS          = 42
    BALLS_OFFSET         = 0x430        # Poké Balls pocket (13 slots × 4 bytes)
    BALLS_SLOTS          = 13

    # Poké Mart buy menu — sShopData (static in shop.c). Derived + verified live at
    # the Viridian Mart (itemList=[4,13,14,18], itemCount=4). Fields (struct ShopData):
    #   +0x04 const u16* itemList   (ROM ptr to the mart's item ids)
    #   +0x08 u32 itemPrice         (unit price × current quantity in the qty selector)
    #   +0x0C u16 selectedRow       (highlighted row within the visible window)
    #   +0x0E u16 scrollOffset      (list scroll; highlighted index = scroll + row)
    #   +0x10 u16 itemCount         (number of items the mart sells)
    #   +0x14 u16 maxQuantity       (most you can afford of the selected item)
    SHOP_DATA          = 0x02039934
    SHOP_ITEMLIST      = 0x04
    SHOP_ITEMPRICE     = 0x08
    SHOP_SELROW        = 0x0C
    SHOP_SCROLL        = 0x0E
    SHOP_ITEMCOUNT     = 0x10
    SHOP_MAXQTY        = 0x14

    # In-battle Bag menu — gBagMenuState (static struct BagStruct in item_menu.c).
    # Derived + verified live (bagOpen=1, pocket flips on Right). The battle bag is
    # opened from the action menu by selecting BAG (action cursor = 1) with the same
    # write-cursor+A method as flee_battle; it hands off across a controller handshake,
    # so cb2 leaves CB2_BATTLE (→ IN_MENU) once it's up. Fields (struct BagStruct):
    #   +0x04 u8 location   (5 = ITEMMENULOCATION_BATTLE)
    #   +0x05 u8 bagOpen
    #   +0x06 u16 pocket    (0=Items, 1=Key Items, 2=Poké Balls)
    #   +0x0E u16 cursorPos[3]
    BAG_MENU_STATE     = 0x0203ACFC
    BAG_LOCATION_OFF   = 0x04
    BAG_POCKET_OFF     = 0x06
    BAG_POCKET_BALLS   = 2
    ACTION_BAG         = 1     # gActionSelectionCursor value for BAG

    # DEPRECATED — empirically WRONG for context detection; kept only for the
    # legacy diagnostic tool. OVERWORLD_FLAG reads 0 during free-roam overworld
    # (its logic was inverted); BATTLE_FLAGS is transient during a battle and
    # stale afterward. Do not use these in detect_context.
    OVERWORLD_FLAG = 0x0202287C
    BATTLE_FLAGS   = 0x02022880

    # Map header — DataCrystal: "Current Map Header 0x02036DFC"
    # The struct MapHeader sits directly at this address (not a pointer to it).
    # First 4 bytes are the mapLayout ROM pointer (0x08xxxxxx).
    MAP_HEADER   = 0x02036DFC   # struct MapHeader in EWRAM

    # ⚠ These absolute addresses are the PARENT OUTDOOR map, NOT the current map:
    # they stay on the town (e.g. Pallet 3/0) the whole time you are inside its
    # buildings, so they misreport every interior. Verified live: reads 3/0 in
    # both the player's bedroom and Pallet Town. Kept only for diagnostics — the
    # current map comes from the DMA block below (read_current_map). Do not use
    # these for context/navigation.
    MAP_BANK     = 0x02031DBC   # u8: parent outdoor map bank (stale for interiors)
    MAP_ID       = 0x02031DBD   # u8: parent outdoor map id  (stale for interiors)

    # Live player tile coordinates AND current map — always indirect; the target
    # block is DMA-protected and its address changes on every map transition.
    # DataCrystal RAM map, relative to [PLAYER_PTR]:
    #   +0x000 = Camera X (2b) = player tile X
    #   +0x002 = Camera Y (2b) = player tile Y
    #   +0x004 = current map GROUP (1b)  — matches the first key in MAP_NAMES
    #   +0x005 = current map NUM   (1b)  — matches the second key in MAP_NAMES
    # read_player_pos(): ptr=read32(PLAYER_PTR); x=read16(ptr); y=read16(ptr+2).
    # read_current_map(): (read8(ptr+0x04), read8(ptr+0x05)) — the TRUE current
    # map, e.g. (3,0) Pallet Town outdoors vs (4,2) the player's house indoors.
    # DO NOT cache or store the resolved address — it drifts.
    PLAYER_PTR       = 0x03005008   # IRAM → DMA-protected map data block
    MAP_GROUP_OFFSET = 0x04         # + [PLAYER_PTR] → current map group (bank)
    MAP_NUM_OFFSET   = 0x05         # + [PLAYER_PTR] → current map number (id)

    # Player sprite object (overworld, 36 bytes). Player is always OW slot 0.
    # Offsets within OW struct (from pokefirered decomp / DataCrystal):
    #   +0x1C, +0x20 = sub-tile pixel offsets (not tile coords — do not use for navigation)
    OW_PLAYER    = 0x02036E38   # struct OW[0], 36 bytes

    # (Removed an incorrect note claiming 0x0202402C is gFrameCount. Verified live:
    # u32@0x0202402C is STABLE across frames during battle (a frame counter would
    # increment) and decodes to the on-screen wild/lead Pokémon — it IS gEnemyParty
    # (see ENEMY_PARTY above). read_enemy_lead uses it and IDs opponents correctly.)

    # Object events (NPCs) currently loaded: gObjectEvents[16], 36-byte stride,
    # base = OW_PLAYER (slot 0 is the player). Used to route walk_to around NPCs.
    #   +0x00 bit0 = active;  +0x01 bit5 = invisible;  +0x02 bit0 = isPlayer
    #   +0x10 s16 currentCoords.x, +0x12 s16 currentCoords.y  (grid coord + 7)
    # Only on-screen NPCs are loaded here (far ones aren't).
    OBJECT_EVENTS       = 0x02036E38
    OBJECT_EVENT_STRIDE = 0x24
    OBJECT_EVENT_COUNT  = 16
    OBJECT_COORD_OFFSET = 7


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

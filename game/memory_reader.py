from game.mgba_client import MGBAClient
from game.state import GameState, PokemonStatus, StateDiff, GameContext
from game.constants import Addr, SPECIES_NAMES, MOVE_NAMES

# ── Gen III XOR Decryption (Tier 2) ─────────────────────────────────────────

SUBSTRUCT_ORDER = [
    "GAEM", "GAME", "GEAM", "GEMA", "GMAE", "GMEA",
    "AGEM", "AGME", "AEGM", "AEMG", "AMGE", "AMEG",
    "EGAM", "EGMA", "EAGM", "EAMG", "EMGA", "EMAG",
    "MGAE", "MGEA", "MAGE", "MAEG", "MEGA", "MEAG",
]


def decrypt_substructs(raw_100: bytes) -> dict[str, bytes]:
    pid   = int.from_bytes(raw_100[0:4], "little")
    ot_id = int.from_bytes(raw_100[4:8], "little")
    key   = pid ^ ot_id
    enc   = bytearray(raw_100[32:80])
    for i in range(0, 48, 4):
        word = int.from_bytes(enc[i:i+4], "little") ^ key
        enc[i:i+4] = word.to_bytes(4, "little")
    order = SUBSTRUCT_ORDER[pid % 24]
    return {letter: bytes(enc[i * 12:(i + 1) * 12]) for i, letter in enumerate(order)}


def parse_species(sub: dict) -> int:
    return int.from_bytes(sub["G"][0:2], "little")


def parse_moves(sub: dict) -> tuple[list[int], list[int]]:
    a = sub["A"]
    return [int.from_bytes(a[i*2:(i+1)*2], "little") for i in range(4)], [a[8+i] for i in range(4)]


def decode_status(word: int) -> str:
    if word == 0: return "healthy"
    sleep = word & 0b111
    if sleep: return f"asleep ({sleep} turns)"
    if word & (1 << 3): return "poisoned"
    if word & (1 << 4): return "burned"
    if word & (1 << 5): return "frozen"
    if word & (1 << 6): return "paralyzed"
    if word & (1 << 7): return "badly_poisoned"
    return "unknown"


# ── Main reader class ────────────────────────────────────────────────────────

class LeafGreenReader:
    def __init__(self, client: MGBAClient, decrypt: bool = True):
        self.client  = client
        self.decrypt = decrypt

    def read_badges(self) -> tuple[int, int]:
        """Returns (badge_count, raw_bitmask).
        badge_count = popcount of the u8 bitmask (0–8).
        raw_bitmask = the u8 itself — use for bitwise diff to detect which bit flipped."""
        raw = self.client.read8(Addr.BADGES)
        return bin(raw).count("1"), raw

    def detect_context(self) -> GameContext:
        # gMain.callback2 is the game's live "current screen" dispatcher and the
        # authoritative gate (verified live via libmgba). The old OVERWORLD_FLAG /
        # BATTLE_FLAGS addresses were wrong: OVERWORLD_FLAG reads 0 during
        # free-roam (inverted), and BATTLE_FLAGS is transient/persists. See the
        # constants.py notes for the full signal table.
        cb2 = self.client.read32(Addr.GMAIN_CALLBACK2)
        if cb2 == Addr.CB2_BATTLE:
            return GameContext.IN_BATTLE
        if cb2 == Addr.CB2_OVERWORLD:
            # Start menu overlay: its callback is a ROM pointer while open.
            # Check before SCREEN_FADE, which is ALSO 1 the whole time the Start
            # menu is open (verified live) — otherwise the menu would be
            # misclassified as TRANSITIONING and could get spurious auto-A taps.
            if 0x08000000 <= self.client.read32(Addr.START_MENU_CB) <= 0x08FFFFFF:
                return GameContext.IN_MENU
            if self.client.read8(Addr.SCREEN_FADE) == 0x01:
                return GameContext.TRANSITIONING
            # SCRIPT_RAM[0] != 0 while a map script runs (NPC dialog, signs, ...).
            if self.client.read8(Addr.SCRIPT_RAM) != 0:
                return GameContext.DIALOG_OPEN
            return GameContext.OVERWORLD
        # Menus, map warps/loads, battle intro/outro, and other screens.
        return GameContext.TRANSITIONING

    def read_party(self) -> list[PokemonStatus]:
        party = []
        for slot in range(6):
            raw = self.client.read_range(Addr.PARTY_DATA + slot * 100, 100)
            if len(raw) < 100:
                continue
            # Empty slots have level 0 — skip them (no separate party-count address)
            if raw[0x54] == 0:
                continue

            # Unencrypted fields — always readable (offsets within party struct)
            status_word = int.from_bytes(raw[0x50:0x54], "little")
            level       = raw[0x54]
            current_hp  = int.from_bytes(raw[0x56:0x58], "little")
            max_hp      = int.from_bytes(raw[0x58:0x5A], "little")

            species_id, species_name = 0, "Unknown"
            move_ids   = [0] * 4
            move_names = [""] * 4
            pp         = [0] * 4

            if self.decrypt:
                try:
                    sub = decrypt_substructs(raw)
                    species_id   = parse_species(sub)
                    species_name = SPECIES_NAMES.get(species_id, f"#{species_id}")
                    move_ids, pp = parse_moves(sub)
                    move_names   = [MOVE_NAMES.get(m, f"move_{m}") if m else "" for m in move_ids]
                except Exception:
                    pass  # decryption failed — Tier 1 data still valid

            party.append(PokemonStatus(
                slot=slot,
                level=level,
                current_hp=current_hp,
                max_hp=max_hp,
                status=decode_status(status_word),
                species_id=species_id,
                species_name=species_name,
                move_ids=move_ids,
                move_names=move_names,
                pp=pp,
            ))
        return party

    def read_player_pos(self) -> tuple[int, int]:
        """
        Read live player tile coordinates via the DMA-protected map block.
        DataCrystal: [0x03005008]+0x000 = Camera X (= player tile X),
                     [0x03005008]+0x002 = Camera Y (= player tile Y).
        The block address changes on every map transition — always deref
        PLAYER_PTR rather than caching the resolved address.
        """
        ptr = self.client.read32(Addr.PLAYER_PTR)
        return self.client.read16(ptr), self.client.read16(ptr + 2)

    def read_state(self) -> GameState:
        context = self.detect_context()
        party   = self.read_party()
        px, py  = self.read_player_pos()
        badge_count, badge_bits = self.read_badges()
        return GameState(
            context=context,
            badges=badge_count,
            badge_bits=badge_bits,
            party=party,
            party_count=len(party),
            map_bank=self.client.read8(Addr.MAP_BANK),
            map_id=self.client.read8(Addr.MAP_ID),
            player_x=px,
            player_y=py,
            screen_fading=(context == GameContext.TRANSITIONING),
        )

    def diff(self, before: GameState | None, after: GameState) -> StateDiff:
        d = StateDiff()
        if before is None:
            return d
        d.badges_changed     = before.badges != after.badges
        d.party_size_changed = before.party_count != after.party_count
        d.battle_started     = (before.context != GameContext.IN_BATTLE and
                                after.context  == GameContext.IN_BATTLE)
        d.battle_ended       = (before.context == GameContext.IN_BATTLE and
                                after.context  != GameContext.IN_BATTLE)
        d.context_changed    = before.context != after.context

        for i in range(min(len(before.party), len(after.party))):
            b, a = before.party[i], after.party[i]
            if b.current_hp != a.current_hp:
                d.hp_changed.append(i)
                if a.current_hp < b.current_hp:
                    d.notes.append(f"Slot {i} took damage: {b.current_hp}→{a.current_hp} HP")
                else:
                    d.notes.append(f"Slot {i} healed: {b.current_hp}→{a.current_hp} HP")
            if b.level != a.level:
                d.level_changed.append(i)
                d.notes.append(f"Slot {i} leveled up: {b.level}→{a.level}")
            if b.move_ids != a.move_ids:
                d.moves_changed.append(i)
                d.notes.append(f"Slot {i} learned a new move")
        if d.badges_changed:
            d.notes.append(f"Badge count: {before.badges}→{after.badges}")
        return d

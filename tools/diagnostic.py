"""Phase 11 Smoke Test.

Verifies each subsystem against live game memory.
No LLM, no loop. Run before main.py to confirm the stack is healthy.
"""
import sys
import os

# Allow importing project modules from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rich.console import Console
from rich.table import Table
from rich import box

from game.mgba_client import MGBAClient
from game.memory_reader import LeafGreenReader
from game.constants import Addr, SPECIES_NAMES, MOVE_NAMES

console = Console()


def check(label: str, passed: bool, detail: str = "") -> bool:
    status = "[green]PASS[/]" if passed else "[red]FAIL[/]"
    line   = f"  {status}  {label}"
    if detail:
        line += f"  [dim]{detail}[/]"
    console.print(line)
    return passed


def section(title: str):
    console.print(f"\n[bold cyan]-- {title} --[/]")


def run():
    console.rule("[bold green]Pokemon LeafGreen Agent - Diagnostic")

    mgba   = MGBAClient()
    reader = LeafGreenReader(mgba, decrypt=True)

    all_ok = True

    # ── 1. Connection ────────────────────────────────────────────────────────
    section("1. mGBA-http Connection")
    try:
        title = mgba.get_game_title()
        code  = mgba.get_game_code()
        ok    = "BPGE" in code
        all_ok &= check("Game code", ok, f"{title!r} / {code!r}")
        if not ok:
            console.print("[red]    Wrong ROM or emulator not running. Aborting.[/]")
            return
    except Exception as e:
        check("Game code", False, str(e))
        console.print("[red]    Cannot reach mGBA-http. Is the binary running?[/]")
        return

    # ── 2. IRAM reads ────────────────────────────────────────────────────────
    section("2. IRAM Reads")
    try:
        fade = mgba.read8(Addr.SCREEN_FADE)
        check("Screen-fade register (0x03000F9C)", True, f"value={fade} ({'fading' if fade == 1 else 'normal'})")
    except Exception as e:
        all_ok &= check("Screen-fade register", False, str(e))

    # Script RAM - 74 bytes starting at 0x03000EB0
    try:
        script_raw = mgba.read_range(Addr.SCRIPT_RAM, 74)
        first_byte = script_raw[0] if script_raw else 0xFF
        nonzero    = sum(1 for b in script_raw if b)
        check(
            "Script RAM (0x03000EB0, 74 B)",
            len(script_raw) == 74,
            f"first_byte=0x{first_byte:02X}  nonzero_count={nonzero}",
        )
        console.print(f"    [dim]hex: {' '.join(f'{b:02x}' for b in script_raw[:20])}...[/]")
    except Exception as e:
        all_ok &= check("Script RAM", False, str(e))

    # ── 3. Battle flag ───────────────────────────────────────────────────────
    section("3. Battle / Context Flags")
    try:
        battle = mgba.read32(Addr.BATTLE_FLAGS)
        check(f"Battle flag ({hex(Addr.BATTLE_FLAGS)})", True,
              f"value=0x{battle:08X}  (address reliability: see section 8)")
    except Exception as e:
        all_ok &= check("Battle flag", False, str(e))

    try:
        ctx = reader.detect_context()
        check("detect_context()", True, f"{ctx.name}")
    except Exception as e:
        all_ok &= check("detect_context()", False, str(e))

    # ── 4. Badges ────────────────────────────────────────────────────────────
    section("4. Badges")
    try:
        raw_badges = mgba.read8(Addr.BADGES)
        badges     = bin(raw_badges).count("1")
        check("Badge bitmask (0x02025968)", True, f"raw=0b{raw_badges:08b}  badges={badges}/8")
    except Exception as e:
        all_ok &= check("Badge bitmask", False, str(e))

    # ── 5. Map / Position ────────────────────────────────────────────────────
    section("5. Map & Player Position")
    try:
        bank = mgba.read8(Addr.MAP_BANK)
        mid  = mgba.read8(Addr.MAP_ID)
        px   = mgba.read16(Addr.PLAYER_X)
        py   = mgba.read16(Addr.PLAYER_Y)
        check("Map reads", True, f"bank={bank}  map={mid}  x={px}  y={py}")
    except Exception as e:
        all_ok &= check("Map reads", False, str(e))

    # ── 6. Party ─────────────────────────────────────────────────────────────
    section("6. Party (Tier 1 + Tier 2 Decryption)")
    try:
        party = reader.read_party()
        if not party:
            check("Party count", True, "0 Pokémon in party (title screen or empty save)")
        else:
            check("Party count", True, f"{len(party)} Pokémon")
            t = Table(box=box.SIMPLE, show_header=True, header_style="bold")
            t.add_column("Slot", justify="right")
            t.add_column("Species")
            t.add_column("Lv")
            t.add_column("HP")
            t.add_column("Status")
            t.add_column("Moves")
            for p in party:
                moves_str = ", ".join(m for m in p.move_names if m) or "(none)"
                t.add_row(
                    str(p.slot),
                    f"{p.species_name} (#{p.species_id})",
                    str(p.level),
                    f"{p.current_hp}/{p.max_hp}",
                    p.status,
                    moves_str,
                )
            console.print(t)

            # Sanity checks on first slot
            lead = party[0]
            all_ok &= check("Lead species_id > 0", lead.species_id > 0, f"species_id={lead.species_id}")
            all_ok &= check("Lead level > 0", lead.level > 0, f"level={lead.level}")
            all_ok &= check("Lead max_hp > 0", lead.max_hp > 0, f"max_hp={lead.max_hp}")
    except Exception as e:
        all_ok &= check("Party read", False, str(e))

    # ── 7. Raw party slot bytes (for debugging decryption) ───────────────────
    section("7. Raw Slot 0 (first 32 bytes - unencrypted header)")
    try:
        raw = mgba.read_range(Addr.PARTY_DATA, 32)
        if len(raw) >= 4:
            pid   = int.from_bytes(raw[0:4], "little")
            ot_id = int.from_bytes(raw[4:8], "little") if len(raw) >= 8 else 0
            check("Slot 0 header read", True,
                  f"PID=0x{pid:08X}  OT_ID=0x{ot_id:08X}  key=0x{pid^ot_id:08X}")
            console.print(f"    [dim]raw[0:32]: {' '.join(f'{b:02x}' for b in raw)}[/]")
        else:
            check("Slot 0 header read", False, f"only {len(raw)} bytes returned")
    except Exception as e:
        all_ok &= check("Slot 0 raw read", False, str(e))

    # ── 8. Battle address candidates ─────────────────────────────────────────
    # Run this on the OVERWORLD and note the values. Then enter a battle and
    # run again. Any address that is 0 on overworld and non-zero in battle
    # (or consistently different) is the correct BATTLE_FLAGS to use.
    section("8. Battle Address Candidates (run on overworld AND in battle to compare)")
    candidates = [
        ("0x02022878", 0x02022878),
        ("0x0202287C", 0x0202287C),
        ("0x02022880", 0x02022880),   # current (unreliable)
        ("0x02022884", 0x02022884),
        ("0x02022B3C", 0x02022B3C),
        ("0x02022B40", 0x02022B40),   # possible gBattleMainFunc
        ("0x02022B44", 0x02022B44),
        ("0x02022B48", 0x02022B48),
        ("0x02022B4C", 0x02022B4C),   # gBattleTypeFlags (known to persist)
        ("0x02022B50", 0x02022B50),
        ("0x02022B54", 0x02022B54),
        ("0x020244EC", 0x020244EC),
        ("0x020244F0", 0x020244F0),
        ("0x030022C0", 0x030022C0),   # gMain.callback1 (IWRAM)
        ("0x030022C4", 0x030022C4),   # gMain.callback2 (IWRAM)
    ]
    for label, addr in candidates:
        try:
            val = mgba.read32(addr)
            console.print(f"    {label}  =  0x{val:08X}  ({val})")
        except Exception as e:
            console.print(f"    {label}  ERROR: {e}")

    # ── 9. Lookup table coverage ─────────────────────────────────────────────
    section("9. Lookup Table Coverage")
    console.print(f"    SPECIES_NAMES: {len(SPECIES_NAMES)} entries")
    console.print(f"    MOVE_NAMES:    {len(MOVE_NAMES)} entries")
    check("Species table >= 151", len(SPECIES_NAMES) >= 151, f"{len(SPECIES_NAMES)} entries")
    check("Move table >= 100", len(MOVE_NAMES) >= 100, f"{len(MOVE_NAMES)} entries")

    # ── Summary ──────────────────────────────────────────────────────────────
    console.print()
    if all_ok:
        console.rule("[bold green]All critical checks passed - ready for main.py")
    else:
        console.rule("[bold red]Some checks FAILED - see above before running main.py")


if __name__ == "__main__":
    run()

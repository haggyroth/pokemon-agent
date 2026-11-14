"""Story quests that gate progress and need a fixed interaction script.

get_cut(): the S.S. Anne's Captain gives HM01 Cut. Vermilion's harbor lets you aboard with the SS Ticket;
the Captain's Office is on 2F (graph route Vermilion → Exterior → 1F → 2F → office). Talk to him (he is
seasick; the game rubs his back for you), take HM01 (flag 0x237), then teach_move('HM01'). Cut trees
that block the way (the Vermilion Gym door) are then cleared by go_to itself (see nav._go_to).

get_ss_ticket(): Bill's Sea Cottage (Route 25). Until FLAG_GOT_SS_TICKET is set, Cerulean's south exit is
blocked by a Slowbro + Lass and its east exit by a policeman (decomp `CeruleanCity_EventScript_BlockExits`),
so nothing past Cerulean — Vermilion, Cut, Surge — is reachable. The script, from the decomp scripts
(Route25_SeaCottage/scripts.inc) and verified live:
  1. talk to Bill-as-Clefairy (YES) → he walks into the left teleporter;
  2. use the computer (stand below it, face up, A) → the cell-separation cutscene → human Bill appears;
  3. talk to human Bill → SS Ticket (key item 265, flag 0x234).
"""
from game.state import GameContext

SS_TICKET_ITEM = 265
FLAG_GOT_SS_TICKET = 0x234
BILL_GFX, CLEFAIRY_GFX = 73, 113          # OBJ_EVENT_GFX_BILL / OBJ_EVENT_GFX_CLEFAIRY
COTTAGE = (30, 0)
FLAG_GOT_HM01 = 0x237
FLAG_VERMILION_SWITCHES = 0x264           # FLAG_FOUND_BOTH_VERMILION_GYM_SWITCHES
VERMILION_GYM = (9, 6)
CUT_MOVE_ID = 15
CAPTAIN_OFFICE = (1, 11)
CAPTAIN_SPOT = ((5, 5), "Up")             # the Captain stands at (5,4)
CLEFAIRY_SPOT = ((10, 7), "Up")           # Clefairy-Bill starts at (10,6)
COMPUTER_SPOT = ((4, 6), "Up")            # the computer is the sign at (4,5)


def trash_can_tile(can: int) -> tuple[int, int]:
    """(x, y) of Vermilion Gym trash can `can` (1..15): a 5x3 grid, ids left→right then top→bottom."""
    i = can - 1
    return 1 + 2 * (i % 5), 10 + 2 * (i // 5)


class QuestMixin:
    def _has_ss_ticket(self) -> bool:
        return (SS_TICKET_ITEM in self.reader.read_key_items()
                or bool(self.reader.read_flag(FLAG_GOT_SS_TICKET)))

    def _get_ss_ticket(self) -> str:
        if self._has_ss_ticket():
            return "You already have the SS Ticket — Cerulean's exits are open. go_to Vermilion City."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        # 1. Get to the cottage: resumable travel (trainers on Nugget Bridge are auto-fought; stops on a
        # lost fight / low HP with advice), so keep calling it, healing when it asks.
        for _ in range(12):
            if self.reader.read_current_map() == COTTAGE:
                break
            out = self._go_to("Bill's Sea Cottage")
            if self.reader.read_current_map() == COTTAGE:
                break
            if "heal()" in out or "Lost a trainer" in out:
                heal = self._heal()
                if not heal.startswith(("Healed", "Party is already")):
                    return f"Couldn't heal on the way to Bill's cottage ({heal}) — heal(), then get_ss_ticket() again."
                continue
            if "Blocked" in out or "gated" in out:
                return f"Can't reach Bill's Sea Cottage: {out}"
        if self.reader.read_current_map() != COTTAGE:
            return "Didn't reach Bill's Sea Cottage yet — call get_ss_ticket() again to continue (it resumes)."

        # 2. Clefairy-Bill → teleporter. (Skipped on a re-run if he's already gone.)
        if self.reader.read_objects_by_gfx([CLEFAIRY_GFX]) and not self.reader.read_objects_by_gfx([BILL_GFX]):
            if not self._press_on_tile(*CLEFAIRY_SPOT, yesno=True):
                return "Couldn't reach the Clefairy (Bill) in the cottage — walk_to (10,7), face up, press A, answer YES."
        # 3. The computer runs the cell separator; wait for human Bill to appear.
        if not self.reader.read_objects_by_gfx([BILL_GFX]):
            if not self._press_on_tile(*COMPUTER_SPOT):
                return "Couldn't reach Bill's computer at (4,5) — walk_to (4,6), face up, press A."
            for _ in range(30):
                if self.reader.detect_context() == GameContext.OVERWORLD and self.reader.read_objects_by_gfx([BILL_GFX]):
                    break
                self._advance_to_control(tries=30)
        bill = self.reader.read_objects_by_gfx([BILL_GFX])
        if not bill:
            return "Ran Bill's computer but he didn't appear — call get_ss_ticket() again."
        # 4. Talk to Bill (stand below him), take the ticket.
        bx, by = bill[0]
        for stand, face in (((bx, by + 1), "Up"), ((bx - 1, by), "Right"), ((bx + 1, by), "Left")):
            if self._press_on_tile(stand, face):
                break
        for _ in range(12):
            if self._has_ss_ticket():
                break
            self._advance_to_control(tries=30)
        if not self._has_ss_ticket():
            return "Talked to Bill but no ticket yet — call get_ss_ticket() again."
        self._advance_to_control(tries=24)
        return ("Got the SS Ticket from Bill! Cerulean's south and east exits are open now — "
                "go_to Vermilion City (heal first if hurt).")

    # ── HM01 Cut from the S.S. Anne's Captain ──────────────────────────────────
    def _knows_cut(self) -> bool:
        return any(CUT_MOVE_ID in (p.move_ids or []) for p in self.reader.read_party())

    def _get_cut(self) -> str:
        if self._knows_cut():
            return "A Pokémon in your party already knows Cut — use_hm('cut') on a tree, or just go_to."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        if not self.reader.read_flag(FLAG_GOT_HM01):
            if not self._has_ss_ticket():
                return "You need the SS Ticket to board the S.S. Anne — call get_ss_ticket() first."
            for _ in range(14):
                if self.reader.read_current_map() == CAPTAIN_OFFICE:
                    break
                out = self._go_to("S.S. Anne Captain's Office")
                if self.reader.read_current_map() == CAPTAIN_OFFICE:
                    break
                if "heal()" in out or "Lost a trainer" in out:
                    heal = self._heal()
                    if not heal.startswith(("Healed", "Party is already")):
                        return f"Couldn't heal on the way to the S.S. Anne ({heal}) — heal(), then get_cut() again."
                    continue
                if "Can't get to" in out or "No route" in out:
                    return f"Can't reach the S.S. Anne's Captain: {out}"
            if self.reader.read_current_map() != CAPTAIN_OFFICE:
                return "Didn't reach the Captain's Office yet — call get_cut() again to continue (it resumes)."
            if not self._press_on_tile(*CAPTAIN_SPOT):
                return "Couldn't reach the Captain — walk_to (5,5), face up, press A."
            for _ in range(12):
                if self.reader.read_flag(FLAG_GOT_HM01):
                    break
                self._advance_to_control(tries=30)
            if not self.reader.read_flag(FLAG_GOT_HM01):
                return "Talked to the Captain but no HM01 yet — call get_cut() again."
            self._advance_to_control(tries=24)
        out = self._teach_move("HM01", "", "")
        if not self._knows_cut():
            return f"Got HM01 but couldn't teach it: {out} — teach_move('HM01') yourself (pick a Pokémon that can learn Cut)."
        return (f"Got HM01 and {out} Cut trees now clear with use_hm('cut') — and go_to does it for you "
                "when one blocks the way (Vermilion Gym's door).")

    # ── Vermilion Gym: the two electric-lock switches (trash cans) ──────────────────────────────
    def _solve_vermilion_switches(self) -> str:
        """Lt. Surge's gym hides two switches in the 15 trash cans (a 5x3 grid at x=1,3,5,7,9 / y=10,12,14).
        The game rolls them on map load into VAR_TEMP_0 / VAR_TEMP_1 (can ids 1..15, read left→right,
        top→bottom), so instead of guessing we READ them and press exactly those two cans. (A wrong second
        can would reset both locks, so there is no guessing here.)"""
        if self.reader.read_flag(FLAG_VERMILION_SWITCHES):
            return "The electric locks are already open."
        s1, s2 = self.reader.read_var(0x4000), self.reader.read_var(0x4001)
        if not (1 <= s1 <= 15 and 1 <= s2 <= 15):
            return f"Couldn't read the trash-can switches (got {s1}, {s2}) — search the cans by hand (A on each)."
        for can in (s1, s2):
            x, y = trash_can_tile(can)
            if not self._press_on_tile((x, y + 1), "Up"):
                return f"Couldn't reach trash can {can} at ({x},{y}) — walk_to ({x},{y + 1}), face up, press A."
        if not self.reader.read_flag(FLAG_VERMILION_SWITCHES):
            return "Pressed both switch cans but the locks didn't open — try again."
        return "Both electric locks are open — the way to Lt. Surge is clear."

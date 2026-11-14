"""Story quests that gate progress and need a fixed interaction script.

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
CLEFAIRY_SPOT = ((10, 7), "Up")           # Clefairy-Bill starts at (10,6)
COMPUTER_SPOT = ((4, 6), "Up")            # the computer is the sign at (4,5)


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

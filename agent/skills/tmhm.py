"""Teach a TM/HM move to a party Pokémon through the TM Case.

Flow (live-verified): Start -> Bag -> Key Items -> TM CASE -> OPEN -> pick the TM/HM -> USE ->
party screen ("Teach which POKéMON?", ABLE / NOT ABLE) -> pick the Pokémon -> [if it already
knows 4 moves: "Should a move be deleted…?" YES -> summary screen, pick the move to forget -> A].

Every stage reads the live state (callback2, list cursor = scroll + row, party slot, summary
cursor) and is confirmed by the OUTCOME: the move shows up in the party data (and the forgotten
one is gone, and a TM — not an HM — was consumed). Never a blind button count.
"""
from game.constants import Addr
from game.state import GameContext
from knowledge.leafgreen_data import MOVE_POWER
from knowledge.tmhm import HM_MOVE_NAMES, TMHM, pick_forget, resolve_tmhm
from knowledge.tmhm_learnsets import can_learn


class TMHMMixin:

    def _cb2(self) -> int:
        return self.mgba.read32(Addr.GMAIN_CALLBACK2)

    def _open_tm_case(self) -> str | None:
        """Bag -> Key Items -> TM CASE -> OPEN. Returns an error string, or None when the case is up."""
        res = self._menus.open_menu("Bag")
        if "Bag screen open" not in res:
            return f"Couldn't open the Bag ({res})"
        self.mgba.tick(40)
        if not self._bag_pocket_open(Addr.BAG_POCKET_KEYITEMS):
            return "Couldn't reach the Key Items pocket."
        keys = self.reader.read_key_items()
        if not self._bag_cursor_to(keys.index(Addr.TM_CASE_ITEM), pocket=Addr.BAG_POCKET_KEYITEMS):
            return "Couldn't select the TM Case in the Bag."
        for _ in range(8):                          # context menu (OPEN is row 0), then OPEN
            if self._cb2() == Addr.TMCASE_CB2:
                break
            self.mgba.tap("A")
            self.mgba.tick(40)
        if self._cb2() != Addr.TMCASE_CB2:
            return "The TM Case didn't open."
        self.mgba.tick(40)
        return None

    def _tmcase_select(self, iid: int) -> bool:
        order = [i for i, _ in self.reader.read_tmhm_pocket()]
        target = order.index(iid)
        for _ in range(80):
            cur = self.mgba.read8(Addr.TMCASE_ROW) + self.mgba.read8(Addr.TMCASE_SCROLL)
            if cur == target:
                return True
            self.mgba.tap("Down" if cur < target else "Up")
            self.mgba.tick(16)
        return (self.mgba.read8(Addr.TMCASE_ROW) + self.mgba.read8(Addr.TMCASE_SCROLL)) == target

    def _knows(self, slot: int, move_id: int) -> bool:
        p = self.reader.read_party()
        return slot < len(p) and move_id in (p[slot].move_ids or [])

    def _teach_once(self, iid: int, slot: int, forget: str) -> tuple[bool, str]:
        """One attempt on party `slot`. Returns (learned, note)."""
        label, move, move_id = TMHM[iid]
        party = self.reader.read_party()
        who = party[slot].species_name or f"slot {slot + 1}"
        before = list(party[slot].move_names)
        err = self._open_tm_case()
        if err:
            self._menus.close_menus()
            return False, err
        if not self._tmcase_select(iid):
            self._menus.close_menus()
            return False, f"Couldn't select {label} in the TM Case."
        for _ in range(8):                          # context menu: USE is row 0
            if self._cb2() == Addr.CB2_PARTY_MENU:
                break
            self.mgba.tap("A")
            self.mgba.tick(40)
        if self._cb2() != Addr.CB2_PARTY_MENU:
            self._menus.close_menus()
            return False, f"{label} didn't open the party screen."
        self.mgba.tick(50)
        for _ in range(10):
            cur = self.mgba.read8(Addr.PARTY_FIELD_SLOT)
            if cur == slot:
                break
            self.mgba.tap("Down" if cur < slot else "Up")
            self.mgba.tick(14)
        if self.mgba.read8(Addr.PARTY_FIELD_SLOT) != slot:
            self._menus.close_menus()
            return False, "Couldn't move the party cursor to the target."

        # Decide what to forget up front (only used if the moveset is full).
        full = len([m for m in before if m]) >= 4
        forget_idx = None
        if full:
            if forget:
                fl = forget.strip().lower()
                forget_idx = next((i for i, m in enumerate(before) if m and m.lower() == fl), None)
                if forget_idx is None:
                    self._menus.close_menus()
                    return False, f"{who} doesn't know {forget!r} (moves: {', '.join(before)})."
                if before[forget_idx] in HM_MOVE_NAMES:
                    self._menus.close_menus()
                    return False, f"{forget} is an HM move — it can't be forgotten."
            else:
                forget_idx = pick_forget(before, move, MOVE_POWER)

        others_before = {i: list(p.move_names) for i, p in enumerate(party) if i != slot}
        yn_seen = 0
        gave_up = False
        self.mgba.tap("A")                          # choose the Pokémon
        self.mgba.tick(50)
        for _ in range(60):
            if self._knows(slot, move_id):
                break
            now = self.reader.read_party()
            if any(list(now[i].move_names) != mv for i, mv in others_before.items() if i < len(now)):
                break                               # never keep pressing A into a different Pokémon
            cb2 = self._cb2()
            if cb2 == Addr.SUMMARY_CB2:             # pick the move to forget
                if forget_idx is None:
                    self.mgba.tap("B")              # nothing safe to lose: back out
                    self.mgba.tick(40)
                    continue
                self.mgba.tick(30)
                for _ in range(10):
                    cur = self.mgba.read8(Addr.SUMMARY_MOVE_CURSOR)
                    if cur == forget_idx:
                        break
                    self.mgba.tap("Down" if cur < forget_idx else "Up")
                    self.mgba.tick(16)
                if self.mgba.read8(Addr.SUMMARY_MOVE_CURSOR) != forget_idx:
                    return self._abort_teach("Couldn't move the forget-cursor.", False)
                self.mgba.tap("A")
                self.mgba.tick(60)
                continue
            if cb2 == Addr.CB2_PARTY_MENU and self._menus.choice_live():
                yn_seen += 1
                # 1st box "Should a move be deleted…?"; (if we declined) 2nd "Stop learning…?"
                if forget_idx is None and full:
                    self._menus.answer_prompt("no" if yn_seen == 1 else "yes")
                    if yn_seen >= 2:
                        gave_up = True
                        break
                else:
                    self._menus.answer_prompt("yes")
                self.mgba.tick(40)
                continue
            self.mgba.tap("A")                      # advance text
            self.mgba.tick(35)
        learned = self._knows(slot, move_id)
        for _ in range(4):                          # land in real overworld control (a fade can linger)
            self._menus.close_menus()
            self.mgba.tick(30)
            if self.reader.detect_context() == GameContext.OVERWORLD:
                break
            self._advance_to_control(tries=8)
        after = self.reader.read_party()[slot].move_names
        if learned:
            lost = [m for m in before if m and m not in after]
            extra = f", forgetting {lost[0]}" if lost else ""
            return True, f"{who} learned {move}{extra}."
        if gave_up:
            return False, (f"{who} already knows 4 moves and none is safe to forget "
                           f"({', '.join(before)}); pass forget='<move>' to choose.")
        return False, f"{who} couldn't learn {move} (not compatible, or the sequence stalled)."

    def _abort_teach(self, msg: str, learned: bool):
        self._menus.close_menus()
        return learned, msg

    def _teach_move(self, tm: str, pokemon: str = "", forget: str = "") -> str:
        iid = resolve_tmhm(tm)
        if iid is None:
            return f"Don't recognise {tm!r}. Use e.g. 'TM09', 'HM01', 'Cut', 'Giga Drain'."
        label, move, move_id = TMHM[iid]
        if self.reader.detect_context() != GameContext.OVERWORLD:
            return "Teach moves from the overworld (not in a menu/battle)."
        owned = dict(self.reader.read_tmhm_pocket())
        if iid not in owned:
            have = ", ".join(f"{TMHM[i][0]} {TMHM[i][1]}" for i in owned if i in TMHM) or "none"
            return f"You don't have {label} ({move}). TMs/HMs you have: {have}."
        if Addr.TM_CASE_ITEM not in self.reader.read_key_items():
            return "You don't have the TM Case yet."
        party = self.reader.read_party()
        if not party:
            return "No Pokémon to teach."
        knowers = [p.species_name for p in party if move_id in (p.move_ids or [])]
        if knowers and not pokemon:
            return f"{knowers[0]} already knows {move}."
        if pokemon:
            slot = self._resolve_party_target(pokemon, party)
            if slot is None:
                return f"Can't find {pokemon!r} in your party."
            slots = [slot]
        else:
            slots = list(range(len(party)))
        notes = []
        qty0 = owned[iid]
        for slot in slots:
            p = party[slot]
            if self._knows(slot, move_id):
                notes.append(f"{p.species_name} already knows {move}.")
                continue
            if not can_learn(p.species_id, iid):
                notes.append(f"{p.species_name} can't learn {move} ({label} isn't compatible).")
                continue
            moves = [m for m in p.move_names if m]
            if len(moves) >= 4 and not forget and pick_forget(p.move_names, move, MOVE_POWER) is None:
                notes.append(f"{p.species_name} knows 4 moves and none is safe to forget "
                             f"({', '.join(moves)}); pass forget='<move>' to choose one.")
                continue
            ok, note = self._teach_once(iid, slot, forget)
            if ok:
                left = dict(self.reader.read_tmhm_pocket()).get(iid, 0)
                spent = "" if label.startswith("HM") else (f" ({label} used up)" if left < qty0 else "")
                return note + spent
            notes.append(note)
        return " ".join(notes) or f"Couldn't teach {move}."

"""Party management out of battle: swap two party slots / pick the lead through the Start-menu party screen.

In a battle the equivalent is `switch_pokemon` (BattleMixin). Out of battle the game offers SWITCH in a
Pokémon's sub-menu (Start → POKéMON → pick a mon → SWITCH → pick the destination). The sub-menu is
[SUMMARY, <field moves the mon knows>, SWITCH, ITEM, CANCEL], so SWITCH sits at index
1 + (number of field moves), the same layout _party_field_move relies on.
"""
from game.constants import Addr
from game.state import GameContext

from agent.skills.hm import _FIELD_MOVE_IDS


class PartyMixin:
    def _party_sig(self):
        return [(p.species_id, p.level, p.max_hp) for p in self.reader.read_party()]

    def _party_cursor_to(self, slot: int, addr=None) -> bool:
        addr = addr or Addr.PARTY_FIELD_SLOT
        for _ in range(12):
            cur = self.mgba.read8(addr)
            if cur == slot:
                return True
            self.mgba.tap("Down" if cur < slot else "Up")
            self.mgba.tick(14)
        return self.mgba.read8(addr) == slot

    def _reorder_party(self, first: str, second: str) -> str:
        """Swap two party members (1-based slot or species/nickname) via Start → POKéMON → SWITCH.
        Menu inputs are occasionally dropped, so the result is verified against the party order and retried."""
        out = ""
        for _ in range(3):
            out = self._reorder_party_once(first, second)
            if out.startswith(("Swapped", "That's the same", "Couldn't find", "Reorder the party")):
                return out
        return out

    def _reorder_party_once(self, first: str, second: str) -> str:
        if self.reader.detect_context() != GameContext.OVERWORLD:
            return "Reorder the party from the overworld (in a battle use switch_pokemon)."
        party = self.reader.read_party()
        a = self._resolve_party_target(str(first), party)
        b = self._resolve_party_target(str(second), party)
        if a is None or b is None:
            return f"Couldn't find {first!r} / {second!r} in your party: {', '.join(p.species_name for p in party)}."
        if a == b:
            return "That's the same Pokémon — nothing to swap."
        before = self._party_sig()
        res = self._menus.open_menu("Pokemon")
        if "screen open" not in res:
            return f"Couldn't open the party screen ({res})."
        self.mgba.tick(40)
        try:
            if not self._party_cursor_to(a):
                return "Couldn't move the party cursor to the first Pokémon."
            self.mgba.tap("A")
            self.mgba.tick(50)
            idx = 1 + sum(1 for m in (party[a].move_ids or []) if m in _FIELD_MOVE_IDS)
            for _ in range(12):
                cur = self.mgba.read8(Addr.MENU_CURSOR)
                if cur == idx:
                    break
                self.mgba.tap("Down" if cur < idx else "Up")
                self.mgba.tick(14)
            if self.mgba.read8(Addr.MENU_CURSOR) != idx:
                return "Couldn't reach SWITCH in the Pokémon's menu."
            self.mgba.tap("A")
            self.mgba.tick(40)
            # "Move to where?": the cursor starts on the source slot. Its slot address doesn't track in this
            # mode, so press the exact number of steps with long waits (inputs are swallowed otherwise);
            # the caller verifies the resulting order and retries.
            for _ in range(abs(b - a)):
                self.mgba.hold("Down" if b > a else "Up", 6)
                self.mgba.tick(40)
            self.mgba.tap("A")
            self.mgba.tick(70)
        finally:
            self._menus.close_menus()
        after = self._party_sig()
        want = list(before)
        want[a], want[b] = want[b], want[a]
        if after != want:
            return ("The swap didn't take (party order unchanged) — try again, or "
                    f"open_menu('Pokemon') and do it by hand. Order now: {self._party_names()}.")
        return f"Swapped slots {a + 1} and {b + 1}. Party order: {self._party_names()}."

    def _party_names(self) -> str:
        return ", ".join(f"{i + 1}. {p.nickname or p.species_name} L{p.level}"
                         for i, p in enumerate(self.reader.read_party()))

    def _set_lead(self, who: str) -> str:
        party = self.reader.read_party()
        t = self._resolve_party_target(str(who), party)
        if t is None:
            return f"Couldn't find {who!r} in your party: {', '.join(p.species_name for p in party)}."
        if t == 0:
            return f"{party[0].nickname or party[0].species_name} is already your lead."
        if party[t].current_hp == 0:
            return f"{party[t].nickname or party[t].species_name} has fainted — it can't lead. heal() first."
        return self._reorder_party("1", str(t + 1))

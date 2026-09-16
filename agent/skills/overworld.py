"""Overworld skills: heal at a Pokémon Center, shop at a Mart, grind wild
battles, and pick up item balls. See agent.lm_studio_client.AgentClient
(which inherits OverworldMixin)."""

from knowledge.navigation import MAP_NAMES


class OverworldMixin:


    def _bag_and_keys(self) -> tuple[dict, int]:
        return self.reader.read_bag(), self.reader.read_key_item_count()

    def _pick_up_items(self) -> str:
        """Collect every item ball currently visible on this map. For each, walks up
        next to it, faces it, presses A, and advances the 'found ITEM!' text — the
        deterministic version of what the model would otherwise fumble. Confirms each
        pickup by the bag/key-item total rising (or the ball vanishing). Item balls
        are surfaced in the observation so the model knows to call this."""
        from game.state import GameContext
        from knowledge.shopping import ITEM_NAMES
        if self.reader.detect_context() != GameContext.OVERWORLD:
            return "Can only pick up items while walking around (not in a menu/battle)."
        got: list[str] = []
        for _ in range(8):                       # bounded: at most 8 balls per call
            balls = self.reader.read_item_ball_tiles()
            if not balls:
                break
            px, py = self.reader.read_player_pos()
            bx, by = min(balls, key=lambda t: abs(t[0] - px) + abs(t[1] - py))
            if not self._approach_adjacent(bx, by):
                return self._pickup_result(got, f"couldn't reach the item at ({bx},{by})")
            before_bag, before_keys = self._bag_and_keys()
            picked = False
            for _ in range(6):
                px, py = self.reader.read_player_pos()
                face = self._facing_dir(px, py, bx, by)
                if face:
                    self.mgba.tap(face)          # turn to face the ball (bumps it, no move)
                self.mgba.tap("A")               # pick up
                self.mgba.tick(15)
                self._advance_to_control()       # advance "found ITEM!" text to control
                after_bag, after_keys = self._bag_and_keys()
                if after_keys > before_keys or sum(after_bag.values()) > sum(before_bag.values()) \
                        or (bx, by) not in self.reader.read_item_ball_tiles():
                    picked = True
                    break
            if not picked:
                return self._pickup_result(got, f"the item at ({bx},{by}) didn't respond")
            after_bag, after_keys = self._bag_and_keys()
            new = [ITEM_NAMES.get(iid, f"item#{iid}") for iid, q in after_bag.items()
                   if q > before_bag.get(iid, 0)]
            if after_keys > before_keys:
                new.append("a key item")
            got.append(", ".join(new) if new else "an item")
        return self._pickup_result(got)

    @staticmethod
    def _pickup_result(got: list[str], problem: str = "") -> str:
        if not got and problem:
            return f"No items picked up — {problem}."
        if not got:
            return "No item balls visible here."
        head = f"Picked up {len(got)} item(s): {'; '.join(got)}."
        return head + (f" Stopped: {problem}." if problem else "")

    # Nurse Joy stands at (7,2) in the shared Pokémon Center interior, behind the
    # counter at (7,3). The player stands one tile below the counter, at (7,4), and
    # presses A facing up — the counter metatile forwards the interaction to the
    # nurse behind it. The heal is a pure dialogue: greeting → YES/NO (defaults to
    # YES) → heal → "restored". So we advance with A and confirm success by the
    # party returning to full HP.
    _NURSE_TILE = (7, 4)

    def _party_full_hp(self) -> bool:
        party = self.reader.read_party()
        return bool(party) and all(m.current_hp == m.max_hp for m in party)

    def _heal(self) -> str:
        """Heal the whole party at a Pokémon Center. Travels to the nearest one if
        not already inside, walks to Nurse Joy, and advances the heal dialogue
        until the party is at full HP. Resumable: if a wild battle/dialog interrupts
        the trip, it stops and reports so the caller can resume."""
        from game.state import GameContext
        from knowledge.map_graph import MAP_KIND
        if self._party_full_hp():
            return "Party is already at full HP — no need to heal."
        # Get inside a Pokémon Center first (resumable travel).
        if MAP_KIND.get(self.reader.read_current_map()) != "pokecenter":
            res = self._go_to("Pokemon Center")
            if MAP_KIND.get(self.reader.read_current_map()) != "pokecenter":
                return f"On the way to a Pokémon Center to heal: {res}"
        # Walk to the nurse's counter and face her.
        nx, ny = self._NURSE_TILE
        self._walk_to(nx, ny)
        if self.reader.read_player_pos() != (nx, ny):
            return (f"Couldn't reach Nurse Joy's counter at {self._NURSE_TILE} "
                    f"(at {self.reader.read_player_pos()}). Try walk_to it, then talk.")
        self.mgba.tap("Up")            # face the nurse across the counter
        # Advance greeting → YES/NO (YES is default) → heal → closing. A-mash and
        # watch for full HP; nudge Up before confirming so the cursor sits on YES.
        for _ in range(40):
            if self._party_full_hp():
                # Advance the nurse's closing dialogue AND wait out the heal fade until
                # we're back in real OVERWORLD control. A fixed few A-taps left the
                # player standing on the counter tile still flagged IN_MENU, where
                # walk_to can't move — the Poké Center exit stall (the agent re-issued
                # walk_to(exit) for ~50s until the fade happened to clear).
                self._advance_to_control(tries=24)
                return "Healed the party to full HP at the Pokémon Center."
            self.mgba.tap("Up")        # keep the YES/NO cursor on YES if it's up
            self.mgba.tap("A")
            self.mgba.tick(12)
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return "A battle started while healing — handle it, then heal again."
        return ("Talked to Nurse Joy but couldn't confirm a full heal — "
                "try heal again, or check you're facing her at the counter.")

    # ── Poké Mart shopping ────────────────────────────────────────────────────
    # Standard marts share LAYOUT_MART: the clerk is behind a counter at (2,3); the
    # player stands in front at (2,5) (walk_to (2,4) stops there — the counter is
    # impassable) and presses A facing up to talk across it. The buy menu is driven
    # through sShopData (Addr.SHOP_DATA): the highlighted item is
    # itemList[scrollOffset + selectedRow], so we navigate the list by reading those
    # and pressing Down/Up, set quantity by watching itemPrice, and confirm each
    # purchase by the bag count rising. Menu inputs get dropped during animations, so
    # every step re-reads state and retries rather than pressing blindly.
    _MART_CLERK_APPROACH = (2, 4)

    def _buy_list_open(self) -> bool:
        from game.constants import Addr
        lp = self.mgba.read32(Addr.SHOP_DATA + Addr.SHOP_ITEMLIST)
        return (0x08000000 <= lp < 0x0A000000
                and 0 < self.mgba.read16(Addr.SHOP_DATA + Addr.SHOP_ITEMCOUNT) <= 30)

    def _buy_list_interactive(self) -> bool:
        """Probe whether the buy ITEM LIST is live and taking D-pad input: on the list
        a Down nudges selectedRow (we immediately undo it); on a text box / mid-fade /
        transition it's inert. ONLY safe when we're not on the Buy/Sell choice menu
        (i.e. after Buy is selected / after a purchase), where Down would move a
        different cursor. Used to wait out the post-purchase 'Here you go!' text."""
        from game.constants import Addr
        SD = Addr.SHOP_DATA
        r0 = self.mgba.read16(SD + Addr.SHOP_SELROW)
        self.mgba.tap("Down")
        self.mgba.tick(8)
        if self.mgba.read16(SD + Addr.SHOP_SELROW) != r0:
            self.mgba.tap("Up")            # undo the probe, back to where we were
            self.mgba.tick(8)
            return True
        return False

    def _shop_item_list(self) -> list[int]:
        from game.constants import Addr
        lp = self.mgba.read32(Addr.SHOP_DATA + Addr.SHOP_ITEMLIST)
        n = self.mgba.read16(Addr.SHOP_DATA + Addr.SHOP_ITEMCOUNT)
        if not (0x08000000 <= lp < 0x0A000000):
            return []
        return [self.mgba.read16(lp + 2 * i) for i in range(min(n, 30))]

    def _open_buy_menu(self) -> bool:
        """Talk to the clerk, then select Buy so the interactive item list is open.
        sShopData.itemList is set as soon as the Buy/Sell menu appears (before Buy is
        chosen), so 'itemList valid' only means the shop menu is up — we then select
        Buy (top option, default cursor) and let the item list fade in before the
        caller navigates (Task_BuyMenu ignores D-pad while gPaletteFade is active)."""
        self._walk_to(*self._MART_CLERK_APPROACH)   # lands at the counter-front tile
        # 1. Talk to the clerk and advance the greeting until the shop menu appears.
        shop_up = False
        for _ in range(3):
            self.mgba.tap("Up")                       # face the clerk
            for _ in range(8):
                if self._buy_list_open():
                    shop_up = True
                    break
                self.mgba.tap("A")                    # advance greeting
                self.mgba.tick(20)
            if shop_up:
                break
        if not shop_up:
            return False
        # 2. Select Buy (default top option) → enter the item list, then settle so the
        #    fade finishes and the list starts taking D-pad input.
        self.mgba.tap("A")
        if hasattr(self.mgba, "wait_until_idle"):
            self.mgba.wait_until_idle()
        self.mgba.tick(40)
        return self._buy_list_open()

    def _buy_one_item(self, item_id: int, qty: int, unit_price: int) -> int:
        """Navigate to item_id in the open list, buy `qty`, return how many were
        actually added to the bag (0 if not sold here / couldn't afford any)."""
        from game.constants import Addr
        SD = Addr.SHOP_DATA
        items = self._shop_item_list()
        if item_id not in items:
            return 0
        target = items.index(item_id)
        # Move the highlight to the target row (verify each press; retry drops).
        for _ in range(40):
            cur = self.mgba.read16(SD + Addr.SHOP_SCROLL) + self.mgba.read16(SD + Addr.SHOP_SELROW)
            if cur == target:
                break
            self.mgba.tap("Down" if cur < target else "Up")
            self.mgba.tick(8)
        else:
            return 0
        before = self.reader.read_bag().get(item_id, 0)
        idle = getattr(self.mgba, "wait_until_idle", None)
        # Select the item → the "How many?" quantity box. Wait for its init to run
        # (it computes maxQuantity = money/price; 0 means it hasn't run yet).
        if idle:
            idle()
        self.mgba.tap("A")
        maxq = 0
        for _ in range(10):
            if idle:
                idle()
            self.mgba.tick(6)
            maxq = self.mgba.read16(SD + Addr.SHOP_MAXQTY)
            if maxq > 0:
                break
        if maxq <= 0:
            return 0                     # quantity box never opened
        want = max(1, min(qty, maxq))
        # Dial the quantity up from 1 to `want` (Up = +1), confirming via
        # itemPrice = unit×count. Re-read after each press; retry drops.
        for _ in range(want + 15):
            cur_n = self.mgba.read32(SD + Addr.SHOP_ITEMPRICE) // unit_price if unit_price else 1
            if cur_n >= want:
                break
            self.mgba.tap("Up")
            self.mgba.tick(6)
        # Confirm + purchase. A opens the "…you wanted N?" YES/NO box (YES default),
        # another A selects YES → the purchase runs and the bag grows. Press A until
        # the bag actually increases — self-verifying, so a dropped input just means
        # another press rather than a mis-aligned sequence. Then a SINGLE A dismisses
        # the "Here you go!" line back to the list (never press A on the list itself —
        # there it re-selects the highlighted item).
        got = 0
        for _ in range(10):
            self.mgba.tap("A")
            if idle:
                idle()
            self.mgba.tick(10)
            got = self.reader.read_bag().get(item_id, 0) - before
            if got > 0:
                break
        if got > 0:
            # Advance the "Here you go! Thank you!" text (which may still be printing)
            # until the item list is interactive again — probe first so we never press
            # A while ON the list (that would re-select the item).
            for _ in range(12):
                if self._buy_list_interactive():
                    break
                self.mgba.tap("A")
                if idle:
                    idle()
                self.mgba.tick(10)
        return max(0, got)

    def _close_buy_menu(self) -> None:
        from game.state import GameContext
        for _ in range(12):
            if self.reader.detect_context() == GameContext.OVERWORLD:
                return
            self.mgba.tap("B")
            self.mgba.tick(12)

    def _shop(self) -> str:
        """Restock at the Poké Mart per the badge-gated purchase policy: travel to a
        Mart if needed, open the buy menu, buy the affordable par-level list of items
        this mart sells, and leave. The model just calls shop()."""
        from knowledge.map_graph import MAP_KIND
        from knowledge.shopping import compute_shopping_list, ITEM_NAMES, ITEM_PRICES
        if MAP_KIND.get(self.reader.read_current_map()) != "mart":
            res = self._go_to("Mart")
            if MAP_KIND.get(self.reader.read_current_map()) != "mart":
                return f"On the way to a Mart to restock: {res}"
        money = self.reader.read_money()
        plan = compute_shopping_list(self.reader.read_bag(),
                                     self.ltm.data["badges_earned"], money)
        if not plan["lines"]:
            return f"Bag is already stocked (¥{money}) — nothing to buy."
        if not self._open_buy_menu():
            return ("Couldn't open the Mart buy menu — walk up to the clerk at the "
                    "counter and call shop() again.")
        sold = set(self._shop_item_list())
        bought, spent, skipped = [], 0, []
        for line in plan["lines"]:
            iid, qty = line["item_id"], line["qty"]
            if iid not in sold:
                skipped.append(ITEM_NAMES.get(iid, str(iid)))
                continue
            got = self._buy_one_item(iid, qty, ITEM_PRICES.get(iid, line["unit_price"]))
            if got > 0:
                bought.append(f"{got}× {ITEM_NAMES.get(iid, iid)}")
                spent += got * line["unit_price"]
        self._close_buy_menu()
        if not bought:
            return ("At the Mart but bought nothing (this mart doesn't sell the "
                    "recommended items, or you couldn't afford them).")
        msg = f"Bought {', '.join(bought)} (¥{spent}). Money left: ¥{self.reader.read_money()}."
        if skipped:
            msg += f" (Not sold here: {', '.join(dict.fromkeys(skipped))}.)"
        return msg

    _OPPOSITE = {"Up": "Down", "Down": "Up", "Left": "Right", "Right": "Left"}

    def _wander_step(self) -> bool:
        """Take one overworld step to seek a wild encounter, PACING back and forth so
        we stay in the local (grassy) patch instead of drifting out of it. Keeps a
        heading, reverses when blocked, and rotates axis if fully boxed in. Returns
        True if a battle started."""
        from game.state import GameContext
        heading = getattr(self, "_wander_dir", "Up")
        # Try the current heading, then its reverse, then the other axis.
        order = [heading, self._OPPOSITE[heading]]
        for d in ("Up", "Down", "Left", "Right"):
            if d not in order:
                order.append(d)
        for mv in order:
            before = self.reader.read_player_pos()
            self.mgba.tap(mv)
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                self._wander_dir = mv
                return True
            if self.reader.read_player_pos() != before:
                self._wander_dir = mv   # keep pacing this way until blocked
                return False
        return False

    def _nearest_grass(self) -> tuple[int, int] | None:
        """Closest tall-grass tile to the player on the current map (Manhattan), or
        None if the map has no grass. Uses the metatile-behavior reader so grind can
        route the player onto a real patch instead of guessing from encounters."""
        self.tilemap.refresh()
        tiles = self.tilemap.grass_tiles()
        if not tiles:
            return None
        px, py = self.reader.read_player_pos()
        return min(tiles, key=lambda t: abs(t[0] - px) + abs(t[1] - py))

    def _relocate_to_grass(self, exclude_current: bool = False) -> bool:
        """Deterministically travel to the nearest grass route so grind has grass to
        work with, instead of handing a 'go find grass' message back to the model
        (which it tends to ignore). Returns True if we end up somewhere with grass."""
        from knowledge.map_graph import nearest_grass
        bank, mid = self.reader.read_current_map()
        found = nearest_grass((bank, mid), exclude_current=exclude_current)
        if found is None:
            return False
        goal_map = found[0]
        if goal_map == (bank, mid):
            return self._nearest_grass() is not None
        name = MAP_NAMES.get(goal_map)
        if not name:
            return False
        self._go_to(name)                       # resumable; may stop on battle/dialog
        return self._nearest_grass() is not None

    _GRIND_HP_FLOOR = 0.35

    def _grind(self, target_level: int) -> str:
        """Grind wild battles until the lead reaches target_level. Wanders the
        current area to trigger encounters and auto-fights each with the best
        damaging move — the LLM doesn't drive each battle. Routes the player onto
        tall grass first (real metatile detection), so it works even if called from
        a path tile. Stops at the target level, when the lead's HP gets low (heal,
        then grind again), or if the current map has no grass at all."""
        from game.state import GameContext
        party = self.reader.read_party()
        if not party:
            return "No Pokémon to grind with."
        target_level = max(1, min(int(target_level), 100))
        start = party[0].level
        if start >= target_level:
            return f"Lead is already L{start} (target L{target_level}) — no need to grind."

        # No grass on this map ⇒ travel to the nearest grass route ourselves rather
        # than bouncing a "go find grass" message off the model (it ignores it).
        if self._nearest_grass() is None and not self._relocate_to_grass():
            return ("No tall grass reachable from here — go_to a route with grass "
                    "(e.g. 'Route 1'/'Route 2' or Viridian Forest), then call "
                    f"grind({target_level}) again.")

        battles = 0
        stuck_steps = 0      # overworld steps that couldn't reach grass
        relocations = 0      # deterministic grass-route relocations spent
        for _ in range(400):
            party = self.reader.read_party()
            if not party:
                break
            lvl = party[0].level
            if lvl >= target_level:
                return (f"Grinded L{start}→L{lvl} in {battles} battles. "
                        f"heal(), then head to the gym.")
            if party[0].max_hp and party[0].hp_percent < self._GRIND_HP_FLOOR:
                return (f"Grinding paused at L{lvl} — lead HP low "
                        f"({party[0].hp_percent:.0%}). Call heal(), then grind({target_level}) again.")
            ctx = self.reader.detect_context()
            if ctx == GameContext.IN_BATTLE:
                self._auto_fight()
                battles += 1
                stuck_steps = 0
            elif ctx == GameContext.OVERWORLD:
                px, py = self.reader.read_player_pos()
                if self.tilemap.is_tall_grass(px, py):
                    # On grass — pace back and forth to trigger encounters.
                    self._wander_step()
                    stuck_steps = 0
                else:
                    # Off grass — route back onto the patch (walk_to is ledge-aware,
                    # so downhill-ledge patches like Route 1's are reachable now).
                    target = self._nearest_grass()
                    if target is not None:
                        self._walk_to(*target)
                    stuck_steps += 1
                    # Can't reach any grass on this map (walled off / none) — try a
                    # deterministic relocation to another grass route before giving up.
                    if stuck_steps >= 25:
                        if relocations < 2 and self._relocate_to_grass(exclude_current=True):
                            relocations += 1
                            stuck_steps = 0
                        else:
                            return ("Couldn't reach tall grass to grind. go_to a grassy "
                                    f"route yourself, then call grind({target_level}) again.")
            else:
                self.mgba.tap("A")        # advance a dialog/transition
                self.mgba.tick()
        party = self.reader.read_party()
        lvl = party[0].level if party else start
        return f"Grinded L{start}→L{lvl} in {battles} battles. Call grind({target_level}) again to continue."

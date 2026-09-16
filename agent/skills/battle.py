"""Battle skills: use_move, flee, catch, switch, use_item, and the
best-move auto-fight driver. See agent.lm_studio_client.AgentClient
(which inherits BattleMixin)."""


class BattleMixin:


    def _battle_press(self, button: str) -> None:
        """A battle-reliable press: wait until the game is idle (text finished /
        menu up), then hold long enough to register. Short taps are silently
        dropped during battle animations/printing."""
        waiter = getattr(self.mgba, "wait_until_idle", None)
        if waiter:
            waiter()
        self.mgba.hold(button, 20)

    def _battle_truly_over(self) -> bool:
        """Distinguish a real battle end from a transient non-IN_BATTLE state — a Gym
        Leader's fainted Pokémon being replaced by its next one briefly reads as a
        menu/transition. gBattleOutcome is 0 all through a battle (including send-outs)
        and non-zero only at the true end; OVERWORLD also means it's over. (Without
        this, use_move declared victory after only Brock's Geodude, so the agent left
        the gym at 0 badges and got stuck at the Pewter guard.)"""
        from game.constants import Addr
        from game.state import GameContext
        if self.reader.detect_context() == GameContext.OVERWORLD:
            return True
        return self.mgba.read8(Addr.BATTLE_OUTCOME) != 0

    def _use_move(self, name: str) -> str:
        """Use a move by name in battle, deterministically.

        Per pokefirered HandleInputChooseMove, pressing A commits
        gMoveSelectionCursor[gActiveBattler] as the chosen move. So we: advance to
        the FIGHT move menu (detected by gBattlerControllerFuncs[0] ==
        CTRL_CHOOSE_MOVE), WRITE the target slot into the cursor, press A to
        commit, then let the turn RESOLVE (the move executes and PP decrements only
        after both sides have chosen and the turn plays out — checking sooner is
        why this looked broken before). Success = that move's PP dropped (or the
        battle ended). Single-battle scope (player = battler 0)."""
        from game.constants import Addr
        from game.state import GameContext
        party = self.reader.read_party()
        if not party:
            return "No active Pokémon."
        # Validate + index against the ACTIVE battler's moves (gBattleMons[0]) — the set
        # the FIGHT menu shows and MOVE_CURSOR indexes. Using the lead (party[0]) here is
        # wrong once another mon is out (switch / forced send-out after a faint): its slot
        # order differs, so the cursor could land on an EMPTY slot (a caught Pidgey with
        # two moves). Out of battle, fall back to the lead so name errors still read sanely.
        in_battle = self.reader.detect_context() == GameContext.IN_BATTLE
        if in_battle:
            _ids, move_names, pp = self.reader.read_active_battle_moves()
        else:
            move_names, pp = party[0].move_names, party[0].pp
        names = [n.lower() for n in move_names]
        key = name.lower().strip()
        if not key or key not in names:   # `not key` guards an empty name matching an empty slot
            known = ", ".join(m for m in move_names if m)
            return f"'{name}' is not a known move. Known moves: {known}."
        slot = names.index(key)
        move_label = move_names[slot]
        if pp[slot] == 0:
            return f"{move_label} has no PP left — choose another move."
        # Remember who's giving the order so we can tell if it fainted mid-turn (#68):
        # a faster foe can KO our lead before our move executes, in which case PP never
        # drops and the naive success check would mash A blindly through the forced
        # send-out prompt. 0 means Tier-2 decryption gave us nothing usable — don't
        # arm the identity guard on it (only the HP==0 faint signal is trustworthy then).
        species_before = self.reader.read_active_battle_species() if in_battle else party[0].species_id

        # A prior level-up may have left a move-learn prompt pending — resolve it
        # before attacking (else committing a move would mash it into an overwrite).
        learn = self._maybe_drive_learn()
        if learn:
            return learn

        for _ in range(20):
            if self.reader.detect_context() != GameContext.IN_BATTLE:
                if self._battle_truly_over():
                    self._settle_evolution()   # a level-up this battle may now evolve
                    self._advance_to_control(tries=30)   # clear post-battle text/blackout to overworld
                    return "Battle is over."
                # Transient (a fainted foe being replaced by the Leader's next
                # Pokémon reads as a brief menu/transition) — advance, don't bail.
                self._battle_press("A")
                continue
            if hasattr(self.mgba, "wait_until_idle"):
                self.mgba.wait_until_idle()
            if self.mgba.read32(Addr.BATTLE_CTRL_FUNC) != Addr.CTRL_CHOOSE_MOVE:
                # A level-up delete box (offered move pending) hides behind the same
                # "advance text" path — resolve it instead of pressing A through it.
                learn = self._maybe_drive_learn()
                if learn:
                    return learn
                self._battle_press("A")   # advance intro/result text, or open FIGHT
                continue
            # Move menu is up: pick the slot and commit. PP is read from the ACTIVE
            # battler (gBattleMons[0]) — the live in-battle PP that decrements when the
            # move lands, and matches the slot the cursor indexes.
            pp_before = self.reader.read_active_battle_moves()[2][slot]
            self.mgba.write8(Addr.MOVE_CURSOR, slot)
            self.mgba.hold("A", 20)       # A edge → commits gMoveSelectionCursor
            # Let the turn resolve — advance result text until OUR move's PP drops,
            # the battle truly ends, or the next action menu appears.
            for _ in range(24):
                if self.reader.read_active_battle_moves()[2][slot] < pp_before:
                    return f"Used {move_label}."          # our move landed
                # A KO can trigger a level-up move-learn while we're still advancing
                # result text — catch it (offered set ~16 frames before the box) and
                # resolve per policy rather than mashing A into an overwrite.
                learn = self._maybe_drive_learn()
                if learn:
                    return f"Used {move_label}. {learn}."
                if self.reader.detect_context() != GameContext.IN_BATTLE and self._battle_truly_over():
                    self._settle_evolution()   # a level-up this battle may now evolve
                    self._advance_to_control(tries=30)   # clear post-battle text/blackout to overworld
                    return f"Used {move_label} (battle ended)."
                # The active mon fainted (or was swapped out) before the move resolved — its
                # PP never dropped, so we'd otherwise mash A through the forced send-out and
                # confirm a switch blind (#68). Stop and hand the model a truthful obs so it
                # can pick who to send out next (switch_pokemon), rather than a misleading
                # "Could not use…". Read the ACTIVE battler (gBattleMons[0]), not the lead.
                if (self.reader.read_active_battle_hp() == 0
                        or (species_before and self.reader.read_active_battle_species() != species_before)):
                    return (f"Your lead fainted before {move_label} could resolve — "
                            f"the foe was faster. Send out your next Pokémon with "
                            f"switch_pokemon.")
                if hasattr(self.mgba, "wait_until_idle"):
                    self.mgba.wait_until_idle()
                self.mgba.hold("A", 18)
        return f"Could not use {name} — the battle menu did not respond as expected."

    def _flee_battle(self) -> str:
        """Run from a WILD battle. Drives the action menu to RUN (writes the action
        cursor, like use_move does for the move cursor) and confirms escape by the
        battle ending. Trainer battles can't be fled. The escape roll can fail (the
        foe is faster) — this retries across turns, and reports if it can't get
        away so the caller can fight instead."""
        from game.state import GameContext
        from game.constants import Addr
        if self.reader.detect_context() != GameContext.IN_BATTLE:
            return "Not in a battle — nothing to flee."
        if self.mgba.read32(Addr.BATTLE_TYPE_FLAGS) & Addr.BATTLE_TYPE_TRAINER:
            return "Can't run from a trainer battle — win it or switch Pokémon."
        idle = getattr(self.mgba, "wait_until_idle", None)
        for _ in range(20):
            if self.reader.detect_context() != GameContext.IN_BATTLE:
                return "Got away safely — fled the wild battle."
            if idle:
                idle()
            if self.mgba.read32(Addr.BATTLE_CTRL_FUNC) == Addr.CTRL_CHOOSE_ACTION:
                self.mgba.write8(Addr.ACTION_CURSOR, Addr.ACTION_RUN)   # select RUN
                self.mgba.hold("A", 20)                                 # commit
            else:
                self._battle_press("A")   # advance intro / result / escape text
        if self.reader.detect_context() != GameContext.IN_BATTLE:
            return "Got away safely — fled the wild battle."
        return ("Couldn't get away (the escape failed or the foe is faster) — "
                "try flee_battle again, or use_move to fight.")

    # ── Catching ──────────────────────────────────────────────────────────────
    def _ball_count(self) -> int:
        bag = self.reader.read_bag()
        return sum(bag.get(b, 0) for b in (1, 2, 3, 4))   # Master/Ultra/Great/Poké

    def _battle_bag_open(self) -> bool:
        """True only when the in-battle Bag is actually up: the main callback has left
        CB2_BATTLE (so it's not mid-turn) AND gBagMenuState.location ==
        ITEMMENULOCATION_BATTLE(5). (bagOpen reads 0 while open, so it's unusable.)"""
        from game.constants import Addr
        return (self.mgba.read32(Addr.GMAIN_CALLBACK2) != Addr.CB2_BATTLE
                and self.mgba.read8(Addr.BAG_MENU_STATE + Addr.BAG_LOCATION_OFF) == 5)

    def _open_battle_bag(self) -> bool:
        """Open the Bag from a battle by selecting BAG (action cursor = 1), the same
        write-cursor+A method flee_battle uses for RUN. The bag hands off across a
        controller handshake; confirm it's really up via gBagMenuState, not just a
        callback change."""
        from game.constants import Addr
        from game.state import GameContext
        idle = getattr(self.mgba, "wait_until_idle", None)
        for _ in range(30):
            if self._battle_bag_open():
                return True
            if self.reader.detect_context() == GameContext.OVERWORLD:
                return False                 # battle ended out from under us
            if idle:
                idle()
            # The action-menu controller value VARIES by turn (0x08030611 on turn 1,
            # 0x0802e439 later), so don't gate on it. Instead: if the MOVE menu is up,
            # back out with B (never attack); otherwise write the BAG cursor and press
            # A — at the action menu that opens the bag, and on intro/result text it
            # just advances (the cursor write is ignored there).
            if self.mgba.read32(Addr.BATTLE_CTRL_FUNC) == Addr.CTRL_CHOOSE_MOVE:
                self._battle_press("B")
            else:
                self.mgba.write8(Addr.ACTION_CURSOR, Addr.ACTION_BAG)
                self.mgba.hold("A", 20)
            self.mgba.tick(6)
        return self._battle_bag_open()

    def _catch(self) -> str:
        """Throw a Poké Ball at the wild Pokémon. Opens the Bag, switches to the Poké
        Balls pocket (via gBagMenuState.pocket), throws the top ball, and reports the
        outcome (caught / broke free). Weaken the foe with use_move first for a better
        rate. Can't catch trainer battles."""
        from game.constants import Addr
        from game.state import GameContext
        if self.reader.detect_context() != GameContext.IN_BATTLE:
            return "Not in a battle — you can only catch a wild Pokémon during its battle."
        if self.mgba.read32(Addr.BATTLE_TYPE_FLAGS) & Addr.BATTLE_TYPE_TRAINER:
            return "You can't catch a trainer's Pokémon — only wild ones. Win with use_move."
        balls0 = self._ball_count()
        if balls0 <= 0:
            return "No Poké Balls — buy some at a Mart with shop(), then catch."
        idle = getattr(self.mgba, "wait_until_idle", None)
        if not self._open_battle_bag():
            return "Couldn't open the Bag in battle — try catch again."
        if idle:
            idle()
        self.mgba.tick(12)
        # Switch to the Poké Balls pocket (Right cycles Items→Key Items→Balls).
        SD = Addr.BAG_MENU_STATE
        for _ in range(8):
            if self.mgba.read16(SD + Addr.BAG_POCKET_OFF) == Addr.BAG_POCKET_BALLS:
                break
            self.mgba.tap("Right")
            if idle:
                idle()
            self.mgba.tick(8)
        if self.mgba.read16(SD + Addr.BAG_POCKET_OFF) != Addr.BAG_POCKET_BALLS:
            self._exit_battle_menus()
            return "Couldn't reach the Poké Balls pocket — try catch again."
        # Throw the ball. Selecting the ball opens a USE/CANCEL context menu (USE is
        # the default); A there throws it. Press A until a ball is actually consumed —
        # self-verifying, so a dropped input in the list→context→USE chain just means
        # another press instead of stranding us mid-menu (the old flaky spot).
        if idle:
            idle()
        for _ in range(10):
            self.mgba.tap("A")
            if idle:
                idle()
            self.mgba.tick(10)
            if self._ball_count() < balls0:
                break
        if self._ball_count() >= balls0:
            self._exit_battle_menus()
            return ("Couldn't throw the ball this time — you're back in the battle; "
                    "try catch() again.")
        # A ball was thrown. Resolve using gBattleOutcome — the ONLY reliable verdict:
        # a transient action-menu handler flickers through even a successful catch, and
        # the party count lags. == B_OUTCOME_CAUGHT the instant the catch succeeds.
        # Advance with B only — it advances capture/broke-free/Pokédex text, declines
        # the "give a nickname?" prompt, and is a harmless no-op at the action menu
        # (unlike A, which would attack). If the outcome stays 0 through the loop, the
        # mon broke free (still battling).
        OUTCOME = Addr.BATTLE_OUTCOME
        caught = False
        for _ in range(60):
            if idle:
                idle()
            self.mgba.tick(10)
            if self.mgba.read8(OUTCOME) == Addr.B_OUTCOME_CAUGHT:
                caught = True
                break
            if self.reader.detect_context() == GameContext.OVERWORLD:
                break
            self.mgba.tap("B")
        self._exit_battle_menus()            # clear any prompt; never strand in a menu
        if caught or self.mgba.read8(OUTCOME) == Addr.B_OUTCOME_CAUGHT:
            return "Gotcha! Caught the wild Pokémon — it's on your team now."
        return ("It broke free! Weaken it more with use_move (bring its HP low, or "
                "inflict a status like sleep), then catch() again.")

    @staticmethod
    def _resolve_party_target(target: str, party) -> int | None:
        """Map a switch target — a 1-based slot number or a species name (exact, then
        partial) — to a 0-based party slot index, or None if it doesn't match."""
        key = target.lower().strip()
        if key.isdigit():
            i = int(key) - 1
            return i if 0 <= i < len(party) else None
        for i, p in enumerate(party):
            if p.species_name and p.species_name.lower() == key:
                return i
        for i, p in enumerate(party):
            if p.species_name and key in p.species_name.lower():
                return i
        return None

    def _open_party_menu(self) -> bool:
        """Open the party menu from a battle by selecting POKEMON (action cursor = 2),
        the same looped write-cursor+A method _open_battle_bag uses for BAG. Confirms
        via the callback leaving CB2_BATTLE (the party screen has its own callback)."""
        from game.constants import Addr
        from game.state import GameContext
        idle = getattr(self.mgba, "wait_until_idle", None)
        opened = False
        for _ in range(30):
            if self.mgba.read32(Addr.GMAIN_CALLBACK2) != Addr.CB2_BATTLE:
                opened = True
                break                             # the party screen is coming up
            if self.reader.detect_context() == GameContext.OVERWORLD:
                return False                      # battle ended out from under us
            if idle:
                idle()
            if self.mgba.read32(Addr.BATTLE_CTRL_FUNC) == Addr.CTRL_CHOOSE_MOVE:
                self._battle_press("B")           # back out of the move menu; never attack
            else:
                self.mgba.write8(Addr.ACTION_CURSOR, Addr.ACTION_POKEMON)
                self.mgba.hold("A", 20)
            self.mgba.tick(6)
        if not opened:
            return False
        # The party screen transitions through a LOADING callback before it becomes
        # interactive; returning too early leaves inputs ignored (a switch froze here).
        # Settle until gMain.callback2 stops changing (and is no longer CB2_BATTLE).
        prev = None
        for _ in range(20):
            cb = self.mgba.read32(Addr.GMAIN_CALLBACK2)
            if cb != Addr.CB2_BATTLE and cb == prev:
                return True                       # stable, interactive party screen
            prev = cb
            self.mgba.tick(6)
        return self.mgba.read32(Addr.GMAIN_CALLBACK2) != Addr.CB2_BATTLE

    def _battle_display_slot(self, field_slot: int) -> int:
        """Map a field-order party slot to its on-screen slot in the in-battle party menu.

        The menu lists mons in BATTLE order via gBattlePartyCurrentOrder (packed nibbles:
        display slot → field party id; slot even → high nibble, odd → low nibble). It's
        identity at battle start but a switch permutes it, so field slot and display slot
        diverge (#120). Returns the display slot whose party id == field_slot; falls back
        to identity if none matches (e.g. read glitch)."""
        from game.constants import Addr
        for s in range(6):
            b = self.mgba.read8(Addr.BATTLE_PARTY_ORDER + (s >> 1))
            pid = (b & 0xF) if (s & 1) else (b >> 4)
            if pid == field_slot:
                return s
        return field_slot

    def _switch_pokemon(self, target: str) -> str:
        """Switch the active Pokémon in battle to another party member (by species name
        or 1-based slot). Opens the party menu (POKEMON), moves the cursor to the target
        slot, selects it, and confirms SHIFT — then verifies the active battler's species
        actually changed. Switching uses your turn (the opponent gets a free hit), so do
        it to gain a type advantage or save a low mon, not casually."""
        from game.constants import Addr
        from game.state import GameContext
        if self.reader.detect_context() != GameContext.IN_BATTLE:
            return "switch_pokemon is only for battles."
        party = self.reader.read_party()
        if len(party) < 2:
            return "You only have one Pokémon — nothing to switch to. Catch a team first."
        slot = self._resolve_party_target(target, party)
        if slot is None:
            roster = ", ".join(f"{i+1}:{p.species_name}" for i, p in enumerate(party) if p.species_name)
            return f"Can't find '{target}' in your party ({roster})."
        mon = party[slot]
        if mon.current_hp == 0:
            return f"{mon.species_name} has fainted — pick a Pokémon with HP left."
        active_species = self.mgba.read16(Addr.BATTLE_MON0_SPECIES)
        if mon.species_id == active_species:
            return f"{mon.species_name} is already the one battling."
        target_species = mon.species_id
        idle = getattr(self.mgba, "wait_until_idle", None)
        if not self._open_party_menu():
            return "Couldn't open the party menu — try switch_pokemon again."
        if idle:
            idle()
        self.mgba.tick(30)                        # let the party screen settle
        # The in-battle party menu lists mons in BATTLE order (gBattlePartyCurrentOrder),
        # which is remapped after each switch — so the target's field slot is NOT its
        # on-screen slot once you've already switched this battle. Translate field slot →
        # display slot; without this the cursor lands on the active mon and the game
        # rejects it as "already in battle" (why a 2nd switch used to silently fail, #120).
        disp_slot = self._battle_display_slot(slot)
        for _ in range(12):                       # move the cursor to the target's display slot
            cur = self.mgba.read8(Addr.PARTY_MENU_SLOT)
            if cur == disp_slot:
                break
            self.mgba.tap("Down" if cur < disp_slot else "Up")
            if idle:
                idle()
            self.mgba.tick(8)
        if self.mgba.read8(Addr.PARTY_MENU_SLOT) != disp_slot:
            self._exit_battle_menus()
            return f"Couldn't select {mon.species_name} in the party menu — try again."
        # Select the slot → SHIFT (default) → confirm. Self-verifying: press A until the
        # active battler's species becomes the target's (the send-out animation takes a
        # few frames), or bail out cleanly.
        for _ in range(10):
            if self.mgba.read16(Addr.BATTLE_MON0_SPECIES) == target_species:
                break
            self.mgba.tap("A")
            if idle:
                idle()
            self.mgba.tick(16)
        if self.mgba.read16(Addr.BATTLE_MON0_SPECIES) != target_species:
            self._exit_battle_menus()
            return f"Couldn't switch to {mon.species_name} — try switch_pokemon again."
        # Advance the "come back! / go!" send-out text so the caller lands cleanly.
        for _ in range(6):
            if self.mgba.read32(Addr.BATTLE_CTRL_FUNC) in (
                    Addr.CTRL_CHOOSE_ACTION, Addr.CTRL_CHOOSE_ACTION_ALT, Addr.CTRL_CHOOSE_MOVE):
                break
            self._battle_press("A")
        return f"Switched in {mon.species_name} (L{mon.level}). It's now your active Pokémon."

    def _use_item(self, item: str) -> str:
        """Use a Bag item on your ACTIVE Pokémon during battle — a Potion to heal, an
        Antidote/Paralyze Heal/etc. to cure status. Opens the Bag, switches to the Items
        pocket, navigates the list to the named item (via the live cursor), and uses it
        on the lead, confirming by the item being consumed / HP rising / status clearing.
        Using an item spends your turn. (Overworld item use isn't handled here.)"""
        from game.constants import Addr
        from game.state import GameContext
        from knowledge.shopping import ITEM_NAMES
        if self.reader.detect_context() != GameContext.IN_BATTLE:
            return "use_item is for battles. (In the overworld, items apply automatically where needed.)"
        key = item.lower().strip().replace("é", "e")
        name2id = {v.lower().replace("é", "e"): k for k, v in ITEM_NAMES.items()}
        iid = name2id.get(key)
        if iid is None:
            hits = [k for n, k in name2id.items() if key and key in n]
            iid = hits[0] if len(hits) == 1 else None
        if iid is None:
            return f"Don't recognise the item '{item}'. Try e.g. Potion, Super Potion, Antidote."
        pocket = self.reader.read_items_pocket()
        order = [i for i, _ in pocket]
        if iid not in order:
            have = ", ".join(ITEM_NAMES.get(i, f"#{i}") for i in order) or "nothing usable"
            return f"No {ITEM_NAMES.get(iid, item)} in your Items pocket (you have: {have})."
        target_index = order.index(iid)
        before_qty = dict(pocket).get(iid, 0)
        lead0 = self.reader.read_party()
        before_hp = lead0[0].current_hp if lead0 else 0
        before_status = lead0[0].status if lead0 else "healthy"
        idle = getattr(self.mgba, "wait_until_idle", None)
        if not self._open_battle_bag():
            return "Couldn't open the Bag in battle — try use_item again."
        if idle:
            idle()
        self.mgba.tick(12)
        SD = Addr.BAG_MENU_STATE
        for _ in range(8):                       # Left cycles Balls→Key Items→Items
            if self.mgba.read16(SD + Addr.BAG_POCKET_OFF) == Addr.BAG_POCKET_ITEMS:
                break
            self.mgba.tap("Left")
            if idle:
                idle()
            self.mgba.tick(8)
        if self.mgba.read16(SD + Addr.BAG_POCKET_OFF) != Addr.BAG_POCKET_ITEMS:
            self._exit_battle_menus()
            return "Couldn't reach the Items pocket — try use_item again."
        for _ in range(16):                      # walk the list cursor to the item
            cur = self.mgba.read8(Addr.BAG_LIST_CURSOR)
            if cur == target_index:
                break
            self.mgba.tap("Down" if cur < target_index else "Up")
            if idle:
                idle()
            self.mgba.tick(6)
        if self.mgba.read8(Addr.BAG_LIST_CURSOR) != target_index:
            self._exit_battle_menus()
            return f"Couldn't select {ITEM_NAMES.get(iid, item)} in the bag — try again."

        def used() -> bool:
            pk = self.reader.read_party()
            p = pk[0] if pk else None
            qty = dict(self.reader.read_items_pocket()).get(iid, 0)
            return (qty < before_qty) or (p is not None and (
                p.current_hp > before_hp
                or (before_status != "healthy" and p.status == "healthy")))

        # Select → USE (default) → party menu (lead is the default slot) → confirm text.
        # Self-verifying A presses: a dropped input in the chain just costs another press
        # instead of stranding us, and we stop the instant the item takes effect.
        for _ in range(16):
            if used():
                break
            self.mgba.tap("A")
            if idle:
                idle()
            self.mgba.tick(12)
        self._exit_battle_menus()
        if not used():
            return f"Couldn't use the {ITEM_NAMES.get(iid, item)} — you're back in the battle; try again."
        p = self.reader.read_party()[0]
        gained = p.current_hp - before_hp
        if gained > 0:
            return f"Used {ITEM_NAMES.get(iid, item)} — {p.species_name or 'lead'} healed +{gained} HP ({p.current_hp}/{p.max_hp})."
        if before_status != "healthy" and p.status == "healthy":
            return f"Used {ITEM_NAMES.get(iid, item)} — cured {p.species_name or 'lead'}'s {before_status}."
        return f"Used {ITEM_NAMES.get(iid, item)}."

    def _exit_battle_menus(self) -> None:
        """Back out of any Bag / context / prompt menu until we're on solid ground
        (IN_BATTLE or OVERWORLD), so a catch attempt never strands the agent. Settles
        before each press (menu inputs drop mid-animation) and tries B then A."""
        from game.state import GameContext
        idle = getattr(self.mgba, "wait_until_idle", None)
        for _ in range(14):
            if self.reader.detect_context() in (GameContext.IN_BATTLE, GameContext.OVERWORLD):
                return
            if idle:
                idle()
            self.mgba.tap("B")
            self.mgba.tick(8)
            if self.reader.detect_context() in (GameContext.IN_BATTLE, GameContext.OVERWORLD):
                return
            self.mgba.tap("A")
            self.mgba.tick(8)

    @staticmethod
    def _best_damaging_move(move_names, pp) -> str | None:
        """From parallel (move_names, pp) lists, the highest-power move that still has PP,
        or (if none has listed power) the first move with PP. None only if every move is
        out of PP. Empty slots (name "") are skipped, so a mon with <4 moves is safe."""
        from knowledge.leafgreen_data import MOVE_POWER
        best, best_pow = None, 0
        for name, p in zip(move_names, pp):
            if not name or p <= 0:
                continue
            pw = MOVE_POWER.get(name, 0)
            if pw > best_pow:
                best, best_pow = name, pw
        if best is not None:
            return best
        for name, p in zip(move_names, pp):   # fallback: any move with PP
            if name and p > 0:
                return name
        return None

    def _auto_fight(self) -> None:
        """Fight the current battle to the end with the best damaging move each turn."""
        from game.state import GameContext
        for _ in range(24):
            if self._maybe_drive_learn():      # a KO offered a level-up move
                continue
            if self.reader.detect_context() != GameContext.IN_BATTLE:
                break
            # Pick from the ACTIVE battler's moves (gBattleMons[0]), not the lead — the
            # mon fighting may be a switched-in / sent-out teammate with a different set.
            _ids, names, pp = self.reader.read_active_battle_moves()
            mv = self._best_damaging_move(names, pp)
            if mv:
                self._use_move(mv)
            else:
                self._battle_press("A")   # no PP → Struggle / advance
        self._settle_evolution()   # let a level-up evolution play out (A, never B)

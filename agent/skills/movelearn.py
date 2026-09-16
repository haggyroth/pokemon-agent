"""Level-up move-learn driver: frame-stepped, never cripples the moveset.
See agent.lm_studio_client.AgentClient (which inherits MoveLearnMixin)."""


class MoveLearnMixin:
    # Arming (see _maybe_drive_learn): a move-learn prompt only follows a level-up,
    # but gMoveToLearn LINGERS after one (a declined move stays "offered" forever).
    # We arm on a lead level-up edge and disarm after driving, so the driver never
    # re-engages on the stale value mid-battle (which starved use_move of a clean
    # move menu during Brock's Onix and forfeited the gym).
    _learn_armed = False
    _lead_level_seen = None
    # The last move-offer id we already resolved (declined/accepted). gMoveToLearn
    # AND learnMoveState both LINGER after a decline, so _delete_box_live() keeps
    # reading a phantom box every turn — which made use_move re-decline the same
    # move instead of attacking, looping the whole battle. We refuse to re-drive an
    # offer whose id we've already handled until it actually clears.
    _offer_resolved = 0


    # ── Level-up move learning (frame-stepped driver: never cripple the moveset) ──
    def _offered_move(self) -> int:
        """The move id a level-up is offering the lead right now, or 0. gMoveToLearn
        is only meaningful while a delete box is genuinely live — a valid id the lead
        does not already know (it goes stale between prompts, holding the last one)."""
        from game.constants import Addr
        ml = self.mgba.read16(Addr.MOVE_TO_LEARN)
        if not (1 <= ml <= 559):
            return 0
        party = self.reader.read_party()
        if not party:
            return 0
        ids = party[0].move_ids
        return ml if (len(ids) == 4 and all(1 <= i <= 559 for i in ids) and ml not in ids) else 0

    def _delete_box_live(self) -> bool:
        """True iff a 'Delete a move to make room?' box is up and WAITING for input
        (learnMoveState == 1 during a battle, offering a genuinely new move). Because
        the driver advances text in small steps and checks this before every A, it
        catches the box at state 1 and never mashes it to YES (state 2)."""
        from game.constants import Addr
        return (self.mgba.read8(Addr.LEARN_MOVE_STATE) == 1
                and self.mgba.read32(Addr.GMAIN_CALLBACK2) == Addr.CB2_BATTLE
                and self._offered_move() != 0)

    def _resolve_move_learn(self) -> str | None:
        """At a LIVE delete box, apply the forget policy: accept only when the chosen
        slot is 0 (reliable — the summary cursor defaults there); otherwise decline
        (policy says keep, or wants a slot 1-3 we can't reach deterministically). Never
        forgets the wrong move / never cripples. Returns a short note."""
        from knowledge.movelearn import choose_move_to_forget
        from game.constants import MOVE_NAMES
        party = self.reader.read_party()
        cur = party[0].move_names if party else []
        ml = self._offered_move()
        new_name = MOVE_NAMES.get(ml, f"move {ml}")
        slot = choose_move_to_forget(cur, new_name) if len(cur) == 4 else None
        if slot == 0:
            self._accept_forget_slot0()
            return f"learned {new_name} (forgot {cur[0]})"
        self._decline_at_box()
        if slot is None:
            return f"declined {new_name} (kept current moves — avoids losing a damaging move / stacking status)"
        return f"kept current moves rather than forget {cur[slot]} for {new_name}"

    def _wait_idle(self) -> None:
        fn = getattr(self.mgba, "wait_until_idle", None)
        if fn:
            fn()

    def _press_until_lms_leaves(self, button: str, val: int, cap: int = 8) -> bool:
        """Press `button` at an interactive box until learnMoveState leaves `val` — i.e.
        until that box consumed the input — then return IMMEDIATELY. After pressing we
        poll frame by frame and bail the instant the state changes, so we never keep
        pressing into the NEXT box (the following prompt is also lms==1: e.g. the give-up
        box and the next move's delete box both read 1; over-pressing A there would
        accept the next move). Retries only if the press was dropped (lms still == val)."""
        from game.constants import Addr
        for _ in range(cap):
            self._wait_idle()
            if self.mgba.read8(Addr.LEARN_MOVE_STATE) != val:
                return True
            self.mgba.tap(button)
            for _ in range(8):
                self.mgba.tick(1)
                if self.mgba.read8(Addr.LEARN_MOVE_STATE) != val:
                    return True
        return self.mgba.read8(Addr.LEARN_MOVE_STATE) != val

    def _decline_at_box(self) -> None:
        """Decline the learn from a live delete box, per the decomp flow (verified
        live): B at the 'Delete a move?' box (cursor default YES) → learnMoveState 4 →
        a 'Stop learning X?' message → the 'Give up learning?' box (learnMoveState back
        to 1, cursor default YES) where A confirms the decline.

        KEY subtlety (decomp Cmd_yesnoboxstoplearningmove): confirming the give-up box
        with A advances the battle-script pointer but does NOT change learnMoveState —
        lms lingers at 1. So we cannot gate the give-up A on "lms leaves 1" (it never
        does); that over-presses A straight into the NEXT move's delete box and accepts
        it. Instead gate on the OFFERED move changing (the script has moved on to the
        next level-up move, or the battle ended) and stop the instant it does."""
        from game.constants import Addr
        from game.state import GameContext
        LMS = Addr.LEARN_MOVE_STATE
        off0 = self._offered_move()
        # Phase 1 — reach and decline the REAL delete box by mashing B until lms==4.
        # This is the robust part: B advances text and, at the delete box, declines it
        # (→ lms 4); on a lingering lms==1 (left over from a previous move's give-up box,
        # which never resets lms) B does nothing. Because we never press A here, there
        # is zero risk of accidentally ACCEPTING a box while walking through the stale
        # state to the real one.
        for _ in range(50):
            if self.mgba.read8(LMS) == 4:
                break
            if self._offered_move() != off0 or self.reader.detect_context() == GameContext.OVERWORLD:
                return
            self._wait_idle()
            self.mgba.tap("B")
            self.mgba.tick(3)
        # Phase 2 — confirm the give-up. From lms==4 the script prints "Stop learning
        # X?" then shows the give-up box (cursor default YES) where A declines. A also
        # just advances the surrounding text, and confirming the give-up does NOT change
        # lms (it advances the script pointer), so we gate on the OFFERED move changing
        # (next level-up move) / battle end — and stop the instant it does, so A never
        # bleeds into the next move's delete box (which would accept it).
        for _ in range(20):
            if self._offered_move() != off0 or self.reader.detect_context() == GameContext.OVERWORLD:
                return
            self._wait_idle()
            self.mgba.tap("A")
            for _ in range(8):
                self.mgba.tick(1)
                if self._offered_move() != off0 or self.reader.detect_context() == GameContext.OVERWORLD:
                    return

    def _accept_forget_slot0(self) -> None:
        """Accept the learn and forget slot 0 (the summary cursor's default position),
        so no summary navigation is needed. A at the delete box (cursor YES) → summary
        → A selects the top move → the '1,2,3 poof!' result advances back to battle."""
        from game.constants import Addr
        self._press_until_lms_leaves("A", 1)          # accept the delete box → lms 2
        # Wait for the summary to open (callback2 leaves the battle main callback).
        for _ in range(15):
            if self.mgba.read32(Addr.GMAIN_CALLBACK2) != Addr.CB2_BATTLE:
                break
            self._wait_idle()
            self.mgba.tick(4)
        self.mgba.tick(24)   # settle the fade-in (A ignored mid-fade)
        # A selects slot 0; then advance the forgot/learned text back to the battle.
        for _ in range(20):
            if self.mgba.read32(Addr.GMAIN_CALLBACK2) == Addr.CB2_BATTLE and not self._delete_box_live():
                break
            self._wait_idle()
            self.mgba.tap("A")
            self.mgba.tick(6)

    def _maybe_drive_learn(self) -> str | None:
        """If a level-up is offering the lead a new move, take over and drive the whole
        move-learn flow carefully per policy. Returns a note if it did, else None. Cheap
        no-op on a normal turn. This is the single entry point; it's called wherever a
        battle would otherwise press A into the box.

        Gating: gMoveToLearn is set ~16 frames BEFORE the interactive delete box (good
        for early, un-mashed detection) but it also LINGERS afterward — a DECLINED move
        stays "offered" for the rest of the battle. Detecting on that alone made the
        driver re-engage every turn of Brock's Onix and starve use_move of a move menu
        (it forfeited the gym at 0 badges). Since a move-learn only ever follows a
        level-up, we ARM on a lead level-up edge and DISARM once we've driven the offer,
        so a stale gMoveToLearn can't re-trigger mid-battle. As a safety net we also
        engage when a delete box is live RIGHT NOW (learnMoveState == 1). BUT that state
        ALSO lingers after a decline (the 'give up learning?' confirm advances the script
        without resetting it), so _delete_box_live() reads a phantom box every subsequent
        turn — which looped use_move on 'declined X' instead of attacking for a whole
        trainer gauntlet. Guard: never re-drive an offer id we've already resolved until
        it clears (a genuinely new move has a different gMoveToLearn id)."""
        party = self.reader.read_party()
        lvl = party[0].level if party else 0
        if self._lead_level_seen is not None and lvl > self._lead_level_seen:
            self._learn_armed = True     # a level-up just happened → a learn may be pending
        self._lead_level_seen = lvl
        off = self._offered_move()
        if off == 0:
            self._offer_resolved = 0     # offer cleared → a future offer is fresh again
            return None
        if off == self._offer_resolved:
            return None      # this exact offer already declined/accepted; it's lingering
        if not self._learn_armed and not self._delete_box_live():
            return None      # not armed and no box on screen → ignore a lingering offer
        note = self._drive_pending_learn()
        self._learn_armed = False
        # Remember whatever offer still lingers now, so we don't re-drive it next turn.
        # (Read AFTER driving: back-to-back same-level learns leave the LAST move's id.)
        self._offer_resolved = self._offered_move()
        return note

    def _drive_pending_learn(self) -> str | None:
        """Frame-step the level-up move-learn flow to completion, resolving each delete
        box per policy (decline, or accept only when the chosen slot is 0). Entered only
        with a move genuinely pending. Advances in SMALL steps so a box halts us at the
        ~2-frame interactive window (lms==1) instead of being mashed; handles back-to-
        back same-level learns (Bulbasaur L15). Terminates on the battle's own state —
        a normal input menu or the overworld — never on the lingering learnMoveState."""
        from game.state import GameContext
        from game.constants import Addr
        note = None
        # Iterations since we last resolved a box. We CANNOT terminate on
        # gBattlerControllerFuncs (CHOOSE_ACTION/MOVE): that value goes STALE during the
        # end-of-battle victory/level-up sequence (it reads CHOOSE_ACTION even though no
        # menu is up), which bailed the driver before the box ever appeared. Instead we
        # end on the overworld (wild battle) or, for a battle that continues (trainer),
        # when no further box has appeared for a while — the learn flow is over.
        idle = 0
        for _ in range(300):
            if self._delete_box_live():
                n = self._resolve_move_learn()
                note = f"{note}; {n}" if note else n
                idle = 0
                continue
            if self.reader.detect_context() == GameContext.OVERWORLD:
                return note   # battle ended (a box lives in CB2_BATTLE, so only the
                              # overworld — not the stale controller func — ends the flow)
            idle += 1
            if idle > 24:
                return note   # no further box appeared — the learn flow is done and the
                              # battle has resumed (trainer battle continues past it)
            # Advance the "wants to learn"/result text one step. wait_until_idle can
            # land us exactly on a freshly-interactive box, so re-check lms after it
            # and bail to the top (to resolve) rather than pressing A — otherwise the A
            # bleeds through the ~2-frame lms==1 window as an accept. After pressing,
            # watch frame by frame so the next A never lands on a box either.
            self._wait_idle()
            if self.mgba.read8(Addr.LEARN_MOVE_STATE) == 1:
                continue
            self.mgba.tap("A")
            for _ in range(6):
                self.mgba.tick(1)
                if self.mgba.read8(Addr.LEARN_MOVE_STATE) == 1:
                    break
        return note

"""Regressions found in watched runs, replayed on the real ROM (see tests/live/README.md)."""
import json

from game.state import GameContext


def test_grind_balance_never_spins_with_attacks_out_of_pp(live, monkeypatch):
    """Run #2: attacks at 0 PP → the old picker spammed Growl/Harden forever. Now: heals itself,
    switches, finishes — and returns (the watchdog would cut it off otherwise)."""
    from agent import budgets
    monkeypatch.setitem(budgets.BUDGETS, "grind", (60_000, 15_000))           # keep the test short
    live.load("threemon")
    live.patch_mon(0, [33, 45, 73, 22], [0, 40, 0, 0], level=19, exp=4575)   # attacks gone, L19
    live.patch_mon(2, [106, 81, 0, 0], [30, 40, 0, 0])                         # Harden-only trainee
    out = live.c._execute("grind", json.dumps({}))
    assert "no progress" not in out, out          # a stall = the bug; a plain time limit is fine
    assert "heal" in out or "time limit" in out or "Party balanced" in out or "Training progress" in out, out


def test_watchdog_cuts_off_the_old_status_spam_bug(live, monkeypatch):
    """Re-introduce the original bug (status-move fallback, no heal): the watchdog must end the call."""
    import knowledge.party as kp
    from agent.lm_studio_client import AgentClient
    live.load("threemon")
    live.patch_mon(0, [33, 45, 73, 22], [0, 40, 0, 0], level=19, exp=4575)
    live.patch_mon(1, None, None, level=19, exp=6859)           # nobody lags → the Growl-only ace fights the grass itself
    live.patch_mon(2, None, None, level=19, exp=6859)
    live.heal_hp()

    def old_picker(names, pp, *a):
        return next((n for n, p in zip(names, pp) if n and p > 0), None)
    monkeypatch.setattr(AgentClient, "_best_damaging_move", staticmethod(old_picker))
    monkeypatch.setattr(live.c, "_no_attack_turn", lambda: live.c._use_move("Growl"))
    monkeypatch.setattr(kp, "can_attack", lambda m: True)
    monkeypatch.setattr(kp, "attack_pp", lambda m: 99)
    out = live.c._execute("grind", json.dumps({"level": 40}))
    assert "was stopped" in out and "no progress" in out, out


def test_catch_vets_the_nickname_then_names_the_catch(live):
    live.load("threemon")
    assert live.wild_battle()
    foe = live.r.read_enemy_lead().species_name
    balls = live.c._ball_count()
    out = live.c._catch(foe + "1")
    assert out.startswith("No ball thrown") and live.c._ball_count() == balls      # refused, free
    for _ in range(10):
        live.set_foe_hp(1)
        out = live.c._catch("Mr. Zap!")
        if "Gotcha" in out:
            break
    assert "Gotcha" in out and "Mr. Zap!" in out, out
    assert any(p.nickname == "Mr. Zap!" for p in live.r.read_party())


def test_broke_free_ball_returns_without_a_long_menu_wait(live):
    live.load("threemon")
    assert live.wild_battle()
    taps = {"B": 0}
    orig = live.m.tap

    def tap(b):
        taps[b] = taps.get(b, 0) + 1
        return orig(b)
    live.m.tap = tap
    try:
        for _ in range(8):
            if live.r.detect_context() != GameContext.IN_BATTLE:
                break
            live.set_foe_hp(live.m.read16(0x02023BE4 + 0x58 + 0x2C))      # full HP: likely to break free
            taps["B"] = 0
            out = live.c._catch("Wiggles")
            if "broke free" in out:
                assert taps["B"] < 60, f"waited through {taps['B']} B presses at the menu"
                return
    finally:
        live.m.tap = orig
    # every throw succeeded or the foe fled: nothing to assert about the break-free path


def test_disabled_move_is_refused_without_pressing_anything(live):
    live.load("disabled")
    if live.r.detect_context() != GameContext.IN_BATTLE:
        import pytest
        pytest.skip("fixture is not mid-battle")
    out = live.c._use_move("Tackle")
    assert "DISABLED" in out or "refused" in out, out


def test_catching_with_a_full_party_reports_the_box(live):
    from game.constants import Addr
    live.load("threemon")
    for slot in (3, 4, 5):                                   # clone the last mon up to a full party
        for i in range(100):
            live.m.write8(Addr.PARTY_DATA + 100 * slot + i, live.m.read8(Addr.PARTY_DATA + 200 + i))
    live.m.write8(0x02024284 - 4, 6)
    live.heal_hp()
    assert live.wild_battle()
    for _ in range(10):
        live.set_foe_hp(1)
        out = live.c._catch("Box Buddy")
        if "Gotcha" in out:
            break
    assert "PC box" in out, out
    assert len(live.r.read_party()) == 6 and live.r.detect_context() == GameContext.OVERWORLD


def test_get_ss_ticket_then_cross_cerulean_to_vermilion(live):
    """Bill's quest end to end (post-Misty fixture), then the Underground Path to Vermilion — covers the
    Saffron-shell routing fix and the directional stairs probe."""
    live.load("post_misty")
    out = live.c._execute("get_ss_ticket", "{}")
    assert "Got the SS Ticket" in out or "already have" in out, out
    assert live.c._has_ss_ticket()
    for _ in range(6):
        out = live.c._execute("go_to", json.dumps({"destination": "Vermilion City"}))
        if live.r.read_current_map() == (3, 5):
            break
        if "heal" in out or "Lost" in out:
            live.heal_hp()                      # a Route 5/6 trainer beat us: top up and retry
    assert live.r.read_current_map() == (3, 5), out


def test_get_cut_then_enter_the_vermilion_gym_and_open_the_locks(live):
    """S.S. Anne → Captain → HM01 → teach Cut → go_to Gym cuts the door tree → trash-can switches read from
    memory open the electric locks."""
    live.load("vermilion")
    live.c.ltm.data["gyms_beaten"] = ["Brock", "Misty"]
    out = live.c._execute("get_cut", "{}")
    assert "Got HM01" in out or "already knows Cut" in out, out
    assert live.c._knows_cut()
    for _ in range(6):
        live.c._execute("go_to", json.dumps({"destination": "Gym", "force": True}))
        if live.r.read_current_map() == (9, 6):
            break
    assert live.r.read_current_map() == (9, 6)
    res = live.c._solve_vermilion_switches()
    assert res.startswith("Both"), res
    assert live.r.read_flag(0x264)


def test_reorder_party_and_set_lead_drive_the_party_menu(live):
    live.load("threemon")
    out = live.c._execute("reorder_party", json.dumps({"first": "1", "second": "3"}))
    assert out.startswith("Swapped"), out
    assert [p.species_name for p in live.r.read_party()][0] == "Caterpie"
    out = live.c._execute("set_lead", json.dumps({"pokemon": "Pikachu"}))
    assert out.startswith("Swapped") and live.r.read_party()[0].species_name == "Pikachu", out
    assert live.r.detect_context() == GameContext.OVERWORLD


def test_first_arrival_in_a_town_heals_at_its_center_once(live):
    live.load("post_misty")
    live.c.ltm.data["pc_visited"] = []
    out = live.c._execute("go_to", json.dumps({"destination": "Cerulean City"}))
    assert out.startswith("Arrived"), out
    assert live.c.ltm.data["pc_visited"] == ["3,3"]


def test_grind_catches_a_worthwhile_wild_pokemon_and_names_it(live, monkeypatch):
    import knowledge.catch_policy as cp
    monkeypatch.setattr(cp, "evaluate", lambda party, sid, lvl, max_team=6, dex_owned=None: cp.Verdict(True, "test", 0))
    live.load("threemon")
    balls = live.c._ball_count()
    out = live.c._execute("grind", json.dumps({"level": 9}))
    assert "caught" in out, out
    assert live.c._ball_count() < balls and len(live.r.read_party()) > 3
    assert live.r.detect_context() == GameContext.OVERWORLD


def test_leaving_the_cerulean_mart_toward_the_north_does_not_loop_through_the_door(live):
    """Run 20261114-101556: from inside the Mart, go_to a northern route walked out, picked an unreachable
    north-edge tile in another region, then 'stepped off the edge' back through the Mart door — forever."""
    live.load("post_misty")
    live.c.ltm.data["gyms_beaten"] = ["Brock"]
    assert live.c._execute("go_to", json.dumps({"destination": "Mart"})).startswith("Arrived")
    out = live.c._execute("go_to", json.dumps({"destination": "Route 24"}))
    assert out.startswith("Arrived") and live.r.read_current_map() == (3, 43), out


def test_level_up_prompt_can_forget_any_slot(live):
    """The old driver could only forget slot 0 and declined everything else (SolarBeam / Razor Leaf refused)."""
    live.load("delete_box")
    for slot, expect in ((2, ["Tackle", "Growl", "Vine Whip", "Scratch"]), (3, ["Tackle", "Growl", "Leech Seed", "Vine Whip"])):
        live.m.load_state_file(str(live.dir / "delete_box.ss1"))
        live.m.tick(10)
        assert live.c._accept_forget_slot(slot)
        assert live.r.read_party()[0].move_names == expect


def test_balance_training_keeps_the_ace_from_stealing_xp(live, monkeypatch):
    from agent import budgets
    monkeypatch.setitem(budgets.BUDGETS, "grind", (90_000, 15_000))
    live.load("threemon")
    live.patch_mon(0, [33, 45, 73, 22], [35, 40, 10, 25], level=19, exp=4575)
    out = live.c._execute("grind", json.dumps({"catch": False}))
    party = live.r.read_party()
    assert party[0].species_name == "Bulbasaur" and party[0].level == 19, (out, [(p.species_name, p.level, p.current_hp) for p in party])
    assert max(p.level for p in party[1:]) > 5                                  # the trainees actually levelled


def test_pc_deposit_list_and_withdraw_through_the_real_menus(live):
    live.load("threemon")
    out = live.c._execute("pc_deposit", json.dumps({"pokemon": "Pikachu"}))
    assert out.startswith("Deposited") and len(live.r.read_party()) == 2, out
    assert live.r.detect_context() == GameContext.OVERWORLD
    assert "Pikachu" in live.c._execute("pc_boxes", "{}")
    out = live.c._execute("pc_withdraw", json.dumps({"pokemon": "pikachu"}))
    assert out.startswith("Withdrew") and len(live.r.read_party()) == 3, out
    assert live.r.read_boxes() == []


def test_pc_withdraw_from_another_box_and_grid_slot(live):
    live.load("threemon")
    assert live.c._execute("pc_deposit", json.dumps({"pokemon": "Caterpie"})).startswith("Deposited")
    base = live.r._storage_ptr()
    src, dst = base + 4, base + 4 + (1 * 30 + 14) * 80          # box 1 slot 0 → box 2 slot 14 (col 2, row 2)
    for i in range(80):
        live.m.write8(dst + i, live.m.read8(src + i))
        live.m.write8(src + i, 0)
    out = live.c._execute("pc_withdraw", json.dumps({"pokemon": "2:14"}))
    assert out.startswith("Withdrew") and live.r.read_current_box() == 1, out
    assert [p.species_name for p in live.r.read_party()][-1] == "Caterpie"


def test_tagged_out_trainee_shares_the_xp_and_is_never_swapped_back(live, monkeypatch):
    """Watched run: the trainee led, the ace was switched in, then the loop switched the trainee BACK in and
    it was knocked out for no XP. Now: trainee leads, tags out on turn one, the ace finishes; the trainee
    gains experience and keeps its HP."""
    live.load("threemon")
    live.patch_mon(0, [33, 45, 73, 22], [35, 40, 10, 25], level=40, exp=56660)       # Bulbasaur L40: the ace
    live.patch_mon(1, None, None, level=3, exp=27)
    live.patch_mon(2, None, None, level=3, exp=27)
    live.heal_hp()
    assert live.c._lead_trainee(live.r.read_party()[1])                                # a L3 leads
    lead = live.r.read_party()[0]
    sig = (lead.species_id, lead.max_hp)
    exp0 = live.read_exp(0)
    switches = []
    orig = live.c._switch_pokemon
    monkeypatch.setattr(live.c, "_switch_pokemon", lambda t, *a, **k: (switches.append(t), orig(t, *a, **k))[1])
    monkeypatch.setattr(live.c, "_grind_try_catch", lambda: None)
    # a foe above the trainee's level+2 is guaranteed to be "tough" for a L3 → expect a turn-one tag-out
    assert live.wild_battle(), "no wild battle found"
    hp0 = live.r.read_party()[0].current_hp
    live.c._train_fight(sig)
    assert len(switches) <= 1, switches                                                # one tag-out, no swap back
    assert live.read_exp(0) > exp0 or live.r.read_party()[0].level > 3                # the trainee got XP
    if switches:
        assert live.r.read_party()[0].current_hp >= hp0 - 1                            # …without being hurt


def test_travel_battle_catches_a_worthwhile_wild_pokemon_instead_of_fleeing(live, monkeypatch):
    """The team stalled at four because go_to fled everything after a single 'offer' and never past 4 members."""
    import knowledge.catch_policy as cp
    monkeypatch.setattr(cp, "evaluate", lambda party, sid, lvl, max_team=6, dex_owned=None: cp.Verdict(True, "test", 0))
    live.load("threemon")
    n, balls = len(live.r.read_party()), live.c._ball_count()
    assert live.wild_battle(), "no wild battle found"
    stop = live.c._handle_travel_battle("somewhere")
    assert stop is None
    assert live.c.__dict__.get("_travel_caught"), "nothing was caught"
    assert len(live.r.read_party()) == n + 1 and live.c._ball_count() < balls
    assert live.r.detect_context() == GameContext.OVERWORLD

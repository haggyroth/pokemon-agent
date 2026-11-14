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

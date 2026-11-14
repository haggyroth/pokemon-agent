"""The rule-based LLM stand-in (agent/scripted_policy.py) used for zero-token end-to-end runs."""
import json
from types import SimpleNamespace

from agent.scripted_policy import FakeLLM, ScriptedPolicy, _response
from game.state import GameContext, PokemonStatus


def mon(level, hp=30, max_hp=30, moves=("Tackle",), pp=(30,)):
    return PokemonStatus(slot=0, level=level, current_hp=hp, max_hp=max_hp, status="healthy",
                         species_id=1, species_name="Bulbasaur", move_names=list(moves), pp=list(pp))


def policy(ctx, party, gyms_beaten=(), cur_map=(3, 1), needs_heal=False, ticket=True, knows_cut=True):
    reader = SimpleNamespace(detect_context=lambda: ctx, read_party=lambda: party,
                             read_current_map=lambda: cur_map)
    client = SimpleNamespace(_party_needs_heal=lambda: needs_heal, _has_ss_ticket=lambda: ticket,
                             _knows_cut=lambda: knows_cut)
    rt = SimpleNamespace(client=client, reader=reader, mgba=SimpleNamespace(),
                         ltm=SimpleNamespace(data={"gyms_beaten": list(gyms_beaten)}))
    return ScriptedPolicy(rt)


def test_response_looks_like_an_openai_tool_call():
    r = _response("", "grind", {"level": 13})
    tc = r.choices[0].message.tool_calls[0]
    assert tc.function.name == "grind" and json.loads(tc.function.arguments) == {"level": 13}
    assert tc.model_dump()["function"]["name"] == "grind" and tc.id
    assert _response("done").choices[0].message.tool_calls is None


def test_after_a_tool_result_it_hands_control_back_with_plain_text():
    p = policy(GameContext.OVERWORLD, [mon(8)])
    llm = FakeLLM(p)
    msg = llm._create(messages=[{"role": "user", "content": "obs"},
                                {"role": "tool", "content": "ok"}]).choices[0].message
    assert msg.tool_calls is None


def test_menus_and_dialogs_are_cleared_first():
    assert policy(GameContext.IN_MENU, [mon(8)]).decide()[0] == "close_menus"
    assert policy(GameContext.DIALOG_OPEN, [mon(8)]).decide()[0] == "advance_dialog"


def test_underlevelled_lead_grinds_to_the_gym_target():
    assert policy(GameContext.OVERWORLD, [mon(8)]).decide() == ("grind", {"level": 14})


def test_hurt_party_heals_before_anything_else():
    p = policy(GameContext.OVERWORLD, [mon(8, hp=5)], needs_heal=True)
    assert p.decide()[0] == "heal"


def test_ready_lead_goes_to_the_gym_then_challenges():
    assert policy(GameContext.OVERWORLD, [mon(15)]).decide() == ("go_to", {"destination": "Gym"})
    from knowledge.leafgreen_data import GYM_MAP_LEADER
    brock_map = next(m for m, l in GYM_MAP_LEADER.items() if l == "Brock")
    assert policy(GameContext.OVERWORLD, [mon(15)], cur_map=brock_map).decide() == ("challenge_leader", {})


def test_next_gym_advances_after_a_badge():
    p = policy(GameContext.OVERWORLD, [mon(15)], gyms_beaten=["Brock"])
    assert p.decide() == ("grind", {"level": 21})        # Misty wants a stronger lead


def test_after_misty_it_fetches_the_ss_ticket_first():
    p = policy(GameContext.OVERWORLD, [mon(30)], gyms_beaten=["Brock", "Misty"], ticket=False)
    assert p.decide() == ("get_ss_ticket", {})
    hurt = policy(GameContext.OVERWORLD, [mon(30, hp=20)], gyms_beaten=["Brock", "Misty"], ticket=False)
    assert hurt.decide() == ("heal", {})            # the rival fight is on the way: go in healthy
    p = policy(GameContext.OVERWORLD, [mon(30)], gyms_beaten=["Brock", "Misty"], ticket=True)
    assert p.decide() == ("go_to", {"destination": "Gym"})


def test_with_the_ticket_but_no_cut_it_gets_cut_before_the_gym():
    p = policy(GameContext.OVERWORLD, [mon(30)], gyms_beaten=["Brock", "Misty"], ticket=True, knows_cut=False)
    assert p.decide() == ("get_cut", {})

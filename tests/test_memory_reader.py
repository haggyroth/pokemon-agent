"""LeafGreenReader against a fake memory — party, badges, context, diff."""
from game.constants import Addr
from game.memory_reader import LeafGreenReader
from game.state import GameContext
from conftest import FakeClient, build_party_mon, stage_overworld


def make_reader(fc: FakeClient) -> LeafGreenReader:
    return LeafGreenReader(fc, decrypt=True)


def test_read_badges_popcount():
    fc = FakeClient()
    fc.set8(Addr.BADGES, 0b1011)  # 3 bits set
    count, bits = make_reader(fc).read_badges()
    assert count == 3
    assert bits == 0b1011


def test_read_party_skips_empty_slots_and_decodes():
    fc = FakeClient()
    mon0 = build_party_mon(0x1234, 0x9999, level=12, cur_hp=25, max_hp=40,
                           species=1, moves=(33, 0, 0, 0), pp=(35, 0, 0, 0))
    mon1 = build_party_mon(0x5678, 0xAAAA, level=7, cur_hp=0, max_hp=22,
                           species=4, status_word=(1 << 6))  # paralyzed, fainted
    fc.set_bytes(Addr.PARTY_DATA + 0 * 100, mon0)
    fc.set_bytes(Addr.PARTY_DATA + 1 * 100, mon1)
    # slots 2-5 left at level 0 → empty, must be skipped

    party = make_reader(fc).read_party()
    assert len(party) == 2
    assert party[0].level == 12
    assert party[0].current_hp == 25 and party[0].max_hp == 40
    assert party[0].species_id == 1
    assert party[0].move_ids[0] == 33
    assert party[1].level == 7
    assert party[1].is_fainted
    assert party[1].status == "paralyzed"


def test_detect_context_overworld():
    fc = FakeClient()
    stage_overworld(fc)
    assert make_reader(fc).detect_context() == GameContext.OVERWORLD


def test_detect_context_transitioning_on_fade():
    fc = FakeClient()
    stage_overworld(fc)
    fc.set8(Addr.SCREEN_FADE, 0x01)
    assert make_reader(fc).detect_context() == GameContext.TRANSITIONING


def test_detect_context_dialog():
    fc = FakeClient()
    stage_overworld(fc)
    fc.set8(Addr.SCRIPT_RAM, 1)
    assert make_reader(fc).detect_context() == GameContext.DIALOG_OPEN


def test_detect_context_start_menu():
    fc = FakeClient()
    stage_overworld(fc)
    fc.set32(Addr.START_MENU_CB, 0x0806F1F1)  # ROM pointer → Start menu open
    assert make_reader(fc).detect_context() == GameContext.IN_MENU


def test_non_pointer_menu_value_is_not_menu():
    # The quest-log state leaves a non-pointer value here; must NOT read IN_MENU.
    fc = FakeClient()
    stage_overworld(fc)
    fc.set32(Addr.START_MENU_CB, 0x0019000E)
    assert make_reader(fc).detect_context() == GameContext.OVERWORLD


def test_detect_context_battle():
    fc = FakeClient()
    fc.set32(Addr.GMAIN_CALLBACK2, Addr.CB2_BATTLE)  # battle dispatcher active
    assert make_reader(fc).detect_context() == GameContext.IN_BATTLE


def test_unknown_callback_is_transitioning():
    # Menus, warps, battle intro/outro use other callback2 values → TRANSITIONING.
    fc = FakeClient()
    fc.set32(Addr.GMAIN_CALLBACK2, 0x08000000)  # some other screen callback
    assert make_reader(fc).detect_context() == GameContext.TRANSITIONING


def test_post_battle_overworld_is_overworld():
    # Regression for the old bug: once the battle ends, callback2 returns to the
    # field value, so we must read OVERWORLD even though the old gBattleTypeFlags
    # address would still be non-zero (stale).
    fc = FakeClient()
    stage_overworld(fc)
    fc.set32(Addr.BATTLE_FLAGS, 0x04)  # stale leftover — must be ignored now
    assert make_reader(fc).detect_context() == GameContext.OVERWORLD


def test_read_state_and_player_pos():
    fc = FakeClient()
    stage_overworld(fc, x=9, y=14, map_bank=3, map_id=2)
    fc.set_bytes(Addr.PARTY_DATA, build_party_mon(0x1, 0x2, level=5, cur_hp=19, max_hp=19))
    st = make_reader(fc).read_state()
    assert st.context == GameContext.OVERWORLD
    assert st.player_x == 9 and st.player_y == 14
    assert st.map_bank == 3 and st.map_id == 2
    assert st.party_count == 1


def test_diff_detects_damage_level_and_badges():
    fc = FakeClient()
    stage_overworld(fc)
    fc.set_bytes(Addr.PARTY_DATA, build_party_mon(0x1, 0x2, level=5, cur_hp=20, max_hp=20))
    reader = make_reader(fc)
    before = reader.read_state()

    # Take damage + level up + earn a badge.
    fc.set_bytes(Addr.PARTY_DATA, build_party_mon(0x1, 0x2, level=6, cur_hp=8, max_hp=22))
    fc.set8(Addr.BADGES, 0b1)
    after = reader.read_state()

    d = reader.diff(before, after)
    assert 0 in d.hp_changed
    assert 0 in d.level_changed
    assert d.badges_changed
    assert d.anything_changed


def test_diff_none_before_is_empty():
    fc = FakeClient()
    stage_overworld(fc)
    fc.set_bytes(Addr.PARTY_DATA, build_party_mon(0x1, 0x2, level=5, cur_hp=20, max_hp=20))
    st = make_reader(fc).read_state()
    d = make_reader(fc).diff(None, st)
    assert not d.anything_changed

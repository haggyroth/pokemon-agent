"""LeafGreenReader against a fake memory — party, badges, context, diff."""
from game.constants import Addr
from game.memory_reader import LeafGreenReader
from game.state import GameContext
from conftest import FakeClient, build_party_mon, stage_overworld


def make_reader(fc: FakeClient) -> LeafGreenReader:
    return LeafGreenReader(fc, decrypt=True)


def test_read_badges_popcount():
    fc = FakeClient()
    sb = 0x02025540
    fc.set32(Addr.SAVEBLOCK1_PTR, sb)
    fc.set8(sb + Addr.BADGES_OFFSET, 0b1011)  # 3 bits set, via the live pointer
    count, bits = make_reader(fc).read_badges()
    assert count == 3
    assert bits == 0b1011


def test_read_badges_ignores_stale_fixed_address():
    # Regression: badges must follow the relocated SaveBlock1, not a fixed addr.
    # A non-zero byte at the old fixed location must NOT be read as a badge.
    fc = FakeClient()
    sb = 0x02025600                       # block relocated away from canonical base
    fc.set32(Addr.SAVEBLOCK1_PTR, sb)
    fc.set8(sb + Addr.BADGES_OFFSET, 0)   # true badges = 0
    fc.set8(Addr.BADGES, 0x04)            # stale garbage at the old fixed address
    count, bits = make_reader(fc).read_badges()
    assert (count, bits) == (0, 0)


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


def test_read_current_map_uses_dma_block_not_stale_parent():
    # Regression: the absolute MAP_BANK/MAP_ID stay on the parent outdoor map
    # (e.g. Pallet Town 3/0) while indoors. read_current_map must report the
    # TRUE current map from the DMA block at [PLAYER_PTR]+0x04/0x05.
    fc = FakeClient()
    stage_overworld(fc)                 # sets both to (3, 0)
    fc.set8(Addr.MAP_BANK, 3)           # parent stays Pallet Town...
    fc.set8(Addr.MAP_ID, 0)
    ptr = fc.read32(Addr.PLAYER_PTR)
    fc.set8(ptr + Addr.MAP_GROUP_OFFSET, 4)   # ...but we're really in the house
    fc.set8(ptr + Addr.MAP_NUM_OFFSET, 2)
    assert make_reader(fc).read_current_map() == (4, 2)
    assert make_reader(fc).read_state().map_bank == 4
    assert make_reader(fc).read_state().map_id == 2


def test_read_enemy_lead_decodes_opponent():
    fc = FakeClient()
    # gEnemyParty[0]: a Pidgey (species 16), L3, 16/16 HP
    fc.set_bytes(Addr.ENEMY_PARTY,
                 build_party_mon(0xABCD, 0x1234, level=3, cur_hp=16, max_hp=16,
                                 species=16, moves=(33, 0, 0, 0), pp=(35, 0, 0, 0)))
    enemy = make_reader(fc).read_enemy_lead()
    assert enemy is not None
    assert enemy.species_id == 16
    assert enemy.level == 3
    assert enemy.current_hp == 16 and enemy.max_hp == 16


def test_read_enemy_lead_none_when_empty():
    fc = FakeClient()  # ENEMY_PARTY slot is level 0 → no battle
    assert make_reader(fc).read_enemy_lead() is None


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
    # Overlay menu (Start/Save): field callback2, MENU_OPEN set, AND SCREEN_FADE
    # 1 while it is on screen. All three are needed — MENU_OPEN alone is
    # unreliable (it over-stays after a menu closes; see the stale regression).
    fc = FakeClient()
    stage_overworld(fc)
    fc.set8(Addr.MENU_OPEN, 1)
    fc.set8(Addr.SCREEN_FADE, 1)
    assert make_reader(fc).detect_context() == GameContext.IN_MENU


def test_detect_context_fullscreen_submenu():
    # Bag/Party/etc. swap callback2 to their own handler AND set MENU_OPEN.
    fc = FakeClient()
    fc.set32(Addr.GMAIN_CALLBACK2, 0x08107EB9)  # e.g. the Bag callback
    fc.set8(Addr.MENU_OPEN, 1)
    fc.set8(Addr.SCREEN_FADE, 1)
    assert make_reader(fc).detect_context() == GameContext.IN_MENU


def test_stale_menu_flag_after_close_is_overworld():
    # Regression for the phantom-menu trap: after a full-screen menu closes, the
    # game returns to the field callback and clears SCREEN_FADE, but MENU_OPEN can
    # stay 1 (stale). We must read OVERWORLD, not IN_MENU — otherwise the agent
    # "closes the menu" forever (this killed a real run).
    fc = FakeClient()
    stage_overworld(fc)
    fc.set8(Addr.MENU_OPEN, 1)     # stale leftover
    fc.set8(Addr.SCREEN_FADE, 0)   # nothing on screen → the menu really is closed
    assert make_reader(fc).detect_context() == GameContext.OVERWORLD


def test_stale_menu_flag_does_not_block_dialog():
    # Same stale MENU_OPEN, but a script/dialog is now running — must read
    # DIALOG_OPEN, not IN_MENU.
    fc = FakeClient()
    stage_overworld(fc)
    fc.set8(Addr.MENU_OPEN, 1)     # stale
    fc.set8(Addr.SCREEN_FADE, 0)
    fc.set8(Addr.SCRIPT_RAM, 1)
    assert make_reader(fc).detect_context() == GameContext.DIALOG_OPEN


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


def test_read_key_item_count():
    fc = FakeClient()
    sb = 0x02025544
    fc.set32(Addr.SAVEBLOCK1_PTR, sb)
    fc.set16(sb + Addr.KEY_ITEMS_OFFSET + 0, 366)  # occupied slot
    fc.set16(sb + Addr.KEY_ITEMS_OFFSET + 4, 361)  # occupied slot (Town Map)
    # remaining slots default to id 0 (empty)
    assert make_reader(fc).read_key_item_count() == 2


def test_key_item_count_zero_when_pointer_invalid():
    fc = FakeClient()
    fc.set32(Addr.SAVEBLOCK1_PTR, 0)  # not a valid EWRAM pointer
    assert make_reader(fc).read_key_item_count() == 0


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

    # Take damage + level up + earn a badge (badge via the live SaveBlock1 pointer).
    fc.set_bytes(Addr.PARTY_DATA, build_party_mon(0x1, 0x2, level=6, cur_hp=8, max_hp=22))
    fc.set8(fc.read32(Addr.SAVEBLOCK1_PTR) + Addr.BADGES_OFFSET, 0b1)
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

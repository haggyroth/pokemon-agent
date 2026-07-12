"""BattleJournal caches its parsed records (keyed on the file's mtime/size) so
get_loss_lessons — called every in-battle decision step — doesn't re-parse the whole
JSONL each tick (#70). Cache invalidates on append."""
from memory.battle_journal import BattleJournal, BattleRecord


def _rec(enemy="BROCK", outcome="loss", **kw):
    d = dict(timestamp="t", location="Pewter", enemy_name=enemy, enemy_level=14,
             player_lead="Bulbasaur", outcome=outcome, turns=3, moves_used=["Tackle"],
             hp_remaining_pct=0.0, reward=-1.0, notes="fainted")
    d.update(kw)
    return BattleRecord(**d)


def test_all_is_cached_between_calls(tmp_path):
    j = BattleJournal(path=tmp_path / "battles.jsonl")
    j.log(_rec())
    first = j._all()
    second = j._all()
    assert second is first            # same object → reused, not re-parsed


def test_append_invalidates_cache(tmp_path):
    j = BattleJournal(path=tmp_path / "battles.jsonl")
    j.log(_rec(turns=1))
    a = j._all()
    j.log(_rec(turns=2))
    b = j._all()
    assert b is not a                 # re-parsed after the append
    assert len(b) == 2 and [r.turns for r in b] == [1, 2]


def test_loss_lessons_still_correct(tmp_path):
    j = BattleJournal(path=tmp_path / "battles.jsonl")
    j.log(_rec(enemy="BROCK", outcome="win"))       # wins excluded
    j.log(_rec(enemy="BROCK", outcome="loss", notes="onix swept"))
    j.log(_rec(enemy="MISTY", outcome="loss"))      # different enemy excluded
    out = j.get_loss_lessons("BROCK")
    assert "Past losses against BROCK" in out and "onix swept" in out
    assert "MISTY" not in out
    assert j.get_loss_lessons("LT_SURGE") == ""     # no losses → empty


def test_missing_file_is_empty(tmp_path):
    j = BattleJournal(path=tmp_path / "nope.jsonl")
    assert j._all() == []
    assert j.get_loss_lessons("BROCK") == ""

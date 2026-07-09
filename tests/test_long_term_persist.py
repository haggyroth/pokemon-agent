"""Persistence robustness for LongTermMemory (#62).

progress.json is the only cross-session memory. save() must be atomic (a crash
mid-write must not truncate it) and _load() must tolerate a corrupt file instead
of crashing startup.
"""
import json
import memory.long_term as lt


def make_ltm(monkeypatch, tmp_path):
    monkeypatch.setattr(lt, "PROGRESS_PATH", tmp_path / "progress.json")
    return lt.LongTermMemory()


def test_save_then_reload_roundtrips(monkeypatch, tmp_path):
    ltm = make_ltm(monkeypatch, tmp_path)
    ltm.data["badges_earned"] = 3
    ltm.data["starter"] = "Bulbasaur"
    ltm.save()
    reloaded = lt.LongTermMemory()
    assert reloaded.data["badges_earned"] == 3
    assert reloaded.data["starter"] == "Bulbasaur"


def test_save_leaves_no_temp_file(monkeypatch, tmp_path):
    ltm = make_ltm(monkeypatch, tmp_path)
    ltm.save()
    # The atomic write renames the temp into place — nothing left behind.
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_save_is_valid_json_on_disk(monkeypatch, tmp_path):
    ltm = make_ltm(monkeypatch, tmp_path)
    ltm.data["towns_visited"] = ["Pallet Town"]
    ltm.save()
    on_disk = json.loads((tmp_path / "progress.json").read_text())
    assert on_disk["towns_visited"] == ["Pallet Town"]


def test_corrupt_file_recovers_to_defaults(monkeypatch, tmp_path):
    path = tmp_path / "progress.json"
    path.write_text('{"badges_earned": 3, TRUNCATED')  # invalid JSON
    monkeypatch.setattr(lt, "PROGRESS_PATH", path)
    ltm = lt.LongTermMemory()          # must not raise
    assert ltm.data["badges_earned"] == 0        # fell back to DEFAULTS
    assert ltm.data["milestones"] == []


def test_corrupt_file_is_renamed_aside(monkeypatch, tmp_path):
    path = tmp_path / "progress.json"
    path.write_text("not json at all")
    monkeypatch.setattr(lt, "PROGRESS_PATH", path)
    lt.LongTermMemory()
    # The bad file is moved to a .corrupt-*.bak sibling, not silently deleted.
    baks = list(tmp_path.glob("progress.json.corrupt-*.bak"))
    assert len(baks) == 1
    assert baks[0].read_text() == "not json at all"


def test_recovered_instance_can_save_again(monkeypatch, tmp_path):
    path = tmp_path / "progress.json"
    path.write_text("}{ broken")
    monkeypatch.setattr(lt, "PROGRESS_PATH", path)
    ltm = lt.LongTermMemory()
    ltm.data["badges_earned"] = 1
    ltm.save()                          # writing over the (renamed-away) path works
    assert json.loads(path.read_text())["badges_earned"] == 1

"""Badge reconciliation — RAM is the source of truth, LTM mirrors monotonically."""
import memory.long_term as lt
from knowledge.leafgreen_data import badges_in_bitmask


# ── Pure decoder ──────────────────────────────────────────────────────────────

def test_badges_in_bitmask_empty():
    assert badges_in_bitmask(0) == []


def test_badges_in_bitmask_maps_bits_to_leaders():
    got = badges_in_bitmask(0b11)  # Brock (bit 0) + Misty (bit 1)
    assert [b for b, _, _ in got] == [0, 1]
    assert ("Brock" in got[0]) and got[0][2] == "beat_brock"
    assert ("Misty" in got[1]) and got[1][2] == "beat_misty"


def test_badges_in_bitmask_all_eight():
    assert len(badges_in_bitmask(0xFF)) == 8


# ── LTM reconciliation ────────────────────────────────────────────────────────

def make_ltm(monkeypatch, tmp_path):
    monkeypatch.setattr(lt, "PROGRESS_PATH", tmp_path / "progress.json")
    return lt.LongTermMemory()


def test_reconcile_adopts_ram_badges(monkeypatch, tmp_path):
    ltm = make_ltm(monkeypatch, tmp_path)
    adopted = ltm.reconcile_badges_from_ram(0b11)
    assert set(adopted) == {"beat_brock", "beat_misty"}
    assert ltm.data["badges_earned"] == 2
    assert ltm.data["gyms_beaten"] == ["Brock", "Misty"]
    assert "beat_brock" in ltm.data["milestones"]


def test_reconcile_is_monotonic_on_ram_regression(monkeypatch, tmp_path):
    ltm = make_ltm(monkeypatch, tmp_path)
    ltm.reconcile_badges_from_ram(0b11)          # earned 2 badges
    adopted = ltm.reconcile_badges_from_ram(0b0)  # RAM rolled back via load_state
    assert adopted == []
    assert ltm.data["badges_earned"] == 2        # not un-earned
    assert ltm.data["gyms_beaten"] == ["Brock", "Misty"]


def test_reconcile_is_idempotent(monkeypatch, tmp_path):
    ltm = make_ltm(monkeypatch, tmp_path)
    ltm.reconcile_badges_from_ram(0b101)          # Brock + Surge
    assert ltm.reconcile_badges_from_ram(0b101) == []
    assert ltm.data["badges_earned"] == 2


def test_reconcile_persists(monkeypatch, tmp_path):
    ltm = make_ltm(monkeypatch, tmp_path)
    ltm.reconcile_badges_from_ram(0b1)
    # A fresh instance reading the same file sees the adopted badge.
    reloaded = lt.LongTermMemory()
    assert reloaded.data["badges_earned"] == 1
    assert "Brock" in reloaded.data["gyms_beaten"]


# ── Authoritative startup sync (journal must not get ahead of the cartridge) ──

def test_authoritative_drops_badges_the_save_lacks(monkeypatch, tmp_path):
    ltm = make_ltm(monkeypatch, tmp_path)
    # Journal claims Brock beaten (from a prior run) ...
    ltm.data["gyms_beaten"] = ["Brock"]
    ltm.data["badges_earned"] = 1
    ltm.data["milestones"] = ["starter_chosen", "beat_brock"]
    # ... but the loaded cartridge has 0 badges.
    res = ltm.reconcile_badges_authoritative(0)
    assert ltm.data["badges_earned"] == 0
    assert ltm.data["gyms_beaten"] == []
    assert "beat_brock" not in ltm.data["milestones"]
    assert "starter_chosen" in ltm.data["milestones"]   # non-gym milestone kept
    assert "Brock" in res["dropped"] and "beat_brock" in res["dropped"]


def test_authoritative_adopts_and_reports(monkeypatch, tmp_path):
    ltm = make_ltm(monkeypatch, tmp_path)
    res = ltm.reconcile_badges_authoritative(0b1)   # save has Boulder
    assert ltm.data["badges_earned"] == 1
    assert "Brock" in ltm.data["gyms_beaten"]
    assert "Brock" in res["adopted"]


def test_authoritative_noop_when_in_sync(monkeypatch, tmp_path):
    ltm = make_ltm(monkeypatch, tmp_path)
    ltm.data["gyms_beaten"] = ["Brock"]
    ltm.data["badges_earned"] = 1
    ltm.data["milestones"] = ["beat_brock"]
    res = ltm.reconcile_badges_authoritative(0b1)
    assert res == {"adopted": [], "dropped": []}
    assert ltm.data["badges_earned"] == 1

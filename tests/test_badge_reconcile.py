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

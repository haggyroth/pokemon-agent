"""Checkpoints + resume (#185 item 2)."""
import json

from memory.checkpoints import CheckpointManager, find_latest


def fake_saver(path):
    open(path, "wb").write(b"state")
    return True


def test_rolling_saves_every_n_ticks_and_prunes(tmp_path):
    m = CheckpointManager(tmp_path / "c", fake_saver, every_ticks=5, keep=2)
    saved = [m.maybe(step, 0, "OVERWORLD") for step in range(1, 31)]
    assert sum(1 for x in saved if x) == 6                    # steps 1, 6, 11, 16, 21, 26
    assert len(list((tmp_path / "c").glob("ckpt_*.ss1"))) == 2   # only the newest `keep` survive


def test_new_badge_is_a_permanent_checkpoint(tmp_path):
    m = CheckpointManager(tmp_path / "c", fake_saver, every_ticks=1000, keep=1)
    m.maybe(1, 0)
    p = m.maybe(40, 1)
    assert p and p.name.startswith("badge1_")
    for step in range(41, 5000, 1001):
        m.maybe(step, 1)
    assert p.exists()                                          # rolling pruning never touches it


def test_latest_json_points_at_the_newest_file(tmp_path):
    m = CheckpointManager(tmp_path / "c", fake_saver, every_ticks=1)
    m.maybe(1, 0, "IN_BATTLE", meta={"map": [3, 0]})
    m.maybe(2, 0, "OVERWORLD", meta={"map": [3, 1]})
    info = json.loads((tmp_path / "c" / "latest.json").read_text())
    assert info["step"] == 2 and info["path"].endswith("ckpt_00002_OVERWORLD.ss1")
    assert info["meta"]["map"] == [3, 1]


def test_disabled_and_failing_savers_are_harmless(tmp_path):
    assert CheckpointManager(tmp_path / "a", fake_saver, every_ticks=0).maybe(1, 0) is None
    bad = CheckpointManager(tmp_path / "b", lambda p: False, every_ticks=1)
    assert bad.maybe(1, 0) is None
    boom = CheckpointManager(tmp_path / "c", lambda p: 1 / 0, every_ticks=1)
    assert boom.maybe(1, 0) is None                            # never raises


def test_find_latest_picks_newest_run_with_an_existing_file(tmp_path):
    import os
    a = CheckpointManager(tmp_path / "20261101-000000" / "checkpoints", fake_saver, every_ticks=1)
    a.maybe(1, 0)
    b = CheckpointManager(tmp_path / "20261102-000000" / "checkpoints", fake_saver, every_ticks=1)
    pb = b.maybe(7, 0)
    os.utime(tmp_path / "20261102-000000" / "checkpoints" / "latest.json", (9e9, 9e9))
    assert find_latest(tmp_path)["step"] == 7
    pb.unlink()                                                # newest file gone → fall back to older run
    assert find_latest(tmp_path)["step"] == 1
    assert find_latest(tmp_path / "missing") is None

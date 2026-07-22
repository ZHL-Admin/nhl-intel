import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from replayprobe import probe  # noqa: E402


def test_decisive_facts_reproduce():
    r = probe.reproduce()
    assert r["has_puck"] is True                     # puck tracked (entity key '1')
    assert r["entities_per_frame"] == 13             # 12 players + puck
    assert r["sample_player_has_xy_playerid"] is True
    assert r["goal_frame_count"] > 60                # ~120 frames (10 Hz, ~12s)
    assert "GOALS ONLY" in r["scope"]
    assert r["cache_status"]["goal_200"] > 0 and r["cache_status"]["nongoal_403"] > 0

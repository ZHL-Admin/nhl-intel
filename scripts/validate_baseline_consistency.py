"""Hard gate: the Roster Builder's unedited baseline == the offseason forecast's projected points.

For every team, an UNEDITED roster-evaluate must reproduce the offseason forecast's projected points for
the team's current transition (within +/- 1 point of integer rounding) with points_delta EXACTLY 0 — the
two tools share ONE "current team" number by construction (roster_evaluate seeds R_current from the
roster_forecast row). Fails loudly (non-zero exit) if any team drifts, so it can gate the calibrate/
validate flow.

Run: SERVING_BACKEND=duckdb python -m scripts.validate_baseline_consistency
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for p in (_ROOT, _ROOT / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

os.environ.setdefault("SERVING_BACKEND", "duckdb")

TOL = 1   # +/- points of integer-rounding slack allowed between the two tools


def main() -> int:
    from services import tools as T           # noqa: E402
    from services import offseason as off      # noqa: E402

    board = off.offseason_board()              # every team's roster_forecast row
    rows = []
    for r in board:
        tid = int(r["team_id"])
        off_pts = r.get("projected_points")
        if off_pts is None:
            continue
        ev = T.roster_evaluate(tid)             # unedited baseline (roster=None, optimize=False)
        rows.append((r.get("team_abbrev") or tid, int(off_pts), ev["projected_points"],
                     ev["points_delta"], ev.get("baseline_source"), ev["baseline_points"]))

    print(f"{'team':6} {'forecast':>9} {'roster-bld':>11} {'Δpts':>6} {'source':>15}")
    bad = []
    for abbr, off_pts, rb_pts, dpts, src, base_pts in sorted(rows):
        ok = abs(rb_pts - off_pts) <= TOL and abs(dpts) < 1e-9 and abs(base_pts - off_pts) <= TOL
        flag = "" if ok else "  <-- MISMATCH"
        if not ok:
            bad.append(abbr)
        print(f"{str(abbr):6} {off_pts:>9} {rb_pts:>11} {dpts:>6.1f} {str(src):>15}{flag}")

    n = len(rows)
    print(f"\n{n} teams; {n - len(bad)} match within +/-{TOL} pt and points_delta == 0.")
    if bad:
        print(f"FAIL: {len(bad)} team(s) drift: {bad}")
        return 1
    print("OK: the Roster Builder baseline reproduces the offseason forecast for every team.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

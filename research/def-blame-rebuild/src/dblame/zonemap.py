"""Link 1 rev2 · R1 responsibility-zone map (league-common situational geometry, per R1-SPEC).

IMPORTANT FRAMING (owner ruling 2026-07-15): this map encodes ONLY the league-universal, situation-driven
coverage geometry that def-scheme Phase 1 found rock-stable (~1.0 split-half, shared by all teams) — NOT
the team-specific scheme identity F26 found unrecoverable. It contains nothing team-specific, enters as a
graded, context-softened input (never an assignment verdict), and is the largest new risk to the eye test;
the tape-keyed validation gate is what checks it. Anchors are an encoded starting map (refit deferred).

Map frame: lateral = attack_sign*y_std (neg = left of the defending goalie), depth = 89 - attack_sign*x_std
(0 at goal line, ~64 at blue line). Zone applies only while the puck is in the defensive zone (depth<64).
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C

R_ZONE = 9.0          # zone radius (ft)
DZ_DEPTH = 64.0       # puck beyond this depth => no map (outside DZ)
SOFT = 4.0            # interpolation softening (ft^2)
MOD_FACEOFF, MOD_ENTRY = 0.3, 0.5     # context modifiers (swap-active handled in events2)

# five base anchor scenes: puck [lat,depth] -> {role: [lat,depth]}
_BASE = [
    {"puck": (-36, 10), "LD": (-31, 8), "RD": (1, 5), "C": (-17, 13), "LW": (-27, 46), "RW": (8, 38)},
    {"puck": (-38, 30), "LD": (-15, 9), "RD": (3, 5), "C": (-24, 18), "LW": (-33, 32), "RW": (9, 40)},
    {"puck": (-26, 56), "LD": (-8, 9), "RD": (6, 6), "C": (-2, 28), "LW": (-24, 50), "RW": (9, 43)},
    {"puck": (0, -6), "LD": (-7, 5), "RD": (7, 5), "C": (0, 13), "LW": (-26, 46), "RW": (26, 46)},
    {"puck": (0, 26), "LD": (-8, 7), "RD": (8, 7), "C": (0, 29), "LW": (-20, 38), "RW": (20, 38)},
]
ROLES = ["LD", "RD", "C", "LW", "RW"]


def _anchors() -> list[dict]:
    """8 scenes: the 5 base + 3 mirrors of scenes 1-3 (negate lateral, swap L<->R roles)."""
    scenes = [dict(s) for s in _BASE]
    for s in _BASE[:3]:
        m = {"puck": (-s["puck"][0], s["puck"][1])}
        m["RD"] = (-s["LD"][0], s["LD"][1]); m["LD"] = (-s["RD"][0], s["RD"][1])
        m["RW"] = (-s["LW"][0], s["LW"][1]); m["LW"] = (-s["RW"][0], s["RW"][1])
        m["C"] = (-s["C"][0], s["C"][1])
        scenes.append(m)
    return scenes


_SCENES = _anchors()
_PUCKS = np.array([s["puck"] for s in _SCENES], dtype=float)                       # (8,2)
_CENTERS = {r: np.array([s[r] for s in _SCENES], dtype=float) for r in ROLES}      # role -> (8,2)


def expected_center(puck_lat: float, puck_depth: float, role: str) -> tuple[float, float]:
    """Inverse-distance-squared weighted expected zone center for a role given puck [lat,depth]."""
    d2 = (_PUCKS[:, 0] - puck_lat) ** 2 + (_PUCKS[:, 1] - puck_depth) ** 2
    w = 1.0 / (d2 + SOFT)
    c = _CENTERS[role]
    return float((w * c[:, 0]).sum() / w.sum()), float((w * c[:, 1]).sum() / w.sum())


def expected_centers_vec(puck_lat, puck_depth, role):
    """Vectorised over arrays of equal length (per-frame)."""
    puck_lat = np.asarray(puck_lat); puck_depth = np.asarray(puck_depth); role = np.asarray(role)
    out = np.full((len(puck_lat), 2), np.nan)
    for r in ROLES:
        m = role == r
        if not m.any():
            continue
        d2 = (_PUCKS[:, 0][None, :] - puck_lat[m, None]) ** 2 + (_PUCKS[:, 1][None, :] - puck_depth[m, None]) ** 2
        w = 1.0 / (d2 + SOFT)
        out[m, 0] = (w * _CENTERS[r][:, 0][None, :]).sum(1) / w.sum(1)
        out[m, 1] = (w * _CENTERS[r][:, 1][None, :]).sum(1) / w.sum(1)
    return out[:, 0], out[:, 1]


def assign_roles(df: pl.DataFrame) -> pl.DataFrame:
    """Per goal, assign LD/RD/C/LW/RW from position (D/F) + mean lateral over the window.

    df: game_id, event_id, player_id, is_def(pos D), mean_lat. Returns +role, +role_ambiguous.
    """
    out = []
    for (gid, eid), g in df.group_by(["game_id", "event_id"], maintain_order=True):
        d = g.sort("mean_lat").to_dicts()
        defs = [r for r in d if r["is_def"]]
        fwds = [r for r in d if not r["is_def"]]
        amb = False
        role = {}
        if len(defs) == 2:
            role[defs[0]["player_id"]] = "LD"; role[defs[1]["player_id"]] = "RD"
            amb = amb or abs(defs[0]["mean_lat"] - defs[1]["mean_lat"]) < 3
        if len(fwds) == 3:
            c = min(fwds, key=lambda r: abs(r["mean_lat"]))
            wings = [r for r in fwds if r["player_id"] != c["player_id"]]
            wings.sort(key=lambda r: r["mean_lat"])
            role[c["player_id"]] = "C"; role[wings[0]["player_id"]] = "LW"; role[wings[1]["player_id"]] = "RW"
            amb = amb or (len(wings) == 2 and abs(wings[0]["mean_lat"] - wings[1]["mean_lat"]) < 3)
        for r in d:
            out.append({"game_id": gid, "event_id": eid, "player_id": r["player_id"],
                        "role": role.get(r["player_id"]), "role_ambiguous": amb})
    return pl.DataFrame(out)


def oop_weight(dist_to_center, puck_depth, faceoff_recent, entry_recent, swap_active):
    """Graded out-of-zone weight (never binary); softened by context modifiers. Puck outside DZ => 0."""
    base = np.maximum(0.0, (np.asarray(dist_to_center) - R_ZONE) / R_ZONE)
    mod = np.ones(len(base))
    mod = np.where(np.asarray(faceoff_recent), mod * MOD_FACEOFF, mod)
    mod = np.where(np.asarray(entry_recent), mod * MOD_ENTRY, mod)
    mod = np.where(np.asarray(swap_active), 0.0, mod)
    w = base * mod
    return np.where(np.asarray(puck_depth) < DZ_DEPTH, w, 0.0)

"""Phase Value — pure-Python reference possession-state machine (Stage 1, spec Section 5).

THIS IS THE SPEC. The dbt SQL (int_phase_events / int_phase_spells / int_zone_episodes) must conform
to this; `stage1_reconcile.py` diffs the two on real games. No BigQuery dependency — takes a list of
event dicts for ONE game and returns per-event state + spell segmentation + DZ episodes. Golden vectors
in tests/phase_value/test_golden_vectors.py pin the behavior (GV1-GV8).

Event dict keys: {t: int elapsed-seconds-in-period, type: type_desc_key, owner: team id (== home or away
passed to run), zone: owner-relative zone_code 'O'/'D'/'N'/None}. Events must be ordered (t, then input
order for ties). Periods are handled by period-boundary events (period-start/period-end/game-end) which
reset state; callers pass one game's events across periods, or one period's events.

Binding decisions embedded: PV-D005 (blocked-shot event owner is the BLOCKING team, so possession goes
to opponent(owner) and zone_abs is derived from the actual owner — equivalent to the spec's
"normalize to the shooting team" because zone_abs is ABSOLUTE), PV-D006 (failed-shot-attempt -> LIVE
no-op + unmapped; shootout-complete -> DEAD boundary).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

D_HOME, N, D_AWAY = "D_home", "N", "D_away"

# defaults mirror the dbt vars / PHASE_VALUE_CONFIG (Appendix C)
GAP_SECONDS = 4            # phase_episode_gap_seconds
RUSH_WINDOW = 4            # rush_window_seconds (reused)
OZ_FACEOFF_LINK = 2        # phase_oz_faceoff_link_seconds
DEAD_TYPES = {"stoppage", "penalty", "period-end", "game-end", "period-start", "shootout-complete"}
RESET_TYPES = {"period-start", "period-end", "game-end"}
SHOT_TYPES = {"shot-on-goal", "missed-shot", "goal"}


def opponent(team, home, away):
    return away if team == home else home


def zone_abs(owner, zone_code, home, away) -> Optional[str]:
    """Absolute puck zone from an owner-relative zone_code. None if zone_code is null (keep previous)."""
    if zone_code is None:
        return None
    if owner == home:
        return {"O": D_AWAY, "D": D_HOME, "N": N}[zone_code]
    return {"O": D_HOME, "D": D_AWAY, "N": N}[zone_code]


def rel_to_attacker(owner, zone_code, attacker):
    """Re-express an owner-relative zone_code relative to the attacking team (mirror int_shot_sequence):
    keep when the attacker owns it, flip O<->D when the defender owns it, N is symmetric."""
    if zone_code is None:
        return None
    if owner == attacker:
        return zone_code
    return {"O": "D", "D": "O", "N": "N"}[zone_code]


@dataclass
class EventState:
    t: int
    type: str
    owner: object
    zone_code: Optional[str]
    poss: Optional[object]      # possession after this event
    zone: Optional[str]         # zone_abs after this event
    live: bool                  # liveness after this event
    idx: int


def _apply(ev, prev_poss, prev_zone, home, away, unmapped):
    """Return (poss, zone, live, unmapped_delta) after applying one event to the carried state."""
    typ, owner, zc = ev["type"], ev["owner"], ev.get("zone")
    za = zone_abs(owner, zc, home, away)

    if typ == "faceoff":
        return owner, za, True, 0                          # revives from DEAD; za always present
    if typ in ("shot-on-goal", "missed-shot"):
        return owner, (za if za is not None else prev_zone), True, 0
    if typ == "goal":
        return owner, (za if za is not None else prev_zone), False, 0   # DEAD after recording
    if typ == "blocked-shot":                               # PV-D005: owner = blocking team
        return opponent(owner, home, away), (za if za is not None else prev_zone), True, 0
    if typ == "giveaway":
        return opponent(owner, home, away), (za if za is not None else prev_zone), True, 0
    if typ == "takeaway":
        return owner, (za if za is not None else prev_zone), True, 0
    if typ == "hit":
        return prev_poss, (za if za is not None else prev_zone), True, 0   # possession unchanged
    if typ in ("penalty", "stoppage", "shootout-complete"):
        return prev_poss, prev_zone, False, 0
    if typ in RESET_TYPES:
        return None, None, False, 0
    if typ == "delayed-penalty":
        return prev_poss, prev_zone, True, 0               # no-op, stays live
    # fallback (incl. failed-shot-attempt): unchanged poss, update zone only if present, LIVE, unmapped++
    return prev_poss, (za if za is not None else prev_zone), True, 1


def _states(events, home, away):
    poss, zone, live, unmapped = None, None, False, 0
    out = []
    for i, ev in enumerate(events):
        poss, zone, live, d = _apply(ev, poss, zone, home, away, unmapped)
        unmapped += d
        out.append(EventState(ev["t"], ev["type"], ev["owner"], ev.get("zone"), poss, zone, live, i))
    return out, unmapped


def _dzone(d, home):
    return D_HOME if d == home else D_AWAY


def _detect_episodes(states, d, home, away, gap, rush_w, ozfo_link, is_5v5=None):
    """DZ episodes for defending team d, from the per-event state series. An interval [t_i, t_{i+1})
    carries state_after(i); it is 'in-zone' iff poss==attacker, zone==d's D zone, and (live or atk goal).
    If is_5v5 (list aligned to the original event indices) is given, each episode is tagged with the
    start event's is_5v5 for parity with the 5v5-scoped dbt model."""
    attacker = opponent(d, home, away)
    dz = _dzone(d, home)
    n = len(states)

    def is_atk_goal(s):
        return s.type == "goal" and s.poss == attacker

    def in_zone(s):
        # attacker possessing in d's D zone; live OR a terminating attacker goal (spec §5.4: the raw
        # interval condition is possession+zone; a goal is the attacker culminating in-zone even though
        # play goes DEAD after, so it anchors/ends the episode). This is what covers rush/quick goals.
        return s.poss == attacker and s.zone == dz and (s.live or is_atk_goal(s))

    def dz_ok(s):
        # gap-merge test: puck stayed in d's zone and live (or a terminal attacker goal)
        return s.zone == dz and (s.live or is_atk_goal(s))

    # raw in-zone runs over event indices (each index i owns interval [t_i, t_{i+1}))
    raw = []
    i = 0
    while i < n:
        if in_zone(states[i]):
            j = i
            while j + 1 < n and in_zone(states[j + 1]):
                j += 1
            raw.append((i, j))            # indices; interval start = states[i].t, "end" = states[j+1].t
            i = j + 1
        else:
            i += 1
    if not raw:
        return []

    # merge consecutive raw runs across a gap that (a) <= gap seconds, (b) puck stays in dz every gap
    # interval, (c) no DEAD inside. The gap spans event indices (r0_end+1 .. r1_start-1).
    merged = [list(raw[0])]
    for (a, b) in raw[1:]:
        pa, pb = merged[-1]
        gap_start_t = states[pb + 1].t if pb + 1 < n else states[pb].t
        gap_end_t = states[a].t
        gap_secs = gap_end_t - gap_start_t
        gap_ok = gap_secs <= gap
        for k in range(pb + 1, a):
            if not dz_ok(states[k]):              # puck left the zone or went DEAD (non-goal) -> cannot merge
                gap_ok = False
                break
        if gap_ok:
            merged[-1][1] = b
        else:
            merged.append([a, b])

    episodes = []
    for (a, b) in merged:
        start_t = states[a].t
        if is_atk_goal(states[b]):
            # the episode's last in-zone spell IS the attacker goal: it ends here, reason goal.
            end_t = states[b].t
            end_reason = "goal"
        else:
            # episode end = end of the last in-zone interval = time of the first event after index b
            end_t = states[b + 1].t if b + 1 < n else states[b].t
            end_reason = _end_reason(states, a, b, d, home, away, gap)
        start_type = _start_type(states, a, d, home, away, rush_w, ozfo_link)
        # unblocked attempts by attacker with t in [start,end]; goals among them
        n_unblocked = sum(1 for s in states if s.owner == attacker and s.type in SHOT_TYPES
                          and start_t <= s.t <= end_t)
        goals = sum(1 for s in states if s.owner == attacker and s.type == "goal"
                    and start_t <= s.t <= end_t)
        # 5v5 keep rule: keep an episode if ANY of its in-zone spells contains a 5v5 event. This retains
        # episodes crossing a strength boundary INTO 5v5 (a PP expires, the goal is 5v5) so 5v5 goals are
        # not dropped; it is spell-exact-matchable to the dbt model. Stage 3 intersects with 5v5 stints
        # for exact accounting, so clipped/boundary episodes do not pollute the fits.
        keep_5v5 = None
        if is_5v5 is not None:
            keep_5v5 = any(is_5v5[states[k].idx] for k in range(a, b + 1) if in_zone(states[k]))
        episodes.append({
            "defending_team": d, "attacking_team": attacker,
            "start": start_t, "end": end_t, "start_type": start_type, "end_reason": end_reason,
            "n_unblocked": n_unblocked, "goals": goals,
            "start_5v5": (is_5v5[states[a].idx] if is_5v5 is not None else None),
            "keep_5v5": keep_5v5,
        })
    return episodes


def _start_type(states, a, d, home, away, rush_w, ozfo_link):
    attacker = opponent(d, home, away)
    dz = _dzone(d, home)
    se = states[a]           # the start event
    start_t = se.t

    def is_oz_fo(s):
        return s.type == "faceoff" and s.owner == attacker and zone_abs(s.owner, s.zone_code, home, away) == dz

    # oz_faceoff: start event itself is such a faceoff, or occurs <= link seconds after one
    if is_oz_fo(se):
        return "oz_faceoff"
    for s in states:
        if is_oz_fo(s) and 0 <= start_t - s.t <= ozfo_link:
            return "oz_faceoff"

    # rush: a prior event within rush_w before start, zone-rel-attacker in {D,N}, after every faceoff in window
    last_fo_t = None
    for s in states:
        if s.type == "faceoff" and start_t - rush_w <= s.t < start_t:
            last_fo_t = s.t if last_fo_t is None else max(last_fo_t, s.t)
    for s in states:
        if not (start_t - rush_w <= s.t < start_t):
            continue
        rel = rel_to_attacker(s.owner, s.zone_code, attacker)
        if rel in ("D", "N") and (last_fo_t is None or s.t > last_fo_t):
            return "rush"

    # forecheck: start event is an attacker takeaway or a defender giveaway, located in d's D zone
    if se.zone == dz:
        if (se.type == "takeaway" and se.owner == attacker) or (se.type == "giveaway" and se.owner == d):
            return "forecheck"
    return "carry_other"


def _end_reason(states, a, b, d, home, away, gap):
    attacker = opponent(d, home, away)
    dz = _dzone(d, home)
    n = len(states)
    if b + 1 >= n:
        return "open"                     # truncated at end of the event vector (e.g. GV3)
    term = states[b + 1]                  # first event after the last in-zone interval
    # goal: the terminating event is an attacker goal (goal state is DEAD, so it ends the run)
    if term.type == "goal" and term.owner == attacker:
        return "goal"
    if not term.live:                     # DEAD boundary
        return "stoppage"
    # live but no longer in-zone: either the puck left the zone (exit) or the defender took it (flip)
    if term.zone != dz:
        return "exit"
    # defender possession inside dz: exit if the puck leaves within `gap`, else flip_sustained
    for k in range(b + 1, n):
        s = states[k]
        if s.t - term.t > gap:
            break
        if not s.live:
            return "stoppage"
        if s.zone != dz:
            return "exit"
    return "flip_sustained"


def run(events, home, away, gap=GAP_SECONDS, rush_w=RUSH_WINDOW, ozfo_link=OZ_FACEOFF_LINK,
        is_5v5=None) -> dict:
    """Process one game's events. Returns per_event states, episodes (both defending sides), unmapped count.
    is_5v5 (optional, aligned to events) tags each episode's start-event strength for 5v5 parity with dbt."""
    states, unmapped = _states(events, home, away)
    episodes = (_detect_episodes(states, home, home, away, gap, rush_w, ozfo_link, is_5v5)
                + _detect_episodes(states, away, home, away, gap, rush_w, ozfo_link, is_5v5))
    episodes.sort(key=lambda e: (e["start"], str(e["defending_team"])))
    per_event = [{"t": s.t, "type": s.type, "poss": s.poss, "zone": s.zone, "live": s.live} for s in states]
    return {"per_event": per_event, "episodes": episodes, "unmapped": unmapped}

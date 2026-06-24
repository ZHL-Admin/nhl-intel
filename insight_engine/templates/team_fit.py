"""
Trade/free-agency fit explanation templates (Phase 5.3, blueprint 6.4).

Deterministic, data-driven reasons for how well a player addresses a team's needs. No LLM. The
scorer (models_ml/score_team_fit.py) passes the player's archetype mix + composite components and
the team's archetype/component gaps; this builds 2-3 sentences that each reference a number in the
payload (consistency rule). Reused by the Phase 6 insight engine.

The bottom half of this module is the VERDICT clause-assembly system: a deterministic trajectory
classifier over the player's per-season WAR series, plus a conditional clause builder that selects
which clauses appear, their order, and their words from computed signals. Every function here is
PURE (it takes already-computed numbers, never touches BigQuery), so the verdict can be unit-tested
against fixtures and its claims guaranteed against the numbers on the page. score_team_fit.py
computes the signals and calls these; the same trajectory descriptor + numbers drive BOTH the
verdict and the quality-card sentence, so the two can never disagree. See player-fit.md.
"""

from __future__ import annotations

import math

COMPONENT_PHRASE = {
    "ev_offense": "even-strength offense", "ev_defense": "even-strength defense",
    "pp": "power-play offense", "pk": "penalty killing", "finishing": "finishing",
}

# a team "needs" an archetype when its mix trails the top teams by at least this (mix-share units)
ARCH_NEED_THRESHOLD = 0.01


def reasons(*, player_primary_arch: str | None, player_arch_weight: float,
            team_arch_needs: dict[str, float], player_top_component: str,
            player_top_component_value: float, team_component_needs: dict[str, float]) -> list[str]:
    out: list[str] = []

    # 1) archetype fit: does the player's primary role fill a gap?
    if player_primary_arch:
        gap = team_arch_needs.get(player_primary_arch, 0.0)
        if gap >= ARCH_NEED_THRESHOLD:
            out.append(f"He profiles as a {player_primary_arch} "
                       f"({player_arch_weight * 100:.0f}% of his mix), a role they lack relative "
                       f"to the top teams.")
        else:
            out.append(f"They already have {player_primary_arch} depth, so he does not add a "
                       f"missing role.")

    # 2) component fit: does the player's strongest value address a component gap?
    comp_phrase = COMPONENT_PHRASE.get(player_top_component, player_top_component)
    if team_component_needs.get(player_top_component, 0.0) > 0:
        out.append(f"His {comp_phrase} ({player_top_component_value:+.1f} goals) addresses their "
                   f"{comp_phrase} gap.")

    # 3) the biggest unaddressed need
    if team_component_needs:
        biggest = max(team_component_needs, key=team_component_needs.get)
        if team_component_needs[biggest] > 0 and biggest != player_top_component:
            out.append(f"He does not address their largest need, "
                       f"{COMPONENT_PHRASE.get(biggest, biggest)} "
                       f"({team_component_needs[biggest]:+.1f} goals behind the top teams).")

    return out[:3]


# ======================================================================================
# VERDICT CLAUSE ASSEMBLY  (pure; fixtures in tests/test_trade_fit_verdict.py)
# ======================================================================================
#
# A) trajectory classifier  -> classify_trajectory()
# B) supporting phrasers     -> tier_phrase(), signature_phrase()
# C) clause assembly         -> build_verdict()  and the shared quality_note()
#
# All take already-computed numbers (the WAR series, the projection, the per-component
# percentiles, the match dimensions, the grade). Nothing here queries data or randomises,
# so a given set of inputs always yields one identical string (determinism rule).

# trajectory buckets, in priority order of the words they unlock.
TRAJ_BUCKETS = (
    "career_year", "down_year", "declining", "ascending", "volatile", "established_stable",
)


def _finite(xs):
    out = []
    for x in xs:
        try:
            f = float(x)
        except (TypeError, ValueError):
            continue
        if math.isfinite(f):
            out.append(f)
    return out


def _lin_slope(chrono):
    """Least-squares slope per season of a chronological (oldest -> newest) series; 0 if < 2 pts."""
    n = len(chrono)
    if n < 2:
        return 0.0
    xm = (n - 1) / 2.0
    ym = sum(chrono) / n
    num = sum((i - xm) * (chrono[i] - ym) for i in range(n))
    den = sum((i - xm) ** 2 for i in range(n))
    return (num / den) if den > 0 else 0.0


def _trailing_monotone(chrono, decreasing):
    """# of consecutive season-over-season moves (in `decreasing` direction) ending at the newest."""
    n = 0
    for i in range(len(chrono) - 1, 0, -1):
        if decreasing and chrono[i] < chrono[i - 1]:
            n += 1
        elif (not decreasing) and chrono[i] > chrono[i - 1]:
            n += 1
        else:
            break
    return n


def classify_trajectory(series, proj_war, last_war, proj_sd, age, aging_ratio, cfg):
    """Deterministically bucket a player's per-season WAR/impact series into a trajectory.

    `series` is newest -> oldest (the projection's GAR rows). Returns a dict with the bucket, the
    consecutive-decline count `n_straight` (for the "slipped N straight seasons" phrase), and the
    derived signals, so the caller can both phrase and test it. The tier word the caller renders
    always maps to the PROJECTION, never to last season; declining/volatile force a trend caveat.
    """
    t = cfg["TRAJ"]
    s = _finite(series)
    n = len(s)
    last = (s[0] if s else (float(last_war) if last_war is not None else 0.0))
    proj = float(proj_war) if proj_war is not None else last
    prior = s[1:]                                   # the established track record (excl. newest)
    prior_mean = (sum(prior) / len(prior)) if prior else last
    chrono = list(reversed(s))                      # oldest -> newest
    slope = _lin_slope(chrono)
    prior_slope = _lin_slope(list(reversed(prior)))
    n_dec = _trailing_monotone(chrono, decreasing=True)
    n_inc = _trailing_monotone(chrono, decreasing=False)
    band = t["TIER_BAND_WAR"]
    depth_proj = sum(1 for w in s if abs(w - proj) <= band)            # seasons at the projected tier
    depth_prior = sum(1 for w in prior if abs(w - prior_mean) <= band)  # prior seasons at the proven tier
    cv = (float(proj_sd) / (abs(proj) + t["CV_EPS"])) if proj_sd else 0.0
    series_cv = ((statistics_pstdev(s) / (abs(sum(s) / n) + t["CV_EPS"])) if n >= 2 else 0.0)

    if prior and (last - prior_mean) >= t["CAREER_YEAR_GAP_WAR"] and proj < last:
        bucket = "career_year"
    elif (prior and (prior_mean - last) >= t["DOWN_YEAR_GAP_WAR"]
          and prior_slope >= -t["SLOPE_FLAT"] and depth_prior >= t["MIN_TRACK_DEPTH"] and proj > last):
        bucket = "down_year"
    elif (n_dec >= t["DECLINE_MIN_SEASONS"] and slope <= -t["SLOPE_DECLINE"]
          and prior_slope <= -t["SLOPE_DECLINE_PRIOR"]):
        bucket = "declining"
    elif n_inc >= t["ASCEND_MIN_SEASONS"] and slope >= t["SLOPE_ASCEND"] and proj >= prior_mean:
        bucket = "ascending"
    elif cv >= t["VOLATILE_CV"] or series_cv >= t["VOLATILE_SERIES_CV"]:
        bucket = "volatile"
    else:
        bucket = "established_stable"

    return {"bucket": bucket, "n_straight": (n_dec if bucket == "declining" else n_inc),
            "depth_proj": depth_proj, "depth_prior": depth_prior, "slope": slope,
            "prior_slope": prior_slope, "prior_mean": prior_mean, "cv": cv, "series_cv": series_cv,
            "n_seasons": n}


def statistics_pstdev(xs):
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / n)


# ---------------------------------------------------------------- B) phrasers
def _tier_entries(pos_group, cfg):
    return cfg["TIER_LABELS"].get(pos_group, cfg["TIER_LABELS"]["F"])


def tier_phrase(pctile, pos_group, cfg):
    """Map a PROJECTED within-position percentile to a tier noun (and the next tier down). The
    adjective mirrors the quality chip's cuts so the verdict and the chip never disagree."""
    entries = _tier_entries(pos_group, cfg)
    idx = len(entries) - 1
    if pctile is not None:
        for i, (cut, _noun) in enumerate(entries):
            if pctile >= cut:
                idx = i
                break
    noun = entries[idx][1]
    lower = entries[min(idx + 1, len(entries) - 1)][1]
    return {"noun": noun, "lower": lower, "index": idx}


def _article(noun):
    return "an" if noun and noun[0].lower() in "aeiou" else "a"


def signature_phrase(comp_pct, role, is_goalie, cfg):
    """The player's signature strength (top role/skill by within-role percentile). Returns the phrase
    + the driving component, or (None, None) when nothing clears the bar (degrade, never invent)."""
    phrases = cfg["SIGNATURE_PHRASES"]
    if is_goalie:
        gp = comp_pct.get("goaltending")
        if gp is not None and gp >= cfg["SIGNATURE_MIN_PCT"]:
            return phrases["goaltending"], "goaltending"
        return None, None
    present = {k: v for k, v in comp_pct.items() if v is not None}
    if not present:
        return None, None
    # two-way signature: both even-strength sides elite
    evo, evd = present.get("ev_offense"), present.get("ev_defense")
    if (evo is not None and evd is not None
            and evo >= cfg["SIGNATURE_TWO_WAY_PCT"] and evd >= cfg["SIGNATURE_TWO_WAY_PCT"]):
        return phrases["two_way"], "two_way"
    top_key = max(present, key=present.get)
    if present[top_key] < cfg["SIGNATURE_MIN_PCT"]:
        return None, None
    text = phrases.get(top_key, top_key)
    if top_key == "ev_offense" and role == "D":
        text += " from the back end"        # positional qualifier (a D who drives offense)
    return text, top_key


# ---------------------------------------------------------------- C) clause assembly
def _identity_clause(name, traj, tier, signature, cfg):
    """The always-present opener. Uses a flat "is a {tier}" ONLY for an established_stable player with
    a deep track record; every other bucket hedges with "projects/profiles as" and (for declining/
    volatile) carries the trend caveat, so a high projection never sits beside a downward trend."""
    bucket = traj["bucket"]
    noun, art = tier["noun"], _article(tier["noun"])
    tail = f" who {signature}" if signature else ""           # graceful degrade: no invented strength
    deep = traj["depth_proj"] >= cfg["TRAJ"]["MIN_DEPTH_FOR_IS"]

    if bucket == "established_stable" and deep:
        return f"{name} is {art} {noun}{tail}."
    if bucket == "established_stable":
        return f"{name} profiles as {art} {noun}{tail}."
    if bucket == "career_year":               # build_verdict routes career_year to _career_year_identity;
        return _career_year_identity(name, tier, signature)  # kept here so the helper is self-contained
    if bucket == "down_year":
        join = f", and he still {signature}" if signature else ""
        return f"{name} is a proven {noun} coming off a down year the model regresses back up{join}."
    if bucket == "ascending":
        join = f", and he {signature}" if signature else ""
        return f"{name} is trending up; he profiles as {art} {noun} and still climbing{join}."
    if bucket == "declining":
        nstr = traj["n_straight"] or cfg["TRAJ"]["DECLINE_MIN_SEASONS"]
        lower = tier["lower"]
        join = f", and he still {signature}" if signature else ""
        return (f"{name} has slipped {nstr} straight seasons; he profiles as {art} {noun} but the "
                f"projection trends down toward {_article(lower)} {lower}{join}.")
    if bucket == "volatile":
        join = f", and he {signature}" if signature else ""
        return f"{name} swings year to year; he profiles as {art} {noun} on a wide band{join}."
    return f"{name} profiles as {art} {noun}{tail}."


def _career_year_identity(name, tier, signature):
    """career_year reads cleanest with the strength clause inside the comma series."""
    noun, art = tier["noun"], _article(tier["noun"])
    if signature:
        return f"{name} projects as {art} {noun}, coming off a career year, who {signature}."
    return f"{name} projects as {art} {noun}, coming off a career year."


def _fit_driver_clause(abbr, need_breakdown, role_word, unit_word):
    """Always present, chosen from the need decomposition: a real role he fills, or no real need."""
    fills = [b for b in (need_breakdown or []) if b.get("tag") == "fills"]
    if fills:
        top = max(fills, key=lambda b: b.get("team_need", 0.0))
        comp = top["label"].split("· ")[-1].lower()       # the component he fills (e.g. "even-strength offense")
        return (f"That's {abbr}'s thinnest spot at {comp} {unit_word}, so he fills a real need.",
                "need")
    return (f"But {abbr} are already deep at {role_word}, so he doesn't fill a real need.", "need")


def _cap_reason(dim, factor):
    """A dimension's cap phrase, agreeing with its level (same cuts as the style/line notes)."""
    lvl = dim.get("level") if dim else None
    if factor == "style":
        if lvl is not None and lvl >= 0.46:
            return "a partial style mismatch"
        return "a style mismatch"
    if factor == "line":
        if lvl is not None and lvl < 0.46:
            return "a weak line projection"
        return "a neutral line projection"
    return "an unproven one-year projection"


def _cap_clause(grade, fit, match, dims, traj, fit_driver_factor, cfg):
    """Conditional: the largest MATERIAL weighted shortfall among the match dimensions (plus an
    "unproven one-year projection" cap for a career-year/volatile bucket). Names a DIFFERENT factor
    than the fit driver already covered. If nothing material caps it, a confidence closer (top
    grades) or nothing."""
    by = {d["key"]: d for d in dims}
    w = cfg["MATCH_WEIGHTS"]
    cands = []                                  # (magnitude, factor)
    for k in ("style", "line"):
        d = by.get(k)
        if d and d.get("level") is not None:
            cands.append((w[k] * (1.0 - d["level"]), k))
    if traj["bucket"] in ("career_year", "volatile"):
        cands.append((cfg["PROJ_CAP_MAG"], "projection"))
    cands = [(m, f) for (m, f) in cands
             if m > cfg["MATERIAL_CAP"] and f != fit_driver_factor and f != "need"]
    if cands:
        _m, factor = max(cands, key=lambda c: c[0])
        reason = _cap_reason(by.get(factor), factor)
        if grade in cfg["TOP_GRADES"]:
            return f"{reason[0].upper()}{reason[1:]} is the only thing keeping it from higher."
        return f"{reason[0].upper()}{reason[1:]} pulls it further down."
    if grade in cfg["TOP_GRADES"]:
        return "Nothing meaningful argues against the fit."
    return None


def build_verdict(*, name, abbr, grade, fit, match, dims, need_breakdown, traj, tier,
                  signature, role, is_goalie, cfg):
    """Assemble the verdict from conditional clauses: identity (always) -> fit driver (always) ->
    cap or confidence closer (conditional) -> floor note (conditional) -> grade (always). Clauses
    with nothing to say are dropped; the strongest signal leads, the binding constraint ends."""
    role_word = {"C": "center", "W": "wing", "D": "defense", "G": "goaltender"}.get(role, "the role")
    # unit phrase carries its own preposition so "on the blue line" / "up front" / "in net" all read.
    unit_word = {"D": "on the blue line", "C": "up front", "W": "up front",
                 "G": "in net"}.get(role, "on the depth chart")
    if traj["bucket"] == "career_year":
        identity = _career_year_identity(name, tier, signature)
    else:
        identity = _identity_clause(name, traj, tier, signature, cfg)

    driver, driver_factor = _fit_driver_clause(abbr, need_breakdown, role_word, unit_word)
    parts = [identity, driver]

    # _cap_clause handles missing style/line dimensions itself (goalies have need only), so it is
    # safe to call uniformly: it falls back to the projection cap / a confidence closer / nothing.
    cap = _cap_clause(grade, fit, match, dims, traj, driver_factor, cfg)
    if cap:
        parts.append(cap)

    if (fit - match) >= cfg["FLOOR_LIFT_MIN"]:
        parts.append("His quality keeps a floor under the grade.")

    parts.append(f"Fit grades {grade}.")
    return " ".join(parts)


def quality_note(*, quality, pos_label, tier, traj, cfg, prod_pctile=None, pd_pctile=None):
    """The quality-card sentence — built from the SAME tier descriptor + the SAME numbers the verdict
    uses, plus a trajectory tail, so the card and the verdict can never contradict each other. The
    headline percentile is the BLENDED Overall lens (production + isolated play-driving); when both
    component lenses are present (skaters) the note shows the split, which is exactly where a
    finishing-luck spike shows up (high production, lower play-driving)."""
    pct, war, war_sd, last = (quality.get("percentile"), quality.get("war"),
                              quality.get("war_sd"), quality.get("last_war"))
    if pct is None:
        return "No multi-season value estimate (too little NHL history to project)."
    from models_ml.textfmt import ordinal
    war_txt = (f"{war:+.1f} WAR" + (f" ± {war_sd:.1f}" if war_sd else "")) if war is not None else ""
    if prod_pctile is not None and pd_pctile is not None:
        # blended lens, with the production/play-driving split made explicit and honest
        head = (f"Projects as {_article(tier['noun'])} {tier['noun']} — "
                f"{ordinal(round(pct * 100))}-percentile all-around value among {pos_label}: "
                f"{ordinal(round(prod_pctile * 100))} in production"
                f"{(' (' + war_txt + ')') if war_txt else ''}, "
                f"{ordinal(round(pd_pctile * 100))} in isolated play-driving.")
    else:
        head = (f"Projects as {_article(tier['noun'])} {tier['noun']} — "
                f"{ordinal(round(pct * 100))}-percentile value among {pos_label}"
                f"{(' (' + war_txt + ')') if war_txt else ''}.")
    tail = _trajectory_tail(traj, last, war, tier, cfg)
    return head + (f" {tail}" if tail else "")


def _trajectory_tail(traj, last, war, tier, cfg):
    b = traj["bucket"]
    last_txt = f"{last:+.1f} WAR" if last is not None else None
    if b == "career_year" and last_txt:
        return f"Last season {last_txt} — a career year the projection regresses toward his multi-season level."
    if b == "down_year" and last_txt:
        return f"Last season {last_txt} — a down year the projection regresses back up."
    if b == "declining":
        n = traj["n_straight"] or cfg["TRAJ"]["DECLINE_MIN_SEASONS"]
        return f"Down {n} straight seasons — the projection trends toward {_article(tier['lower'])} {tier['lower']}."
    if b == "ascending":
        return "Trending up — the projection still climbing."
    if b == "volatile":
        return "Swings year to year — a deliberately wide band."
    return None

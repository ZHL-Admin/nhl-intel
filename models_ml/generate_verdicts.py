"""
Player Verdict — Gemini narration + consistency checker + persistence (Workstream B).

Gemini narrates the deterministic payload from build_verdict_payload (it narrates only; it never
computes). Every figure the model references is verified against the payload by the consistency
checker before persistence; a verdict that fails the check is regenerated once, then dropped and
never shown (mirrors the insight-engine consistency rule).

ZONE-USAGE GATE: the prompt admits zone usage ONLY as the NHL Edge OZ-start percentile
(`current.deployment.oz_start_pctile_edge`), labeled "NHL Edge". No PDO, no live hot/cold, no
team faceoff proxy, no 50%-threshold lean.

Cadence (see docs / DAG):
  - identity inputs (player_impact 3yr, archetypes) recompute on their own slow clock; this job
    only READS them.
  - the written paragraph regenerates WEEKLY, scoped to players who played in the last 7 days
    (`--weekly`); `--full` backfills/refit-regenerates everyone; `--players`/`--sample` for spot runs.
  - idempotent: re-running replaces the (player_id, season) rows.

Output: nhl_models.player_verdict (player_id, season, long, short, numbers_used, identity_confidence,
model_version, generated_at, payload_hash).

Run examples:
  python -m models_ml.generate_verdicts --players 8478402 8471675 --season 2025-26 --dry-run
  python -m models_ml.generate_verdicts --weekly --season 2025-26
  python -m models_ml.generate_verdicts --full  --season 2025-26
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

import pandas as pd

from models_ml import bq, config
from models_ml.build_verdict_payload import build_payload, _impact_frame

SYSTEM_PROMPT = """You write a scouting read for an NHL player profile, using ONLY the JSON payload provided.
The payload has two horizons: `identity` (durable, multi-year) and `current` (this season),
plus `deltas` (how current differs from career) and an optional `horizon` note.

Rules:
- Use only facts present in the payload. Never introduce a number, trait, or judgment not present.
- Every descriptive phrase maps to a payload field. No eye-test adjectives for unmeasured traits
  (stickhandling, compete, hockey IQ). "Fast"/"wheels" only if a skating spoke supports it.
- Voice: plain, confident, hockey-literate. No hype, no cliches, no exclamation.
- Refer to the player by `display_name` on first reference, then by pronoun. NEVER open with a label as
  if it were a name (no "This North-South Forward...").
- IDENTITY NOUN comes from the ASSESSMENT TIER, not the cluster: build "what kind of player" from
  `current.assessment.tier_label` + `identity.archetype.family` + `identity.durable_traits`
  (e.g. "a first-line forward with two-way value", "a top-pair defenseman"). Use `tier_label` verbatim
  as the tier noun. `identity.archetype.style` is HOW he plays — PARAPHRASE it naturally into your own
  words; do NOT paste it verbatim and do NOT force it into a "plays a ___ game" template. NEVER use
  `identity.archetype.cluster_label` as the identity noun and never import a tier/quality word from it;
  the ASSESSMENT TIER sets the tier, nothing else. If `season_sensitive` is true, present the style as
  one that has shifted.
- CONFIDENCE + RANGE: pitch certainty to `current.assessment.confidence_label` (high/medium/low). You
  MAY name a TWO-TIER RANGE ("a first- or second-line forward") ONLY when
  `current.assessment.tier_confidence < 0.55` AND `current.assessment.tier_prob_within_one >=
  current.assessment.within_one_range_copy`; otherwise name the single assigned tier.
- INACTIVE: if `current.assessment.disqualify_reason == "inactive"`, state plainly that he is inactive
  and name `current.assessment.last_played_season`; make NO current-tier claim.
- DEPENDENCE: if `current.assessment.dependence_n_partners` is present and < 3, any linemate-dependence
  statement MUST be hedged (thin partner sample); if it is null, make no dependence claim.
- DURABLE TRAITS describe a spread: if several durable_traits are present, characterize the player by
  that spread, not by the single highest one. Do not reduce a many-sided player to one spike.
- HORIZON: if a `horizon` note is present, you MAY state it plainly and NEUTRALLY as the two lenses
  (production vs three-year impact) measuring different things. NEVER write it as the model being
  wrong, underrating, or overrating anyone. It is an observation, not a correction.
- ZONE usage may be described ONLY from `current.deployment.oz_start_pctile_edge`, and ONLY in the
  deployment portion of the read, EXACTLY ONCE. Do not mention zone starts in any other sentence. The
  one zone clause MUST state the percentile number AND the words "NHL Edge" (e.g. "starts in the
  offensive zone at the 95th percentile, per NHL Edge"). Never a vague phrase like "high zone start
  percentage", never any other zone-start number. If the field is absent, omit zone usage entirely.
- Structure the long read as: (1) durable identity first (assessment tier + family + durable traits, with
  style woven in); (2) what is notably different this season, from `deltas`/`horizon`/`current`, as a
  contrast; (3) sustainability, from finishing/consistency and any sample_flags; (4) deployment and
  what not to over-read, using honesty tags (a high skill spoke with low usage deployment is not a
  deployed role).
- Calibrate certainty to `identity.confidence` and `current.games_played`. High: state identity
  plainly. Low/medium (thin career sample): make the same specific observations but tie them to the
  actual games played and call current production a strong start, not a settled trait. Never promote
  a partial season into permanent identity.
- LENGTH IS A HARD LIMIT: "long" is 2 to 4 sentences. Never write a fifth sentence. "short" is one
  clause naming the kind of player (value tier + family/role), not the raw cluster label.
- State each fact once. Do not repeat a clause within the read (the zone clause appears at most once).
- Never print a raw decimal or proportion (no "0.013", "0.091"). Describe finishing qualitatively
  (above / below / in line with expected); express any rate only as a whole-number percentage.
- Round percentages sensibly. List every figure you reference in numbers_used with its source field
  (a dotted path into the payload, e.g. "current.overall.percentile") and the value you assert. When
  you cite a qualitative judgment (e.g. "above expected"), cite the field holding that WORD
  (`current.finishing.verdict`), never the numeric `current.finishing.delta`.

Return JSON only: { "long": "...", "short": "...", "numbers_used": [ { "field": "...", "asserts": "..." } ] }.
"""


def _gemini(payload: dict) -> Optional[dict]:
    """Call Gemini with the payload; return parsed {long, short, numbers_used} or None on failure."""
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("LLM_API_KEY not set; cannot generate (run with --dry-run to skip Gemini)")
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(config.VERDICT["LLM_MODEL"], system_instruction=SYSTEM_PROMPT)
    resp = model.generate_content(
        json.dumps(payload),
        generation_config={"temperature": 0.4, "response_mime_type": "application/json"},
    )
    txt = (resp.text or "").strip()
    txt = re.sub(r"^```(?:json)?|```$", "", txt, flags=re.MULTILINE).strip()
    try:
        out = json.loads(txt)
    except Exception:
        return None
    if not isinstance(out, dict) or "long" not in out:
        return None
    out.setdefault("short", "")
    out.setdefault("numbers_used", [])
    return out


# --- consistency checker ----------------------------------------------------------------------
def _resolve(payload: dict, path: str) -> Any:
    # accept both bracket (durable_traits[0].x) and dotted (durable_traits.0.x) index notation
    norm = re.sub(r"\[(\d+)\]", r".\1", str(path))
    cur: Any = payload
    for part in norm.split("."):
        if part == "":
            continue
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
                continue
            except Exception:
                return None
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _first_number(s: Any) -> Optional[float]:
    if isinstance(s, (int, float)):
        return float(s)
    m = re.search(r"-?\d+(?:\.\d+)?", str(s))
    return float(m.group()) if m else None


def consistency_check(payload: dict, numbers_used: list) -> tuple[bool, list[str]]:
    """Each cited number must match the payload value (within tolerance) after normalising
    percentile scales (0-1 vs 0-100). Returns (ok, failures)."""
    tol = config.VERDICT["CHECK_TOL"]
    failures: list[str] = []
    for nu in numbers_used or []:
        field = nu.get("field") if isinstance(nu, dict) else None
        asserts = nu.get("asserts") if isinstance(nu, dict) else None
        if not field:
            failures.append(f"missing field in {nu}")
            continue
        src = _resolve(payload, field)
        if src is None:
            failures.append(f"{field}: not in payload")
            continue
        want, got = _first_number(asserts), _first_number(src)
        if want is None or got is None:
            # non-numeric assertion (e.g. a label) — require exact substring match
            if str(src).lower() not in str(asserts).lower() and str(asserts).lower() not in str(src).lower():
                failures.append(f"{field}: '{asserts}' != '{src}'")
            continue
        # normalise a 0-1 payload value against a 0-100 assertion (percentiles)
        if got <= 1.0 and want > 1.5:
            got *= 100
        if abs(want - got) > tol:
            failures.append(f"{field}: asserts {want} but payload {got}")
    return (len(failures) == 0, failures)


def quality_check(payload: dict, result: dict) -> tuple[bool, list[str]]:
    """Non-numeric guards that also trigger a regenerate: the long read must be <= MAX_SENTENCES,
    and any zone clause must carry the explicit 'NHL Edge' attribution (no vague zone phrasing)."""
    failures: list[str] = []
    long = str(result.get("long", ""))
    n_sent = len(re.findall(r"[.!?]+(?=\s|$)", long.strip()))
    if n_sent > config.VERDICT["MAX_SENTENCES"]:
        failures.append(f"length: {n_sent} sentences (max {config.VERDICT['MAX_SENTENCES']})")
    has_edge = (payload.get("current", {}).get("deployment", {}) or {}).get("oz_start_pctile_edge") is not None
    # Match the zone-START clause specifically, NOT the bare words "offensive zone" — an Elite
    # Offensive Driver's style descriptor ("drives play from the offensive zone") is not a zone-start
    # mention and must not be counted as one.
    zone_start = re.findall(r"zone starts?|start\w*[^.]{0,40}\bzone\b|deploy\w*[^.]{0,40}\bzone\b",
                            long, flags=re.IGNORECASE)
    if has_edge and zone_start and "nhl edge" not in long.lower():
        failures.append("zone clause without 'NHL Edge' attribution")
    if len(zone_start) > 1:
        failures.append("zone-start clause stated more than once")
    if re.search(r"\b0\.\d+", long):   # a raw decimal/proportion leaked into the prose
        failures.append("raw decimal in prose (use whole-number percentages)")
    return (len(failures) == 0, failures)


def assessment_check(payload: dict, result: dict) -> tuple[bool, list[str]]:
    """D15/M4: any tier / confidence / range / inactive / dependence claim in the prose must agree
    with `current.assessment`. Retired value-tier nouns can no longer stand in for the tier."""
    a = ((payload.get("current") or {}).get("assessment")) or None
    if not a:
        return (True, [])
    long = str(result.get("long", "")).lower()
    fails: list[str] = []
    _TIER_NOUNS = ["first-line", "second-line", "third-line", "fourth-line", "top-pair",
                   "second-pair", "third-pair", "number-one", "elite", "starter", "tandem", "backup"]

    if a.get("disqualify_reason") == "inactive":
        if not any(s in long for s in ("inactive", "last played", "hasn't played", "has not played")):
            fails.append("inactive player: prose must state he is inactive")
        lp = str(a.get("last_played_season") or "").lower()
        if lp and lp not in long:
            fails.append(f"inactive: prose must name last_played_season ({lp})")
        claimed = next((n for n in _TIER_NOUNS if n in long), None)
        if claimed:
            fails.append(f"inactive player: prose makes a current-tier claim ('{claimed}')")
        return (len(fails) == 0, fails)

    label = str(a.get("tier_label") or "").lower()
    conf = a.get("tier_confidence") or 0.0
    within = a.get("tier_prob_within_one") or 0.0
    thr = a.get("within_one_range_copy") or 0.85
    range_licensed = (conf < 0.55) and (within >= thr)
    range_claim = bool(re.search(
        r"(first|second|third|fourth|top|number)[\w-]*\s+or\s+(first|second|third|fourth|top|number)", long))
    if range_claim and not range_licensed:
        fails.append("unlicensed two-tier range claim (stored within-one condition does not hold)")
    if label and not range_claim:
        core = re.sub(r"\s+(forward|defenseman|goalie|starter)$", "", label).strip()
        if core and core not in long:
            fails.append(f"prose omits the assessment tier '{core}' (D15: tier must match the assessment)")

    n = a.get("dependence_n_partners")
    if n is not None and n < 3:
        if re.search(r"linemate|without his|carries his line", long) and not re.search(
                r"thin|small sample|few partners|limited", long):
            fails.append("linemate-dependence claim on <3 partners must be hedged")
    return (len(fails) == 0, fails)


# --- target selection -------------------------------------------------------------------------
def _weekly_players(season: str) -> list[int]:
    """Skaters who played an NHL game in the last 7 days of the season's data."""
    p = bq.project()
    df = bq.query_df(f"""
        with last_day as (
            select max(game_date) as d from `{p}.nhl_mart.mart_player_game_stats` where season = '{season}'
        )
        select distinct s.player_id
        from `{p}.nhl_mart.mart_player_game_stats` s, last_day
        where s.season = '{season}'
          and s.game_date >= date_sub(last_day.d, interval 7 day)
          and substr(cast(s.game_id as string), 5, 2) in ('02', '03')
          and s.position_code in ('C', 'L', 'R', 'D')
    """)
    return [int(x) for x in df["player_id"].tolist()]


def _all_players(season: str) -> list[int]:
    p = bq.project()
    df = bq.query_df(f"""
        select player_id from `{p}.nhl_models.player_overall` where season_window = '{season}'
    """)
    return [int(x) for x in df["player_id"].tolist()]


def _persist(rows: list[dict], season: str) -> None:
    if not rows:
        return
    df = pd.DataFrame(rows)
    ids = ", ".join(str(int(r["player_id"])) for r in rows)
    table_id = f"{bq.project()}.{config.MODELS_DATASET}.player_verdict"
    try:
        bq.client().get_table(table_id)
        bq.client().query(
            f"DELETE FROM `{table_id}` WHERE season = '{season}' AND player_id IN ({ids})").result()
        bq.write_df(df, "player_verdict", write_disposition="WRITE_APPEND")
    except Exception:
        bq.write_df(df, "player_verdict", write_disposition="WRITE_TRUNCATE")


def _generate_one(pid: int, season: str, gen_ts: str) -> tuple[int, Optional[dict], str]:
    """Build the payload, generate + consistency/quality check (regenerating up to the limit), and
    return (pid, row|None, status). Never raises: a failed player is reported as dropped, not fatal,
    so one bad record cannot kill a long backfill."""
    try:
        payload = build_payload(pid, season)
        result, last = None, []
        for _ in range(config.VERDICT["MAX_REGEN_ATTEMPTS"]):
            cand = _gemini(payload)
            if not cand:
                continue
            ok, failures = consistency_check(payload, cand.get("numbers_used", []))
            qok, qfail = quality_check(payload, cand)
            aok, afail = assessment_check(payload, cand)   # D15/M4: tier/confidence/range/inactive
            if ok and qok and aok:
                result = cand
                break
            last = failures + qfail + afail
        if not result:
            return (pid, None, f"dropped (checks: {last})")
        row = {
            "player_id": int(pid), "season": season,
            "long": result["long"], "short": result.get("short", ""),
            "numbers_used": json.dumps(result.get("numbers_used", [])),
            "identity_confidence": payload["identity"].get("confidence"),
            "model_version": config.VERDICT["MODEL_VERSION"],
            "generated_at": gen_ts,
            "payload_hash": hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16],
        }
        return (pid, row, f"ok [{payload['identity'].get('confidence')}] {result.get('short', '')}")
    except Exception as e:  # noqa: BLE001 - a single bad player must not abort the run
        return (pid, None, f"error: {e}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="2025-26")
    ap.add_argument("--players", type=int, nargs="*", help="explicit player ids")
    ap.add_argument("--weekly", action="store_true", help="players who played in the last 7 days")
    ap.add_argument("--full", action="store_true", help="all players with an overall row this season (backfill/refit)")
    ap.add_argument("--sample", type=int, default=0, help="cap the target set to N players (spot runs)")
    ap.add_argument("--dry-run", action="store_true", help="build payloads + print; no Gemini, no write")
    ap.add_argument("--no-write", action="store_true", help="generate + check + print the prose, but do NOT persist (review mode)")
    ap.add_argument("--skip-existing", action="store_true", help="skip players already in player_verdict for the season (resume)")
    ap.add_argument("--concurrency", type=int, default=config.VERDICT["BACKFILL_CONCURRENCY"],
                    help="parallel workers (Gemini calls are I/O-bound)")
    args = ap.parse_args()

    if args.players:
        targets = [int(x) for x in args.players]
    elif args.weekly:
        targets = _weekly_players(args.season)
    elif args.full:
        targets = _all_players(args.season)
    else:
        ap.error("choose --players, --weekly, or --full")
    if args.sample:
        targets = targets[:args.sample]

    if args.dry_run:
        for pid in targets:
            print(json.dumps(build_payload(int(pid), args.season), indent=2))
        return

    # resume: skip players already written for this season
    if args.skip_existing and not args.no_write:
        try:
            tbl = f"{bq.project()}.{config.MODELS_DATASET}.player_verdict"
            done = bq.query_df(f"select distinct player_id from `{tbl}` where season = '{args.season}'")
            have = {int(x) for x in done["player_id"].tolist()}
            before = len(targets)
            targets = [t for t in targets if int(t) not in have]
            print(f"skip-existing: {before - len(targets)} already present, {len(targets)} to generate")
        except Exception:
            pass  # table not created yet

    print(f"verdict targets: {len(targets)} players (season {args.season}), concurrency {args.concurrency}")
    _impact_frame(config.VERDICT["IDENTITY_WINDOW"])  # pre-warm the shared league frame before the pool

    gen_ts = str(pd.Timestamp.utcnow())
    total, dropped, done_n = len(targets), 0, 0
    written, pending = 0, []
    batch = config.VERDICT["PERSIST_BATCH"]
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as ex:
        futs = {ex.submit(_generate_one, int(pid), args.season, gen_ts): int(pid) for pid in targets}
        for fut in as_completed(futs):
            pid, row, status = fut.result()
            done_n += 1
            print(f"  [{done_n}/{total}] {pid}: {status}")
            if row is None:
                dropped += 1
                continue
            pending.append(row); written += 1
            if not args.no_write and len(pending) >= batch:
                _persist(pending, args.season)
                print(f"  ... checkpoint: persisted {len(pending)} ({written} written so far)")
                pending = []

    if not args.no_write and pending:
        _persist(pending, args.season)
    if args.no_write:
        print(f"review mode (--no-write): {written} generated, {dropped} dropped; nothing persisted.")
    else:
        print(f"wrote {written} verdicts, dropped {dropped}.")


if __name__ == "__main__":
    main()

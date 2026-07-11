#!/usr/bin/env bash
# P4 consumer-sweep recompute chain. Re-runs every models_ml consumer downstream of the
# retrained player_impact + shot_xg, in DAG dependency order. Continues past failures and
# records per-job exit codes for triage (does NOT auto-stop the whole sweep on one job).
set -u
cd /Users/codytownsend/Desktop/nhl/NIR
export GOOGLE_APPLICATION_CREDENTIALS="$PWD/secrets/nhl-intel-sa.json"
export GCP_PROJECT_ID=nhl-intel-498216
export VECLIB_MAXIMUM_THREADS=1 OMP_NUM_THREADS=1
PY=research/deployment-atlas/.venv/bin/python
DBT=/Library/Frameworks/Python.framework/Versions/3.10/bin/dbt
LOGDIR=docs/rebuild-reports/p4_chain
mkdir -p "$LOGDIR"
SUMMARY=docs/rebuild-reports/p4_chain_summary.tsv
: > "$SUMMARY"

run() { # run <label> <module+args...>
  local label="$1"; shift
  echo "### $(date +%H:%M:%S) START $label"
  $PY -m "$@" > "$LOGDIR/$label.log" 2>&1
  local rc=$?
  printf "%s\t%s\n" "$label" "$rc" >> "$SUMMARY"
  echo "### $(date +%H:%M:%S) END   $label rc=$rc"
}
rundbt() { # rundbt <label> <select>
  local label="$1"; local sel="$2"
  echo "### $(date +%H:%M:%S) START $label (dbt)"
  (cd dbt && $DBT run --select "$sel") > "$LOGDIR/$label.log" 2>&1
  local rc=$?
  printf "%s\t%s\n" "$label" "$rc" >> "$SUMMARY"
  echo "### $(date +%H:%M:%S) END   $label rc=$rc"
}

# --- Wave 1: foundations (need rebuilt marts + retrained player_impact) ---
run compute_ratings            models_ml.compute_ratings
run score_winprob              models_ml.score_winprob
rundbt int_event_leverage      int_event_leverage
run compute_composite          models_ml.compute_composite
run compute_gar                models_ml.compute_gar
run write_archetypes           models_ml.fit_archetypes_v2 --write

# --- Wave 2: team-context + goalie lenses (independent of composite) ---
run simulate_deserved          models_ml.simulate_deserved
run compute_style_map          models_ml.compute_style_map
run streak_doctor              models_ml.streak_doctor
run compute_consistency        models_ml.compute_consistency
run compute_coach_trust        models_ml.compute_coach_trust
run compute_goalie_radar       models_ml.compute_goalie_radar
run compute_goalie_gar         models_ml.compute_goalie_gar
run compute_physical           models_ml.compute_physical
run compute_twins              models_ml.compute_twins

# --- Wave 3: depend on composite / gar / archetypes / leverage / winprob ---
run compute_clutch             models_ml.compute_clutch
run compute_divergence         models_ml.compute_divergence
run compute_deployment_efficiency models_ml.compute_deployment_efficiency
run compute_player_radar       models_ml.compute_player_radar
run fit_aging_curves           models_ml.fit_aging_curves
run compute_overall            models_ml.compute_overall
run compute_assessment         models_ml.compute_assessment

# --- Wave 4: context layer + fits (depend on wave 3) ---
run compute_prior_quality      models_ml.compute_prior_quality
rundbt build_quality_context   mart_player_quality_context
run compute_archetype_explainer models_ml.compute_archetype_explainer
run compute_team_needs         models_ml.compute_team_needs
run train_linefit              models_ml.train_linefit
run roster_forecast            models_ml.project_roster_forecast --full

echo "### CHAIN COMPLETE"

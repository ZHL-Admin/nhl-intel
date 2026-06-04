"""LLM-based narrative summary generation for daily reports."""
import json
import os
from typing import Any, List, Dict
import google.generativeai as genai


SYSTEM_PROMPT = """
You are a hockey analytics assistant writing the daily summary section of an internal intelligence report.
Write 4 to 6 sentences. Be specific and cite the metrics provided. Use plain language.
Do not use cliches like 'battle-tested' or 'fired on all cylinders'.
Do not speculate beyond what the data shows.
"""


def build_user_prompt(metrics: Dict[str, Any]) -> str:
    """Build the user prompt from structured metric data.

    Args:
        metrics: Dict containing pre-computed metrics from mart tables.

    Returns:
        Formatted prompt string for the LLM.
    """
    return f"""
Yesterday's NHL metrics summary:

{json.dumps(metrics, indent=2)}

Write the daily intelligence summary based on the above data.
"""


def generate_summary(report_data: List[Dict[str, Any]]) -> str:
    """Generate narrative summary using Gemini API.

    Args:
        report_data: List of dicts from mart_daily_report_feed query.

    Returns:
        Narrative paragraph summarizing the day's games and key metrics.
    """
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        return _generate_fallback_summary(report_data)

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
    except Exception as e:
        print(f"LLM client creation error: {type(e).__name__}: {str(e)}")
        return _generate_fallback_summary(report_data)

    # Extract metrics for LLM prompt
    metrics = {
        "games": [],
        "notable_performances": [],
        "team_trends": []
    }

    games_seen = set()
    for row in report_data:
        game_id = row["game_id"]

        if game_id not in games_seen:
            games_seen.add(game_id)

        # Collect team data
        team_data = {
            "team": row["team_abbrev"],
            "home_away": row["home_away"],
            "score": f"{row['goals_for']}-{row['goals_against']}" if row["goals_for"] is not None else "N/A",
            "cf_pct": f"{row['cf_pct']:.1%}" if row["cf_pct"] is not None else "N/A",
            "hdcf_per60": f"{row['hdcf_per60']:.1f}" if row["hdcf_per60"] is not None else "N/A",
            "rolling_cf_pct": f"{row['rolling_cf_pct_5gp']:.1%}" if row["rolling_cf_pct_5gp"] is not None else "N/A",
        }
        metrics["games"].append(team_data)

        # Collect notable players
        if row["top_player_name"]:
            metrics["notable_performances"].append({
                "player": row["top_player_name"],
                "team": row["team_abbrev"],
                "points_per60": f"{row['top_player_points_per60']:.1f}",
                "status": row["top_player_hot_cold"]
            })

    user_prompt = build_user_prompt(metrics)

    try:
        response = model.generate_content(
            f"{SYSTEM_PROMPT}\n\n{user_prompt}",
            generation_config={
                'temperature': 0.7,
                'max_output_tokens': 1000,
            }
        )
        return response.text.strip()
    except Exception as e:
        print(f"LLM API error: {type(e).__name__}: {str(e)}")
        return _generate_fallback_summary(report_data)


def _generate_fallback_summary(report_data: List[Dict[str, Any]]) -> str:
    """Generate a basic summary when LLM is unavailable.

    Args:
        report_data: List of dicts from mart_daily_report_feed query.

    Returns:
        Simple narrative summary based on the data.
    """
    if not report_data:
        return "No games were played yesterday."

    game_count = len(set(row["game_id"] for row in report_data))

    summaries = []
    for row in report_data:
        if row["goals_for"] is not None and row["home_away"] == "home":
            away_row = next((r for r in report_data if r["game_id"] == row["game_id"] and r["home_away"] == "away"), None)
            if away_row:
                winner = row["team_abbrev"] if row["goals_for"] > row["goals_against"] else away_row["team_abbrev"]
                score = f"{row['goals_for']}-{row['goals_against']}" if row["home_away"] == "home" else f"{away_row['goals_for']}-{away_row['goals_against']}"
                summaries.append(f"{winner} won {score}")

    summary_text = f"Yesterday saw {game_count} NHL game{'s' if game_count > 1 else ''}. "
    if summaries:
        summary_text += ". ".join(summaries) + "."

    return summary_text

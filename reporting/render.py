"""HTML report rendering using Jinja2 templates."""
from datetime import datetime
from pathlib import Path
from typing import Any, List, Dict, Optional, Tuple
from jinja2 import Environment, FileSystemLoader


def render_report(report_data: List[Dict[str, Any]], summary: str, report_date: str) -> str:
    """Render HTML report from query data and LLM summary.

    Args:
        report_data: List of dicts from mart_daily_report_feed query.
        summary: AI-generated narrative summary.
        report_date: Date string in YYYY-MM-DD format.

    Returns:
        Rendered HTML string.
    """
    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("report.html")

    games = _structure_games(report_data)
    team_trends = _structure_team_trends(report_data)

    context = {
        "report_date": report_date,
        "summary": summary,
        "games": games,
        "team_trends": team_trends,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
    }

    return template.render(**context)


def _structure_games(report_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Structure game data for template rendering.

    Args:
        report_data: Raw report data from query.

    Returns:
        List of game dicts with nested team data.
    """
    games_dict = {}

    for row in report_data:
        game_id = row["game_id"]

        if game_id not in games_dict:
            games_dict[game_id] = {
                "game_id": game_id,
                "teams": []
            }

        team_data = {
            "abbrev": row["team_abbrev"],
            "score": f"{row['goals_for']}-{row['goals_against']}" if row["goals_for"] is not None else "N/A",
            "cf_pct": f"{row['cf_pct']:.1%}" if row["cf_pct"] is not None else "N/A",
            "hdcf_per60": f"{row['hdcf_per60']:.1f}" if row["hdcf_per60"] is not None else "N/A",
            "hdca_per60": f"{row['hdca_per60']:.1f}" if row["hdca_per60"] is not None else "N/A",
            "top_player": None
        }

        if row["top_player_name"]:
            team_data["top_player"] = {
                "name": row["top_player_name"],
                "position": row["top_player_position"],
                "points_per60": f"{row['top_player_points_per60']:.1f}",
                "status": row["top_player_hot_cold"]
            }

        games_dict[game_id]["teams"].append(team_data)

    return list(games_dict.values())


def _structure_team_trends(report_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Structure team trend data with directional indicators.

    Args:
        report_data: Raw report data from query.

    Returns:
        List of team trend dicts with trend indicators.
    """
    trends = []

    for row in report_data:
        if not row["has_full_5game_sample"]:
            continue

        cf_trend, cf_symbol = _calculate_trend(
            row["cf_pct"],
            row["rolling_cf_pct_5gp"]
        )

        hdcf_trend, hdcf_symbol = _calculate_trend(
            row["hdcf_per60"],
            row["rolling_hdcf_per60_5gp"]
        )

        trends.append({
            "abbrev": row["team_abbrev"],
            "rolling_cf_pct": f"{row['rolling_cf_pct_5gp']:.1%}" if row["rolling_cf_pct_5gp"] is not None else "N/A",
            "cf_trend": cf_trend,
            "cf_trend_symbol": cf_symbol,
            "rolling_hdcf_per60": f"{row['rolling_hdcf_per60_5gp']:.1f}" if row["rolling_hdcf_per60_5gp"] is not None else "N/A",
            "hdcf_trend": hdcf_trend,
            "hdcf_trend_symbol": hdcf_symbol,
        })

    return trends


def _calculate_trend(current: Optional[float], rolling: Optional[float]) -> Tuple[str, str]:
    """Calculate trend direction and symbol.

    Args:
        current: Current game metric value.
        rolling: Rolling average metric value.

    Returns:
        Tuple of (trend_class, trend_symbol).
    """
    if current is None or rolling is None:
        return ("neutral", "—")

    diff_pct = (current - rolling) / rolling if rolling != 0 else 0

    if diff_pct > 0.05:
        return ("up", "↑")
    elif diff_pct < -0.05:
        return ("down", "↓")
    else:
        return ("neutral", "—")

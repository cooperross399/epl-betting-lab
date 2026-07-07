from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from epl_betting_lab.models.ratings import simple_form_table


@dataclass(frozen=True)
class AgentBriefConfig:
    current_season: str = "2627"
    recent_matches: int = 6


def _clean_matches(matches: pd.DataFrame) -> pd.DataFrame:
    return matches.dropna(subset=["date", "home_team", "away_team", "home_goals", "away_goals"]).sort_values("date").copy()


def filter_current_season(matches: pd.DataFrame, current_season: str) -> pd.DataFrame:
    """Return current-season matches if present; otherwise return an empty frame."""
    if "season" not in matches.columns:
        return matches.iloc[0:0].copy()
    season = matches[matches["season"].astype(str) == str(current_season)].copy()
    return _clean_matches(season) if not season.empty else season


def build_market_trends(matches: pd.DataFrame) -> dict[str, float | int]:
    """Summarize simple league-wide trends from completed matches."""
    df = _clean_matches(matches)
    if df.empty:
        return {
            "matches": 0,
            "avg_goals": 0.0,
            "home_win_rate": 0.0,
            "draw_rate": 0.0,
            "away_win_rate": 0.0,
            "over_2_5_rate": 0.0,
            "btts_rate": 0.0,
        }

    total_goals = df["home_goals"] + df["away_goals"]
    return {
        "matches": int(len(df)),
        "avg_goals": round(float(total_goals.mean()), 2),
        "home_win_rate": round(float((df["home_goals"] > df["away_goals"]).mean()), 3),
        "draw_rate": round(float((df["home_goals"] == df["away_goals"]).mean()), 3),
        "away_win_rate": round(float((df["home_goals"] < df["away_goals"]).mean()), 3),
        "over_2_5_rate": round(float((total_goals > 2.5).mean()), 3),
        "btts_rate": round(float(((df["home_goals"] > 0) & (df["away_goals"] > 0)).mean()), 3),
    }


def build_team_snapshot(matches: pd.DataFrame, recent_matches: int = 6) -> pd.DataFrame:
    """Return recent team form plus goals per match columns."""
    if matches.empty:
        return pd.DataFrame(columns=[
            "team", "matches", "points", "wins", "draws", "losses", "goals_for",
            "goals_against", "goal_diff", "points_per_match", "gf_per_match", "ga_per_match",
        ])

    form = simple_form_table(matches, last_n=recent_matches).copy()
    form["gf_per_match"] = (form["goals_for"] / form["matches"].replace(0, pd.NA)).round(2)
    form["ga_per_match"] = (form["goals_against"] / form["matches"].replace(0, pd.NA)).round(2)
    return form


def build_team_market_profile(matches: pd.DataFrame) -> pd.DataFrame:
    """Summarize team-level over/BTTS rates for completed matches."""
    df = _clean_matches(matches)
    rows: list[dict[str, object]] = []
    teams = sorted(set(df["home_team"]).union(set(df["away_team"]))) if not df.empty else []

    for team in teams:
        team_games = df[(df["home_team"] == team) | (df["away_team"] == team)].copy()
        totals = team_games["home_goals"] + team_games["away_goals"]
        btts = (team_games["home_goals"] > 0) & (team_games["away_goals"] > 0)
        rows.append({
            "team": team,
            "matches": int(len(team_games)),
            "avg_total_goals": round(float(totals.mean()), 2) if len(team_games) else 0.0,
            "over_2_5_rate": round(float((totals > 2.5).mean()), 3) if len(team_games) else 0.0,
            "btts_rate": round(float(btts.mean()), 3) if len(team_games) else 0.0,
        })

    return pd.DataFrame(rows).sort_values(["over_2_5_rate", "avg_total_goals"], ascending=False) if rows else pd.DataFrame(rows)


def render_agent_brief(
    all_matches: pd.DataFrame,
    current_season: str = "2627",
    recent_matches: int = 6,
) -> tuple[str, pd.DataFrame, pd.DataFrame]:
    """Render a markdown brief for the coding agent and return supporting tables."""
    current = filter_current_season(all_matches, current_season)
    if current.empty:
        basis = _clean_matches(all_matches).tail(380).copy()
        basis_label = f"No `{current_season}` matches found yet. Using the latest 380 completed matches as preseason baseline."
    else:
        basis = current
        basis_label = f"Using current season `{current_season}` completed EPL matches."

    trends = build_market_trends(basis)
    team_form = build_team_snapshot(basis, recent_matches=recent_matches)
    team_profile = build_team_market_profile(basis)

    top_form = team_form.head(8)
    bottom_form = team_form.tail(8).sort_values(["points_per_match", "goal_diff"], ascending=[True, True])
    high_event = team_profile.head(8) if not team_profile.empty else pd.DataFrame()
    low_event = team_profile.tail(8).sort_values(["over_2_5_rate", "avg_total_goals"], ascending=[True, True]) if not team_profile.empty else pd.DataFrame()

    lines = [
        "# EPL Betting Lab — Agent Weekly Brief",
        "",
        f"**Data basis:** {basis_label}",
        "",
        "## League market trends",
        "",
        f"- Completed matches in basis: {trends['matches']}",
        f"- Average goals per match: {trends['avg_goals']}",
        f"- Home win rate: {trends['home_win_rate']:.1%}",
        f"- Draw rate: {trends['draw_rate']:.1%}",
        f"- Away win rate: {trends['away_win_rate']:.1%}",
        f"- Over 2.5 rate: {trends['over_2_5_rate']:.1%}",
        f"- BTTS rate: {trends['btts_rate']:.1%}",
        "",
        "## Teams to review manually",
        "",
        "Use these lists as prompts for model review, not automatic bets.",
        "",
        "### Strong recent form",
        "",
        top_form.to_markdown(index=False) if not top_form.empty else "No team form available yet.",
        "",
        "### Weak recent form",
        "",
        bottom_form.to_markdown(index=False) if not bottom_form.empty else "No team form available yet.",
        "",
        "### High-event teams",
        "",
        high_event.to_markdown(index=False) if not high_event.empty else "No team market profile available yet.",
        "",
        "### Low-event teams",
        "",
        low_event.to_markdown(index=False) if not low_event.empty else "No team market profile available yet.",
        "",
        "## Codex next-step checklist",
        "",
        "- Check whether the backtest is over-firing on any market.",
        "- Compare current-season goal environment to the historical baseline.",
        "- Review promoted teams separately before adding automatic fades.",
        "- Do not change thresholds because of one result or one matchweek.",
        "- If current odds are missing, request manual odds before generating a real weekly card.",
    ]
    return "\n".join(lines), team_form, team_profile


def save_agent_brief(
    all_matches: pd.DataFrame,
    output_dir: Path,
    current_season: str = "2627",
    recent_matches: int = 6,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown, team_form, team_profile = render_agent_brief(
        all_matches,
        current_season=current_season,
        recent_matches=recent_matches,
    )
    brief_path = output_dir / "agent_weekly_brief.md"
    brief_path.write_text(markdown, encoding="utf-8")
    team_form.to_csv(output_dir / "agent_team_recent_form.csv", index=False)
    team_profile.to_csv(output_dir / "agent_team_market_profile.csv", index=False)
    return brief_path

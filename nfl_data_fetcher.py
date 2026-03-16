"""
nfl_data_fetcher.py — NFL Team Stats Fetcher

Fetches team offensive and defensive stats from ESPN.
Computes EPA-like efficiency metrics from PPG, OPPG, yards, turnovers.

Outputs:
  - nfl_stats_cache.json  (full season stats)
  - nfl_stats_recent_cache.json  (last 4 games)
  - nfl_sos_cache.json  (strength of schedule)
"""

import json
import os
import requests
from datetime import datetime
from nfl_teams_static import resolve_team_name, _NFL_TEAMS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATS_CACHE = os.path.join(BASE_DIR, 'nfl_stats_cache.json')
RECENT_CACHE = os.path.join(BASE_DIR, 'nfl_stats_recent_cache.json')
SOS_CACHE = os.path.join(BASE_DIR, 'nfl_sos_cache.json')

# ESPN API endpoints for NFL team stats
ESPN_STANDINGS_URL = "https://site.api.espn.com/apis/v2/sports/football/nfl/standings"
ESPN_TEAMS_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams"
ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def _fetch_json(url, params=None):
    """Fetch JSON from ESPN API."""
    resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _extract_stat(stats_list, stat_name, default=0.0):
    """Extract a named stat from ESPN's stats array."""
    for s in stats_list:
        if s.get('name') == stat_name or s.get('abbreviation') == stat_name:
            try:
                return float(s.get('value', default))
            except (ValueError, TypeError):
                return default
    return default


def fetch_team_stats(season=None):
    """Fetch team standings/stats from ESPN.

    Returns dict keyed by full team name:
    {
        'TeamName': {
            'OFF_EPA': float,  # Approximated from PPG/yards efficiency
            'DEF_EPA': float,  # Approximated from OPPG/yards-allowed
            'NET_EPA': float,
            'PPG': float,
            'OPPG': float,
            'wins': int,
            'losses': int,
            'record': str,
        }
    }
    """
    params = {}
    if season:
        params['season'] = season

    data = _fetch_json(ESPN_STANDINGS_URL, params)
    stats = {}

    # League averages for EPA approximation
    all_ppg = []
    all_oppg = []

    for group in data.get('children', []):
        for division in group.get('children', []):
            for entry in division.get('standings', {}).get('entries', []):
                team_info = entry.get('team', {})
                team_name = team_info.get('displayName', '')
                if not team_name:
                    continue

                resolved = resolve_team_name(team_name) or team_name
                stat_values = entry.get('stats', [])

                wins = _extract_stat(stat_values, 'wins')
                losses = _extract_stat(stat_values, 'losses')
                ppg = _extract_stat(stat_values, 'pointsFor')
                oppg = _extract_stat(stat_values, 'pointsAgainst')

                # Normalize to per-game if needed
                games = wins + losses
                if games > 0 and ppg > 50:  # Likely season totals, not per-game
                    ppg = ppg / games
                    oppg = oppg / games

                all_ppg.append(ppg)
                all_oppg.append(oppg)

                stats[resolved] = {
                    'PPG': round(ppg, 1),
                    'OPPG': round(oppg, 1),
                    'wins': int(wins),
                    'losses': int(losses),
                    'record': f"{int(wins)}-{int(losses)}",
                    'games': int(games),
                }

    # Approximate EPA from PPG relative to league average
    if all_ppg:
        lg_ppg = sum(all_ppg) / len(all_ppg)
        lg_oppg = sum(all_oppg) / len(all_oppg)
    else:
        lg_ppg, lg_oppg = 22.5, 22.5

    for team, s in stats.items():
        # Offensive EPA ≈ how much better than average the offense is
        s['OFF_EPA'] = round((s['PPG'] - lg_ppg) / 3.0, 3)  # Scale to ~EPA range
        # Defensive EPA ≈ how much WORSE opponents score (lower = better defense)
        s['DEF_EPA'] = round((s['OPPG'] - lg_oppg) / 3.0, 3)
        s['NET_EPA'] = round(s['OFF_EPA'] - s['DEF_EPA'], 3)

    return stats


def fetch_recent_stats(num_weeks=4):
    """Fetch recent game results to compute last-N-weeks form.

    Uses ESPN scoreboard API with explicit week parameters to retrieve
    the correct past weeks instead of fetching only the current week.
    Returns dict similar to fetch_team_stats but for recent games only.
    """
    recent_ppg = {}  # team → [list of recent scores]
    recent_oppg = {}  # team → [list of opponent scores]

    # Determine current week from default scoreboard response
    try:
        current_data = _fetch_json(ESPN_SCOREBOARD_URL)
        current_week = current_data.get('week', {}).get('number', 1)
        season_type = current_data.get('season', {}).get('type', 2)
    except Exception:
        current_week = 1
        season_type = 2

    for offset in range(num_weeks):
        target_week = current_week - offset
        if target_week < 1:
            break
        try:
            params = {'week': target_week, 'seasontype': season_type}
            data = _fetch_json(ESPN_SCOREBOARD_URL, params)
            for event in data.get('events', []):
                # Only include completed games
                completed = event.get('status', {}).get('type', {}).get('completed', False)
                if not completed:
                    continue

                competitors = event.get('competitions', [{}])[0].get('competitors', [])
                if len(competitors) < 2:
                    continue
                for comp in competitors:
                    team_name = comp.get('team', {}).get('displayName', '')
                    score = int(comp.get('score', 0))
                    resolved = resolve_team_name(team_name) or team_name
                    recent_ppg.setdefault(resolved, []).append(score)

                # Cross-reference opponents
                t1 = resolve_team_name(competitors[0].get('team', {}).get('displayName', ''))
                t2 = resolve_team_name(competitors[1].get('team', {}).get('displayName', ''))
                s1 = int(competitors[0].get('score', 0))
                s2 = int(competitors[1].get('score', 0))
                if t1:
                    recent_oppg.setdefault(t1, []).append(s2)
                if t2:
                    recent_oppg.setdefault(t2, []).append(s1)
        except Exception:
            continue

    stats = {}
    all_ppg = []
    all_oppg = []

    for team in recent_ppg:
        ppg_list = recent_ppg.get(team, [])
        oppg_list = recent_oppg.get(team, [])
        if not ppg_list:
            continue
        avg_ppg = sum(ppg_list) / len(ppg_list)
        avg_oppg = sum(oppg_list) / len(oppg_list) if oppg_list else 22.5
        all_ppg.append(avg_ppg)
        all_oppg.append(avg_oppg)
        stats[team] = {'PPG': round(avg_ppg, 1), 'OPPG': round(avg_oppg, 1)}

    lg_ppg = sum(all_ppg) / len(all_ppg) if all_ppg else 22.5
    lg_oppg = sum(all_oppg) / len(all_oppg) if all_oppg else 22.5

    for team, s in stats.items():
        s['OFF_EPA'] = round((s['PPG'] - lg_ppg) / 3.0, 3)
        s['DEF_EPA'] = round((s['OPPG'] - lg_oppg) / 3.0, 3)
        s['NET_EPA'] = round(s['OFF_EPA'] - s['DEF_EPA'], 3)

    return stats


def _fetch_season_matchups():
    """Fetch all completed regular-season results to build opponent map.

    Iterates through each completed week of the current season to build
    a mapping of team → [(opponent, team_score, opp_score), ...].

    Returns: {team_name: [(opponent_name, team_score, opp_score), ...]}
    """
    try:
        current_data = _fetch_json(ESPN_SCOREBOARD_URL)
        current_week = current_data.get('week', {}).get('number', 1)
        season_type = current_data.get('season', {}).get('type', 2)
    except Exception:
        return {}

    matchups = {}
    for week in range(1, current_week + 1):
        try:
            params = {'week': week, 'seasontype': season_type}
            data = _fetch_json(ESPN_SCOREBOARD_URL, params)
            for event in data.get('events', []):
                completed = event.get('status', {}).get('type', {}).get('completed', False)
                if not completed:
                    continue
                comps = event.get('competitions', [{}])[0].get('competitors', [])
                if len(comps) < 2:
                    continue
                t1 = resolve_team_name(comps[0].get('team', {}).get('displayName', ''))
                t2 = resolve_team_name(comps[1].get('team', {}).get('displayName', ''))
                s1 = int(comps[0].get('score', 0))
                s2 = int(comps[1].get('score', 0))
                if t1 and t2:
                    matchups.setdefault(t1, []).append((t2, s1, s2))
                    matchups.setdefault(t2, []).append((t1, s2, s1))
        except Exception:
            continue

    return matchups


def compute_sos(stats, matchups=None):
    """Compute strength of schedule from actual opponents' records.

    When matchups are provided (from _fetch_season_matchups), calculates
    real SOS as the average opponent win percentage minus league average,
    scaled to spread-point range.

    Falls back to neutral (0.0) if no matchup data is available.

    Returns: {team: sos_value} where positive = faced stronger opponents.
    """
    if not stats:
        return {}

    # Build win percentage lookup from standings
    win_pct = {}
    for team, s in stats.items():
        games = s.get('games', 0)
        win_pct[team] = s.get('wins', 0) / games if games > 0 else 0.5

    league_avg_wp = sum(win_pct.values()) / len(win_pct) if win_pct else 0.5

    sos = {}
    if matchups:
        # Real SOS: average opponent win percentage
        for team in stats:
            opps = matchups.get(team, [])
            if not opps:
                sos[team] = 0.0
                continue
            opp_wps = [win_pct.get(opp_name, 0.5) for opp_name, _, _ in opps]
            avg_opp_wp = sum(opp_wps) / len(opp_wps)
            # Positive = faced stronger-than-average opponents
            sos[team] = round((avg_opp_wp - league_avg_wp) * 6, 3)
        total_games = sum(len(v) for v in matchups.values()) // 2
        print(f"  [SOS] Computed from {total_games} actual game results")
    else:
        # No opponent data — assume neutral SOS for all teams
        print("  [SOS] No matchup data available — setting all teams to 0.0")
        for team in stats:
            sos[team] = 0.0

    return sos


def save_cache(data, path):
    """Save data dict to JSON cache with timestamp."""
    output = {
        'fetched_at': datetime.now().isoformat(),
        'data': data,
    }
    with open(path, 'w') as f:
        json.dump(output, f, indent=2)


def main():
    print("[NFL] Fetching team stats from ESPN...")
    try:
        stats = fetch_team_stats()
        # Unwrap for compatibility: cache stores {team: stats_dict} directly
        save_cache(stats, STATS_CACHE)
        print(f"[SUCCESS] Season stats: {len(stats)} teams → {os.path.basename(STATS_CACHE)}")
    except Exception as e:
        print(f"[ERROR] Season stats failed: {e}")

    print("[NFL] Fetching recent form (last 4 weeks)...")
    try:
        recent = fetch_recent_stats(num_weeks=4)
        save_cache(recent, RECENT_CACHE)
        print(f"[SUCCESS] Recent stats: {len(recent)} teams → {os.path.basename(RECENT_CACHE)}")
    except Exception as e:
        print(f"[ERROR] Recent stats failed: {e}")

    print("[NFL] Computing strength of schedule...")
    try:
        stats = fetch_team_stats()
        print("  [SOS] Fetching season matchups for opponent records...")
        matchups = _fetch_season_matchups()
        sos = compute_sos(stats, matchups)
        with open(SOS_CACHE, 'w') as f:
            json.dump(sos, f, indent=2)
        print(f"[SUCCESS] SOS: {len(sos)} teams → {os.path.basename(SOS_CACHE)}")
    except Exception as e:
        print(f"[ERROR] SOS computation failed: {e}")


if __name__ == '__main__':
    main()

"""
schedule_scraper.py — NFL Schedule Fetcher

Fetches the NFL weekly schedule from ESPN.
Outputs: nfl_schedule_cache.json
"""

import json
import os
import requests
from datetime import datetime
from nfl_teams_static import resolve_team_name

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEDULE_CACHE = os.path.join(BASE_DIR, 'nfl_schedule_cache.json')

ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def fetch_week_schedule(season_type=2, week=None):
    """Fetch NFL schedule for a given week from ESPN.

    Args:
        season_type: 1=preseason, 2=regular, 3=postseason
        week: Week number (1-18 for regular season)

    Returns list of game dicts.
    """
    params = {'seasontype': season_type}
    if week:
        params['week'] = week

    resp = requests.get(ESPN_SCOREBOARD_URL, headers=HEADERS, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    games = []
    for event in data.get('events', []):
        competition = event.get('competitions', [{}])[0]
        competitors = competition.get('competitors', [])
        if len(competitors) < 2:
            continue

        # ESPN: competitors[0] is usually home (homeAway == 'home')
        home_comp = None
        away_comp = None
        for comp in competitors:
            if comp.get('homeAway') == 'home':
                home_comp = comp
            elif comp.get('homeAway') == 'away':
                away_comp = comp

        if not home_comp or not away_comp:
            continue

        home_name = home_comp.get('team', {}).get('displayName', '')
        away_name = away_comp.get('team', {}).get('displayName', '')
        home_resolved = resolve_team_name(home_name) or home_name
        away_resolved = resolve_team_name(away_name) or away_name

        # Game time
        game_date = event.get('date', '')
        try:
            dt = datetime.fromisoformat(game_date.replace('Z', '+00:00'))
            time_str = dt.strftime('%-I:%M %p')
            date_str = dt.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            time_str = ''
            date_str = ''

        # Game state
        status = event.get('status', {})
        state = status.get('type', {}).get('state', 'pre')  # pre, in, post

        # Venue
        venue = competition.get('venue', {})
        venue_name = venue.get('fullName', '')
        indoor = venue.get('indoor', False)

        games.append({
            'away': away_resolved,
            'home': home_resolved,
            'time': time_str,
            'date': date_str,
            'state': state,
            'venue': venue_name,
            'indoor': indoor,
            'home_score': int(home_comp.get('score', 0)) if state != 'pre' else None,
            'away_score': int(away_comp.get('score', 0)) if state != 'pre' else None,
        })

    return games


def fetch_full_schedule(season_type=2, weeks=range(1, 19)):
    """Fetch schedule for all specified weeks.

    Returns: {week_num: {'games': [...], 'fetched_at': str}}
    """
    schedule = {}
    for week in weeks:
        try:
            games = fetch_week_schedule(season_type=season_type, week=week)
            schedule[str(week)] = {
                'games': games,
                'fetched_at': datetime.now().isoformat(),
                'game_count': len(games),
            }
            print(f"  Week {week}: {len(games)} games")
        except Exception as e:
            print(f"  Week {week}: ERROR - {e}")
            schedule[str(week)] = {'games': [], 'error': str(e)}
    return schedule


def save_schedule(schedule_data, path=SCHEDULE_CACHE):
    """Save schedule to JSON cache."""
    output = {
        'fetched_at': datetime.now().isoformat(),
        'weeks': schedule_data,
    }
    with open(path, 'w') as f:
        json.dump(output, f, indent=2)


def main():
    import sys
    print("[NFL] Fetching schedule from ESPN...")

    # Default: fetch current week only
    if len(sys.argv) > 1 and sys.argv[1] == 'all':
        print("  Fetching all 18 weeks...")
        schedule = fetch_full_schedule()
    else:
        # Fetch current week
        try:
            games = fetch_week_schedule()
            week_label = 'current'
            schedule = {week_label: {
                'games': games,
                'fetched_at': datetime.now().isoformat(),
                'game_count': len(games),
            }}
            print(f"  Current week: {len(games)} games")
        except Exception as e:
            print(f"[ERROR] Schedule fetch failed: {e}")
            return 1

    save_schedule(schedule)
    print(f"[SUCCESS] Schedule saved to {os.path.basename(SCHEDULE_CACHE)}")
    return 0


if __name__ == '__main__':
    exit(main())

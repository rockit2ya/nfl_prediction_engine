"""
odds_api.py — NFL Odds Fetcher (The Odds API)

Fetches live NFL spreads and totals from multiple sportsbooks.
Requires THE_ODDS_API_KEY environment variable.

Outputs: nfl_odds_cache.json
"""

import json
import os
import requests
from datetime import datetime
from nfl_teams_static import resolve_team_name

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ODDS_CACHE = os.path.join(BASE_DIR, 'nfl_odds_cache.json')

API_KEY = os.environ.get('THE_ODDS_API_KEY', '')
ODDS_API_BASE = "https://api.the-odds-api.com/v4/sports"
SPORT = "americanfootball_nfl"
MARKETS = "spreads,totals"
REGIONS = "us"
ODDS_FORMAT = "american"


def fetch_nfl_odds():
    """Fetch current NFL odds from The Odds API.

    Returns dict: {
        'matchup_key': {
            'away': str, 'home': str,
            'commence_time': str,
            'spreads': {book: {'home': float, 'away': float}},
            'totals': {book: {'over': float, 'under': float}},
            'fetched_at': str,
        }
    }
    """
    if not API_KEY:
        raise ValueError("THE_ODDS_API_KEY not set. Get a free key at https://the-odds-api.com")

    url = f"{ODDS_API_BASE}/{SPORT}/odds"
    params = {
        'apiKey': API_KEY,
        'regions': REGIONS,
        'markets': MARKETS,
        'oddsFormat': ODDS_FORMAT,
    }

    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    # Check remaining quota
    remaining = resp.headers.get('x-requests-remaining', '?')
    used = resp.headers.get('x-requests-used', '?')
    print(f"  Odds API quota: {remaining} remaining ({used} used)")

    games = {}
    now = datetime.now().isoformat()

    for event in data:
        away_team = resolve_team_name(event.get('away_team', '')) or event.get('away_team', '')
        home_team = resolve_team_name(event.get('home_team', '')) or event.get('home_team', '')
        commence = event.get('commence_time', '')
        key = f"{away_team} @ {home_team}"

        spreads = {}
        totals = {}

        for bookmaker in event.get('bookmakers', []):
            book_name = bookmaker.get('title', '')
            for market in bookmaker.get('markets', []):
                if market.get('key') == 'spreads':
                    outcomes = market.get('outcomes', [])
                    book_spread = {}
                    for o in outcomes:
                        team = resolve_team_name(o.get('name', '')) or o.get('name', '')
                        point = o.get('point', 0)
                        if team == home_team:
                            book_spread['home'] = point
                        elif team == away_team:
                            book_spread['away'] = point
                    if book_spread:
                        spreads[book_name] = book_spread

                elif market.get('key') == 'totals':
                    outcomes = market.get('outcomes', [])
                    book_total = {}
                    for o in outcomes:
                        if o.get('name') == 'Over':
                            book_total['over'] = o.get('point', 0)
                        elif o.get('name') == 'Under':
                            book_total['under'] = o.get('point', 0)
                    if book_total:
                        totals[book_name] = book_total

        games[key] = {
            'away': away_team,
            'home': home_team,
            'commence_time': commence,
            'spreads': spreads,
            'totals': totals,
            'fetched_at': now,
        }

    return games


def get_consensus_spread(game_data):
    """Get the consensus (average) spread from all books for a game.

    Returns: float (home team spread, negative = home favored)
    """
    spreads = game_data.get('spreads', {})
    if not spreads:
        return None
    home_spreads = [s['home'] for s in spreads.values() if 'home' in s]
    if not home_spreads:
        return None
    return round(sum(home_spreads) / len(home_spreads), 1)


def get_market_total(away, home):
    """Get the consensus total from the odds cache for a matchup."""
    if not os.path.exists(ODDS_CACHE):
        return None
    try:
        with open(ODDS_CACHE, 'r') as f:
            cache = json.load(f)
        games = cache.get('games', {})
        for key, gdata in games.items():
            if gdata.get('away') == away and gdata.get('home') == home:
                totals = gdata.get('totals', {})
                if totals:
                    all_overs = [t['over'] for t in totals.values() if 'over' in t]
                    if all_overs:
                        return round(sum(all_overs) / len(all_overs), 1)
    except Exception:
        pass
    return None


def save_odds(games, path=ODDS_CACHE):
    """Save odds to JSON cache."""
    output = {
        'fetched_at': datetime.now().isoformat(),
        'games': games,
    }
    with open(path, 'w') as f:
        json.dump(output, f, indent=2)


def main():
    print("[NFL] Fetching odds from The Odds API...")
    try:
        games = fetch_nfl_odds()
        save_odds(games)
        print(f"[SUCCESS] {len(games)} games with odds → {os.path.basename(ODDS_CACHE)}")
        for key, g in games.items():
            num_books = len(g.get('spreads', {}))
            consensus = get_consensus_spread(g)
            c_str = f"{consensus:+.1f}" if consensus is not None else "N/A"
            print(f"  {key}: {num_books} books, consensus {c_str}")
    except ValueError as e:
        print(f"[ERROR] {e}")
        return 1
    except Exception as e:
        print(f"[ERROR] Odds fetch failed: {e}")
        return 1
    return 0


if __name__ == '__main__':
    exit(main())

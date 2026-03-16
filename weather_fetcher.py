"""
weather_fetcher.py — NFL Game Weather Fetcher

Fetches weather conditions for outdoor NFL games using Open-Meteo free API.
For dome games, returns neutral (indoor) conditions.

Outputs: nfl_weather_cache.json
"""

import json
import os
import requests
from datetime import datetime
from nfl_teams_static import TEAM_NAME_TO_INFO, is_dome_game

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEATHER_CACHE = os.path.join(BASE_DIR, 'nfl_weather_cache.json')

# Open-Meteo free API (no key required)
OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"

# NFL stadium coordinates (lat, lon) for weather lookups
STADIUM_COORDS = {
    'Arizona Cardinals': (33.5276, -112.2626),
    'Atlanta Falcons': (33.7554, -84.4010),
    'Baltimore Ravens': (39.2780, -76.6227),
    'Buffalo Bills': (42.7738, -78.7870),
    'Carolina Panthers': (35.2258, -80.8528),
    'Chicago Bears': (41.8623, -87.6167),
    'Cincinnati Bengals': (39.0954, -84.5160),
    'Cleveland Browns': (41.5061, -81.6995),
    'Dallas Cowboys': (32.7473, -97.0945),
    'Denver Broncos': (39.7439, -105.0201),
    'Detroit Lions': (42.3400, -83.0456),
    'Green Bay Packers': (44.5013, -88.0622),
    'Houston Texans': (29.6847, -95.4107),
    'Indianapolis Colts': (39.7601, -86.1639),
    'Jacksonville Jaguars': (30.3239, -81.6373),
    'Kansas City Chiefs': (39.0489, -94.4839),
    'Las Vegas Raiders': (36.0909, -115.1833),
    'Los Angeles Chargers': (33.9535, -118.3391),
    'Los Angeles Rams': (33.9535, -118.3391),
    'Miami Dolphins': (25.9580, -80.2389),
    'Minnesota Vikings': (44.9736, -93.2575),
    'New England Patriots': (42.0909, -71.2643),
    'New Orleans Saints': (29.9511, -90.0812),
    'New York Giants': (40.8128, -74.0742),
    'New York Jets': (40.8128, -74.0742),
    'Philadelphia Eagles': (39.9008, -75.1675),
    'Pittsburgh Steelers': (40.4468, -80.0158),
    'San Francisco 49ers': (37.4032, -121.9698),
    'Seattle Seahawks': (47.5952, -122.3316),
    'Tampa Bay Buccaneers': (27.9759, -82.5033),
    'Tennessee Titans': (36.1665, -86.7713),
    'Washington Commanders': (38.9076, -76.8645),
}


def fetch_game_weather(home_team, game_datetime=None):
    """Fetch weather for a game at the home team's stadium.

    Args:
        home_team: Full team name (e.g. 'Buffalo Bills')
        game_datetime: datetime object for the game (default: now)

    Returns dict: {
        'temp_f': float,
        'wind_mph': float,
        'precip': bool,
        'conditions': str,
        'is_dome': bool,
    }
    """
    # Check if dome game
    if is_dome_game(home_team, home_team):
        return {
            'temp_f': 72.0,
            'wind_mph': 0.0,
            'precip': False,
            'conditions': 'Indoor / Dome',
            'is_dome': True,
        }

    coords = STADIUM_COORDS.get(home_team)
    if not coords:
        return None

    lat, lon = coords

    try:
        params = {
            'latitude': lat,
            'longitude': lon,
            'hourly': 'temperature_2m,wind_speed_10m,precipitation,weather_code',
            'temperature_unit': 'fahrenheit',
            'wind_speed_unit': 'mph',
            'precipitation_unit': 'inch',
            'forecast_days': 7,
            'timezone': 'America/New_York',
        }

        resp = requests.get(OPEN_METEO_BASE, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        hourly = data.get('hourly', {})
        times = hourly.get('time', [])
        temps = hourly.get('temperature_2m', [])
        winds = hourly.get('wind_speed_10m', [])
        precips = hourly.get('precipitation', [])
        weather_codes = hourly.get('weather_code', [])

        if not times:
            return None

        # Find closest hour to game time
        if game_datetime:
            target = game_datetime.strftime('%Y-%m-%dT%H:00')
        else:
            target = datetime.now().strftime('%Y-%m-%dT%H:00')

        idx = 0
        for i, t in enumerate(times):
            if t >= target:
                idx = i
                break

        # Average over a 3-hour game window
        end_idx = min(idx + 3, len(times))
        window_temps = temps[idx:end_idx]
        window_winds = winds[idx:end_idx]
        window_precips = precips[idx:end_idx]
        window_codes = weather_codes[idx:end_idx]

        avg_temp = sum(window_temps) / len(window_temps) if window_temps else 72.0
        avg_wind = sum(window_winds) / len(window_winds) if window_winds else 0.0
        total_precip = sum(window_precips) if window_precips else 0.0
        has_precip = total_precip > 0.01

        # Decode weather code to conditions string
        conditions = _decode_weather_code(window_codes[0] if window_codes else 0)

        return {
            'temp_f': round(avg_temp, 1),
            'wind_mph': round(avg_wind, 1),
            'precip': has_precip,
            'conditions': conditions,
            'is_dome': False,
        }

    except Exception as e:
        print(f"  [WARN] Weather fetch failed for {home_team}: {e}")
        return None


def _decode_weather_code(code):
    """Convert WMO weather code to human-readable string."""
    code_map = {
        0: 'Clear', 1: 'Mostly Clear', 2: 'Partly Cloudy', 3: 'Overcast',
        45: 'Foggy', 48: 'Freezing Fog',
        51: 'Light Drizzle', 53: 'Drizzle', 55: 'Heavy Drizzle',
        61: 'Light Rain', 63: 'Rain', 65: 'Heavy Rain',
        66: 'Freezing Rain', 67: 'Heavy Freezing Rain',
        71: 'Light Snow', 73: 'Snow', 75: 'Heavy Snow',
        77: 'Snow Grains',
        80: 'Light Showers', 81: 'Showers', 82: 'Heavy Showers',
        85: 'Light Snow Showers', 86: 'Heavy Snow Showers',
        95: 'Thunderstorm', 96: 'Thunderstorm w/ Hail', 99: 'Severe Thunderstorm',
    }
    return code_map.get(code, f'Code {code}')


def fetch_weekly_weather(schedule_data, week):
    """Fetch weather for all games in a given week.

    Args:
        schedule_data: dict from nfl_schedule_cache.json
        week: int week number

    Returns dict: {matchup_key: weather_dict}
    """
    results = {}
    weeks = schedule_data.get('weeks', {})
    week_games = weeks.get(str(week), [])

    for game in week_games:
        home = game.get('home', '')
        away = game.get('away', '')
        game_time = game.get('date', '')

        game_dt = None
        try:
            game_dt = datetime.fromisoformat(game_time.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass

        wx = fetch_game_weather(home, game_dt)
        if wx:
            key = f"{away} @ {home}"
            results[key] = wx

    return results


def save_weather(weather_data, path=WEATHER_CACHE):
    """Save weather data to JSON cache."""
    output = {
        'fetched_at': datetime.now().isoformat(),
        'games': weather_data,
    }
    with open(path, 'w') as f:
        json.dump(output, f, indent=2)


def load_weather_cache(path=WEATHER_CACHE):
    """Load weather from cache."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def main():
    print("[NFL] Fetching weather for outdoor stadiums...")
    # Demo: fetch current weather for a few notable outdoor stadiums
    demo_teams = [
        'Buffalo Bills', 'Green Bay Packers', 'Denver Broncos',
        'Chicago Bears', 'New England Patriots', 'Kansas City Chiefs',
    ]
    results = {}
    for team in demo_teams:
        wx = fetch_game_weather(team)
        if wx:
            results[team] = wx
            dome = "DOME" if wx['is_dome'] else "OUTDOOR"
            print(f"  {team} ({dome}): {wx['temp_f']}°F, {wx['wind_mph']}mph, "
                  f"precip={wx['precip']}, {wx['conditions']}")

    save_weather(results)
    print(f"[SUCCESS] Weather for {len(results)} stadiums → {os.path.basename(WEATHER_CACHE)}")
    return 0


if __name__ == '__main__':
    exit(main())

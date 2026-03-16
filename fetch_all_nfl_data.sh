#!/usr/bin/env bash
#
# fetch_all_nfl_data.sh — Refresh all NFL data caches
#
# Fetches injuries, team stats, schedule, weather, and odds.
# Run before game analysis to ensure fresh data.
#
# Usage:
#   chmod +x fetch_all_nfl_data.sh
#   ./fetch_all_nfl_data.sh
#
# Environment:
#   THE_ODDS_API_KEY — required for odds fetching (optional if skipping odds)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="${PYTHON:-python3}"

echo ""
echo "  🏈 NFL Prediction Engine — Data Refresh"
echo "  ========================================="
echo ""

# 1. Injuries
echo "  [1/5] Fetching injury reports (CBS Sports)..."
$PYTHON -c "
from injury_scraper import fetch_injury_data, save_injuries
data = fetch_injury_data()
save_injuries(data)
print(f'        {len(data)} injury records saved.')
"
echo ""

# 2. Team stats
echo "  [2/5] Fetching team stats (ESPN)..."
$PYTHON -c "
from nfl_data_fetcher import fetch_team_stats, fetch_recent_stats, compute_sos, save_cache, _fetch_season_matchups
import json, os
stats = fetch_team_stats()
save_cache(stats, 'nfl_stats_cache.json')
print(f'        Season stats: {len(stats)} teams → nfl_stats_cache.json')
recent = fetch_recent_stats()
save_cache(recent, 'nfl_stats_recent_cache.json')
print(f'        Recent stats: {len(recent)} teams → nfl_stats_recent_cache.json')
matchups = _fetch_season_matchups()
sos = compute_sos(stats, matchups)
with open('nfl_sos_cache.json', 'w') as f:
    json.dump(sos, f, indent=2)
print(f'        SOS data:     {len(sos)} teams → nfl_sos_cache.json')
"
echo ""

# 3. Schedule
echo "  [3/5] Fetching weekly schedule (ESPN)..."
$PYTHON -c "
from schedule_scraper import fetch_week_schedule, save_schedule
games = fetch_week_schedule()
save_schedule(games)
print(f'        {len(games)} games loaded.')
"
echo ""

# 4. Weather
echo "  [4/5] Fetching weather forecasts (Open-Meteo)..."
$PYTHON -c "
from weather_fetcher import fetch_weekly_weather
import json, os
weather = fetch_weekly_weather()
print(f'        Weather data for {len(weather)} games.')
"
echo ""

# 5. Odds
if [ -n "${THE_ODDS_API_KEY:-}" ]; then
    echo "  [5/5] Fetching odds (The Odds API)..."
    $PYTHON -c "
from odds_api import fetch_nfl_odds, save_odds
odds = fetch_nfl_odds()
save_odds(odds)
print(f'        {len(odds)} game odds saved.')
"
else
    echo "  [5/5] Skipping odds (THE_ODDS_API_KEY not set)"
fi

echo ""
echo "  ✅ All data refreshed."
echo ""

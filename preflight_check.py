#!/usr/bin/env python3
"""
preflight_check.py — Pre-Bet Validation & Data Health Monitor (NFL)
====================================================================

Run BEFORE placing any bets each game week.
Audits every data feed, model config, and downstream calculation
to catch silent failures, stale data, or out-of-range values.

Usage:
    python preflight_check.py              # Full audit
    python preflight_check.py --quick      # Data freshness + structure only
    python preflight_check.py --fix        # Re-run fetchers for any FAIL items
"""

import os
import sys
import json
import csv
import glob
import subprocess
from datetime import datetime, timedelta

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# 32 NFL teams (canonical full names)
EXPECTED_TEAMS = {
    'Arizona Cardinals', 'Atlanta Falcons', 'Baltimore Ravens',
    'Buffalo Bills', 'Carolina Panthers', 'Chicago Bears',
    'Cincinnati Bengals', 'Cleveland Browns', 'Dallas Cowboys',
    'Denver Broncos', 'Detroit Lions', 'Green Bay Packers',
    'Houston Texans', 'Indianapolis Colts', 'Jacksonville Jaguars',
    'Kansas City Chiefs', 'Las Vegas Raiders', 'Los Angeles Chargers',
    'Los Angeles Rams', 'Miami Dolphins', 'Minnesota Vikings',
    'New England Patriots', 'New Orleans Saints', 'New York Giants',
    'New York Jets', 'Philadelphia Eagles', 'Pittsburgh Steelers',
    'San Francisco 49ers', 'Seattle Seahawks', 'Tampa Bay Buccaneers',
    'Tennessee Titans', 'Washington Commanders',
}
TEAM_COUNT = 32

# Valid injury status keywords (lowercase substrings)
KNOWN_INJURY_STATUSES = {
    'out', 'doubtful', 'questionable', 'probable', 'limited',
    'full', 'injured reserve', 'ir', 'suspended', 'pup',
    'out for season', 'full participant',
}

# Reasonable NFL value ranges
PPG_RANGE = (12.0, 38.0)
OPPG_RANGE = (12.0, 38.0)
EPA_RANGE = (-3.0, 3.0)
NET_EPA_RANGE = (-6.0, 6.0)
SPREAD_RANGE = (-25.0, 25.0)
TOTAL_RANGE = (30.0, 60.0)
SOS_RANGE = (-3.0, 3.0)
WIND_RANGE = (0.0, 60.0)
TEMP_RANGE = (-20.0, 120.0)
KELLY_RANGE = (0.0, 15.0)

STALE_HOURS = 48  # NFL weekly cadence — data older than this is flagged

# ── Helpers ───────────────────────────────────────────────────────────────────
PASS_COUNT = 0
WARN_COUNT = 0
FAIL_COUNT = 0
FAIL_DETAILS = []
WARN_DETAILS = []


def _ts(label, status, msg, detail=None, fix=None):
    """Print a check result line."""
    global PASS_COUNT, WARN_COUNT, FAIL_COUNT
    icons = {'PASS': '✅', 'WARN': '⚠️ ', 'FAIL': '❌'}
    icon = icons.get(status, '  ')
    print(f"  {icon} [{label:.<44s}] {msg}")
    if detail:
        for d in (detail if isinstance(detail, list) else [detail]):
            print(f"       ↳ {d}")
    if status == 'PASS':
        PASS_COUNT += 1
    elif status == 'WARN':
        WARN_COUNT += 1
        if fix:
            WARN_DETAILS.append((label, msg, fix))
    elif status == 'FAIL':
        FAIL_COUNT += 1
        FAIL_DETAILS.append((label, msg, fix or 'Investigate manually.'))


def _parse_ts(raw):
    """Parse an ISO timestamp string into datetime."""
    if not raw or raw in ('Unknown', 'Missing'):
        return None
    for fmt in ('%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f'):
        try:
            return datetime.strptime(raw.strip(), fmt)
        except ValueError:
            continue
    return None


def _freshness(ts_dt, label, threshold=STALE_HOURS):
    """Check if a timestamp is recent enough."""
    if ts_dt is None:
        _ts(label, 'FAIL', 'Timestamp missing or unparseable',
            fix='Re-run: bash fetch_all_nfl_data.sh')
        return
    age = datetime.now() - ts_dt
    hrs = age.total_seconds() / 3600
    if hrs > threshold:
        _ts(label, 'WARN', f'Data is {hrs:.1f}h old (stale > {threshold}h)',
            f'Last updated: {ts_dt.strftime("%Y-%m-%d %H:%M:%S")}',
            fix='Re-run: bash fetch_all_nfl_data.sh')
    else:
        _ts(label, 'PASS', f'Fresh ({hrs:.1f}h old)')


def _load_json_safe(path, label):
    """Load and validate a JSON file. Returns (data, ok)."""
    if not os.path.exists(path):
        _ts(f'{label}.exists', 'FAIL', f'{os.path.basename(path)} not found',
            fix='Run: bash fetch_all_nfl_data.sh')
        return None, False
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        _ts(f'{label}.parse', 'FAIL', f'JSON parse error: {e}',
            fix=f'Delete {os.path.basename(path)} and re-run: bash fetch_all_nfl_data.sh')
        return None, False
    _ts(f'{label}.parse', 'PASS', f'{os.path.basename(path)} — valid JSON')
    return data, True


# ═══════════════════════════════════════════════════════════════════════════════
#  Section 1: DATA FEED CHECKS
# ═══════════════════════════════════════════════════════════════════════════════

def check_stats_cache():
    """Validate nfl_stats_cache.json — team stats from ESPN."""
    print("\n─── 1. TEAM STATS (nfl_stats_cache.json) ─────────────────────────")
    cache, ok = _load_json_safe('nfl_stats_cache.json', 'stats')
    if not ok:
        return {}

    ts = _parse_ts(cache.get('fetched_at', ''))
    _freshness(ts, 'stats.freshness')

    data = cache.get('data')
    if not data or not isinstance(data, dict):
        _ts('stats.structure', 'FAIL', 'Missing or invalid "data" key',
            fix='Run: python nfl_data_fetcher.py  (or bash fetch_all_nfl_data.sh)')
        return {}

    # Team count
    teams = set(data.keys())
    if len(teams) == TEAM_COUNT:
        _ts('stats.team_count', 'PASS', f'{TEAM_COUNT} teams present')
    else:
        missing = EXPECTED_TEAMS - teams
        _ts('stats.team_count', 'FAIL', f'{len(teams)} teams (expected {TEAM_COUNT})',
            [f'Missing: {missing}'] if missing else None,
            fix='Run: python nfl_data_fetcher.py')

    # Canonical team names
    unknowns = teams - EXPECTED_TEAMS
    if unknowns:
        _ts('stats.team_names', 'WARN', f'Unexpected team names: {unknowns}')
    else:
        _ts('stats.team_names', 'PASS', 'All team names canonical')

    # Required keys per team + value ranges
    required_keys = ['OFF_EPA', 'DEF_EPA', 'NET_EPA', 'PPG', 'OPPG', 'wins', 'losses', 'games']
    outliers = []
    missing_keys = []
    for team, tdata in data.items():
        mk = [k for k in required_keys if k not in tdata]
        if mk:
            missing_keys.append(f'{team}: missing {mk}')
            continue
        ppg = float(tdata['PPG'])
        oppg = float(tdata['OPPG'])
        off_epa = float(tdata['OFF_EPA'])
        def_epa = float(tdata['DEF_EPA'])
        if not (PPG_RANGE[0] <= ppg <= PPG_RANGE[1]):
            outliers.append(f'{team}: PPG={ppg}')
        if not (OPPG_RANGE[0] <= oppg <= OPPG_RANGE[1]):
            outliers.append(f'{team}: OPPG={oppg}')
        if not (EPA_RANGE[0] <= off_epa <= EPA_RANGE[1]):
            outliers.append(f'{team}: OFF_EPA={off_epa}')
        if not (EPA_RANGE[0] <= def_epa <= EPA_RANGE[1]):
            outliers.append(f'{team}: DEF_EPA={def_epa}')

    if missing_keys:
        _ts('stats.fields', 'FAIL', f'{len(missing_keys)} team(s) with missing keys',
            missing_keys[:5])
    else:
        _ts('stats.fields', 'PASS', f'All {len(required_keys)} required fields present per team')

    if outliers:
        _ts('stats.value_ranges', 'WARN', f'{len(outliers)} outlier(s)',
            outliers[:5] + (['...'] if len(outliers) > 5 else []))
    else:
        _ts('stats.value_ranges', 'PASS', 'PPG/OPPG/EPA all in expected ranges')

    return {'teams': teams, 'data': data, 'timestamp': ts}


def check_recent_stats_cache():
    """Validate nfl_stats_recent_cache.json — last-4-week form."""
    print("\n─── 2. RECENT FORM (nfl_stats_recent_cache.json) ─────────────────")
    cache, ok = _load_json_safe('nfl_stats_recent_cache.json', 'recent')
    if not ok:
        return {}

    ts = _parse_ts(cache.get('fetched_at', ''))
    _freshness(ts, 'recent.freshness')

    data = cache.get('data')
    if not data or not isinstance(data, dict):
        _ts('recent.structure', 'FAIL', 'Missing or invalid "data" key',
            fix='Run: python nfl_data_fetcher.py')
        return {}

    teams = set(data.keys())
    if len(teams) >= 28:
        _ts('recent.team_count', 'PASS', f'{len(teams)} teams present')
    elif len(teams) >= 20:
        _ts('recent.team_count', 'WARN', f'{len(teams)} teams (bye weeks may reduce count)')
    else:
        _ts('recent.team_count', 'FAIL', f'{len(teams)} teams — too few for reliable recency data',
            fix='Run: python nfl_data_fetcher.py')

    # EPA ranges
    outliers = []
    for team, tdata in data.items():
        for key in ('OFF_EPA', 'DEF_EPA'):
            val = tdata.get(key)
            if val is not None:
                try:
                    v = float(val)
                    if not (EPA_RANGE[0] <= v <= EPA_RANGE[1]):
                        outliers.append(f'{team}: {key}={v}')
                except (ValueError, TypeError):
                    outliers.append(f'{team}: {key}={val!r} non-numeric')

    if outliers:
        _ts('recent.value_ranges', 'WARN', f'{len(outliers)} outlier(s)',
            outliers[:5])
    else:
        _ts('recent.value_ranges', 'PASS', 'All recent EPA values in range')

    return {'teams': teams, 'data': data, 'timestamp': ts}


def check_sos_cache():
    """Validate nfl_sos_cache.json — strength of schedule."""
    print("\n─── 3. SOS (nfl_sos_cache.json) ──────────────────────────────────")
    path = 'nfl_sos_cache.json'
    if not os.path.exists(path):
        _ts('sos.exists', 'FAIL', f'{path} not found',
            fix='Run: python nfl_data_fetcher.py')
        return {}

    try:
        with open(path) as f:
            raw = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        _ts('sos.parse', 'FAIL', f'JSON parse error: {e}',
            fix=f'Delete {path} and run: python nfl_data_fetcher.py')
        return {}

    _ts('sos.parse', 'PASS', 'JSON valid')

    # SOS file is a flat dict {team: float} — no wrapper
    # (written directly by nfl_data_fetcher.py main())
    if isinstance(raw, dict) and 'data' in raw:
        data = raw['data']  # wrapped format
    else:
        data = raw  # flat format

    if not data or not isinstance(data, dict):
        _ts('sos.structure', 'FAIL', 'Empty or invalid structure',
            fix='Run: python nfl_data_fetcher.py')
        return {}

    teams = set(data.keys())
    if len(teams) == TEAM_COUNT:
        _ts('sos.team_count', 'PASS', f'{TEAM_COUNT} teams present')
    else:
        missing = EXPECTED_TEAMS - teams
        _ts('sos.team_count', 'FAIL', f'{len(teams)} teams (expected {TEAM_COUNT})',
            [f'Missing: {missing}'] if missing else None)

    # Check for all-zeros (the bug compute_sos had before fix)
    all_zero = all(float(v) == 0.0 for v in data.values())
    if all_zero:
        _ts('sos.all_zeros', 'WARN',
            'All SOS values are 0.0 — matchup data may not have loaded',
            fix='Run: python nfl_data_fetcher.py  (needs full-season matchups)')
    else:
        sos_vals = [float(v) for v in data.values()]
        outliers = [f'{t}: {float(data[t]):.3f}' for t in data
                    if not (SOS_RANGE[0] <= float(data[t]) <= SOS_RANGE[1])]
        if outliers:
            _ts('sos.value_ranges', 'WARN', f'{len(outliers)} SOS value(s) out of range',
                outliers[:5])
        else:
            _ts('sos.value_ranges', 'PASS',
                f'SOS range: [{min(sos_vals):.2f}, {max(sos_vals):.2f}]')

    return {'data': data, 'teams': teams}


def check_injuries():
    """Validate nfl_injuries.csv — CBS Sports injury data."""
    print("\n─── 4. INJURIES (nfl_injuries.csv) ───────────────────────────────")
    path = 'nfl_injuries.csv'
    if not os.path.exists(path):
        _ts('injuries.exists', 'FAIL', 'File not found',
            fix='Run: bash fetch_all_nfl_data.sh')
        return {}

    # Freshness via mtime
    mtime = datetime.fromtimestamp(os.path.getmtime(path))
    _freshness(mtime, 'injuries.freshness')

    with open(path) as f:
        lines = f.readlines()

    if not lines:
        _ts('injuries.empty', 'FAIL', 'File is empty',
            fix='Run: bash fetch_all_nfl_data.sh')
        return {}

    # Parse CSV
    try:
        reader = csv.DictReader(lines)
        rows = list(reader)
    except Exception as e:
        _ts('injuries.parse', 'FAIL', f'CSV parse error: {e}',
            fix='Delete nfl_injuries.csv and re-run')
        return {}

    if not rows:
        _ts('injuries.empty', 'WARN',
            'No injury rows — very unusual for NFL midseason')
        return {'rows': rows}

    _ts('injuries.parse', 'PASS', f'{len(rows)} injury records loaded')

    # Required columns
    expected_cols = ['team', 'player', 'position', 'status']
    cols = list(rows[0].keys())
    missing = [c for c in expected_cols if c not in cols]
    if missing:
        _ts('injuries.columns', 'FAIL', f'Missing columns: {missing}', f'Found: {cols}',
            fix='Check injury_scraper.py — column names may have changed.')
    else:
        _ts('injuries.columns', 'PASS', f'Required columns present')

    # Team coverage
    teams = set(r.get('team', '') for r in rows)
    teams.discard('')
    if len(teams) >= 20:
        _ts('injuries.team_coverage', 'PASS', f'{len(teams)} teams have injury reports')
    elif len(teams) >= 10:
        _ts('injuries.team_coverage', 'WARN', f'Only {len(teams)} teams — some may be missing')
    else:
        _ts('injuries.team_coverage', 'FAIL', f'Only {len(teams)} teams — data likely incomplete',
            fix='Re-run: bash fetch_all_nfl_data.sh')

    # Canonical team names
    bad_teams = teams - EXPECTED_TEAMS
    if bad_teams:
        _ts('injuries.team_names', 'FAIL',
            f'Non-canonical team names: {bad_teams}',
            fix='Update CBS_TEAM_MAP in injury_scraper.py')
    else:
        _ts('injuries.team_names', 'PASS', 'All team names canonical')

    # Player names not empty
    empty = [r for r in rows if not r.get('player') or len(r['player']) < 2]
    if empty:
        _ts('injuries.player_names', 'WARN',
            f'{len(empty)} player(s) with empty/short names')
    else:
        _ts('injuries.player_names', 'PASS', 'All player names valid')

    # Status recognition
    unrecognised = []
    for r in rows:
        s = r.get('status', '').lower()
        if not any(kw in s for kw in KNOWN_INJURY_STATUSES):
            unrecognised.append(f"{r.get('player', '?')}: {r.get('status', '?')!r}")
    if unrecognised:
        _ts('injuries.statuses', 'WARN',
            f'{len(unrecognised)} unrecognised status(es)',
            unrecognised[:5])
    else:
        _ts('injuries.statuses', 'PASS', 'All statuses contain known keywords')

    # QB injuries — high-impact, flag for visibility
    qb_injuries = [r for r in rows
                   if r.get('position', '').upper() == 'QB'
                   and r.get('status', '').lower() in ('out', 'doubtful', 'injured reserve', 'ir')]
    if qb_injuries:
        qb_detail = [f"{r['team']}: {r['player']} ({r['status']})" for r in qb_injuries]
        _ts('injuries.qb_alert', 'WARN',
            f'{len(qb_injuries)} QB(s) OUT/Doubtful/IR — high-impact',
            qb_detail[:8])

    return {'rows': rows, 'teams': teams}


def check_schedule():
    """Validate nfl_schedule_cache.json — ESPN weekly schedule."""
    print("\n─── 5. SCHEDULE (nfl_schedule_cache.json) ────────────────────────")
    cache, ok = _load_json_safe('nfl_schedule_cache.json', 'schedule')
    if not ok:
        return {}

    ts = _parse_ts(cache.get('fetched_at', ''))
    _freshness(ts, 'schedule.freshness')

    weeks = cache.get('weeks', {})
    if not weeks:
        _ts('schedule.structure', 'FAIL', 'No "weeks" key or empty',
            fix='Run: bash fetch_all_nfl_data.sh')
        return {}

    _ts('schedule.weeks', 'PASS', f'{len(weeks)} week(s) cached')

    # Find current or most recent week
    current = weeks.get('current', {})
    if current:
        games = current.get('games', [])
        _ts('schedule.current_week', 'PASS' if games else 'WARN',
            f'{len(games)} game(s) in current week')
    else:
        # Look for the highest numbered week
        numbered = sorted([k for k in weeks if k.isdigit()], key=int, reverse=True)
        if numbered:
            latest = numbered[0]
            games = weeks[latest].get('games', [])
            _ts('schedule.latest_week', 'PASS' if games else 'WARN',
                f'Week {latest}: {len(games)} game(s)')
        else:
            games = []
            _ts('schedule.latest_week', 'WARN', 'No numbered weeks found')

    # Validate team names in schedule
    if games:
        sched_teams = set()
        for g in games:
            sched_teams.add(g.get('away', ''))
            sched_teams.add(g.get('home', ''))
        sched_teams.discard('')
        bad = sched_teams - EXPECTED_TEAMS
        if bad:
            _ts('schedule.team_names', 'WARN', f'Non-canonical names: {bad}')
        else:
            _ts('schedule.team_names', 'PASS', 'All schedule team names canonical')

    return {'weeks': weeks, 'games': games, 'timestamp': ts}


def check_weather():
    """Validate nfl_weather_cache.json — Open-Meteo weather data."""
    print("\n─── 6. WEATHER (nfl_weather_cache.json) ──────────────────────────")
    cache, ok = _load_json_safe('nfl_weather_cache.json', 'weather')
    if not ok:
        return {}

    ts = _parse_ts(cache.get('fetched_at', ''))
    _freshness(ts, 'weather.freshness')

    games = cache.get('games', {})
    if not games:
        _ts('weather.games', 'WARN', 'No game weather data',
            fix='Run: bash fetch_all_nfl_data.sh')
        return {}

    _ts('weather.game_count', 'PASS', f'{len(games)} game(s) in cache')

    outliers = []
    for matchup, wdata in games.items():
        temp = wdata.get('temp_f')
        wind = wdata.get('wind_mph')
        if temp is not None and not (TEMP_RANGE[0] <= float(temp) <= TEMP_RANGE[1]):
            outliers.append(f'{matchup}: temp={temp}°F')
        if wind is not None and not (WIND_RANGE[0] <= float(wind) <= WIND_RANGE[1]):
            outliers.append(f'{matchup}: wind={wind} mph')

    if outliers:
        _ts('weather.value_ranges', 'WARN', f'{len(outliers)} outlier(s)', outliers[:5])
    else:
        _ts('weather.value_ranges', 'PASS', 'All temp/wind values in expected ranges')

    # Check dome games
    dome_count = sum(1 for w in games.values() if w.get('is_dome'))
    _ts('weather.dome_games', 'PASS', f'{dome_count}/{len(games)} dome/indoor game(s)')

    return {'games': games, 'timestamp': ts}


def check_odds():
    """Validate nfl_odds_cache.json — The Odds API data."""
    print("\n─── 7. ODDS (nfl_odds_cache.json) ────────────────────────────────")
    cache, ok = _load_json_safe('nfl_odds_cache.json', 'odds')
    if not ok:
        return {}

    ts = _parse_ts(cache.get('fetched_at', ''))
    _freshness(ts, 'odds.freshness')

    games = cache.get('games', {})
    if not games:
        _ts('odds.games', 'WARN', 'No odds data — predictions will be model-only',
            fix='Set THE_ODDS_API_KEY and run: bash fetch_all_nfl_data.sh')
        return {}

    _ts('odds.game_count', 'PASS', f'{len(games)} game(s) in cache')

    issues = []
    for key, gdata in games.items():
        # Required fields
        for field in ('away', 'home', 'spreads'):
            if field not in gdata:
                issues.append(f'{key}: missing "{field}"')

        # Spread values in range
        spreads = gdata.get('spreads', {})
        if not spreads:
            issues.append(f'{key}: empty spreads — no books')
        elif len(spreads) < 2:
            issues.append(f'{key}: only {len(spreads)} book(s) — thin market')

        for book, sdata in spreads.items():
            if isinstance(sdata, dict):
                home_spread = sdata.get('home')
                if home_spread is not None:
                    try:
                        v = float(home_spread)
                        if not (SPREAD_RANGE[0] <= v <= SPREAD_RANGE[1]):
                            issues.append(f'{key}/{book}: spread={v} out of range')
                    except (ValueError, TypeError):
                        issues.append(f'{key}/{book}: non-numeric spread: {home_spread!r}')

        # Totals validation
        totals = gdata.get('totals', {})
        for book, tdata in totals.items():
            if isinstance(tdata, dict):
                over = tdata.get('over')
                if over is not None:
                    try:
                        v = float(over)
                        if not (TOTAL_RANGE[0] <= v <= TOTAL_RANGE[1]):
                            issues.append(f'{key}/{book}: total={v} out of range')
                    except (ValueError, TypeError):
                        pass

    if issues:
        _ts('odds.integrity', 'WARN', f'{len(issues)} issue(s)', issues[:8])
    else:
        _ts('odds.integrity', 'PASS', 'All odds entries well-formed')

    return {'games': games, 'timestamp': ts}


def check_model_config():
    """Validate model_config.json — tunable parameters and guard rails."""
    print("\n─── 8. MODEL CONFIG (model_config.json) ──────────────────────────")
    cache, ok = _load_json_safe('model_config.json', 'config')
    if not ok:
        return {}

    # Version
    version = cache.get('version')
    if version:
        _ts('config.version', 'PASS', f'Model version: {version}')
    else:
        _ts('config.version', 'WARN', 'No version field')

    # model_params section
    params = cache.get('model_params', {})
    if not params:
        _ts('config.model_params', 'FAIL', 'Missing "model_params" section',
            fix='Check model_config.json structure')
        return cache

    required_params = [
        'REGRESS_FACTOR', 'RECENT_BLEND_WEIGHT', 'FLAT_HFA',
        'MARKET_ANCHOR_WEIGHT', 'QB_IMPACT_WEIGHT', 'SOS_WEIGHT',
    ]
    missing_p = [p for p in required_params if p not in params]
    if missing_p:
        _ts('config.params', 'WARN', f'Missing params (have defaults): {missing_p}')
    else:
        _ts('config.params', 'PASS', f'{len(params)} model params configured')

    # Sanity: key weights in [0, 1]
    for key in ('REGRESS_FACTOR', 'RECENT_BLEND_WEIGHT', 'MARKET_ANCHOR_WEIGHT'):
        val = params.get(key)
        if val is not None and not (0.0 <= float(val) <= 1.0):
            _ts(f'config.{key}', 'WARN', f'{key}={val} — should be in [0, 1]')

    # guard_rails section
    rails = cache.get('guard_rails', {})
    if not rails:
        _ts('config.guard_rails', 'FAIL', 'Missing "guard_rails" section',
            fix='Check model_config.json structure')
        return cache

    required_rails = ['edge_cap', 'min_edge', 'market_divergence_threshold']
    missing_r = [r for r in required_rails if r not in rails]
    if missing_r:
        _ts('config.guard_rails', 'WARN', f'Missing rails (have defaults): {missing_r}')
    else:
        _ts('config.guard_rails', 'PASS', f'{len(rails)} guard rail settings configured')

    # fade_hard_tags exists
    if 'fade_hard_tags' in rails:
        _ts('config.fade_hard_tags', 'PASS',
            f'{len(rails["fade_hard_tags"])} FADE triggers defined')
    else:
        _ts('config.fade_hard_tags', 'WARN',
            'No fade_hard_tags — FADE logic will use hardcoded defaults')

    return cache


def check_bankroll():
    """Validate bankroll.json — betting configuration."""
    print("\n─── 9. BANKROLL CONFIG (bankroll.json) ──────────────────────────")
    cache, ok = _load_json_safe('bankroll.json', 'bankroll')
    if not ok:
        return {}

    required = {
        'starting_bankroll': (100, 100000),
        'unit_size': (1, 1000),
        'edge_cap': (1, 30),
    }
    for field, (lo, hi) in required.items():
        val = cache.get(field)
        if val is None:
            _ts(f'bankroll.{field}', 'FAIL', f'Missing "{field}" key',
                fix=f'Add "{field}" to bankroll.json')
        else:
            try:
                v = float(val)
                if lo <= v <= hi:
                    _ts(f'bankroll.{field}', 'PASS', f'{field}={v}')
                else:
                    _ts(f'bankroll.{field}', 'WARN', f'{field}={v} outside [{lo}, {hi}]')
            except (ValueError, TypeError):
                _ts(f'bankroll.{field}', 'FAIL', f'{field} non-numeric: {val!r}')

    return cache


# ═══════════════════════════════════════════════════════════════════════════════
#  Section 2: CROSS-DATA CONSISTENCY
# ═══════════════════════════════════════════════════════════════════════════════

def check_cross_consistency(stats_info, recent_info, sos_info,
                            injuries_info, schedule_info, weather_info,
                            odds_info):
    """Cross-validate data between feeds."""
    print("\n─── 10. CROSS-DATA CONSISTENCY ───────────────────────────────────")

    stats_teams = stats_info.get('teams', set())
    recent_teams = recent_info.get('teams', set())
    sos_teams = sos_info.get('teams', set())
    injury_teams = injuries_info.get('teams', set())
    sched_games = schedule_info.get('games', [])

    # Injury teams match stats teams
    if injury_teams and stats_teams:
        orphan = injury_teams - stats_teams
        if orphan:
            _ts('cross.injury_vs_stats', 'FAIL',
                f'{len(orphan)} injury team(s) not in stats cache',
                list(orphan)[:5],
                fix='Check injury_scraper.py team name mapping.')
        else:
            _ts('cross.injury_vs_stats', 'PASS', 'All injury teams match stats teams')

    # SOS teams match stats teams
    if sos_teams and stats_teams:
        orphan = sos_teams - stats_teams
        if orphan:
            _ts('cross.sos_vs_stats', 'WARN',
                f'{len(orphan)} SOS team(s) not in stats cache', list(orphan)[:5])
        else:
            _ts('cross.sos_vs_stats', 'PASS', 'SOS teams match stats teams')

    # Recent form coverage vs season stats
    if recent_teams and stats_teams:
        missing_recent = stats_teams - recent_teams
        if missing_recent and len(missing_recent) > 4:
            _ts('cross.recent_vs_stats', 'WARN',
                f'{len(missing_recent)} team(s) in season stats but not recent form',
                detail=[f'Missing from recent: {list(missing_recent)[:5]}'])
        else:
            _ts('cross.recent_vs_stats', 'PASS',
                'Recent form covers all (or most) teams')

    # Schedule games have matching weather data
    weather_games = weather_info.get('games', {})
    if sched_games and weather_games:
        missing_weather = []
        for g in sched_games:
            matchup_key = f"{g.get('away', '')} @ {g.get('home', '')}"
            # Try to find this matchup in weather cache
            found = any(
                g.get('away', '') in wk and g.get('home', '') in wk
                for wk in weather_games
            )
            if not found:
                missing_weather.append(matchup_key)
        if missing_weather:
            _ts('cross.schedule_vs_weather', 'WARN',
                f'{len(missing_weather)} scheduled game(s) without weather data',
                missing_weather[:5])
        else:
            _ts('cross.schedule_vs_weather', 'PASS',
                'All scheduled games have weather data')

    # Schedule games have odds
    odds_games = odds_info.get('games', {})
    if sched_games and odds_games:
        missing_odds = []
        for g in sched_games:
            found = any(
                g.get('away', '') in ok and g.get('home', '') in ok
                for ok in odds_games
            )
            if not found:
                missing_odds.append(f"{g.get('away', '')} @ {g.get('home', '')}")
        if missing_odds:
            _ts('cross.schedule_vs_odds', 'WARN',
                f'{len(missing_odds)} scheduled game(s) without odds',
                missing_odds[:5])
        else:
            _ts('cross.schedule_vs_odds', 'PASS',
                f'All {len(sched_games)} scheduled games have odds data')


# ═══════════════════════════════════════════════════════════════════════════════
#  Section 3: MODEL SPOT-CHECK
# ═══════════════════════════════════════════════════════════════════════════════

def check_model_spot(schedule_info):
    """Run the prediction model on a scheduled game and validate outputs."""
    print("\n─── 11. MODEL CALCULATION SPOT-CHECK ─────────────────────────────")

    games = schedule_info.get('games', [])
    if not games:
        _ts('model.no_games', 'WARN', 'No scheduled games to spot-check')
        return

    # Import model
    try:
        from nfl_analytics import predict_nfl_spread
    except ImportError as e:
        _ts('model.import', 'FAIL', f'Cannot import nfl_analytics: {e}',
            fix='Check for syntax errors: python -c "import nfl_analytics"')
        return

    _ts('model.import', 'PASS', 'nfl_analytics loaded')

    games_checked = 0
    issues = []

    for g in games[:3]:  # Spot-check up to 3 games
        away = g.get('away', '')
        home = g.get('home', '')
        if not away or not home:
            continue
        try:
            result = predict_nfl_spread(away, home)
            # predict_nfl_spread returns a tuple; fair_line is first element
            fair_line = result[0] if isinstance(result, tuple) else result
            games_checked += 1

            if not (SPREAD_RANGE[0] <= fair_line <= SPREAD_RANGE[1]):
                issues.append(f'{away}@{home}: fair_line={fair_line} out of range')
            else:
                _ts(f'model.game_{games_checked}', 'PASS',
                    f'{away} @ {home} → Fair: {fair_line:+.1f}')
        except Exception as e:
            issues.append(f'{away}@{home}: prediction failed: {e}')

    if issues:
        _ts('model.spot_check', 'FAIL', f'{len(issues)} issue(s)', issues[:5])
    elif games_checked == 0:
        _ts('model.spot_check', 'WARN', 'No games could be checked')
    else:
        _ts('model.spot_check', 'PASS',
            f'{games_checked} game(s) produced valid predictions')


# ═══════════════════════════════════════════════════════════════════════════════
#  Section 4: BET TRACKER INTEGRITY
# ═══════════════════════════════════════════════════════════════════════════════

def check_bet_trackers():
    """Scan bet tracker files for conformance."""
    print("\n─── 12. BET TRACKER INTEGRITY ────────────────────────────────────")

    all_trackers = sorted(glob.glob(os.path.join(BASE_DIR, 'bet_tracker_*.csv')))

    if not all_trackers:
        _ts('tracker.exists', 'WARN', 'No bet tracker files found')
        return

    _ts('tracker.count', 'PASS', f'{len(all_trackers)} tracker file(s) found')

    conforming = 0
    non_conforming = 0
    for tp in all_trackers:
        fname = os.path.basename(tp)
        try:
            with open(tp) as f:
                reader = csv.reader(f)
                header = next(reader, [])
        except Exception:
            non_conforming += 1
            continue

        required = ['ID', 'Away', 'Home', 'Fair', 'Market', 'Edge', 'Pick', 'Result']
        missing = [c for c in required if c not in header]
        if missing:
            non_conforming += 1
        else:
            conforming += 1

    if non_conforming:
        _ts('tracker.conformance', 'WARN',
            f'{conforming}/{len(all_trackers)} conforming, {non_conforming} non-conforming')
    else:
        _ts('tracker.conformance', 'PASS',
            f'All {len(all_trackers)} tracker(s) have required columns')


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def run_preflight(quick=False):
    """Run all preflight checks and print summary."""
    global PASS_COUNT, WARN_COUNT, FAIL_COUNT, FAIL_DETAILS, WARN_DETAILS
    PASS_COUNT = WARN_COUNT = FAIL_COUNT = 0
    FAIL_DETAILS = []
    WARN_DETAILS = []

    print("=" * 70)
    print("  🏈 NFL PREDICTION ENGINE — PREFLIGHT CHECK")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # Section 1: Data feeds
    stats_info = check_stats_cache()
    recent_info = check_recent_stats_cache()
    sos_info = check_sos_cache()
    injuries_info = check_injuries()
    schedule_info = check_schedule()
    weather_info = check_weather()
    odds_info = check_odds()
    config = check_model_config()
    bankroll = check_bankroll()

    if not quick:
        # Section 2: Cross-consistency
        check_cross_consistency(stats_info, recent_info, sos_info,
                                injuries_info, schedule_info, weather_info,
                                odds_info)

        # Section 3: Model spot-check
        check_model_spot(schedule_info)

        # Section 4: Bet trackers
        check_bet_trackers()

    # ── Summary ───────────────────────────────────────────────────────────
    total = PASS_COUNT + WARN_COUNT + FAIL_COUNT
    print("\n" + "=" * 70)
    print(f"  PREFLIGHT SUMMARY: {total} checks")
    print(f"    ✅ PASS: {PASS_COUNT}   ⚠️  WARN: {WARN_COUNT}   ❌ FAIL: {FAIL_COUNT}")
    print("=" * 70)

    if FAIL_DETAILS:
        print("\n  🔴 FAILURES (must fix before betting):")
        for label, msg, fix in FAIL_DETAILS:
            print(f"    ❌ {label}: {msg}")
            if fix:
                print(f"       → {fix}")

    if WARN_DETAILS:
        print(f"\n  🟡 WARNINGS ({len(WARN_DETAILS)}):")
        for label, msg, fix in WARN_DETAILS[:10]:
            print(f"    ⚠️  {label}: {msg}")
            if fix:
                print(f"       → {fix}")
        if len(WARN_DETAILS) > 10:
            print(f"    ... and {len(WARN_DETAILS) - 10} more")

    if FAIL_COUNT == 0 and WARN_COUNT == 0:
        print("\n  🟢 ALL CLEAR — Data is healthy. Safe to analyze games.")
        verdict = True
    elif FAIL_COUNT == 0:
        print(f"\n  🟡 MOSTLY CLEAR — {WARN_COUNT} warning(s). Review before betting.")
        verdict = True
    else:
        print(f"\n  🔴 NOT READY — {FAIL_COUNT} failure(s) must be resolved.")
        print("     Run: bash fetch_all_nfl_data.sh  (or use --fix)")
        verdict = False

    print("=" * 70)

    # Write status file for UI integration
    status_file = os.path.join(BASE_DIR, '.preflight_status.json')
    status = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'timestamp': datetime.now().isoformat(),
        'passed': FAIL_COUNT == 0,
        'checks': PASS_COUNT,
        'warnings': WARN_COUNT,
        'failures': FAIL_COUNT,
    }
    with open(status_file, 'w') as f:
        json.dump(status, f, indent=2)

    return verdict


def run_fix():
    """Re-run fetchers to fix FAIL items."""
    print("\n  🔧 Running data refresh to fix failures...\n")
    fetch_script = os.path.join(BASE_DIR, 'fetch_all_nfl_data.sh')
    if not os.path.exists(fetch_script):
        print("  [ERROR] fetch_all_nfl_data.sh not found.")
        return

    result = subprocess.run(
        ['bash', fetch_script],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    for line in result.stdout.splitlines():
        print(f"  {line}")

    print("\n  🔄 Re-running preflight checks...\n")
    run_preflight()


if __name__ == '__main__':
    quick = '--quick' in sys.argv
    fix = '--fix' in sys.argv

    if fix:
        run_fix()
    else:
        passed = run_preflight(quick=quick)
        sys.exit(0 if passed else 1)

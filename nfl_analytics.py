"""
nfl_analytics.py — NFL Prediction Engine: Fair Line & Edge Calculator

Ported from NBA Prediction Engine v3.36 framework.
Calculates fair point spreads using:
  - Offensive/Defensive EPA (Expected Points Added)
  - QB star tax (injury impact scoring)
  - Home-field advantage (with weather/altitude adjustments)
  - Bye week & short week schedule factors
  - Strength of schedule regression
  - Divisional rivalry dampening
  - Weather suppression (wind, cold, precipitation)
  - Motivation adjustments (playoff clinch, elimination games)
  - Market anchor blend (model + Vegas)
  - Edge Confidence Score (ECS)

All tunable parameters loaded from model_config.json.
"""

import os
import csv
import json
from datetime import datetime
from nfl_teams_static import (
    resolve_team_name, get_team_info, same_division,
    is_dome_game, DOME_TEAMS, ABBR_TO_TEAM_NAME,
)

# ── Central config loader ──────────────────────────────────────────────────────
MODEL_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'model_config.json')


def _load_model_config():
    """Load model_config.json and return (model_params_dict, guard_rails_dict)."""
    mp, gr = {}, {}
    try:
        if os.path.exists(MODEL_CONFIG_FILE):
            with open(MODEL_CONFIG_FILE, 'r') as f:
                cfg = json.load(f)
            mp = cfg.get('model_params', {})
            gr = cfg.get('guard_rails', {})
    except Exception as e:
        print(f"  [WARN] Could not load model_config.json: {e} — using hardcoded defaults")
    return mp, gr


_CFG_MP, _CFG_GR = _load_model_config()


def _load_model_version():
    try:
        if os.path.exists(MODEL_CONFIG_FILE):
            with open(MODEL_CONFIG_FILE, 'r') as f:
                return json.load(f).get('version', 'unknown')
    except Exception:
        pass
    return 'unknown'


_MODEL_VERSION = _load_model_version()


def _p(key, default):
    """Get a model parameter from config, falling back to default."""
    return _CFG_MP.get(key, default)


def _gr(key, default):
    """Get a guard rail parameter from config, falling back to default."""
    return _CFG_GR.get(key, default)


# ── Model constants from config ────────────────────────────────────────────────
REGRESS_FACTOR = _p('REGRESS_FACTOR', 0.60)
RECENT_BLEND_WEIGHT = _p('RECENT_BLEND_WEIGHT', 0.35)
FLAT_HFA = _p('FLAT_HFA', 2.5)
MARKET_ANCHOR_WEIGHT = _p('MARKET_ANCHOR_WEIGHT', 0.65)

QB_IMPACT_WEIGHT = _p('QB_IMPACT_WEIGHT', 1.0)
NON_QB_IMPACT_DAMPENER = _p('NON_QB_IMPACT_DAMPENER', 0.25)
STAR_TAX_TEAM_CAP = _p('STAR_TAX_TEAM_CAP', 10)
STAR_TAX_IMPACT_CAP = _p('STAR_TAX_IMPACT_CAP', 12)
STAR_TAX_KEY_PLAYER_THRESHOLD = _p('STAR_TAX_KEY_PLAYER_THRESHOLD', 2.0)
QB_BACKUP_QUALITY_FACTOR = _p('QB_BACKUP_QUALITY_FACTOR', 0.6)

SOS_WEIGHT = _p('SOS_WEIGHT', 0.10)
SOS_CAP = _p('SOS_CAP', 2.0)

BYE_WEEK_ADVANTAGE = _p('BYE_WEEK_ADVANTAGE', 1.5)
SHORT_WEEK_PENALTY = _p('SHORT_WEEK_PENALTY', -1.5)
MONDAY_TO_SUNDAY_PENALTY = _p('MONDAY_TO_SUNDAY_PENALTY', -0.5)

DIVISIONAL_RIVALRY_DAMPENER = _p('DIVISIONAL_RIVALRY_DAMPENER', 0.85)

WEATHER_WIND_THRESHOLD = _p('WEATHER_WIND_THRESHOLD', 15)
WEATHER_WIND_PENALTY_PER_MPH = _p('WEATHER_WIND_PENALTY_PER_MPH', -0.1)
WEATHER_COLD_THRESHOLD = _p('WEATHER_COLD_THRESHOLD', 32)
WEATHER_COLD_ADJ_PER_DEGREE = _p('WEATHER_COLD_ADJ_PER_DEGREE', -0.05)
WEATHER_PRECIP_PENALTY = _p('WEATHER_PRECIP_PENALTY', -1.0)
ALTITUDE_ADVANTAGE = _p('ALTITUDE_ADVANTAGE', 1.0)

MOTIVATION_PLAYOFF_CLINCH_ADJ = _p('MOTIVATION_PLAYOFF_CLINCH_ADJ', -0.5)
MOTIVATION_ELIMINATION_BOOST = _p('MOTIVATION_ELIMINATION_BOOST', 0.5)
MOTIVATION_START_WEEK = _p('MOTIVATION_START_WEEK', 14)

RLM_BONUS = _p('RLM_BONUS', 8)
RLM_PENALTY = _p('RLM_PENALTY', -6)
RLM_MIN_MOVEMENT = _p('RLM_MIN_MOVEMENT', 1.0)
CROSS_BOOK_BONUS = _p('CROSS_BOOK_BONUS', 5)
CROSS_BOOK_DISAGREE_THRESHOLD = _p('CROSS_BOOK_DISAGREE_THRESHOLD', 2.0)

ADAPTIVE_BLEND_DEVIATION_THRESHOLD = _p('ADAPTIVE_BLEND_DEVIATION_THRESHOLD', 4.0)
ADAPTIVE_BLEND_MAX_WEIGHT = _p('ADAPTIVE_BLEND_MAX_WEIGHT', 0.50)
ADAPTIVE_BLEND_MIN_WEIGHT = _p('ADAPTIVE_BLEND_MIN_WEIGHT', 0.20)

# ── League baselines (NFL 2024-25 averages, update each season) ────────────
# Points per game ~ 22.5 each side; EPA baselines normalise to 0
LEAGUE_AVG_OFF_EPA = 0.0    # EPA is zero-centred by definition
LEAGUE_AVG_DEF_EPA = 0.0
LEAGUE_AVG_NET_EPA = 0.0
LEAGUE_AVG_TOTAL = 45.0     # average total points (both teams)

# ── Position-based fallback impact values (pts) ──────────────────────────────
# Used when a player has no tracked EPA/WAR data.
# QB is by far the most impactful position in football.
POSITION_FALLBACK = {
    'QB': 8.0,    # Franchise QB out = massive impact
    'RB': 1.5,    # Running backs are more replaceable
    'WR': 2.0,    # WR1 matters, but WR2/3 much less
    'TE': 1.5,    # Tight end (receiving + blocking)
    'OL': 2.5,    # Offensive line injuries are devastating
    'OT': 2.5,    # Offensive tackle specifically
    'OG': 2.0,    # Offensive guard
    'C': 2.0,     # Center
    'DL': 1.5,    # Defensive line
    'DE': 2.0,    # Pass rusher (edge)
    'DT': 1.5,    # Interior d-line
    'EDGE': 2.5,  # Prime edge rusher
    'LB': 1.5,    # Linebacker
    'CB': 2.0,    # Cornerback (good CBs shadow WR1)
    'S': 1.5,     # Safety
    'K': 0.5,     # Kicker (small but nonzero in close games)
    'P': 0.3,     # Punter
}

# ── Injury status helpers ─────────────────────────────────────────────────────

def is_status_out(status: str) -> bool:
    """Return True if player is definitively OUT."""
    s = status.strip().lower()
    return s in ('out', 'out for season', 'injured reserve', 'ir',
                 'physically unable to perform', 'pup', 'suspended',
                 'reserve/covid-19', 'not expected to play')


def is_status_questionable(status: str) -> bool:
    """Return True if player availability is uncertain."""
    s = status.strip().lower()
    return any(kw in s for kw in ('questionable', 'doubtful', 'game-time decision'))


def is_status_probable(status: str) -> bool:
    s = status.strip().lower()
    return 'probable' in s or s == 'limited'


def get_status_weight(status: str) -> float:
    """Return 0–1 probability-of-missing weight."""
    s = status.strip().lower()
    if s in ('out', 'out for season', 'injured reserve', 'ir', 'suspended'):
        return 1.0
    if s in ('physically unable to perform', 'pup'):
        return 1.0
    if 'doubtful' in s:
        return 0.9
    if 'questionable' in s:
        return 0.5
    if 'game-time decision' in s:
        return 0.6
    if 'probable' in s or s == 'limited':
        return 0.1
    if s in ('full', 'full participant'):
        return 0.0
    return 0.0


# ── Cache file paths ──────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATS_CACHE = os.path.join(BASE_DIR, 'nfl_stats_cache.json')
STATS_RECENT_CACHE = os.path.join(BASE_DIR, 'nfl_stats_recent_cache.json')
INJURY_FILE = os.path.join(BASE_DIR, 'nfl_injuries.csv')
SCHEDULE_CACHE = os.path.join(BASE_DIR, 'nfl_schedule_cache.json')
WEATHER_CACHE = os.path.join(BASE_DIR, 'nfl_weather_cache.json')
ODDS_CACHE = os.path.join(BASE_DIR, 'nfl_odds_cache.json')
SOS_CACHE = os.path.join(BASE_DIR, 'nfl_sos_cache.json')


def _load_json(path):
    """Safely load a JSON file, returning empty dict on failure."""
    try:
        if os.path.exists(path):
            with open(path, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"  [WARN] Could not load {os.path.basename(path)}: {e}")
    return {}


# ── Fair Line Log ─────────────────────────────────────────────────────────────
FAIR_LINE_LOG_HEADER = [
    'Timestamp', 'Date', 'Week', 'Away', 'Home',
    'H_OFF_EPA_raw', 'H_DEF_EPA_raw', 'A_OFF_EPA_raw', 'A_DEF_EPA_raw',
    'H_OFF_EPA_reg', 'H_DEF_EPA_reg', 'A_OFF_EPA_reg', 'A_DEF_EPA_reg',
    'Raw_Diff', 'HFA', 'H_Bye', 'A_Bye', 'Schedule_Adj',
    'H_Star_Tax', 'A_Star_Tax', 'H_QB_Out', 'A_QB_Out',
    'Weather_Wind', 'Weather_Temp', 'Weather_Precip', 'Weather_Adj',
    'Altitude_Adj', 'Divisional', 'Divisional_Adj',
    'H_SOS', 'A_SOS', 'SOS_Adj',
    'Motivation_Adj', 'Motivation_Tag',
    'Fair_Line', 'Star_Tax_Failed',
    'Market_Line', 'Edge', 'Raw_Edge', 'Pick', 'Guard_Rails',
    'Edge_Source', 'Ratings_Pct', 'Injury_Pct',
    'ECS', 'ECS_Tier',
    'RLM_Adj', 'XBook_Adj',
    'ModelVersion',
]


def log_fair_line_components(away, home, week, components):
    """Log all fair-line components to a daily CSV for post-mortem analysis."""
    now = datetime.now()
    filename = f"fair_line_log_{now.strftime('%Y-%m-%d')}.csv"
    filepath = os.path.join(BASE_DIR, filename)
    timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
    date_str = now.strftime('%Y-%m-%d')

    row = [timestamp, date_str, week, away, home] + [
        round(components.get(k, 0), 4) if isinstance(components.get(k, 0), float) else components.get(k, '')
        for k in [
            'h_off_epa_raw', 'h_def_epa_raw', 'a_off_epa_raw', 'a_def_epa_raw',
            'h_off_epa_reg', 'h_def_epa_reg', 'a_off_epa_reg', 'a_def_epa_reg',
            'raw_diff', 'hfa', 'h_bye', 'a_bye', 'schedule_adj',
            'h_star_tax', 'a_star_tax', 'h_qb_out', 'a_qb_out',
            'weather_wind', 'weather_temp', 'weather_precip', 'weather_adj',
            'altitude_adj', 'divisional', 'divisional_adj',
            'h_sos', 'a_sos', 'sos_adj',
            'motivation_adj', 'motivation_tag',
            'fair_line', 'star_tax_failed',
        ]
    ] + ['', '', '', '', '', '', '', '', '', '', '', '', _MODEL_VERSION]

    write_header = not os.path.isfile(filepath)
    with open(filepath, 'a', newline='') as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(FAIR_LINE_LOG_HEADER)
        writer.writerow(row)


def update_fair_line_log_market(away, home, market_line, edge, raw_edge, pick,
                                 guard_rails='', edge_source='', ratings_pct='',
                                 injury_pct='', ecs_score='', ecs_tier='',
                                 rlm_adj='', xbook_adj=''):
    """Update the most recent log row for this matchup with market context."""
    now = datetime.now()
    filename = f"fair_line_log_{now.strftime('%Y-%m-%d')}.csv"
    filepath = os.path.join(BASE_DIR, filename)
    if not os.path.isfile(filepath):
        return
    try:
        with open(filepath, 'r', newline='') as f:
            rows = list(csv.reader(f))
        if len(rows) < 2:
            return
        header = rows[0]
        market_idx = header.index('Market_Line') if 'Market_Line' in header else -1
        if market_idx < 0:
            return
        # Find last row matching this matchup
        for i in range(len(rows) - 1, 0, -1):
            if len(rows[i]) > 4 and rows[i][3] == away and rows[i][4] == home:
                vals = [market_line, edge, raw_edge, pick, guard_rails,
                        edge_source, ratings_pct, injury_pct,
                        ecs_score, ecs_tier, rlm_adj, xbook_adj]
                for j, v in enumerate(vals):
                    idx = market_idx + j
                    while len(rows[i]) <= idx:
                        rows[i].append('')
                    rows[i][idx] = v
                break
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(rows)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  CORE PREDICTION ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def load_team_stats():
    """Load season and recent team stats from cache files.

    Returns:
        (season_stats, recent_stats) — both dicts keyed by team full_name.
        Each value: {'OFF_EPA': float, 'DEF_EPA': float, 'NET_EPA': float,
                     'PPG': float, 'OPPG': float}
    """
    season = _load_json(STATS_CACHE)
    recent = _load_json(STATS_RECENT_CACHE)
    return season, recent


def _blend_stats(season_stats, recent_stats, team):
    """Blend season and recent stats for a team with adaptive weighting.

    Returns dict with OFF_EPA, DEF_EPA, NET_EPA (blended).
    Falls back to season-only if recent unavailable.
    """
    s = season_stats.get(team, {})
    r = recent_stats.get(team, {})

    if not s:
        return {'OFF_EPA': 0.0, 'DEF_EPA': 0.0, 'NET_EPA': 0.0}

    s_off = s.get('OFF_EPA', 0.0)
    s_def = s.get('DEF_EPA', 0.0)

    if not r or 'OFF_EPA' not in r:
        return {'OFF_EPA': s_off, 'DEF_EPA': s_def, 'NET_EPA': s_off - s_def}

    r_off = r.get('OFF_EPA', s_off)
    r_def = r.get('DEF_EPA', s_def)

    # Adaptive blend: if recent deviates significantly, trust recent more
    deviation = abs(r_off - s_off) + abs(r_def - s_def)
    if deviation > ADAPTIVE_BLEND_DEVIATION_THRESHOLD:
        w = min(ADAPTIVE_BLEND_MAX_WEIGHT, RECENT_BLEND_WEIGHT + 0.10)
    elif deviation < ADAPTIVE_BLEND_DEVIATION_THRESHOLD / 2:
        w = max(ADAPTIVE_BLEND_MIN_WEIGHT, RECENT_BLEND_WEIGHT - 0.10)
    else:
        w = RECENT_BLEND_WEIGHT

    off = w * r_off + (1 - w) * s_off
    defe = w * r_def + (1 - w) * s_def

    return {'OFF_EPA': off, 'DEF_EPA': defe, 'NET_EPA': off - defe, 'blend_w': w}


def _regress_to_mean(val, baseline=0.0):
    """Regress a stat toward league baseline."""
    return val * REGRESS_FACTOR + baseline * (1 - REGRESS_FACTOR)


def load_injuries():
    """Load injury data from nfl_injuries.csv.

    Returns dict: {team_name: [{'player': str, 'position': str,
                                 'status': str, 'note': str}, ...]}
    """
    injuries = {}
    if not os.path.exists(INJURY_FILE):
        return injuries
    try:
        with open(INJURY_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                team = row.get('team', '').strip()
                if not team:
                    continue
                full = resolve_team_name(team)
                if not full:
                    full = team
                injuries.setdefault(full, []).append({
                    'player': row.get('player', '').strip(),
                    'position': row.get('position', '').strip().upper(),
                    'status': row.get('status', '').strip(),
                    'note': row.get('note', '').strip(),
                })
    except Exception as e:
        print(f"  [WARN] Could not load injuries: {e}")
    return injuries


def calculate_star_tax(team, injuries_dict):
    """Calculate the injury impact (star tax) for a team.

    NFL-specific: QB injuries are weighted at full impact (QB_IMPACT_WEIGHT=1.0),
    all other positions are dampened (NON_QB_IMPACT_DAMPENER=0.25).

    Returns: (total_tax, qb_out_name, key_players_out, details_list, failed)
    """
    team_injuries = injuries_dict.get(team, [])
    if not team_injuries:
        return 0.0, '', [], [], False

    total_tax = 0.0
    qb_out = ''
    key_players = []
    details = []
    failed = False

    for inj in team_injuries:
        player = inj['player']
        pos = inj['position']
        status = inj['status']
        weight = get_status_weight(status)

        if weight <= 0:
            continue

        # Determine raw impact based on position
        raw_impact = POSITION_FALLBACK.get(pos, 1.0)

        # QB gets full weight; everyone else is dampened
        if pos == 'QB':
            impact = raw_impact * QB_IMPACT_WEIGHT * weight
            if weight >= 0.5:
                qb_out = player
        else:
            impact = raw_impact * NON_QB_IMPACT_DAMPENER * weight

        # Cap per-player impact
        impact = min(impact, STAR_TAX_IMPACT_CAP)

        if impact >= STAR_TAX_KEY_PLAYER_THRESHOLD:
            key_players.append(f"{player} ({pos}, {status})")

        total_tax += impact
        details.append({
            'player': player,
            'position': pos,
            'status': status,
            'weight': weight,
            'raw_impact': raw_impact,
            'final_impact': round(impact, 2),
        })

    # Cap total team tax
    total_tax = min(total_tax, STAR_TAX_TEAM_CAP)
    total_tax = max(total_tax, -STAR_TAX_TEAM_CAP)

    return round(total_tax, 2), qb_out, key_players, details, failed


def calculate_weather_adjustment(weather_data, home_team):
    """Calculate weather impact on the game.

    Returns: (weather_adj, weather_detail_dict)
    weather_adj affects totals primarily; for spreads it's the differential
    impact (dome teams less affected).
    """
    if not weather_data or is_dome_game(home_team):
        return 0.0, {'wind': 0, 'temp': 72, 'precip': False, 'dome': is_dome_game(home_team), 'adj': 0.0}

    wind = weather_data.get('wind_mph', 0)
    temp = weather_data.get('temp_f', 65)
    precip = weather_data.get('precipitation', False)

    adj = 0.0

    # Wind penalty (mostly affects passing game / totals)
    if wind > WEATHER_WIND_THRESHOLD:
        adj += (wind - WEATHER_WIND_THRESHOLD) * WEATHER_WIND_PENALTY_PER_MPH

    # Cold penalty (favours run-heavy / defensive teams)
    if temp < WEATHER_COLD_THRESHOLD:
        adj += (WEATHER_COLD_THRESHOLD - temp) * WEATHER_COLD_ADJ_PER_DEGREE

    # Precipitation
    if precip:
        adj += WEATHER_PRECIP_PENALTY

    detail = {
        'wind': wind, 'temp': temp, 'precip': precip,
        'dome': False, 'adj': round(adj, 2),
    }
    return round(adj, 2), detail


def calculate_schedule_adjustment(home_schedule, away_schedule):
    """Calculate rest/schedule advantage.

    home_schedule/away_schedule: dict with keys:
        'bye_week': bool (coming off bye)
        'short_week': bool (Thu after Sun)
        'monday_to_sunday': bool

    Returns: (schedule_adj, h_sched_detail, a_sched_detail)
    """
    h_adj = 0.0
    a_adj = 0.0

    hs = home_schedule or {}
    as_ = away_schedule or {}

    if hs.get('bye_week'):
        h_adj += BYE_WEEK_ADVANTAGE
    if hs.get('short_week'):
        h_adj += SHORT_WEEK_PENALTY
    if hs.get('monday_to_sunday'):
        h_adj += MONDAY_TO_SUNDAY_PENALTY

    if as_.get('bye_week'):
        a_adj += BYE_WEEK_ADVANTAGE
    if as_.get('short_week'):
        a_adj += SHORT_WEEK_PENALTY
    if as_.get('monday_to_sunday'):
        a_adj += MONDAY_TO_SUNDAY_PENALTY

    return round(h_adj - a_adj, 2), hs, as_


def calculate_sos_adjustment(home_team, away_team, sos_data):
    """Strength of schedule regression.

    sos_data: {team_name: float} where positive = faced stronger opponents.
    Returns: (sos_adj, h_sos, a_sos)
    """
    if not sos_data:
        return 0.0, 0.0, 0.0

    h_sos = sos_data.get(home_team, 0.0)
    a_sos = sos_data.get(away_team, 0.0)

    raw_adj = (h_sos - a_sos) * SOS_WEIGHT
    adj = max(-SOS_CAP, min(SOS_CAP, raw_adj))

    return round(adj, 2), round(h_sos, 2), round(a_sos, 2)


def calculate_motivation_adjustment(home_team, away_team, week, standings=None):
    """Late-season motivation adjustments.

    standings: {team_name: {'clinched': bool, 'eliminated': bool, 'playoff_pct': float}}
    Returns: (motivation_adj, motivation_tag)
    """
    if week < MOTIVATION_START_WEEK or not standings:
        return 0.0, ''

    h_stand = standings.get(home_team, {})
    a_stand = standings.get(away_team, {})

    adj = 0.0
    tags = []

    if h_stand.get('clinched') and not a_stand.get('clinched'):
        adj += MOTIVATION_PLAYOFF_CLINCH_ADJ
        tags.append('H_CLINCHED')
    if a_stand.get('clinched') and not h_stand.get('clinched'):
        adj -= MOTIVATION_PLAYOFF_CLINCH_ADJ
        tags.append('A_CLINCHED')

    if h_stand.get('eliminated') and not a_stand.get('eliminated'):
        adj -= MOTIVATION_ELIMINATION_BOOST
        tags.append('H_ELIMINATED')
    if a_stand.get('eliminated') and not h_stand.get('eliminated'):
        adj += MOTIVATION_ELIMINATION_BOOST
        tags.append('A_ELIMINATED')

    return round(adj, 2), '|'.join(tags)


def predict_nfl_spread(away_team, home_team, week=0,
                        weather_data=None,
                        home_schedule=None, away_schedule=None,
                        standings=None):
    """Core prediction: calculate fair line for an NFL game.

    Args:
        away_team: Away team (full name, abbr, or nickname)
        home_team: Home team (full name, abbr, or nickname)
        week: NFL week number (1-18, or 19-22 for playoffs)
        weather_data: {'wind_mph': int, 'temp_f': int, 'precipitation': bool}
        home_schedule: {'bye_week': bool, 'short_week': bool}
        away_schedule: {'bye_week': bool, 'short_week': bool}
        standings: {team: {'clinched': bool, 'eliminated': bool}}

    Returns:
        (fair_line, components_dict)
        fair_line: negative = home favoured (e.g., -3.5)
    """
    # Resolve team names
    home = resolve_team_name(home_team) or home_team
    away = resolve_team_name(away_team) or away_team

    # Load all data
    season_stats, recent_stats = load_team_stats()
    injuries = load_injuries()
    sos_data = _load_json(SOS_CACHE)

    # ── A. Blend & Regress Stats ──
    h_blended = _blend_stats(season_stats, recent_stats, home)
    a_blended = _blend_stats(season_stats, recent_stats, away)

    h_off_raw = h_blended['OFF_EPA']
    h_def_raw = h_blended['DEF_EPA']
    a_off_raw = a_blended['OFF_EPA']
    a_def_raw = a_blended['DEF_EPA']

    h_off_reg = _regress_to_mean(h_off_raw, LEAGUE_AVG_OFF_EPA)
    h_def_reg = _regress_to_mean(h_def_raw, LEAGUE_AVG_DEF_EPA)
    a_off_reg = _regress_to_mean(a_off_raw, LEAGUE_AVG_OFF_EPA)
    a_def_reg = _regress_to_mean(a_def_raw, LEAGUE_AVG_DEF_EPA)

    # ── B. Core Matchup: home advantage in EPA differential ──
    # Positive = home team is better → negative spread (home favoured)
    raw_diff = (h_off_reg - a_def_reg) - (a_off_reg - h_def_reg)

    # ── C. Home-Field Advantage ──
    hfa = FLAT_HFA

    # Altitude boost for Denver
    altitude_adj = 0.0
    h_info = get_team_info(home)
    if h_info and h_info.get('altitude_ft', 0) > 4000:
        altitude_adj = ALTITUDE_ADVANTAGE

    # ── D. Star Tax (Injuries) ──
    h_tax, h_qb_out, h_key_out, h_inj_details, h_tax_failed = calculate_star_tax(home, injuries)
    a_tax, a_qb_out, a_key_out, a_inj_details, a_tax_failed = calculate_star_tax(away, injuries)
    star_tax_failed = h_tax_failed or a_tax_failed

    # ── E. Schedule Adjustment ──
    schedule_adj, h_sched, a_sched = calculate_schedule_adjustment(home_schedule, away_schedule)

    # ── F. Weather Adjustment ──
    weather_adj, weather_detail = calculate_weather_adjustment(weather_data, home)

    # ── G. Strength of Schedule ──
    sos_adj, h_sos, a_sos = calculate_sos_adjustment(home, away, sos_data)

    # ── H. Divisional Rivalry Dampening ──
    is_divisional = same_division(home, away)
    divisional_adj = 0.0
    # For divisional games, compress the spread toward 0
    # (divisional games are historically closer)

    # ── I. Motivation Adjustment ──
    motivation_adj, motivation_tag = calculate_motivation_adjustment(home, away, week, standings)

    # ── J. Assemble Fair Line ──
    # Convention: negative = home favoured
    # raw_diff is positive when home is better
    fair_line = -(raw_diff + hfa + altitude_adj
                  - h_tax + a_tax
                  + schedule_adj
                  + sos_adj
                  + motivation_adj)

    # Weather adjustment applies to the spread slightly (affects game dynamics)
    # but mostly matters for totals. Small spread effect:
    fair_line += weather_adj * 0.1  # 10% of weather effect on spread

    # Divisional dampening: compress spread toward 0
    if is_divisional:
        fair_line *= DIVISIONAL_RIVALRY_DAMPENER

    # ── Build components dict ──
    components = {
        'h_off_epa_raw': h_off_raw, 'h_def_epa_raw': h_def_raw,
        'a_off_epa_raw': a_off_raw, 'a_def_epa_raw': a_def_raw,
        'h_off_epa_reg': h_off_reg, 'h_def_epa_reg': h_def_reg,
        'a_off_epa_reg': a_off_reg, 'a_def_epa_reg': a_def_reg,
        'raw_diff': raw_diff,
        'hfa': hfa,
        'altitude_adj': altitude_adj,
        'h_star_tax': h_tax, 'a_star_tax': a_tax,
        'h_qb_out': h_qb_out, 'a_qb_out': a_qb_out,
        'h_key_out': ', '.join(h_key_out), 'a_key_out': ', '.join(a_key_out),
        'star_tax_failed': star_tax_failed,
        'h_bye': 1 if (home_schedule or {}).get('bye_week') else 0,
        'a_bye': 1 if (away_schedule or {}).get('bye_week') else 0,
        'schedule_adj': schedule_adj,
        'weather_wind': weather_detail.get('wind', 0),
        'weather_temp': weather_detail.get('temp', 65),
        'weather_precip': weather_detail.get('precip', False),
        'weather_adj': weather_adj,
        'divisional': is_divisional,
        'divisional_adj': divisional_adj,
        'h_sos': h_sos, 'a_sos': a_sos, 'sos_adj': sos_adj,
        'motivation_adj': motivation_adj, 'motivation_tag': motivation_tag,
        'fair_line': round(fair_line, 1),
        'h_blend_w': h_blended.get('blend_w', RECENT_BLEND_WEIGHT),
        'a_blend_w': a_blended.get('blend_w', RECENT_BLEND_WEIGHT),
    }

    # Log to fair line log
    log_fair_line_components(away, home, week, components)

    return round(fair_line, 1), components


def calculate_edge(fair_line, market_line):
    """Calculate edge and apply market anchor.

    Returns: (edge, raw_edge, anchored_fair, edge_capped)
    """
    edge_cap = _gr('edge_cap', 10)

    # Market anchor blend
    w = MARKET_ANCHOR_WEIGHT
    anchored_fair = (1 - w) * fair_line + w * market_line

    raw_edge = abs(anchored_fair - market_line)
    edge = min(raw_edge, edge_cap)
    edge_capped = raw_edge > edge_cap

    return round(edge, 1), round(raw_edge, 1), round(anchored_fair, 1), edge_capped


def determine_pick(fair_line, market_line):
    """Determine which side to bet.

    Returns: (pick_team_side, pick_description)
        pick_team_side: 'HOME' or 'AWAY'
    """
    # If fair line is more negative than market → home is undervalued → pick home
    # If fair line is less negative than market → away is undervalued → pick away
    if fair_line < market_line:
        return 'HOME', 'Home covers (model says home is better than market thinks)'
    else:
        return 'AWAY', 'Away covers (model says away is better than market thinks)'


def decompose_edge(fair_line, market_line, components):
    """Break down the edge into source factors.

    Returns: (edge_source, ratings_pct, injury_pct, decomp_dict)
    """
    total_abs = 0.0001  # avoid division by zero

    ratings_contrib = abs(components.get('raw_diff', 0)) + abs(components.get('hfa', 0))
    injury_contrib = abs(components.get('h_star_tax', 0)) + abs(components.get('a_star_tax', 0))
    schedule_contrib = abs(components.get('schedule_adj', 0))
    weather_contrib = abs(components.get('weather_adj', 0))
    sos_contrib = abs(components.get('sos_adj', 0))
    motivation_contrib = abs(components.get('motivation_adj', 0))

    total_abs = (ratings_contrib + injury_contrib + schedule_contrib +
                 weather_contrib + sos_contrib + motivation_contrib)
    if total_abs < 0.0001:
        total_abs = 0.0001

    ratings_pct = ratings_contrib / total_abs * 100
    injury_pct = injury_contrib / total_abs * 100
    situational_pct = (schedule_contrib + weather_contrib + sos_contrib + motivation_contrib) / total_abs * 100

    if ratings_pct > 60:
        edge_source = 'RATINGS-DRIVEN'
    elif injury_pct > 40:
        edge_source = 'INJURY-DRIVEN'
    elif situational_pct > 50:
        edge_source = 'SITUATIONAL'
    else:
        edge_source = 'MIXED'

    decomp = {
        'ratings_contrib': round(ratings_contrib, 2),
        'injury_contrib': round(injury_contrib, 2),
        'schedule_contrib': round(schedule_contrib, 2),
        'weather_contrib': round(weather_contrib, 2),
        'sos_contrib': round(sos_contrib, 2),
        'motivation_contrib': round(motivation_contrib, 2),
        'ratings_pct': round(ratings_pct, 1),
        'injury_pct': round(injury_pct, 1),
        'edge_source': edge_source,
    }
    return edge_source, round(ratings_pct, 1), round(injury_pct, 1), decomp


def calculate_ecs(edge, raw_edge, edge_capped, components, edge_source,
                   ratings_pct, injury_pct, market_gap, star_tax_failed=False,
                   gtd_count=0):
    """Calculate Edge Confidence Score (0-100).

    NFL-specific adjustments:
    - QB injury drives lower ECS (too binary, unpredictable backup performance)
    - Weather-affected games get penalty
    - Divisional games get slight bonus (more predictable)

    Returns: (ecs_score, ecs_tier, breakdown_list)
    """
    min_edge = _gr('min_edge', 6)
    base = 50
    breakdown = []

    # 1. Edge Sweet Spot
    if edge < min_edge:
        adj = -15
        breakdown.append(f"Below min_edge ({min_edge}): {adj}")
    elif 3 <= edge <= 5:
        adj = +20
        breakdown.append(f"Sweet spot (3-5): +{adj}")
    elif 5 < edge <= 7:
        adj = +10
        breakdown.append(f"Moderate edge (5-7): +{adj}")
    elif 7 < edge <= 10:
        adj = 0
        breakdown.append(f"High edge (7-10): +{adj}")
    else:
        adj = -10
        breakdown.append(f"Extreme edge (10+): {adj}")
    base += adj

    # 2. Edge Source
    if edge_source == 'RATINGS-DRIVEN':
        adj = +15
    elif edge_source == 'MIXED':
        adj = +10
    elif edge_source == 'SITUATIONAL':
        adj = +5
    else:
        adj = 0
    breakdown.append(f"Source ({edge_source}): {adj:+d}")
    base += adj

    # 3. Market Agreement
    if market_gap <= 5:
        adj = +15
    elif market_gap <= 8:
        adj = +5
    elif market_gap <= 12:
        adj = -10
    else:
        adj = -20
    breakdown.append(f"Market gap ({market_gap:.1f}): {adj:+d}")
    base += adj

    # 4. Injury Stability
    if injury_pct <= 20:
        adj = +10
    elif injury_pct <= 40:
        adj = 0
    else:
        adj = -10
    breakdown.append(f"Injury % ({injury_pct:.0f}%): {adj:+d}")
    base += adj

    # 5. Edge Cap Penalty
    if edge_capped:
        adj = -15
        breakdown.append(f"Edge capped: {adj}")
        base += adj

    # 6. Star Tax API Failure
    if star_tax_failed:
        adj = -10
        breakdown.append(f"Star tax failed: {adj}")
        base += adj

    # 7. GTD Players
    if gtd_count > 0:
        adj = min(-5 * gtd_count, -15)
        breakdown.append(f"GTD players ({gtd_count}): {adj}")
        base += adj

    # 8. NFL-specific: QB injury penalty
    h_qb_out = components.get('h_qb_out', '')
    a_qb_out = components.get('a_qb_out', '')
    if h_qb_out or a_qb_out:
        adj = -10
        breakdown.append(f"QB injury ({h_qb_out or a_qb_out}): {adj}")
        base += adj

    # 9. NFL-specific: Weather penalty
    weather_adj = abs(components.get('weather_adj', 0))
    if weather_adj > 1.5:
        adj = -8
        breakdown.append(f"Weather impact ({weather_adj:.1f}): {adj}")
        base += adj

    # 10. NFL-specific: Divisional bonus
    if components.get('divisional'):
        adj = +5
        breakdown.append(f"Divisional game: +{adj}")
        base += adj

    # Clamp
    ecs = max(0, min(100, base))

    # Tier
    if ecs >= 80:
        tier = 'HIGH'
    elif ecs >= 60:
        tier = 'MODERATE'
    elif ecs >= 40:
        tier = 'LOW'
    else:
        tier = 'NONE'

    return ecs, tier, breakdown


# ══════════════════════════════════════════════════════════════════════════════
#  GUARD RAILS
# ══════════════════════════════════════════════════════════════════════════════

def evaluate_guard_rails(home_team, away_team, pick_side, edge, ecs, components,
                          market_line=None, fair_line=None):
    """Evaluate all guard rails and determine bet type.

    Returns: (bet_type, reasons_list, guard_rails_str)
        bet_type: 'REAL', 'SHADOW', 'FADE'
        reasons_list: list of triggered guard rail tags
        guard_rails_str: formatted string for display
    """
    reasons = []
    pick_team = home_team if pick_side == 'HOME' else away_team

    min_edge = _gr('min_edge', 6)
    edge_cap = _gr('edge_cap', 10)
    inj_threshold = _gr('injury_out_threshold', 3)
    inj_tax_threshold = _gr('injury_tax_threshold', 4.0)
    market_div_threshold = _gr('market_divergence_threshold', 7)
    low_conf_ecs = _gr('low_confidence_ecs_threshold', 40)
    conf_conflict_floor = _gr('confidence_conflict_ecs_floor', 50)
    hpe = _gr('home_pick_edge_penalty', 1)
    weather_shadow_wind = _gr('weather_auto_shadow_wind', 25)
    qb_auto_shadow = _gr('qb_injury_auto_shadow', True)
    blacklist = _gr('team_blacklist', [])

    # 1. LOW_EDGE
    if edge < min_edge:
        reasons.append('LOW_EDGE')

    # 2. TEAM_BLACKLIST
    if pick_team in blacklist:
        reasons.append('TEAM_BLACKLIST')

    # 3. QB_INJURY — if our pick's QB is out, auto-shadow
    if qb_auto_shadow:
        if pick_side == 'HOME' and components.get('h_qb_out'):
            reasons.append('QB_INJURY')
        elif pick_side == 'AWAY' and components.get('a_qb_out'):
            reasons.append('QB_INJURY')

    # 4. INJURY_BREAKER — many starters out
    injuries = load_injuries()
    pick_injuries = injuries.get(pick_team, [])
    out_count = sum(1 for inj in pick_injuries if get_status_weight(inj['status']) >= 0.9)
    if out_count >= inj_threshold:
        reasons.append('INJURY_BREAKER')

    # 5. MARKET_DIVERGENCE
    if market_line is not None and fair_line is not None:
        gap = abs(fair_line - market_line)
        if gap > market_div_threshold:
            reasons.append('MARKET_DIVERGENCE')

    # 6. LOW_CONFIDENCE / CONFIDENCE_CONFLICT
    if ecs < low_conf_ecs:
        reasons.append('LOW_CONFIDENCE')
    elif ecs < conf_conflict_floor and edge >= min_edge:
        reasons.append('CONFIDENCE_CONFLICT')

    # 7. HOME_PICK_PENALTY
    if pick_side == 'HOME' and hpe > 0:
        reasons.append('HOME_PICK_PENALTY')

    # 8. WEATHER_RISK
    wind = components.get('weather_wind', 0)
    if wind > weather_shadow_wind:
        reasons.append('WEATHER_RISK')

    # 9. SHORT_WEEK for picked team
    if pick_side == 'HOME' and components.get('schedule_adj', 0) < -1:
        reasons.append('SHORT_WEEK')
    elif pick_side == 'AWAY' and components.get('schedule_adj', 0) > 1:
        reasons.append('SHORT_WEEK')

    # 10. BLOWOUT_RISK
    blowout_threshold = _gr('blowout_net_rating_threshold', 10)
    h_net = components.get('h_off_epa_raw', 0) - components.get('h_def_epa_raw', 0)
    a_net = components.get('a_off_epa_raw', 0) - components.get('a_def_epa_raw', 0)
    if abs(h_net - a_net) > blowout_threshold:
        reasons.append('BLOWOUT_RISK')

    # Determine bet type
    # FADE = high-conviction triggers where the pick is likely wrong
    # SHADOW = uncertainty triggers where the pick may be fine but risk is elevated
    if reasons:
        fade_hard = _gr('fade_hard_tags', [
            'QB_INJURY', 'INJURY_BREAKER', 'MARKET_DIVERGENCE',
            'BLOWOUT_RISK', 'TEAM_BLACKLIST',
        ])
        if any(r in fade_hard for r in reasons):
            bet_type = 'FADE'
            guard_rails_str = f"FADE: {', '.join(reasons)}"
        else:
            bet_type = 'SHADOW'
            guard_rails_str = f"SHADOW: {', '.join(reasons)}"
    else:
        bet_type = 'REAL'
        guard_rails_str = 'CLEAR'

    return bet_type, reasons, guard_rails_str

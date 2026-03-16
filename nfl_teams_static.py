"""
nfl_teams_static.py — Local NFL team data (all 32 teams)

Provides team lookup functions, ID mappings, and division/conference info.

Usage:
    from nfl_teams_static import get_teams, TEAM_NAME_TO_ABBR, ABBR_TO_TEAM_NAME
"""

# ─── Static Team Data ─────────────────────────────────────────────────────────
_NFL_TEAMS = [
    # AFC East
    {'full_name': 'Buffalo Bills', 'nickname': 'Bills', 'abbreviation': 'BUF', 'conference': 'AFC', 'division': 'East', 'stadium': 'Highmark Stadium', 'dome': False, 'altitude_ft': 600},
    {'full_name': 'Miami Dolphins', 'nickname': 'Dolphins', 'abbreviation': 'MIA', 'conference': 'AFC', 'division': 'East', 'stadium': 'Hard Rock Stadium', 'dome': False, 'altitude_ft': 6},
    {'full_name': 'New England Patriots', 'nickname': 'Patriots', 'abbreviation': 'NE', 'conference': 'AFC', 'division': 'East', 'stadium': 'Gillette Stadium', 'dome': False, 'altitude_ft': 230},
    {'full_name': 'New York Jets', 'nickname': 'Jets', 'abbreviation': 'NYJ', 'conference': 'AFC', 'division': 'East', 'stadium': 'MetLife Stadium', 'dome': False, 'altitude_ft': 7},
    # AFC North
    {'full_name': 'Baltimore Ravens', 'nickname': 'Ravens', 'abbreviation': 'BAL', 'conference': 'AFC', 'division': 'North', 'stadium': 'M&T Bank Stadium', 'dome': False, 'altitude_ft': 20},
    {'full_name': 'Cincinnati Bengals', 'nickname': 'Bengals', 'abbreviation': 'CIN', 'conference': 'AFC', 'division': 'North', 'stadium': 'Paycor Stadium', 'dome': False, 'altitude_ft': 480},
    {'full_name': 'Cleveland Browns', 'nickname': 'Browns', 'abbreviation': 'CLE', 'conference': 'AFC', 'division': 'North', 'stadium': 'Huntington Bank Field', 'dome': False, 'altitude_ft': 580},
    {'full_name': 'Pittsburgh Steelers', 'nickname': 'Steelers', 'abbreviation': 'PIT', 'conference': 'AFC', 'division': 'North', 'stadium': 'Acrisure Stadium', 'dome': False, 'altitude_ft': 730},
    # AFC South
    {'full_name': 'Houston Texans', 'nickname': 'Texans', 'abbreviation': 'HOU', 'conference': 'AFC', 'division': 'South', 'stadium': 'NRG Stadium', 'dome': True, 'altitude_ft': 43},
    {'full_name': 'Indianapolis Colts', 'nickname': 'Colts', 'abbreviation': 'IND', 'conference': 'AFC', 'division': 'South', 'stadium': 'Lucas Oil Stadium', 'dome': True, 'altitude_ft': 715},
    {'full_name': 'Jacksonville Jaguars', 'nickname': 'Jaguars', 'abbreviation': 'JAX', 'conference': 'AFC', 'division': 'South', 'stadium': 'EverBank Stadium', 'dome': False, 'altitude_ft': 15},
    {'full_name': 'Tennessee Titans', 'nickname': 'Titans', 'abbreviation': 'TEN', 'conference': 'AFC', 'division': 'South', 'stadium': 'Nissan Stadium', 'dome': False, 'altitude_ft': 430},
    # AFC West
    {'full_name': 'Denver Broncos', 'nickname': 'Broncos', 'abbreviation': 'DEN', 'conference': 'AFC', 'division': 'West', 'stadium': 'Empower Field at Mile High', 'dome': False, 'altitude_ft': 5280},
    {'full_name': 'Kansas City Chiefs', 'nickname': 'Chiefs', 'abbreviation': 'KC', 'conference': 'AFC', 'division': 'West', 'stadium': 'GEHA Field at Arrowhead', 'dome': False, 'altitude_ft': 800},
    {'full_name': 'Las Vegas Raiders', 'nickname': 'Raiders', 'abbreviation': 'LV', 'conference': 'AFC', 'division': 'West', 'stadium': 'Allegiant Stadium', 'dome': True, 'altitude_ft': 2001},
    {'full_name': 'Los Angeles Chargers', 'nickname': 'Chargers', 'abbreviation': 'LAC', 'conference': 'AFC', 'division': 'West', 'stadium': 'SoFi Stadium', 'dome': True, 'altitude_ft': 100},
    # NFC East
    {'full_name': 'Dallas Cowboys', 'nickname': 'Cowboys', 'abbreviation': 'DAL', 'conference': 'NFC', 'division': 'East', 'stadium': 'AT&T Stadium', 'dome': True, 'altitude_ft': 600},
    {'full_name': 'New York Giants', 'nickname': 'Giants', 'abbreviation': 'NYG', 'conference': 'NFC', 'division': 'East', 'stadium': 'MetLife Stadium', 'dome': False, 'altitude_ft': 7},
    {'full_name': 'Philadelphia Eagles', 'nickname': 'Eagles', 'abbreviation': 'PHI', 'conference': 'NFC', 'division': 'East', 'stadium': 'Lincoln Financial Field', 'dome': False, 'altitude_ft': 20},
    {'full_name': 'Washington Commanders', 'nickname': 'Commanders', 'abbreviation': 'WAS', 'conference': 'NFC', 'division': 'East', 'stadium': 'Northwest Stadium', 'dome': False, 'altitude_ft': 60},
    # NFC North
    {'full_name': 'Chicago Bears', 'nickname': 'Bears', 'abbreviation': 'CHI', 'conference': 'NFC', 'division': 'North', 'stadium': 'Soldier Field', 'dome': False, 'altitude_ft': 595},
    {'full_name': 'Detroit Lions', 'nickname': 'Lions', 'abbreviation': 'DET', 'conference': 'NFC', 'division': 'North', 'stadium': 'Ford Field', 'dome': True, 'altitude_ft': 584},
    {'full_name': 'Green Bay Packers', 'nickname': 'Packers', 'abbreviation': 'GB', 'conference': 'NFC', 'division': 'North', 'stadium': 'Lambeau Field', 'dome': False, 'altitude_ft': 640},
    {'full_name': 'Minnesota Vikings', 'nickname': 'Vikings', 'abbreviation': 'MIN', 'conference': 'NFC', 'division': 'North', 'stadium': 'U.S. Bank Stadium', 'dome': True, 'altitude_ft': 830},
    # NFC South
    {'full_name': 'Atlanta Falcons', 'nickname': 'Falcons', 'abbreviation': 'ATL', 'conference': 'NFC', 'division': 'South', 'stadium': 'Mercedes-Benz Stadium', 'dome': True, 'altitude_ft': 1050},
    {'full_name': 'Carolina Panthers', 'nickname': 'Panthers', 'abbreviation': 'CAR', 'conference': 'NFC', 'division': 'South', 'stadium': 'Bank of America Stadium', 'dome': False, 'altitude_ft': 760},
    {'full_name': 'New Orleans Saints', 'nickname': 'Saints', 'abbreviation': 'NO', 'conference': 'NFC', 'division': 'South', 'stadium': 'Caesars Superdome', 'dome': True, 'altitude_ft': 3},
    {'full_name': 'Tampa Bay Buccaneers', 'nickname': 'Buccaneers', 'abbreviation': 'TB', 'conference': 'NFC', 'division': 'South', 'stadium': 'Raymond James Stadium', 'dome': False, 'altitude_ft': 15},
    # NFC West
    {'full_name': 'Arizona Cardinals', 'nickname': 'Cardinals', 'abbreviation': 'ARI', 'conference': 'NFC', 'division': 'West', 'stadium': 'State Farm Stadium', 'dome': True, 'altitude_ft': 1070},
    {'full_name': 'Los Angeles Rams', 'nickname': 'Rams', 'abbreviation': 'LAR', 'conference': 'NFC', 'division': 'West', 'stadium': 'SoFi Stadium', 'dome': True, 'altitude_ft': 100},
    {'full_name': 'San Francisco 49ers', 'nickname': '49ers', 'abbreviation': 'SF', 'conference': 'NFC', 'division': 'West', 'stadium': "Levi's Stadium", 'dome': False, 'altitude_ft': 8},
    {'full_name': 'Seattle Seahawks', 'nickname': 'Seahawks', 'abbreviation': 'SEA', 'conference': 'NFC', 'division': 'West', 'stadium': 'Lumen Field', 'dome': False, 'altitude_ft': 15},
]


def get_teams():
    """Return list of all NFL teams."""
    return list(_NFL_TEAMS)


# ─── Prebuilt Lookup Dicts ────────────────────────────────────────────────────
TEAM_NAME_TO_ABBR = {t['full_name']: t['abbreviation'] for t in _NFL_TEAMS}
ABBR_TO_TEAM_NAME = {t['abbreviation']: t['full_name'] for t in _NFL_TEAMS}
NICKNAME_TO_TEAM = {t['nickname']: t for t in _NFL_TEAMS}
TEAM_NAME_TO_INFO = {t['full_name']: t for t in _NFL_TEAMS}

# Dome lookup: True if team plays in a dome/retractable roof
DOME_TEAMS = {t['full_name'] for t in _NFL_TEAMS if t['dome']}

# Division lookup
DIVISION_TEAMS = {}
for t in _NFL_TEAMS:
    key = f"{t['conference']} {t['division']}"
    DIVISION_TEAMS.setdefault(key, []).append(t['full_name'])

# Common aliases (short names used in schedules/odds feeds)
NICKNAME_ALIASES = {
    'Niners': '49ers',
    'Bucs': 'Buccaneers',
    'Cards': 'Cardinals',
    'Bolts': 'Chargers',
    'Pats': 'Patriots',
    'Jags': 'Jaguars',
    'Pack': 'Packers',
    'Skins': 'Commanders',
    'Football Team': 'Commanders',
    'Redskins': 'Commanders',
}


def resolve_team_name(name_or_abbr):
    """Resolve any team identifier (full name, abbreviation, nickname, alias) to full_name."""
    if name_or_abbr in TEAM_NAME_TO_ABBR:
        return name_or_abbr
    if name_or_abbr in ABBR_TO_TEAM_NAME:
        return ABBR_TO_TEAM_NAME[name_or_abbr]
    if name_or_abbr in NICKNAME_TO_TEAM:
        return NICKNAME_TO_TEAM[name_or_abbr]['full_name']
    if name_or_abbr in NICKNAME_ALIASES:
        alias_nick = NICKNAME_ALIASES[name_or_abbr]
        if alias_nick in NICKNAME_TO_TEAM:
            return NICKNAME_TO_TEAM[alias_nick]['full_name']
    # Fuzzy: check if input is contained in any full name
    lower = name_or_abbr.lower()
    for t in _NFL_TEAMS:
        if lower in t['full_name'].lower() or lower in t['nickname'].lower():
            return t['full_name']
    return None


def is_dome_game(home_team):
    """Return True if the home stadium is a dome/retractable roof."""
    return home_team in DOME_TEAMS


def get_team_info(name_or_abbr):
    """Return full team dict for any identifier."""
    full = resolve_team_name(name_or_abbr)
    return TEAM_NAME_TO_INFO.get(full)


def same_division(team1, team2):
    """Return True if two teams are in the same division (divisional rivalry)."""
    t1 = get_team_info(team1)
    t2 = get_team_info(team2)
    if not t1 or not t2:
        return False
    return t1['conference'] == t2['conference'] and t1['division'] == t2['division']

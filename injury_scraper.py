"""
injury_scraper.py — NFL Injury Report Scraper

Fetches injury data from CBS Sports NFL injury page.
NFL injury reports follow a Wednesday → Thursday → Friday progression:
  - Wednesday: Initial injury report (estimated for Monday/Tuesday games)
  - Thursday: Updated designations
  - Friday: Final game-status designations (Out, Doubtful, Questionable, Probable)

Outputs: nfl_injuries.csv with columns: team, player, position, status, note, updated
"""

import re
import csv
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from nfl_teams_static import resolve_team_name

INJURY_URL = "https://www.cbssports.com/nfl/injuries/"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nfl_injuries.csv')

# CBS Sports abbreviated team names → full team names
CBS_TEAM_MAP = {
    "Arizona": "Arizona Cardinals",
    "Atlanta": "Atlanta Falcons",
    "Baltimore": "Baltimore Ravens",
    "Buffalo": "Buffalo Bills",
    "Carolina": "Carolina Panthers",
    "Chicago": "Chicago Bears",
    "Cincinnati": "Cincinnati Bengals",
    "Cleveland": "Cleveland Browns",
    "Dallas": "Dallas Cowboys",
    "Denver": "Denver Broncos",
    "Detroit": "Detroit Lions",
    "Green Bay": "Green Bay Packers",
    "Houston": "Houston Texans",
    "Indianapolis": "Indianapolis Colts",
    "Jacksonville": "Jacksonville Jaguars",
    "Kansas City": "Kansas City Chiefs",
    "Las Vegas": "Las Vegas Raiders",
    "L.A. Chargers": "Los Angeles Chargers",
    "LA Chargers": "Los Angeles Chargers",
    "L.A. Rams": "Los Angeles Rams",
    "LA Rams": "Los Angeles Rams",
    "Miami": "Miami Dolphins",
    "Minnesota": "Minnesota Vikings",
    "New England": "New England Patriots",
    "New Orleans": "New Orleans Saints",
    "N.Y. Giants": "New York Giants",
    "NY Giants": "New York Giants",
    "N.Y. Jets": "New York Jets",
    "NY Jets": "New York Jets",
    "Philadelphia": "Philadelphia Eagles",
    "Pittsburgh": "Pittsburgh Steelers",
    "San Francisco": "San Francisco 49ers",
    "Seattle": "Seattle Seahawks",
    "Tampa Bay": "Tampa Bay Buccaneers",
    "Tennessee": "Tennessee Titans",
    "Washington": "Washington Commanders",
}


def _clean_player_name(raw):
    """Strip concatenated name artifacts from HTML extraction."""
    if len(raw) < 4:
        return raw
    for i in range(1, len(raw)):
        candidate = raw[i:]
        if candidate[0].isupper() and ' ' in candidate and len(candidate.split()[0]) >= 2:
            return candidate
    return raw


def _load_cached_injuries():
    """Return previously cached injuries as fallback when scraping fails."""
    if not os.path.exists(OUTPUT_FILE):
        return []
    try:
        data = []
        with open(OUTPUT_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append({
                    'team': row.get('team', ''),
                    'player': row.get('player', ''),
                    'position': row.get('position', ''),
                    'status': row.get('status', ''),
                    'note': row.get('note', ''),
                    'updated': row.get('updated', ''),
                })
        if data:
            print(f"  [WARN] Using cached injury data ({len(data)} entries — may be stale)")
        return data
    except Exception:
        return []


def fetch_injury_data(url=INJURY_URL):
    """Fetch and parse NFL injury data from CBS Sports.

    Falls back to previously cached CSV data if CBS scraping fails
    (network error, HTML structure change, etc.).

    Returns list of dicts: [{team, player, position, status, note, updated}, ...]
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"  [WARN] CBS injury fetch failed ({e}). Falling back to cache.")
        return _load_cached_injuries()

    soup = BeautifulSoup(response.text, "html.parser")

    # Strategy 1: Primary CBS class-based selectors
    team_headers = soup.find_all(class_="TeamName")
    tables = soup.find_all("table", {"class": "TableBase-table"})

    # Strategy 2: Broader selectors if CBS renamed their classes
    if not team_headers or not tables:
        team_headers = soup.find_all("h4") or soup.find_all(class_=re.compile(r"[Tt]eam"))
        tables = soup.find_all("table")

    if not team_headers or not tables:
        print("  [WARN] CBS injury page structure changed — tables not found. Using cache.")
        return _load_cached_injuries()

    data = []
    now = datetime.now().isoformat()

    for team_el, table in zip(team_headers, tables):
        try:
            cbs_name = team_el.get_text(strip=True)
            team_full = CBS_TEAM_MAP.get(cbs_name, cbs_name)
            # Fallback to resolve_team_name
            if team_full == cbs_name:
                resolved = resolve_team_name(cbs_name)
                if resolved:
                    team_full = resolved

            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 3:
                    continue

                player_raw = cells[0].get_text(strip=True)
                player = _clean_player_name(player_raw)
                position = cells[1].get_text(strip=True).upper() if len(cells) > 1 else ''
                status = cells[2].get_text(strip=True) if len(cells) > 2 else ''
                note = cells[3].get_text(strip=True) if len(cells) > 3 else ''

                if player and status:
                    data.append({
                        'team': team_full,
                        'player': player,
                        'position': position,
                        'status': status,
                        'note': note,
                        'updated': now,
                    })
        except Exception:
            # Skip individual team parse errors, continue with remaining teams
            continue

    if not data:
        print("  [WARN] CBS parsed 0 injuries — page may have changed. Using cache.")
        return _load_cached_injuries()

    return data


def save_injuries(data, output_path=OUTPUT_FILE):
    """Write injury data to CSV."""
    fieldnames = ['team', 'player', 'position', 'status', 'note', 'updated']
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
    return len(data)


def main():
    print("[NFL] Fetching injury data from CBS Sports...")
    try:
        data = fetch_injury_data()
        count = save_injuries(data)
        print(f"[SUCCESS] Saved {count} injury entries to {os.path.basename(OUTPUT_FILE)}")

        # Summary by team
        teams = {}
        for d in data:
            teams.setdefault(d['team'], []).append(d)
        out_count = sum(1 for d in data if d['status'].lower() in ('out', 'injured reserve', 'ir'))
        print(f"  Teams with injuries: {len(teams)} | Total OUT/IR: {out_count}")
    except Exception as e:
        print(f"[ERROR] Failed to fetch injuries: {e}")
        return 1
    return 0


if __name__ == '__main__':
    exit(main())

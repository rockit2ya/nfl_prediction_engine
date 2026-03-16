#!/usr/bin/env python3
"""
update_results.py — Fetches final NFL scores from ESPN and updates bet tracker CSVs.

Usage:
    python update_results.py               # interactive — pick a tracker file
    python update_results.py now            # auto-update today's tracker
    python update_results.py all            # update every tracker with pending games
    python update_results.py 2026-09-07     # update tracker for a specific date
"""

import os
import sys
import glob
import re
import json
import pandas as pd
import requests
from datetime import datetime
from nfl_teams_static import resolve_team_name, NICKNAME_TO_TEAM

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _load_model_version():
    try:
        with open(os.path.join(BASE_DIR, 'model_config.json')) as f:
            return json.load(f).get('version', 'unknown')
    except Exception:
        return 'unknown'

_MODEL_VERSION = _load_model_version()

ESPN_SCOREBOARD_URL = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard'


def resolve_nickname(name):
    """Resolve team name to canonical form."""
    resolved = resolve_team_name(name)
    return resolved if resolved else name.strip()


def find_bet_tracker_files():
    pattern = os.path.join(BASE_DIR, 'bet_tracker_*.csv')
    return sorted(glob.glob(pattern), reverse=True)


def fetch_scores_for_date(date_str):
    """Fetch all final NFL game scores for a given date from ESPN."""
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    espn_date = dt.strftime('%Y%m%d')

    print(f"  Fetching scores from ESPN for {date_str}...")
    try:
        resp = requests.get(ESPN_SCOREBOARD_URL, params={'dates': espn_date}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  ❌ ESPN API Error: {e}")
        return []

    events = data.get('events', [])
    results = []

    for event in events:
        status_type = event.get('status', {}).get('type', {})
        status_name = status_type.get('name', '')
        completed = status_type.get('completed', False)

        if completed or status_name == 'STATUS_FINAL':
            status_code = 3
        elif status_name == 'STATUS_IN_PROGRESS':
            status_code = 2
        else:
            status_code = 1

        competitors = event.get('competitions', [{}])[0].get('competitors', [])
        if len(competitors) < 2:
            continue

        away = next((c for c in competitors if c.get('homeAway') == 'away'), None)
        home = next((c for c in competitors if c.get('homeAway') == 'home'), None)
        if not away or not home:
            continue

        away_score = int(away.get('score', 0)) if away.get('score') else None
        home_score = int(home.get('score', 0)) if home.get('score') else None

        results.append({
            'away_name': away['team'].get('shortDisplayName', ''),
            'home_name': home['team'].get('shortDisplayName', ''),
            'away_abbrev': away['team'].get('abbreviation', ''),
            'home_abbrev': home['team'].get('abbreviation', ''),
            'away_score': away_score,
            'home_score': home_score,
            'status': status_code,
        })

    return results


def match_game(row, scores):
    """Match a bet tracker row to an ESPN game result."""
    away_csv = resolve_nickname(row['Away'])
    home_csv = resolve_nickname(row['Home'])

    for s in scores:
        away_api = s['away_name']
        home_api = s['home_name']

        away_match = away_csv.lower() == away_api.lower() or away_csv.lower() in away_api.lower() or away_api.lower() in away_csv.lower()
        home_match = home_csv.lower() == home_api.lower() or home_csv.lower() in home_api.lower() or home_api.lower() in home_csv.lower()

        if away_match and home_match:
            return s

    return None


def determine_result(row, score):
    """Determine WIN/LOSS/PUSH based on Pick, Market spread, and final scores."""
    pick = row['Pick'].strip()
    away_name = row['Away'].strip()
    home_name = row['Home'].strip()

    away_score = score['away_score']
    home_score = score['home_score']

    if away_score is None or home_score is None:
        return 'PENDING', ''

    final_score = f"Final Score: {row['Away']} {away_score} - {row['Home']} {home_score}"
    bet_type = row.get('Type', 'Spread').strip()

    # Over/Under grading
    if bet_type == 'Over/Under':
        actual_total = away_score + home_score
        try:
            market_total = float(row['Market'])
        except (ValueError, TypeError):
            return 'PENDING', 'Could not parse Market total'
        if actual_total == market_total:
            return 'PUSH', final_score
        pick_upper = pick.upper()
        if pick_upper == 'OVER':
            covered = actual_total > market_total
        elif pick_upper == 'UNDER':
            covered = actual_total < market_total
        else:
            return 'PENDING', f"{final_score} (could not parse O/U pick '{pick}')"
        return 'WIN' if covered else 'LOSS', final_score

    # Spread / Moneyline grading
    pick_resolved = resolve_nickname(pick)
    away_resolved = resolve_nickname(away_name)
    home_resolved = resolve_nickname(home_name)

    if pick_resolved.lower() == home_resolved.lower() or pick.lower() in home_name.lower():
        actual_margin = home_score - away_score
        try:
            market = float(row['Market'])
        except (ValueError, TypeError):
            return 'PENDING', 'Could not parse Market spread'
        if actual_margin == (-market):
            return 'PUSH', final_score
        covered = actual_margin > (-market)
    elif pick_resolved.lower() == away_resolved.lower() or pick.lower() in away_name.lower():
        actual_margin = away_score - home_score
        try:
            market = float(row['Market'])
        except (ValueError, TypeError):
            return 'PENDING', 'Could not parse Market spread'
        if actual_margin == market:
            return 'PUSH', final_score
        covered = actual_margin > market
    else:
        return 'PENDING', f"{final_score} (could not match pick '{pick}' to either team)"

    return 'WIN' if covered else 'LOSS', final_score


def calc_payout(result, bet_str, odds_str):
    """Calculate payout based on result, bet amount, and American odds."""
    try:
        bet = float(str(bet_str).replace('$', '').replace(',', '').strip())
        odds = int(str(odds_str).replace('+', '').strip())
    except (ValueError, TypeError):
        return None
    if bet <= 0 or odds == 0:
        return None
    if result == 'WIN':
        if odds > 0:
            profit = bet * (odds / 100)
        else:
            profit = bet * (100 / abs(odds))
        return round(profit, 2)
    elif result == 'LOSS':
        return round(-bet, 2)
    elif result == 'PUSH':
        return 0.0
    return None


def update_tracker(filepath):
    """Load CSV, fetch scores, update results, save."""
    match = re.search(r'bet_tracker_(\d{4}-\d{2}-\d{2})\.csv', filepath)
    if not match:
        print("❌ Could not parse date from filename.")
        return
    date_str = match.group(1)

    df = pd.read_csv(filepath)

    # Ensure required columns exist
    for col in ['ClosingLine', 'CLV', 'PreflightCheck', 'PreflightNote']:
        if col not in df.columns:
            df[col] = ''

    for col in ['Notes', 'Odds', 'BetAmount', 'Payout', 'Timestamp', 'Confidence', 'Type', 'ToWin', 'ClosingLine', 'CLV']:
        if col in df.columns:
            df[col] = df[col].fillna('').astype(str)

    pending_mask = df['Result'].str.upper().str.strip() == 'PENDING'
    pending_count = pending_mask.sum()

    if pending_count == 0:
        print("  ✅ No pending games — all results already entered.")
        for _, row in df.iterrows():
            print(f"    {row['ID']}: {row['Away']} @ {row['Home']} → {row['Result']}")
        return

    print(f"  Found {pending_count} pending game(s) to update.\n")

    scores = fetch_scores_for_date(date_str)
    if not scores:
        print("  ⚠️  No game data returned from ESPN.")
        print("     Games may not have started yet, or it's a bye week.")
        return

    print(f"  Retrieved {len(scores)} game(s) from ESPN.\n")

    updated = 0
    still_pending = 0

    for idx, row in df.iterrows():
        if str(row['Result']).strip().upper() != 'PENDING':
            continue

        score = match_game(row, scores)
        if score is None:
            print(f"  ⚠️  {row['ID']}: {row['Away']} @ {row['Home']} — No matching game found")
            still_pending += 1
            continue

        if score['status'] != 3:
            status_text = {1: 'Not Started', 2: 'In Progress'}.get(score['status'], f'Status {score["status"]}')
            print(f"  ⏳ {row['ID']}: {row['Away']} @ {row['Home']} — Game {status_text}")
            still_pending += 1
            continue

        result, final_score = determine_result(row, score)
        df.at[idx, 'Result'] = result

        existing_notes = str(row.get('Notes', '')).strip()
        if existing_notes and existing_notes != 'nan':
            df.at[idx, 'Notes'] = f"{existing_notes} | {final_score}"
        else:
            df.at[idx, 'Notes'] = final_score

        # Calculate Payout
        if 'Payout' in df.columns and 'BetAmount' in df.columns and 'Odds' in df.columns:
            payout = calc_payout(result, row.get('BetAmount', ''), row.get('Odds', ''))
            if payout is not None:
                df.at[idx, 'Payout'] = f"{payout:.2f}"

        icon = '✅' if result == 'WIN' else ('🟰' if result == 'PUSH' else '❌')
        print(f"  {icon} {row['ID']}: {row['Away']} @ {row['Home']} → {result}  ({final_score})")
        updated += 1

    df.to_csv(filepath, index=False)
    print(f"\n  Summary: {updated} updated, {still_pending} still pending")
    print(f"  💾 Saved to {os.path.basename(filepath)}")


def main():
    print("\n" + "=" * 65)
    print(f"  🏈 NFL Prediction Engine — Result Updater v{_MODEL_VERSION}")
    print("=" * 65)

    # CLI arguments
    if len(sys.argv) > 1:
        arg = sys.argv[1].strip().lower()

        if arg == 'now':
            today = datetime.now().strftime('%Y-%m-%d')
            path = os.path.join(BASE_DIR, f'bet_tracker_{today}.csv')
            if not os.path.exists(path):
                print(f"\n  ❌ No tracker for today ({today}).")
                return
            update_tracker(path)
            return

        if arg == 'all':
            files = find_bet_tracker_files()
            if not files:
                print("\n  ❌ No bet tracker files found.")
                return
            for f in files:
                print(f"\n  ── Processing: {os.path.basename(f)} ──")
                update_tracker(f)
            return

        if re.match(r'^\d{4}-\d{2}-\d{2}$', arg):
            path = os.path.join(BASE_DIR, f'bet_tracker_{arg}.csv')
            if not os.path.exists(path):
                print(f"\n  ❌ No tracker for {arg}.")
                return
            update_tracker(path)
            return

    # Interactive mode
    files = find_bet_tracker_files()
    if not files:
        print("\n  ❌ No bet tracker files found.")
        return

    print("\n  Available trackers:\n")
    for i, f in enumerate(files[:15], 1):
        name = os.path.basename(f)
        try:
            df = pd.read_csv(f)
            pending = (df['Result'].str.upper().str.strip() == 'PENDING').sum()
            total = len(df)
            print(f"    [{i}] {name}  ({pending} pending / {total} total)")
        except Exception:
            print(f"    [{i}] {name}")

    print(f"\n    [A] Update ALL trackers")
    print(f"    [Q] Quit\n")

    choice = input("  Select: ").strip().upper()

    if choice == 'Q':
        return
    elif choice == 'A':
        for f in files:
            print(f"\n  ── Processing: {os.path.basename(f)} ──")
            update_tracker(f)
    else:
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(files):
                update_tracker(files[idx])
            else:
                print("  ❌ Invalid selection.")
        except ValueError:
            print("  ❌ Invalid selection.")


if __name__ == "__main__":
    main()

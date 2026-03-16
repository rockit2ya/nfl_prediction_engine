"""
nfl_engine_ui.py — NFL Prediction Engine: Interactive Terminal UI

Ported from NBA Prediction Engine v3.36 framework.
Weekly-oriented interface for NFL game analysis, bet logging, and performance tracking.
"""

import os
import csv
import glob
import json
import re
import subprocess
from datetime import datetime, timedelta, date, timezone
from nfl_analytics import (
    predict_nfl_spread, calculate_edge, determine_pick, decompose_edge,
    calculate_ecs, evaluate_guard_rails, update_fair_line_log_market,
    load_injuries, get_status_weight, is_status_out,
    MARKET_ANCHOR_WEIGHT, _gr, _p,
)
from nfl_teams_static import _NFL_TEAMS, resolve_team_name, ABBR_TO_TEAM_NAME

_TEAM_ABBR = {t['full_name']: t['abbreviation'] for t in _NFL_TEAMS}
_TEAM_ABBR_REVERSE = {v: k for k, v in _TEAM_ABBR.items()}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_model_version():
    config_path = os.path.join(BASE_DIR, 'model_config.json')
    try:
        if os.path.exists(config_path):
            with open(config_path) as f:
                return json.load(f).get('version', 'unknown')
    except Exception:
        pass
    return 'unknown'


_MODEL_VERSION = _load_model_version()


def _load_guard_rails_from_config():
    config_path = os.path.join(BASE_DIR, 'model_config.json')
    try:
        if os.path.exists(config_path):
            with open(config_path) as f:
                return json.load(f).get('guard_rails', {})
    except Exception:
        pass
    return {}


_MODEL_CONFIG_GR = _load_guard_rails_from_config()


# ── Bankroll / Kelly ──────────────────────────────────────────────────────────

def calculate_kelly(market, fair_line):
    """Conservative Quarter-Kelly bankroll sizing."""
    b = 0.91  # standard -110
    edge = abs(fair_line - market)
    prob = min(0.70, max(0.48, 0.524 + (edge * 0.015)))
    kelly_f = ((b * prob) - (1 - prob)) / b
    return round(max(0, kelly_f * 0.25) * 100, 2)


def load_bankroll_config():
    """Load bankroll config from model_config.json guard_rails with defaults."""
    defaults = {
        'edge_cap': 10,
        'min_edge': 6,
        'injury_out_threshold': 3,
        'injury_tax_threshold': 4.0,
        'market_divergence_threshold': 7,
        'max_bets_per_day': 5,
        'home_pick_edge_penalty': 1,
    }
    result = dict(defaults)
    for k in defaults:
        if k in _MODEL_CONFIG_GR:
            result[k] = _MODEL_CONFIG_GR[k]
    return result


# ── Bet Logging ───────────────────────────────────────────────────────────────

BET_TRACKER_HEADER = [
    'ID', 'Timestamp', 'Away', 'Home', 'Week',
    'Fair', 'Market', 'Edge', 'RawEdge', 'Kelly',
    'Confidence', 'Pick', 'Type', 'Sportsbook', 'Odds',
    'BetAmount', 'ToWin', 'Result', 'Payout',
    'ECS', 'ECS_Tier', 'Notes',
    'ClosingLine', 'CLV', 'PreflightCheck', 'PreflightNote',
]


def log_bet(away, home, week, fair_line, market_line, edge, raw_edge,
            kelly, confidence, pick, bet_type, sportsbook, odds,
            bet_amount, to_win, ecs_score='', ecs_tier='', notes=''):
    """Log a bet to the daily bet tracker CSV."""
    now = datetime.now()
    filename = f"bet_tracker_{now.strftime('%Y-%m-%d')}.csv"
    filepath = os.path.join(BASE_DIR, filename)

    # Generate unique ID
    existing_count = 0
    if os.path.isfile(filepath):
        with open(filepath, 'r') as f:
            existing_count = max(0, sum(1 for _ in f) - 1)
    bet_id = f"W{week}-{existing_count + 1}"

    row = [
        bet_id, now.strftime('%Y-%m-%d %H:%M:%S'),
        away, home, week,
        round(fair_line, 1), market_line, edge, raw_edge, kelly,
        confidence, pick, bet_type, sportsbook, odds,
        bet_amount, to_win, 'PENDING', '',
        ecs_score, ecs_tier, notes,
        '', '', '', '',
    ]

    write_header = not os.path.isfile(filepath)
    with open(filepath, 'a', newline='') as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(BET_TRACKER_HEADER)
        writer.writerow(row)

    return bet_id, filepath


# ── Sportsbook Picker ─────────────────────────────────────────────────────────

def _pick_sportsbook():
    """Present sportsbook selection menu."""
    books = ['DraftKings', 'FanDuel', 'BetMGM', 'Caesars', 'PointsBet',
             'BetRivers', 'Hard Rock', 'ESPN BET', 'Fanatics']
    print("     Sportsbook:")
    for i, b in enumerate(books, 1):
        print(f"       {i}. {b}")
    choice = input(f"     Pick [1-{len(books)}] or type name: ").strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(books):
            return books[idx]
    except ValueError:
        pass
    return choice if choice else books[0]


# ── Schedule Loader ───────────────────────────────────────────────────────────

SCHEDULE_CACHE_FILE = os.path.join(BASE_DIR, 'nfl_schedule_cache.json')
_schedule_cache = None


def _load_schedule_cache():
    global _schedule_cache
    if _schedule_cache is not None:
        return _schedule_cache
    if os.path.exists(SCHEDULE_CACHE_FILE):
        try:
            with open(SCHEDULE_CACHE_FILE, 'r') as f:
                _schedule_cache = json.load(f)
            return _schedule_cache
        except (json.JSONDecodeError, IOError):
            pass
    _schedule_cache = {}
    return _schedule_cache


def load_week_schedule(week):
    """Load games for a given NFL week from cache.

    Returns: list of (away, home, time_str, game_info_dict)
    """
    cache = _load_schedule_cache()
    week_key = str(week)
    entry = cache.get('weeks', {}).get(week_key, {})
    games = entry.get('games', [])
    result = []
    for g in games:
        away = resolve_team_name(g.get('away', '')) or g.get('away', '')
        home = resolve_team_name(g.get('home', '')) or g.get('home', '')
        time_str = g.get('time', '')
        info = {
            'weather': g.get('weather'),
            'home_schedule': g.get('home_schedule'),
            'away_schedule': g.get('away_schedule'),
        }
        result.append((away, home, time_str, info))
    return result


# ── Bet Tracker Display ──────────────────────────────────────────────────────

def display_bet_tracker():
    """List and display bet tracker CSVs."""
    while True:
        files = sorted(glob.glob(os.path.join(BASE_DIR, 'bet_tracker_*.csv')), reverse=True)
        if not files:
            print("\n  No bet tracker files found.")
            return

        print("\n BET TRACKERS")
        print("=" * 55)
        for i, f in enumerate(files, 1):
            fname = os.path.basename(f)
            with open(f, 'r') as fh:
                row_count = max(0, sum(1 for _ in fh) - 1)
            print(f"  {i}. {fname}  ({row_count} bet{'s' if row_count != 1 else ''})")
        print(f"  A. All trackers combined")
        print(f"  Q. Back to main menu")
        print("=" * 55)

        pick = input("Select tracker # (or A/Q): ").strip().upper()
        if not pick or pick == 'Q':
            return

        if pick == 'A':
            selected_files = files
            label = "ALL TRACKERS COMBINED"
        else:
            try:
                idx = int(pick) - 1
                if idx < 0 or idx >= len(files):
                    print("Invalid selection.")
                    continue
                selected_files = [files[idx]]
                label = os.path.basename(files[idx])
            except ValueError:
                print("Invalid selection.")
                continue

        all_rows = []
        for filepath in selected_files:
            with open(filepath, 'r', newline='') as f:
                reader = csv.reader(f)
                rows = list(reader)
            if len(rows) < 2:
                continue
            header = rows[0]
            hmap = {h.strip(): i for i, h in enumerate(header)}
            for row in rows[1:]:
                if not row:
                    continue
                r = {}
                for col_name, col_idx in hmap.items():
                    if col_idx < len(row):
                        r[col_name] = row[col_idx].strip()
                    else:
                        r[col_name] = ''
                r['_file'] = os.path.basename(filepath)
                all_rows.append(r)

        if not all_rows:
            print("\n  No bets found.")
            continue

        print(f"\n BET TRACKER: {label}")
        print("=" * 120)
        print(f"  {'ID':<10} {'Matchup':<35} {'Pick':<15} {'Edge':<7} {'ECS':<5} {'Odds':<7} {'Bet':>7} {'Result':<8} {'Payout':>8}")
        print(f"  {'-'*10} {'-'*35} {'-'*15} {'-'*7} {'-'*5} {'-'*7} {'-'*7} {'-'*8} {'-'*8}")

        total_wagered, total_payout = 0.0, 0.0
        wins, losses, pending = 0, 0, 0

        for r in all_rows:
            away = r.get('Away', '')
            home = r.get('Home', '')
            matchup = f"{_TEAM_ABBR.get(away, away[:3])} @ {_TEAM_ABBR.get(home, home[:3])}"
            pick_team = r.get('Pick', '')
            pick_abbr = _TEAM_ABBR.get(pick_team, pick_team[:3])
            market_val = r.get('Market', '')
            bet_type_abbr = {'Spread': 'SP', 'Moneyline': 'ML', 'Over/Under': 'O/U'}.get(r.get('Type', ''), 'SP')

            try:
                mv = float(market_val)
                if r.get('Type', '') == 'Spread' and pick_team == away:
                    mv = -mv
                pick_str = f"{pick_abbr} {mv:+.1f} {bet_type_abbr}"
            except (ValueError, TypeError):
                pick_str = f"{pick_abbr} {bet_type_abbr}"

            edge_str = r.get('Edge', '-')
            ecs_str = r.get('ECS', '-')
            odds_str = r.get('Odds', '-')

            try:
                bet_val = float(r.get('BetAmount', 0))
            except (ValueError, TypeError):
                bet_val = 0.0
            try:
                payout_val = float(r.get('Payout', 0))
            except (ValueError, TypeError):
                payout_val = 0.0

            total_wagered += bet_val
            total_payout += payout_val
            bet_str = f"${bet_val:.0f}" if bet_val else '-'
            payout_str = f"${payout_val:+.2f}" if r.get('Payout') else '-'

            result_raw = r.get('Result', 'PENDING')
            if result_raw == 'WIN':
                result_display = "WIN"
                wins += 1
            elif result_raw == 'LOSS':
                result_display = "LOSS"
                losses += 1
            elif result_raw == 'PUSH':
                result_display = "PUSH"
            else:
                result_display = "PEND"
                pending += 1

            notes = r.get('Notes', '')
            is_shadow = 'SHADOW:' in notes
            tag = ' [S]' if is_shadow else ''

            print(f"  {r.get('ID', ''):<10} {matchup:<35} {pick_str:<15} {edge_str:<7} {ecs_str:<5} {odds_str:<7} {bet_str:>7} {result_display:<8} {payout_str:>8}{tag}")
            if notes:
                print(f"  {' '*10} Notes: {notes}")

        print("=" * 120)
        total_bets = wins + losses + pending
        net = total_payout
        win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0
        roi = (net / total_wagered * 100) if total_wagered > 0 else 0.0
        net_icon = '+' if net >= 0 else ''
        print(f"  SUMMARY: {total_bets} bets | {wins}W-{losses}L{f'-{pending}P' if pending else ''} | WR: {win_rate:.1f}%")
        print(f"  Wagered: ${total_wagered:.0f} | Net: ${net_icon}{net:.2f} | ROI: {roi:+.1f}%")
        print("=" * 120)


# ── Game Analysis ─────────────────────────────────────────────────────────────

def analyze_game(away_team, home_team, market_line, week=0,
                  weather_data=None, home_schedule=None, away_schedule=None,
                  standings=None, interactive=True):
    """Full game analysis: predict, edge, ECS, guard rails, display.

    Returns analysis dict if not interactive, else handles bet logging.
    """
    # 1. Predict fair line
    fair_line, components = predict_nfl_spread(
        away_team, home_team, week=week,
        weather_data=weather_data,
        home_schedule=home_schedule,
        away_schedule=away_schedule,
        standings=standings,
    )

    # 2. Calculate edge
    edge, raw_edge, anchored_fair, edge_capped = calculate_edge(fair_line, market_line)

    # 3. Determine pick
    pick_side, pick_desc = determine_pick(fair_line, market_line)
    recommendation = home_team if pick_side == 'HOME' else away_team

    # 4. Kelly sizing
    kelly = calculate_kelly(market_line, fair_line)

    # 5. Edge decomposition
    edge_source, ratings_pct, injury_pct, decomp = decompose_edge(
        fair_line, market_line, components)

    # 6. ECS
    market_gap = abs(fair_line - market_line)
    gtd_count = 0
    injuries = load_injuries()
    for inj in injuries.get(recommendation, []):
        if 0 < get_status_weight(inj['status']) < 1.0:
            gtd_count += 1

    ecs_score, ecs_tier, ecs_breakdown = calculate_ecs(
        edge, raw_edge, edge_capped, components, edge_source,
        ratings_pct, injury_pct, market_gap,
        star_tax_failed=components.get('star_tax_failed', False),
        gtd_count=gtd_count,
    )

    # 7. Guard rails
    bet_type, gr_reasons, guard_rails_str = evaluate_guard_rails(
        home_team, away_team, pick_side, edge, ecs_score, components,
        market_line=market_line, fair_line=fair_line,
    )

    # 8. Confidence
    conf = 'HIGH'
    if components.get('star_tax_failed'):
        conf = 'MEDIUM (Injury data incomplete)'
    elif gtd_count >= 2:
        conf = 'LOW (High Injury Volatility)'
    elif gtd_count == 1:
        conf = 'MEDIUM'

    # Update fair line log with market context
    update_fair_line_log_market(
        away_team, home_team, market_line, edge, raw_edge, recommendation,
        guard_rails_str, edge_source, ratings_pct, injury_pct,
        ecs_score, ecs_tier,
    )

    # ── Display ──
    h_abbr = _TEAM_ABBR.get(home_team, home_team[:3])
    a_abbr = _TEAM_ABBR.get(away_team, away_team[:3])

    print("\n" + "=" * 60)
    print(f"  NFL PRO ENGINE — {a_abbr} @ {h_abbr} | Week {week}")
    print("=" * 60)

    print(f"\n  RAW MODEL LINE:   {fair_line}")
    print(f"  ANCHORED LINE:    {anchored_fair}  ({int((1-MARKET_ANCHOR_WEIGHT)*100)}% model / {int(MARKET_ANCHOR_WEIGHT*100)}% market)")
    print(f"  MARKET SPREAD:    {market_line}")
    if edge_capped:
        print(f"  CALCULATED EDGE:  {edge} pts (capped from {raw_edge})")
    else:
        print(f"  CALCULATED EDGE:  {edge} pts")
    print(f"  KELLY SUGGESTION: Risk {kelly}% of Bankroll")
    print(f"  CONFIDENCE:       {conf}")

    # ── Edge Decomposition ──
    print(f"\n  EDGE DECOMPOSITION:")
    print(f"     Ratings gap    {decomp.get('ratings_contrib', 0):>+6.1f} pts  ({decomp.get('ratings_pct', 0):4.0f}%)")
    print(f"     Injury impact  {decomp.get('injury_contrib', 0):>+6.1f} pts  ({decomp.get('injury_pct', 0):4.0f}%)")
    print(f"     Schedule adj   {decomp.get('schedule_contrib', 0):>+6.1f} pts")
    print(f"     Weather adj    {decomp.get('weather_contrib', 0):>+6.1f} pts")
    print(f"     SOS adjust     {decomp.get('sos_contrib', 0):>+6.1f} pts")
    print(f"     Motivation     {decomp.get('motivation_contrib', 0):>+6.1f} pts")
    src_icon = '!' if edge_source == 'RATINGS-DRIVEN' else '+' if edge_source == 'SITUATIONAL' else '~'
    print(f"     [{src_icon}] {edge_source}")

    # ── Key injuries ──
    for side, team in [('HOME', home_team), ('AWAY', away_team)]:
        team_inj = injuries.get(team, [])
        key_inj = [i for i in team_inj if get_status_weight(i['status']) >= 0.5]
        if key_inj:
            abbr = _TEAM_ABBR.get(team, team[:3])
            print(f"\n  {side} INJURIES ({abbr}):")
            for inj in key_inj:
                status_tag = 'OUT' if is_status_out(inj['status']) else inj['status'].upper()
                print(f"     [{status_tag}] {inj['player']} ({inj['position']})")

    # QB status highlight
    if components.get('h_qb_out'):
        print(f"\n  QB ALERT: {home_team} QB {components['h_qb_out']} is OUT")
    if components.get('a_qb_out'):
        print(f"\n  QB ALERT: {away_team} QB {components['a_qb_out']} is OUT")

    # Weather
    if weather_data and not components.get('weather_adj', 0) == 0:
        w = weather_data
        print(f"\n  WEATHER: {w.get('temp_f', '?')}F, Wind {w.get('wind_mph', '?')} mph"
              f"{', Rain/Snow' if w.get('precipitation') else ''}")
        print(f"     Weather adjustment: {components.get('weather_adj', 0):+.1f} pts")

    # Divisional
    if components.get('divisional'):
        print(f"\n  DIVISIONAL GAME: Spread dampened by {(1-_p('DIVISIONAL_RIVALRY_DAMPENER', 0.85))*100:.0f}%")

    # ── ECS ──
    print(f"\n  EDGE CONFIDENCE SCORE: {ecs_score}/100 — {ecs_tier}")
    for b in ecs_breakdown:
        print(f"     * {b}")

    # ── Guard Rails ──
    if guard_rails_str != 'CLEAR':
        print(f"\n  GUARD RAILS: {guard_rails_str}")
    else:
        print(f"\n  GUARD RAILS: CLEAR")

    # ── Recommendation ──
    print("\n" + "-" * 60)
    rec_abbr = _TEAM_ABBR.get(recommendation, recommendation)
    if bet_type == 'SHADOW':
        print(f"  SHADOW BET: {rec_abbr} ({pick_desc})")
        print(f"  Logging as shadow ($0) due to: {', '.join(gr_reasons)}")
    elif edge >= 5 and 'HIGH' in conf:
        print(f"  STRONG SIGNAL: Bet {rec_abbr}")
    elif edge >= 3:
        print(f"  LEAN: {rec_abbr} (moderate edge)")
    else:
        print(f"  LOW EDGE: {rec_abbr} (thin margin)")
    print("-" * 60)

    if not interactive:
        return {
            'fair_line': fair_line, 'market_line': market_line,
            'edge': edge, 'raw_edge': raw_edge, 'pick': recommendation,
            'pick_side': pick_side, 'kelly': kelly, 'ecs': ecs_score,
            'ecs_tier': ecs_tier, 'bet_type': bet_type,
            'guard_rails': guard_rails_str, 'components': components,
        }

    # ── Bet Logging ──
    print("\n  LOG THIS BET?")
    if bet_type == 'SHADOW':
        log_choice = input("  Shadow bet — log as $0? (Y/N) [Y]: ").strip().upper()
        if log_choice == 'N':
            # Override: user wants to bet despite shadow
            override = input("  Override shadow and place real bet? (Y/N) [N]: ").strip().upper()
            if override != 'Y':
                print("  Bet not logged.")
                return
            bet_type = 'REAL'
            notes_extra = f"SHADOW_OVERRIDE | {guard_rails_str}"
        else:
            bet_amount = 0.0
            to_win = 0.0
            sportsbook = '-'
            odds = '-110'
            notes_str = f"SHADOW: {', '.join(gr_reasons)}"
            bet_id, fpath = log_bet(
                away_team, home_team, week, fair_line, market_line,
                edge, raw_edge, kelly, conf, recommendation,
                'Spread', sportsbook, odds, bet_amount, to_win,
                ecs_score, ecs_tier, notes_str,
            )
            print(f"  Shadow bet logged: {bet_id} in {os.path.basename(fpath)}")
            return
    else:
        notes_extra = ''

    log_choice = input("  Place bet? (Y/N) [Y]: ").strip().upper()
    if log_choice == 'N':
        print("  Bet not logged.")
        return

    sportsbook = _pick_sportsbook()
    odds_in = input("  Odds (e.g., -110): ").strip() or '-110'
    bet_amount_in = input("  Bet amount ($): ").strip()
    try:
        bet_amount = float(bet_amount_in)
    except (ValueError, TypeError):
        bet_amount = 0.0

    # Calculate to_win from American odds
    try:
        odds_val = int(odds_in)
        if odds_val > 0:
            to_win = round(bet_amount * (odds_val / 100), 2)
        else:
            to_win = round(bet_amount * (100 / abs(odds_val)), 2)
    except (ValueError, TypeError):
        to_win = 0.0

    notes_str = notes_extra if notes_extra else ''

    bet_id, fpath = log_bet(
        away_team, home_team, week, fair_line, market_line,
        edge, raw_edge, kelly, conf, recommendation,
        'Spread', sportsbook, odds_in, bet_amount, to_win,
        ecs_score, ecs_tier, notes_str,
    )
    print(f"  Bet logged: {bet_id} — ${bet_amount:.0f} on {rec_abbr} at {sportsbook}")
    print(f"  Tracker: {os.path.basename(fpath)}")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN UI LOOP
# ══════════════════════════════════════════════════════════════════════════════

def run_ui():
    """Main interactive loop."""
    today_display = datetime.now().strftime("%B %d, %Y")
    custom_counter = 0

    print("\n[SYSTEM] Initializing NFL Pro Analytics Engine...")

    try:
        while True:
            print("\n" + "=" * 75)
            print(f"--- NFL PRO ENGINE v{_MODEL_VERSION} | {today_display} ---")

            # Show cache freshness
            print("--- DATA CACHE FRESHNESS ---")
            cache_files = {
                'Team Stats': 'nfl_stats_cache.json',
                'Recent Form': 'nfl_stats_recent_cache.json',
                'Injuries': 'nfl_injuries.csv',
                'Schedule': 'nfl_schedule_cache.json',
                'Weather': 'nfl_weather_cache.json',
                'Odds': 'nfl_odds_cache.json',
                'SOS': 'nfl_sos_cache.json',
            }
            for label, fname in cache_files.items():
                fpath = os.path.join(BASE_DIR, fname)
                if os.path.exists(fpath):
                    mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
                    age_hrs = (datetime.now() - mtime).total_seconds() / 3600
                    if age_hrs < 1:
                        ts = f"{int(age_hrs * 60)}m ago"
                    elif age_hrs < 24:
                        ts = f"{age_hrs:.1f}h ago"
                    else:
                        ts = f"{age_hrs / 24:.1f}d ago"
                    stale_tag = " [STALE]" if age_hrs > 24 else ""
                    print(f"  {label + ':':<14} {ts}{stale_tag}")
                else:
                    print(f"  {label + ':':<14} Not found")

            print("=" * 75)

            # ── Week Input ──
            week_input = input("\nEnter NFL week # (1-18, or P for playoffs) [or press Enter to skip]: ").strip()
            if week_input.upper() == 'P':
                week = 19  # playoff marker
            elif week_input:
                try:
                    week = int(week_input)
                except ValueError:
                    week = 0
            else:
                week = 0

            # ── Load schedule if available ──
            schedule = {}
            if week > 0:
                games = load_week_schedule(week)
                if games:
                    print(f"\n NFL Week {week} Schedule:")
                    print("-" * 70)
                    for i, (away, home, time_str, info) in enumerate(games):
                        gid = f"G{i+1}"
                        schedule[gid] = (away, home, info)
                        a_abbr = _TEAM_ABBR.get(away, away[:3])
                        h_abbr = _TEAM_ABBR.get(home, home[:3])
                        weather_tag = ''
                        if info.get('weather'):
                            w = info['weather']
                            weather_tag = f" | {w.get('temp_f', '?')}F, Wind {w.get('wind_mph', '?')}mph"
                        print(f"  {gid:<4} {a_abbr:<5} @ {h_abbr:<5}  {time_str}{weather_tag}")
                    print("-" * 70)
                else:
                    print(f"  No schedule data for Week {week}. Use [C] for custom matchup.")

            print("\nCOMMANDS: [G#] (Analyze game) | [C] (Custom matchup) | [B] (Bet tracker)")
            print("          [D] (Refresh data) | [M] (Post-mortem) | [Q] (Quit)")
            choice = input("Enter Command: ").strip().upper()

            if choice == 'Q':
                print("Shutting down. Good luck!")
                break

            elif choice == 'B':
                display_bet_tracker()
                continue

            elif choice == 'D':
                print("\n Refreshing data...")
                fetch_script = os.path.join(BASE_DIR, 'fetch_all_nfl_data.sh')
                if os.path.exists(fetch_script):
                    result = subprocess.run(['bash', fetch_script],
                                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            text=True)
                    for line in result.stdout.splitlines():
                        print(line)
                else:
                    print("  fetch_all_nfl_data.sh not found. Create it to enable auto-refresh.")
                continue

            elif choice == 'M':
                print("\n Launching Post-Mortem...")
                pm_script = os.path.join(BASE_DIR, 'post_mortem.py')
                if os.path.exists(pm_script):
                    subprocess.run(['python', pm_script])
                else:
                    print("  post_mortem.py not found yet.")
                continue

            elif choice == 'C' or choice in schedule:
                if choice == 'C':
                    custom_counter += 1
                    away_input = input("Enter Away Team: ").strip()
                    home_input = input("Enter Home Team: ").strip()
                    away = resolve_team_name(away_input) or away_input
                    home = resolve_team_name(home_input) or home_input
                    game_info = {}
                elif choice in schedule:
                    away, home, game_info = schedule[choice]
                else:
                    print("Command not recognized.")
                    continue

                a_abbr = _TEAM_ABBR.get(away, away[:3])
                h_abbr = _TEAM_ABBR.get(home, home[:3])
                print(f"\n[ANALYZING] {a_abbr} @ {h_abbr}")

                line_in = input(f"Market Line for {h_abbr} (e.g., -3.5): ").strip()
                if not line_in:
                    print("No market line entered.")
                    continue
                try:
                    market = float(line_in)
                except ValueError:
                    print(f"Invalid market line '{line_in}'.")
                    continue

                # Weather input (if not from cache)
                weather_data = game_info.get('weather')
                if not weather_data:
                    from nfl_teams_static import is_dome_game as _is_dome
                    if not _is_dome(home):
                        weather_in = input("Weather? (wind_mph,temp_f,precip Y/N) [skip]: ").strip()
                        if weather_in:
                            parts = weather_in.split(',')
                            if len(parts) >= 3:
                                try:
                                    weather_data = {
                                        'wind_mph': int(parts[0].strip()),
                                        'temp_f': int(parts[1].strip()),
                                        'precipitation': parts[2].strip().upper().startswith('Y'),
                                    }
                                except (ValueError, IndexError):
                                    pass

                # Schedule context
                home_sched = game_info.get('home_schedule')
                away_sched = game_info.get('away_schedule')
                if not home_sched:
                    bye_q = input(f"Is {h_abbr} coming off bye? (Y/N) [N]: ").strip().upper()
                    short_q = input(f"Is {h_abbr} on short week? (Y/N) [N]: ").strip().upper()
                    home_sched = {'bye_week': bye_q == 'Y', 'short_week': short_q == 'Y'}
                if not away_sched:
                    bye_q = input(f"Is {a_abbr} coming off bye? (Y/N) [N]: ").strip().upper()
                    short_q = input(f"Is {a_abbr} on short week? (Y/N) [N]: ").strip().upper()
                    away_sched = {'bye_week': bye_q == 'Y', 'short_week': short_q == 'Y'}

                analyze_game(
                    away, home, market,
                    week=week,
                    weather_data=weather_data,
                    home_schedule=home_sched,
                    away_schedule=away_sched,
                    standings=None,
                    interactive=True,
                )
            else:
                print("Command not recognized. Try G#, C, B, D, M, or Q.")

    except KeyboardInterrupt:
        print("\n\nShutting down. Good luck!")
    except EOFError:
        print("\n\nExiting.")


if __name__ == '__main__':
    run_ui()

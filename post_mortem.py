#!/usr/bin/env python3
"""
post_mortem.py — NFL Prediction Engine Performance Analyzer

Provides single-day post-mortems and lifetime performance dashboards
to determine whether the prediction model is pro-level.

Pro Benchmark: > 52.4% ATS win rate (break-even at -110 vig)

Usage:
    python post_mortem.py               # interactive menu
    python post_mortem.py 2026-09-07    # single-day post-mortem for a specific date
"""

import pandas as pd
import glob
import os
import re
import sys
import json
from datetime import datetime

def _load_model_version():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'model_config.json')) as f:
            return json.load(f).get('version', 'unknown')
    except Exception:
        return 'unknown'

_MODEL_VERSION = _load_model_version()

try:
    from odds_api import get_consensus_spread
    HAS_ODDS_API = True
except ImportError:
    HAS_ODDS_API = False

# ─── Constants ────────────────────────────────────────────────────────────────
BREAKEVEN_RATE = 0.524          # ATS break-even at -110 odds
VIG = -110                      # Standard juice
HIGH_SIGNAL_EDGE = 4            # NFL edges are tighter; 4+ is high-signal
DEFAULT_EDGE_CAP = 10

INJURY_FILE = "nfl_injuries.csv"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _is_pure_shadow(notes_str):
    """Return True if the notes indicate a pure shadow bet (not an override)."""
    return 'SHADOW:' in notes_str and 'SHADOW_OVERRIDE' not in notes_str

def _is_shadow_override(notes_str):
    return 'SHADOW_OVERRIDE' in notes_str

def _pure_shadow_mask(df):
    if 'Notes' not in df.columns:
        return pd.Series(False, index=df.index)
    return df['Notes'].astype(str).apply(_is_pure_shadow)

def _override_mask(df):
    if 'Notes' not in df.columns:
        return pd.Series(False, index=df.index)
    return df['Notes'].astype(str).apply(_is_shadow_override)

def _is_fade(notes_str):
    return 'FADE' in notes_str.upper()

def _fade_mask(df):
    if 'Notes' not in df.columns:
        return pd.Series(False, index=df.index)
    return df['Notes'].astype(str).apply(_is_fade)


def names_match(a, b):
    """Fuzzy team name matching (handles nicknames vs full names)."""
    a = a.strip().lower()
    b = b.strip().lower()
    if a == b:
        return True
    # Check if one contains the other
    return a in b or b in a


def load_edge_cap():
    try:
        path = os.path.join(BASE_DIR, 'model_config.json')
        with open(path) as f:
            cfg = json.load(f)
        return cfg.get('guard_rails', {}).get('edge_cap', DEFAULT_EDGE_CAP)
    except Exception:
        return DEFAULT_EDGE_CAP


def get_raw_edge(row):
    """Get the raw (uncapped) edge for a bet row."""
    notes = str(row.get('Notes', ''))
    match = re.search(r'RawEdge[=:]?\s*([\d.]+)', notes)
    if match:
        return float(match.group(1))
    try:
        return abs(float(row.get('RawEdge', row.get('Edge', 0))))
    except (ValueError, TypeError):
        try:
            return abs(float(row.get('Edge', 0)))
        except (ValueError, TypeError):
            return 0.0


def is_edge_capped(row, edge_cap=None):
    if edge_cap is None:
        edge_cap = load_edge_cap()
    raw = get_raw_edge(row)
    try:
        displayed = abs(float(row.get('Edge', 0)))
    except (ValueError, TypeError):
        return False
    return raw > edge_cap and displayed <= edge_cap


def build_edge_tiers(edge_cap=None):
    if edge_cap is None:
        edge_cap = load_edge_cap()
    tiers = [(0, 3), (3, HIGH_SIGNAL_EDGE), (HIGH_SIGNAL_EDGE, edge_cap), (edge_cap, float('inf'))]
    labels = [f'0–{3}', f'{3}–{HIGH_SIGNAL_EDGE}', f'{HIGH_SIGNAL_EDGE}–{int(edge_cap)}', f'{int(edge_cap)}+']
    return tiers, labels


def load_all_trackers():
    pattern = os.path.join(BASE_DIR, 'bet_tracker_*.csv')
    files = sorted(glob.glob(pattern))
    if not files:
        return pd.DataFrame()
    frames = []
    for f in files:
        try:
            df = pd.read_csv(f)
            match = re.search(r'bet_tracker_(\d{4}-\d{2}-\d{2})\.csv', f)
            if match:
                df['Date'] = match.group(1)
            frames.append(df)
        except Exception:
            continue
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_tracker(date_str):
    path = os.path.join(BASE_DIR, f'bet_tracker_{date_str}.csv')
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    df['Date'] = date_str
    return df


def load_injuries():
    path = os.path.join(BASE_DIR, INJURY_FILE)
    if os.path.exists(path):
        try:
            return pd.read_csv(path)
        except Exception:
            pass
    return None


def parse_margin(row):
    """Parse the margin from Notes (Final Score: AWAY XX - HOME YY)."""
    notes = str(row.get('Notes', ''))
    match = re.search(r'Final Score:.*?(\d+)\s*-\s*(\d+)', notes)
    if not match:
        return None
    s1, s2 = int(match.group(1)), int(match.group(2))
    pick = str(row.get('Pick', '')).strip()
    away = str(row.get('Away', '')).strip()
    try:
        market = float(row.get('Market', 0))
    except (ValueError, TypeError):
        market = 0
    if names_match(pick, away):
        actual_margin = s1 - s2
    else:
        actual_margin = s2 - s1
    return int(actual_margin + market)


def parse_home_spread(row):
    """Parse the actual home-team spread from a final score."""
    notes = str(row.get('Notes', ''))
    match = re.search(r'Final Score:.*?(\d+)\s*-\s*(\d+)', notes)
    if not match:
        return None
    s1, s2 = int(match.group(1)), int(match.group(2))
    # s1 = away score, s2 = home score → home spread = -(home - away)
    return -(s2 - s1)


def calc_units(row):
    """Calculate unit P/L: +1 for WIN, -1.1 for LOSS, 0 for PUSH."""
    result = str(row.get('Result', '')).strip().upper()
    if result == 'WIN':
        return 1.0
    elif result == 'LOSS':
        return -1.1
    return 0.0


def calc_real_dollars(row):
    """Calculate real dollar P/L from Bet/Odds/Result columns."""
    result = str(row.get('Result', '')).strip().upper()
    try:
        bet = float(str(row.get('BetAmount', row.get('Bet', 0))).replace('$', '').replace(',', '').strip())
        odds = int(str(row.get('Odds', 0)).replace('+', '').strip())
    except (ValueError, TypeError):
        return None
    if bet <= 0 or odds == 0:
        return None
    if result == 'WIN':
        if odds > 0:
            return round(bet * (odds / 100), 2)
        else:
            return round(bet * (100 / abs(odds)), 2)
    elif result == 'LOSS':
        return round(-bet, 2)
    elif result == 'PUSH':
        return 0.0
    return None


def has_bet_data(df):
    for col in ['BetAmount', 'Bet']:
        if col in df.columns:
            vals = df[col].astype(str).str.replace('$', '', regex=False).str.replace(',', '', regex=False).str.strip()
            if pd.to_numeric(vals, errors='coerce').dropna().sum() > 0:
                return True
    return False


def calc_kelly_units(row):
    """Calculate Kelly-sized unit P/L (bet size = Kelly fraction * 1 unit)."""
    try:
        kelly = float(row.get('Kelly', 0))
    except (ValueError, TypeError):
        kelly = 0
    if kelly <= 0:
        return calc_units(row) * 0.01  # minimum 1% of a unit
    return calc_units(row) * kelly


def filter_completed(df):
    return df[df['Result'].astype(str).str.upper().str.strip().isin(['WIN', 'LOSS', 'PUSH'])]


def filter_high_signal(df):
    edges = pd.to_numeric(df['Edge'], errors='coerce').fillna(0)
    return df[edges >= HIGH_SIGNAL_EDGE]


def header(title, width=65):
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)

def section(title, width=65):
    print(f"\n  {'─' * (width - 4)}")
    print(f"  {title}")
    print(f"  {'─' * (width - 4)}")


def grade_win_rate(rate, n):
    if n < 10:
        return "⚠️  Small sample — need 10+ bets"
    if rate >= 0.58:
        return "🏆 Elite (58%+)"
    elif rate >= 0.55:
        return "🔥 Pro-Level (55%+)"
    elif rate >= BREAKEVEN_RATE:
        return "✅ Profitable (> 52.4%)"
    elif rate >= 0.50:
        return "⚠️  Above .500 but below vig"
    else:
        return "🔴 Below .500"


# ═══════════════════════════════════════════════════════════════════════════════
#  1. DAILY POST-MORTEM
# ═══════════════════════════════════════════════════════════════════════════════

def daily_post_mortem(date_str):
    """Analyze a single day's bet tracker with loss/win pattern analysis."""
    df = load_tracker(date_str)
    if df is None:
        print(f"  ❌ File not found: bet_tracker_{date_str}.csv")
        return

    completed = filter_completed(df)
    shadow_mask = _pure_shadow_mask(completed)
    override_mask_v = _override_mask(completed)
    fade_mask_v = _fade_mask(completed)
    shadow_bets = completed[shadow_mask]
    override_bets = completed[override_mask_v]
    fade_bets = completed[fade_mask_v]
    real_bets = completed[~shadow_mask]
    high = filter_high_signal(real_bets)
    all_wins = real_bets[real_bets['Result'] == 'WIN']
    all_losses = real_bets[real_bets['Result'] == 'LOSS']
    all_pushes = real_bets[real_bets['Result'] == 'PUSH']
    pending = df[df['Result'] == 'PENDING']

    header(f"📅 Daily Post-Mortem: {date_str}")

    shadow_note = f"  (+ {len(shadow_bets)} shadow)" if not shadow_bets.empty else ""
    print(f"\n  Total bets logged:    {len(df)}")
    print(f"  Completed (real):     {len(real_bets)}{shadow_note}  (Pending: {len(pending)})")
    print(f"  Wins: {len(all_wins)} | Losses: {len(all_losses)} | Pushes: {len(all_pushes)}")

    if len(real_bets) > 0:
        decided = len(all_wins) + len(all_losses)
        day_rate = len(all_wins) / decided if decided > 0 else 0
        day_units = real_bets.apply(calc_units, axis=1).sum()
        print(f"  Win Rate (real):      {day_rate:.1%}")
        print(f"  Day P/L:              {day_units:+.1f} units")

        if has_bet_data(real_bets):
            real_copy = real_bets.copy()
            real_copy['RealPL'] = real_copy.apply(calc_real_dollars, axis=1)
            tracked = real_copy.dropna(subset=['RealPL'])
            if not tracked.empty:
                day_pl = tracked['RealPL'].sum()
                print(f"  Day P/L (real $):     ${day_pl:+,.2f}")

    # High-signal breakdown
    if not high.empty:
        hw = high[high['Result'] == 'WIN']
        hl = high[high['Result'] == 'LOSS']
        section(f"High-Signal Bets (Edge ≥ {HIGH_SIGNAL_EDGE})")
        print(f"  Count: {len(high)}  |  Wins: {len(hw)}  |  Losses: {len(hl)}")
        if (len(hw) + len(hl)) > 0:
            print(f"  Win Rate: {len(hw)/(len(hw)+len(hl)):.1%}")

    # Shadow bet analysis
    if not shadow_bets.empty:
        section("Shadow Bet Analysis (Guard-Rail Validation)")
        sw = shadow_bets[shadow_bets['Result'] == 'WIN']
        sl = shadow_bets[shadow_bets['Result'] == 'LOSS']
        sd = len(sw) + len(sl)
        sr = len(sw) / sd if sd > 0 else 0
        print(f"  Shadow bets:  {len(shadow_bets)}  |  Wins: {len(sw)}  |  Losses: {len(sl)}")
        print(f"  Shadow Win Rate: {sr:.1%}")
        if sr < BREAKEVEN_RATE:
            print(f"  ✅ Guard rails VALIDATED — shadow bets losing (below {BREAKEVEN_RATE:.1%} break-even)")
        else:
            print(f"  ⚠️  Shadow bets are actually WINNING — consider relaxing guard-rail thresholds")

        for _, row in shadow_bets.iterrows():
            notes = str(row.get('Notes', ''))
            margin = parse_margin(row)
            icon = '✅' if row['Result'] == 'WIN' else '❌'
            margin_str = f"Margin: {margin}" if margin is not None else ""
            print(f"  {icon} {row['Away']} @ {row['Home']} | Pick: {row['Pick']} | Edge: {row['Edge']} | {row['Result']} {margin_str}")

    # Loss analysis
    real_losses = real_bets[real_bets['Result'] == 'LOSS']
    injuries = load_injuries()
    if not real_losses.empty:
        section("Loss Analysis")
        edge_cap = load_edge_cap()
        for _, row in real_losses.iterrows():
            margin = parse_margin(row)
            raw = get_raw_edge(row)
            capped = is_edge_capped(row, edge_cap)
            cap_tag = f" ⚠️ CAPPED (raw: {raw})" if capped else ""
            print(f"  ❌ {row['Away']} @ {row['Home']} | Pick: {row['Pick']} | Edge: {row['Edge']}{cap_tag}")
            if margin is not None:
                print(f"     Margin: {margin}")
            if injuries is not None:
                team_inj = injuries[injuries['team'].apply(lambda t: names_match(t, str(row['Pick'])))]
                if not team_inj.empty:
                    for _, inj in team_inj.iterrows():
                        print(f"     🏥 {inj['player']} ({inj['position']}) — {inj.get('status', 'Unknown')}")

    # Win analysis
    real_wins = real_bets[real_bets['Result'] == 'WIN']
    if not real_wins.empty:
        section("Win Analysis")
        for _, row in real_wins.iterrows():
            margin = parse_margin(row)
            print(f"  ✅ {row['Away']} @ {row['Home']} | Pick: {row['Pick']} | Edge: {row['Edge']}")
            if margin is not None:
                print(f"     Margin: {margin:+d}")

    # Fair Line Accuracy (MAE)
    _mae_all = pd.concat([real_bets, shadow_bets]) if not shadow_bets.empty else real_bets
    _mae_data = []
    for _, row in _mae_all.iterrows():
        actual_spread = parse_home_spread(row)
        try:
            fair = float(row['Fair'])
        except (ValueError, TypeError):
            continue
        if actual_spread is not None:
            _mae_data.append({'fair': fair, 'actual': actual_spread,
                              'abs_error': abs(fair - actual_spread)})
    if _mae_data:
        _mae_df = pd.DataFrame(_mae_data)
        section("🎯 Fair Line Accuracy")
        all_mae = _mae_df['abs_error'].mean()
        print(f"  All bets (n={len(_mae_df)}):  MAE = {all_mae:.1f} pts")


# ═══════════════════════════════════════════════════════════════════════════════
#  2. LIFETIME PERFORMANCE DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

def lifetime_dashboard():
    """Aggregate all-time performance across all bet trackers."""
    df = load_all_trackers()
    if df.empty:
        print("  ❌ No bet tracker files found.")
        return

    completed_all = filter_completed(df)
    if completed_all.empty:
        print("  ❌ No completed bets found (all PENDING).")
        return

    shadow_mask = _pure_shadow_mask(completed_all)
    shadow_bets = completed_all[shadow_mask]
    completed = completed_all[~shadow_mask]

    wins = completed[completed['Result'] == 'WIN']
    losses = completed[completed['Result'] == 'LOSS']
    pushes = completed[completed['Result'] == 'PUSH']
    pending = df[df['Result'] == 'PENDING']
    dates = sorted(completed['Date'].unique()) if not completed.empty else []

    header("🏆 LIFETIME PERFORMANCE DASHBOARD")

    section("Overview")
    total = len(completed)
    decided = len(wins) + len(losses)
    win_rate = len(wins) / decided if decided > 0 else 0
    total_units = completed.apply(calc_units, axis=1).sum()
    roi = (total_units / (decided * 1.1)) * 100 if decided > 0 else 0

    if dates:
        print(f"  Date Range:      {dates[0]} → {dates[-1]}  ({len(dates)} day(s))")
    shadow_note = f", Shadow: {len(shadow_bets)}" if not shadow_bets.empty else ""
    print(f"  Total Bets:      {len(df)}  (Completed: {total}{shadow_note}, Pending: {len(pending)})")
    print(f"  Record:          {len(wins)}W - {len(losses)}L - {len(pushes)}P")
    print(f"  Win Rate:        {win_rate:.1%}  (Break-even: {BREAKEVEN_RATE:.1%})")
    print(f"  Grade:           {grade_win_rate(win_rate, total)}")
    print(f"  Total P/L:       {total_units:+.1f} units")
    print(f"  ROI:             {roi:+.1f}%")

    # Real Dollar P/L
    if has_bet_data(completed):
        completed_copy = completed.copy()
        completed_copy['RealPL'] = completed_copy.apply(calc_real_dollars, axis=1)
        tracked = completed_copy.dropna(subset=['RealPL'])
        if not tracked.empty:
            total_wagered = tracked['BetAmount'].apply(
                lambda x: float(str(x).replace('$','').replace(',','').strip())
            ).sum() if 'BetAmount' in tracked.columns else 0
            total_pl = tracked['RealPL'].sum()
            real_roi = (total_pl / total_wagered * 100) if total_wagered > 0 else 0
            section("💰 Real Money P/L")
            print(f"  Tracked Bets:    {len(tracked)} of {total} completed")
            print(f"  Total Wagered:   ${total_wagered:,.2f}")
            print(f"  Net P/L:         ${total_pl:+,.2f}")
            print(f"  ROI:             {real_roi:+.1f}%")

    # High-Signal Only
    high = filter_high_signal(completed)
    if not high.empty:
        hw = high[high['Result'] == 'WIN']
        hl = high[high['Result'] == 'LOSS']
        high_decided = len(hw) + len(hl)
        high_rate = len(hw) / high_decided if high_decided > 0 else 0
        high_units = high.apply(calc_units, axis=1).sum()
        section(f"High-Signal Bets (Edge ≥ {HIGH_SIGNAL_EDGE})")
        print(f"  Record:          {len(hw)}W - {len(hl)}L")
        print(f"  Win Rate:        {high_rate:.1%}")
        print(f"  Grade:           {grade_win_rate(high_rate, len(high))}")
        print(f"  P/L:             {high_units:+.1f} units")

    # Edge Calibration
    EDGE_TIERS, EDGE_TIER_LABELS = build_edge_tiers()
    section("Edge Calibration (do bigger edges win more?)")
    print(f"  {'Tier':<10} {'Record':<12} {'Win Rate':<12} {'P/L':<10} {'Verdict'}")
    print(f"  {'─'*10} {'─'*12} {'─'*12} {'─'*10} {'─'*15}")

    calibration_ok = True
    prev_rate = None
    completed_cal = completed.copy()
    completed_cal['_RawEdge'] = completed_cal.apply(get_raw_edge, axis=1)
    for (lo, hi_bound), label in zip(EDGE_TIERS, EDGE_TIER_LABELS):
        tier = completed_cal[(completed_cal['_RawEdge'] >= lo) & (completed_cal['_RawEdge'] < hi_bound)]
        if tier.empty:
            print(f"  {label:<10} {'—':<12} {'—':<12} {'—':<10} No data")
            continue
        tw = tier[tier['Result'] == 'WIN']
        tl = tier[tier['Result'] == 'LOSS']
        tier_decided = len(tw) + len(tl)
        tr = len(tw) / tier_decided if tier_decided > 0 else 0
        tu = tier.apply(calc_units, axis=1).sum()
        verdict = "✅" if tr >= BREAKEVEN_RATE else "⚠️"
        if prev_rate is not None and tr < prev_rate:
            verdict = "🔻 Inverted"
            calibration_ok = False
        print(f"  {label:<10} {f'{len(tw)}W-{len(tl)}L':<12} {tr:.1%}{'':<7} {tu:+.1f}{'':<5} {verdict}")
        prev_rate = tr

    if calibration_ok and len(EDGE_TIERS) >= 2:
        print("  ✅ Calibration: Higher edges are winning at higher rates.")
    else:
        print("  ⚠️  Calibration issue detected — review edge calculations.")

    # Streak & Drawdown
    section("Streaks & Drawdown")
    results_seq = completed.sort_values('Date').apply(calc_units, axis=1).tolist()
    result_labels = completed.sort_values('Date')['Result'].tolist()

    if result_labels:
        current = result_labels[-1]
        streak = 0
        for r in reversed(result_labels):
            if r == current:
                streak += 1
            else:
                break
        streak_icon = '🔥' if current == 'WIN' else '🧊'
        print(f"  Current Streak:     {streak_icon} {streak} {current}(S)")

    max_w_streak = max_l_streak = cur_w = cur_l = 0
    for r in result_labels:
        if r == 'WIN':
            cur_w += 1; cur_l = 0
        elif r == 'LOSS':
            cur_l += 1; cur_w = 0
        max_w_streak = max(max_w_streak, cur_w)
        max_l_streak = max(max_l_streak, cur_l)
    print(f"  Best Win Streak:    {max_w_streak}")
    print(f"  Worst Loss Streak:  {max_l_streak}")

    cumulative = []
    running = 0
    for u in results_seq:
        running += u
        cumulative.append(running)
    if cumulative:
        peak = cumulative[0]
        max_dd = 0
        for val in cumulative:
            if val > peak:
                peak = val
            dd = peak - val
            if dd > max_dd:
                max_dd = dd
        print(f"  Max Drawdown:       {max_dd:.1f} units")
        print(f"  Current Balance:    {cumulative[-1]:+.1f} units")

    # Daily Trend
    section("Daily Trend")
    daily = completed.groupby('Date').agg(
        W=('Result', lambda x: (x == 'WIN').sum()),
        L=('Result', lambda x: (x == 'LOSS').sum()),
        Bets=('Result', 'count'),
        AvgEdge=('Edge', 'mean')
    ).reset_index()
    daily['Units'] = daily.apply(lambda r: r['W'] * 1.0 + r['L'] * -1.1, axis=1)
    daily['CumUnits'] = daily['Units'].cumsum()

    print(f"  {'Date':<12} {'Record':<10} {'Rate':<8} {'P/L':<8} {'Cum P/L':<10} {'AvgEdge':<8}")
    print(f"  {'─'*12} {'─'*10} {'─'*8} {'─'*8} {'─'*10} {'─'*8}")
    for _, row in daily.iterrows():
        rec = f"{int(row['W'])}W-{int(row['L'])}L"
        decided = int(row['W']) + int(row['L'])
        rate = int(row['W']) / decided if decided > 0 else 0
        print(f"  {row['Date']:<12} {rec:<10} {rate:.0%}{'':<5} {row['Units']:+.1f}{'':<4} {row['CumUnits']:+.1f}{'':<6} {row['AvgEdge']:.1f}")

    # Shadow Bet Summary
    if not shadow_bets.empty:
        sw = shadow_bets[shadow_bets['Result'] == 'WIN']
        sl = shadow_bets[shadow_bets['Result'] == 'LOSS']
        sd = len(sw) + len(sl)
        sr = len(sw) / sd if sd > 0 else 0
        section("👻 Shadow Bet Summary")
        print(f"  Shadow bets:     {len(shadow_bets)}  |  Record: {len(sw)}W-{len(sl)}L  |  Win Rate: {sr:.1%}")
        if sd > 0:
            if sr < BREAKEVEN_RATE:
                print(f"  ✅ Guard rails VALIDATED — shadow bets losing")
            else:
                print(f"  ⚠️  Shadow bets are winning — consider relaxing thresholds")

    # Pro Verdict
    section("🏁 PRO-LEVEL VERDICT")
    checks = []
    checks.append(("ATS Win Rate > 52.4%", win_rate >= BREAKEVEN_RATE, f"{win_rate:.1%}"))
    checks.append(("Positive ROI", roi > 0, f"{roi:+.1f}%"))
    if not high.empty:
        high_wr = len(hw) / (len(hw) + len(hl)) if (len(hw) + len(hl)) > 0 else 0
        checks.append((f"High-Signal (Edge ≥ {HIGH_SIGNAL_EDGE}) Win Rate > 55%", high_wr >= 0.55, f"{high_wr:.1%}"))
    checks.append(("Edge Calibration", calibration_ok, ""))
    checks.append(("Sufficient Sample (20+ bets)", total >= 20, f"n={total}"))

    passed = sum(1 for _, ok, _ in checks if ok)
    for label, ok, val in checks:
        icon = '✅' if ok else '❌'
        suffix = f"  ({val})" if val else ""
        print(f"  {icon} {label}{suffix}")

    print(f"\n  Score: {passed}/{len(checks)} checks passed")
    if passed == len(checks):
        print("  🏆 VERDICT: Model is performing at PRO level!")
    elif passed >= len(checks) - 1:
        print("  📈 VERDICT: Model is near pro-level — close to breaking through.")
    elif win_rate >= BREAKEVEN_RATE and roi > 0:
        print("  📈 VERDICT: Model is profitable — keep building sample size.")
    else:
        print("  🔴 VERDICT: Model needs improvement — review edge calibration and loss patterns.")


# ═══════════════════════════════════════════════════════════════════════════════
#  3. EDGE CALIBRATION REPORT
# ═══════════════════════════════════════════════════════════════════════════════

def edge_calibration_report():
    """Detailed breakdown of model accuracy by edge size."""
    df = load_all_trackers()
    completed = filter_completed(df)
    shadow_mask = _pure_shadow_mask(completed)
    completed = completed[~shadow_mask]

    if completed.empty:
        print("  ❌ No completed bets to analyze.")
        return

    header("📐 Edge Calibration Report")
    completed = completed.copy()
    completed['_RawEdge'] = completed.apply(get_raw_edge, axis=1)

    buckets = [(0, 2), (2, 4), (4, 6), (6, 8), (8, 10), (10, float('inf'))]
    bucket_labels = ['0–2', '2–4', '4–6', '6–8', '8–10', '10+']

    print(f"  {'Edge':<10} {'Bets':<6} {'Record':<10} {'Win %':<8} {'P/L':<8}")
    print(f"  {'─'*10} {'─'*6} {'─'*10} {'─'*8} {'─'*8}")

    for (lo, hi_bound), label in zip(buckets, bucket_labels):
        tier = completed[(completed['_RawEdge'] >= lo) & (completed['_RawEdge'] < hi_bound)]
        if tier.empty:
            print(f"  {label:<10} {'0':<6} {'—':<10} {'—':<8} {'—'}")
            continue
        tw = tier[tier['Result'] == 'WIN']
        tl = tier[tier['Result'] == 'LOSS']
        tier_decided = len(tw) + len(tl)
        tr = len(tw) / tier_decided if tier_decided > 0 else 0
        tu = tier.apply(calc_units, axis=1).sum()
        print(f"  {label:<10} {len(tier):<6} {f'{len(tw)}W-{len(tl)}L':<10} {tr:<8.1%} {tu:<+8.1f}")


# ═══════════════════════════════════════════════════════════════════════════════
#  4. DAILY TREND / PROFIT CURVE
# ═══════════════════════════════════════════════════════════════════════════════

def daily_trend():
    """Day-by-day P/L trend with rolling win rate."""
    df = load_all_trackers()
    completed = filter_completed(df)
    shadow_mask = _pure_shadow_mask(completed)
    completed = completed[~shadow_mask]

    if completed.empty:
        print("  ❌ No completed bets to analyze.")
        return

    header("📈 Daily Trend & Profit Curve")

    daily = completed.groupby('Date').agg(
        W=('Result', lambda x: (x == 'WIN').sum()),
        L=('Result', lambda x: (x == 'LOSS').sum()),
        Bets=('Result', 'count'),
        AvgEdge=('Edge', 'mean')
    ).reset_index().sort_values('Date')
    daily['Units'] = daily.apply(lambda r: r['W'] * 1.0 + r['L'] * -1.1, axis=1)
    daily['CumUnits'] = daily['Units'].cumsum()
    daily['CumW'] = daily['W'].cumsum()
    daily['CumDecided'] = (daily['W'] + daily['L']).cumsum()
    daily['RollingRate'] = daily.apply(lambda r: r['CumW'] / r['CumDecided'] if r['CumDecided'] > 0 else 0, axis=1)

    print(f"\n  {'Date':<12} {'Record':<10} {'Day P/L':<9} {'Cum P/L':<10} {'Cum Rate':<10} {'Trend':<8}")
    print(f"  {'─'*12} {'─'*10} {'─'*9} {'─'*10} {'─'*10} {'─'*8}")

    for _, row in daily.iterrows():
        rec = f"{int(row['W'])}W-{int(row['L'])}L"
        trend_icon = '📈' if row['Units'] > 0 else '📉' if row['Units'] < 0 else '➡️'
        print(f"  {row['Date']:<12} {rec:<10} {row['Units']:+.1f}{'':<4} {row['CumUnits']:+.1f}{'':<5} {row['RollingRate']:.1%}{'':<5} {trend_icon}")


# ═══════════════════════════════════════════════════════════════════════════════
#  5. BANKROLL TRACKER
# ═══════════════════════════════════════════════════════════════════════════════

BANKROLL_FILE = "bankroll.json"

def load_bankroll():
    path = os.path.join(BASE_DIR, BANKROLL_FILE)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None

def save_bankroll(data):
    path = os.path.join(BASE_DIR, BANKROLL_FILE)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def bankroll_tracker():
    """Track bankroll over time."""
    header("💵 BANKROLL TRACKER")

    bankroll_data = load_bankroll()
    if bankroll_data is None:
        section("Setup — First Time")
        print("  No bankroll configured yet. Let's set one up.\n")
        try:
            starting = float(input("  Starting bankroll ($): ").strip().replace('$', '').replace(',', ''))
        except (ValueError, EOFError):
            print("  ❌ Invalid amount.")
            return
        try:
            unit_str = input("  Unit size ($ per flat bet, default = bankroll/100): ").strip().replace('$', '').replace(',', '')
            unit_size = float(unit_str) if unit_str else round(starting / 100, 2)
        except (ValueError, EOFError):
            unit_size = round(starting / 100, 2)

        bankroll_data = {
            "starting_bankroll": starting,
            "unit_size": unit_size,
            "edge_cap": DEFAULT_EDGE_CAP,
            "created": datetime.now().strftime('%Y-%m-%d')
        }
        save_bankroll(bankroll_data)
        print(f"\n  ✅ Bankroll saved: ${starting:,.2f} | Unit: ${unit_size:,.2f}")

    starting = bankroll_data['starting_bankroll']
    unit_size = bankroll_data['unit_size']

    df = load_all_trackers()
    completed = filter_completed(df)
    shadow_mask = _pure_shadow_mask(completed)
    completed = completed[~shadow_mask]

    if completed.empty:
        section("Summary")
        print(f"  Starting Bankroll:  ${starting:,.2f}")
        print(f"  Unit Size:          ${unit_size:,.2f}")
        print("  No completed bets yet.")
        return

    dates = sorted(completed['Date'].unique())
    has_dollars = has_bet_data(completed)

    section("Configuration")
    print(f"  Starting Bankroll:  ${starting:,.2f}")
    print(f"  Unit Size:          ${unit_size:,.2f}")
    print(f"  Tracking Since:     {bankroll_data.get('created', dates[0])}")

    # Day-by-day bankroll
    section("Daily Bankroll")
    print(f"  {'Date':<12} {'Record':<10} {'Day P/L':<12} {'Balance':<12} {'vs Start'}")
    print(f"  {'─'*12} {'─'*10} {'─'*12} {'─'*12} {'─'*10}")

    balance = starting
    for d in dates:
        day_df = completed[completed['Date'] == d]
        w = (day_df['Result'] == 'WIN').sum()
        l = (day_df['Result'] == 'LOSS').sum()
        rec = f"{w}W-{l}L"
        day_pl = day_df.apply(calc_units, axis=1).sum() * unit_size
        balance += day_pl
        change = balance - starting
        change_pct = (change / starting) * 100 if starting != 0 else 0.0
        icon = '📈' if day_pl >= 0 else '📉'
        print(f"  {d:<12} {rec:<10} {icon} ${day_pl:>+9,.2f}  ${balance:>10,.2f}  {change_pct:+.1f}%")

    section("💰 Bankroll Summary")
    total_change = balance - starting
    total_pct = (total_change / starting) * 100 if starting != 0 else 0.0
    print(f"  Starting:     ${starting:,.2f}")
    print(f"  Current:      ${balance:,.2f}")
    print(f"  Net Change:   ${total_change:+,.2f}  ({total_pct:+.1f}%)")


# ═══════════════════════════════════════════════════════════════════════════════
#  6. FAIR LINE COMPONENT ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

def load_fair_line_logs():
    pattern = os.path.join(BASE_DIR, 'fair_line_log_*.csv')
    files = sorted(glob.glob(pattern))
    if not files:
        return pd.DataFrame()
    frames = []
    for f in files:
        try:
            df = pd.read_csv(f)
            frames.append(df)
        except Exception:
            continue
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fair_line_component_analysis():
    """Analyze which fair-line components correlate with wins/losses."""
    logs = load_fair_line_logs()
    if logs.empty:
        print("  ❌ No fair line logs found. Run the engine on some games first.")
        return

    header("🔬 Fair Line Component Analysis")

    section("Component Summary (all analyzed games)")
    numeric_cols = [
        ('HCA', 'HCA'), ('Altitude', 'Altitude'), ('Weather', 'Weather'),
        ('Schedule', 'Schedule'), ('H_Star_Tax', 'H_Star_Tax'), ('A_Star_Tax', 'A_Star_Tax'),
        ('SOS', 'SOS'), ('Motivation', 'Motivation'), ('Raw_Diff', 'Raw_Diff'), ('Fair_Line', 'Fair_Line'),
    ]
    print(f"  {'Component':<18} {'Mean':>8} {'Min':>8} {'Max':>8} {'StdDev':>8}")
    print(f"  {'─'*18} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")
    for label, col in numeric_cols:
        if col not in logs.columns:
            continue
        vals = pd.to_numeric(logs[col], errors='coerce').dropna()
        if vals.empty:
            continue
        print(f"  {label:<18} {vals.mean():>+8.2f} {vals.min():>+8.2f} {vals.max():>+8.2f} {vals.std():>8.2f}")

    print(f"\n  Total games logged: {len(logs)}")


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def list_available_dates():
    pattern = os.path.join(BASE_DIR, 'bet_tracker_*.csv')
    files = sorted(glob.glob(pattern), reverse=True)
    dates = []
    for f in files:
        match = re.search(r'bet_tracker_(\d{4}-\d{2}-\d{2})\.csv', f)
        if match:
            dates.append(match.group(1))
    return dates


def main():
    if len(sys.argv) > 1 and re.match(r'^\d{4}-\d{2}-\d{2}$', sys.argv[1]):
        date_arg = sys.argv[1]
        print("\n" + "=" * 65)
        print(f"  🏈 NFL Prediction Engine — Post-Mortem Analyzer v{_MODEL_VERSION}")
        print("=" * 65)
        daily_post_mortem(date_arg)
        return

    print("\n" + "=" * 65)
    print(f"  🏈 NFL Prediction Engine — Post-Mortem Analyzer v{_MODEL_VERSION}")
    print("=" * 65)

    while True:
        print("\n  [1] Single-Day Post-Mortem")
        print("  [2] Lifetime Performance Dashboard")
        print("  [3] Edge Calibration Report")
        print("  [4] Daily Trend & Profit Curve")
        print("  [5] Bankroll Tracker")
        print("  [6] Fair Line Component Analysis")
        print("  [Q] Quit\n")

        choice = input("  Select: ").strip().upper()

        if choice == 'Q':
            print("  👋 Done.")
            break
        elif choice == '1':
            dates = list_available_dates()
            if dates:
                print(f"\n  Available dates: {', '.join(dates)}")
            date_str = input("  Enter date (YYYY-MM-DD): ").strip()
            daily_post_mortem(date_str)
        elif choice == '2':
            lifetime_dashboard()
        elif choice == '3':
            edge_calibration_report()
        elif choice == '4':
            daily_trend()
        elif choice == '5':
            bankroll_tracker()
        elif choice == '6':
            fair_line_component_analysis()
        else:
            print("  ❌ Invalid choice.")


if __name__ == "__main__":
    main()

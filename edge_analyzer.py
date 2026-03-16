#!/usr/bin/env python3
"""
edge_analyzer.py — NFL Edge Decomposition Diagnostics

Provides detailed breakdowns of what drives each game's edge:
ratings difference, injury tax, schedule/rest, weather, SOS, motivation.

Usage:
    python edge_analyzer.py
"""

import json
import os
import sys
from nfl_analytics import (
    predict_nfl_spread, calculate_edge, decompose_edge,
    calculate_ecs, evaluate_guard_rails, _load_model_config
)
from nfl_teams_static import resolve_team_name

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def analyze_edge(away, home, market_spread, week=None, injuries=None, weather=None):
    """Full edge decomposition for a single NFL matchup.

    Returns a dict with all edge components and analysis.
    """
    config = _load_model_config()
    params = config.get('model_params', {})

    # Predict fair line
    prediction = predict_nfl_spread(
        away, home,
        injuries=injuries,
        weather=weather,
        week=week,
    )

    if prediction is None:
        return None

    fair_line = prediction['fair_line']

    # Calculate edge
    edge_data = calculate_edge(fair_line, market_spread, params)
    edge = edge_data['edge']
    raw_edge = edge_data['raw_edge']
    pick = edge_data['pick']

    # Decompose
    decomp = decompose_edge(prediction)

    # ECS
    ecs_data = calculate_ecs(
        edge=edge,
        raw_edge=raw_edge,
        injuries=injuries,
        weather=weather,
        away=away,
        home=home,
    )

    # Guard rails
    guard_rails = evaluate_guard_rails(
        edge=edge,
        raw_edge=raw_edge,
        fair_line=fair_line,
        market_spread=market_spread,
        injuries=injuries,
        weather=weather,
        away=away,
        home=home,
        week=week,
    )

    return {
        'away': away,
        'home': home,
        'fair_line': fair_line,
        'market_spread': market_spread,
        'edge': edge,
        'raw_edge': raw_edge,
        'pick': pick,
        'decomposition': decomp,
        'ecs': ecs_data,
        'guard_rails': guard_rails,
        'prediction': prediction,
    }


def print_edge_analysis(analysis):
    """Pretty-print an edge analysis result."""
    if analysis is None:
        print("  ❌ Analysis failed — check team names and data availability.")
        return

    away = analysis['away']
    home = analysis['home']
    fair = analysis['fair_line']
    market = analysis['market_spread']
    edge = analysis['edge']
    raw_edge = analysis['raw_edge']
    pick = analysis['pick']
    decomp = analysis['decomposition']
    ecs = analysis['ecs']
    guard_rails = analysis['guard_rails']

    print(f"\n  {'='*60}")
    print(f"  🏈 {away} @ {home}")
    print(f"  {'='*60}")
    print(f"\n  Fair Line:    {fair:+.1f}")
    print(f"  Market:       {market:+.1f}")
    print(f"  Edge:         {edge:.1f} pts (raw: {raw_edge:.1f})")
    print(f"  Pick:         {pick}")

    # Decomposition
    print(f"\n  ── Edge Decomposition ──")
    print(f"  {'Component':<20} {'Contribution':>12}")
    print(f"  {'─'*20} {'─'*12}")
    for comp_name, pct in decomp.items():
        bar = '█' * int(pct / 5) if pct > 0 else ''
        print(f"  {comp_name:<20} {pct:>10.1f}% {bar}")

    # ECS
    print(f"\n  ── Edge Confidence Score ──")
    ecs_score = ecs.get('ecs', 0)
    ecs_tier = ecs.get('tier', 'UNKNOWN')
    print(f"  ECS:   {ecs_score}/100  ({ecs_tier})")
    penalties = ecs.get('penalties', [])
    bonuses = ecs.get('bonuses', [])
    if penalties:
        for p in penalties:
            print(f"    ⚠️  {p}")
    if bonuses:
        for b in bonuses:
            print(f"    ✅ {b}")

    # Guard Rails
    print(f"\n  ── Guard Rail Check ──")
    triggered = guard_rails.get('triggered', [])
    passed = guard_rails.get('passed', [])
    shadow = guard_rails.get('shadow', False)

    if not triggered:
        print(f"  ✅ All clear — no guard rails triggered")
    else:
        for tag in triggered:
            print(f"  🚨 {tag}")

    if shadow:
        print(f"\n  ⚠️  SHADOW BET RECOMMENDED — guard rails flagged concerns")

    print()


def interactive_mode():
    """Interactive edge analysis loop."""
    print("\n" + "=" * 60)
    print("  🏈 NFL Edge Analyzer")
    print("=" * 60)

    while True:
        print("\n  Enter a matchup to analyze (or Q to quit):")
        away = input("  Away team: ").strip()
        if away.upper() == 'Q':
            break

        home = input("  Home team: ").strip()
        if home.upper() == 'Q':
            break

        away_resolved = resolve_team_name(away)
        home_resolved = resolve_team_name(home)

        if not away_resolved:
            print(f"  ❌ Could not resolve team: {away}")
            continue
        if not home_resolved:
            print(f"  ❌ Could not resolve team: {home}")
            continue

        try:
            market = float(input("  Market spread (home team, e.g. -3.5): ").strip())
        except (ValueError, EOFError):
            print("  ❌ Invalid spread.")
            continue

        try:
            week_str = input("  Week number (optional, Enter to skip): ").strip()
            week = int(week_str) if week_str else None
        except (ValueError, EOFError):
            week = None

        analysis = analyze_edge(away_resolved, home_resolved, market, week=week)
        print_edge_analysis(analysis)

    print("  👋 Done.")


def main():
    interactive_mode()


if __name__ == '__main__':
    main()

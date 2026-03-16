#!/usr/bin/env python3
"""
season_backtest.py — NFL 17-Week Season Replay Analysis

Replays a full NFL season to evaluate model accuracy on historical data.
Uses cached stats and schedule to simulate week-by-week predictions.

Usage:
    python season_backtest.py
"""

import json
import os
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_schedule():
    path = os.path.join(BASE_DIR, 'nfl_schedule_cache.json')
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def load_stats():
    path = os.path.join(BASE_DIR, 'nfl_stats_cache.json')
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def backtest_week(week_games, stats):
    """Run model predictions against completed games in a week.

    Returns list of dicts with prediction results.
    """
    from nfl_analytics import predict_nfl_spread

    results = []
    for game in week_games:
        away = game.get('away', '')
        home = game.get('home', '')
        state = game.get('state', '')

        # Only grade completed games
        if state != 'post':
            continue

        away_score = game.get('away_score')
        home_score = game.get('home_score')
        if away_score is None or home_score is None:
            continue

        # Predict
        prediction = predict_nfl_spread(away, home)
        if prediction is None:
            continue

        fair_line = prediction['fair_line']
        actual_spread = -(home_score - away_score)  # home spread convention

        error = fair_line - actual_spread
        abs_error = abs(error)

        results.append({
            'away': away,
            'home': home,
            'fair_line': fair_line,
            'actual_spread': actual_spread,
            'away_score': away_score,
            'home_score': home_score,
            'error': error,
            'abs_error': abs_error,
        })

    return results


def run_backtest():
    """Run full season backtest."""
    schedule = load_schedule()
    if not schedule:
        print("  ❌ No schedule cache found. Run: python schedule_scraper.py")
        return

    stats = load_stats()
    if not stats:
        print("  ⚠️  No stats cache found. Predictions will use defaults.")

    weeks = schedule.get('weeks', {})
    if not weeks:
        print("  ❌ No weeks found in schedule cache.")
        return

    print("\n" + "=" * 65)
    print("  🏈 NFL Season Backtest")
    print("=" * 65)

    all_results = []
    print(f"\n  {'Week':<8} {'Games':<8} {'MAE':<10} {'Bias':<10} {'< 3 pts':<10} {'< 7 pts'}")
    print(f"  {'─'*8} {'─'*8} {'─'*10} {'─'*10} {'─'*10} {'─'*8}")

    for week_num in sorted(weeks.keys(), key=lambda x: int(x)):
        week_games = weeks[week_num]
        results = backtest_week(week_games, stats)

        if not results:
            continue

        mae = sum(r['abs_error'] for r in results) / len(results)
        bias = sum(r['error'] for r in results) / len(results)
        within_3 = sum(1 for r in results if r['abs_error'] < 3) / len(results)
        within_7 = sum(1 for r in results if r['abs_error'] < 7) / len(results)

        print(f"  Wk {week_num:<4} {len(results):<8} {mae:<10.1f} {bias:<+10.1f} {within_3:<10.0%} {within_7:.0%}")
        all_results.extend(results)

    if all_results:
        print(f"\n  {'─'*60}")
        total_mae = sum(r['abs_error'] for r in all_results) / len(all_results)
        total_bias = sum(r['error'] for r in all_results) / len(all_results)
        total_w3 = sum(1 for r in all_results if r['abs_error'] < 3) / len(all_results)
        total_w7 = sum(1 for r in all_results if r['abs_error'] < 7) / len(all_results)

        print(f"  TOTAL  {len(all_results):<8} {total_mae:<10.1f} {total_bias:<+10.1f} {total_w3:<10.0%} {total_w7:.0%}")

        print(f"\n  Season MAE: {total_mae:.1f} pts")
        print(f"  Season Bias: {total_bias:+.1f} pts")
        print(f"  Games within 3 pts: {total_w3:.0%}")
        print(f"  Games within 7 pts: {total_w7:.0%}")

        if total_mae < 8:
            print("\n  ✅ Model accuracy is good (MAE < 8)")
        elif total_mae < 10:
            print("\n  ⚠️  Model accuracy is moderate (MAE 8-10)")
        else:
            print("\n  🔴 Model accuracy needs improvement (MAE > 10)")
    else:
        print("\n  ❌ No completed games found for backtest.")


def main():
    run_backtest()


if __name__ == '__main__':
    main()

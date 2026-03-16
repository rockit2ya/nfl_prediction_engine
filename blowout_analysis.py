#!/usr/bin/env python3
"""
blowout_analysis.py — NFL Blowout Risk Scoring

Estimates the probability of a blowout (margin ≥ 14 points) for NFL games.
NFL blowouts are less common than NBA but have significant ATS implications.

Usage:
    python blowout_analysis.py
"""

import json
import os
from nfl_teams_static import resolve_team_name, same_division

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# NFL blowout threshold: 14+ points (two-TD margin)
BLOWOUT_THRESHOLD = 14

# Base blowout probability for an average NFL game (~18% historically)
BASE_BLOWOUT_PROB = 0.18


def _load_stats():
    """Load team stats from cache."""
    path = os.path.join(BASE_DIR, 'nfl_stats_cache.json')
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def calculate_blowout_risk(away, home, spread=None, weather=None, injuries=None):
    """Calculate blowout risk score (0-100) for an NFL matchup.

    Factors:
      - Spread magnitude (bigger spread → higher blowout risk)
      - Team quality mismatch (efficiency differential)
      - Divisional game (dampens blowout probability)
      - Weather (extreme weather reduces scoring, reduces blowouts)
      - Injury context (QB out increases blowout risk for that team)

    Returns:
        dict: {
            'blowout_risk': int (0-100),
            'favored': str (team name),
            'factors': list of str,
        }
    """
    stats = _load_stats()
    factors = []
    risk = BASE_BLOWOUT_PROB

    # 1. Spread magnitude factor
    if spread is not None:
        abs_spread = abs(spread)
        if abs_spread >= 10:
            risk += 0.20
            factors.append(f"Large spread ({abs_spread:.1f}) → +20% blowout risk")
        elif abs_spread >= 7:
            risk += 0.12
            factors.append(f"Medium spread ({abs_spread:.1f}) → +12% blowout risk")
        elif abs_spread >= 3.5:
            risk += 0.05
            factors.append(f"Moderate spread ({abs_spread:.1f}) → +5% blowout risk")
        else:
            risk -= 0.05
            factors.append(f"Tight spread ({abs_spread:.1f}) → -5% blowout risk")

    # 2. Efficiency mismatch
    away_stats = stats.get(away, {})
    home_stats = stats.get(home, {})
    away_eff = away_stats.get('OFF_EPA', 0) - home_stats.get('DEF_EPA', 0)
    home_eff = home_stats.get('OFF_EPA', 0) - away_stats.get('DEF_EPA', 0)
    eff_diff = abs(home_eff - away_eff)

    if eff_diff > 3.0:
        risk += 0.15
        factors.append(f"Large efficiency mismatch ({eff_diff:.1f}) → +15%")
    elif eff_diff > 1.5:
        risk += 0.08
        factors.append(f"Moderate efficiency mismatch ({eff_diff:.1f}) → +8%")

    # 3. Divisional dampener
    if same_division(away, home):
        risk -= 0.08
        factors.append("Divisional game → -8% (rivals play closer)")

    # 4. Weather dampener (extreme weather = lower scoring = fewer blowouts)
    if weather:
        wind = weather.get('wind_mph', 0)
        temp = weather.get('temp_f', 72)
        if wind > 20 or temp < 20:
            risk -= 0.05
            factors.append("Extreme weather → -5% (suppresses scoring)")

    # 5. QB injury amplifier
    if injuries:
        for team, role in [(away, 'away'), (home, 'home')]:
            for inj in injuries if isinstance(injuries, list) else []:
                if (inj.get('team', '').lower() == team.lower() and
                        inj.get('position', '').upper() == 'QB' and
                        inj.get('status', '').upper() in ['OUT', 'DOUBTFUL']):
                    risk += 0.10
                    factors.append(f"{team} QB out → +10% blowout risk")

    # Clamp to 0-100
    risk_score = max(0, min(100, int(risk * 100)))

    # Determine favored team
    if spread is not None:
        favored = home if spread < 0 else away
    else:
        favored = home if home_eff > away_eff else away

    return {
        'blowout_risk': risk_score,
        'favored': favored,
        'factors': factors,
    }


def print_blowout_analysis(away, home, spread=None, weather=None):
    """Pretty-print blowout risk analysis."""
    result = calculate_blowout_risk(away, home, spread=spread, weather=weather)

    risk = result['blowout_risk']
    favored = result['favored']
    factors = result['factors']

    if risk >= 40:
        tier = "🔴 HIGH"
    elif risk >= 25:
        tier = "🟡 MODERATE"
    else:
        tier = "🟢 LOW"

    print(f"\n  ── Blowout Risk Analysis ──")
    print(f"  {away} @ {home}")
    print(f"  Blowout Risk:  {risk}/100  ({tier})")
    print(f"  Favored:       {favored}")
    if factors:
        print(f"  Factors:")
        for f in factors:
            print(f"    • {f}")

    if risk >= 40:
        print(f"\n  ⚠️  High blowout risk — consider pass or reduced unit size")
    elif risk >= 25:
        print(f"\n  📊 Moderate blowout risk — proceed with caution")
    else:
        print(f"\n  ✅ Low blowout risk — competitive game expected")


def main():
    print("\n" + "=" * 60)
    print("  🏈 NFL Blowout Risk Analyzer")
    print("=" * 60)

    while True:
        print("\n  Enter a matchup (or Q to quit):")
        away = input("  Away team: ").strip()
        if away.upper() == 'Q':
            break

        home = input("  Home team: ").strip()
        if home.upper() == 'Q':
            break

        away_r = resolve_team_name(away) or away
        home_r = resolve_team_name(home) or home

        try:
            spread_str = input("  Market spread (optional, Enter to skip): ").strip()
            spread = float(spread_str) if spread_str else None
        except (ValueError, EOFError):
            spread = None

        print_blowout_analysis(away_r, home_r, spread=spread)

    print("  👋 Done.")


if __name__ == '__main__':
    main()

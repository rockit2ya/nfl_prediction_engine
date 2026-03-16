# 🏈 NFL Prediction Engine v1.0

A config-driven, edge-detection sports analytics engine for NFL game spreads. Ported from the [NBA Prediction Engine v3.36](https://github.com/rockit2ya/nba_prediction_engine) framework with NFL-specific adaptations for QB dominance, weather modeling, bye/short-week rest, divisional rivalry dampening, and EPA-based efficiency.

> **Supersedes** the legacy Super Bowl LX one-off tool that previously lived in this repo.

---

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Data Fetchers   │───▶│  Core Analytics   │───▶│  Interactive UI   │
│                  │    │                   │    │                   │
│ nfl_data_fetcher │    │  nfl_analytics.py │    │  nfl_engine_ui.py │
│ injury_scraper   │    │  model_config.json│    │                   │
│ schedule_scraper │    │                   │    │  edge_analyzer.py │
│ odds_api         │    └──────────────────┘    │  blowout_analysis │
│ weather_fetcher  │                             └──────────────────┘
└─────────────────┘
         │
         ▼
┌──────────────────┐    ┌──────────────────┐
│  Grading Loop     │    │  Utilities        │
│                   │    │                   │
│ update_results.py │    │ calculate_bankroll│
│ post_mortem.py    │    │ snapshot_caches   │
│ season_backtest   │    │ fetch_all_nfl_data│
└──────────────────┘    └──────────────────┘
```

## Key NFL Adaptations (vs. NBA Engine)

| Concept | NBA Engine | NFL Engine |
|---|---|---|
| **Dominant Position** | N/A (team-based) | QB injury = full impact; non-QB dampened 75% |
| **Rest Model** | Back-to-back penalty | Bye week (+1.5) / Short week (-1.5) |
| **Home-Field Advantage** | 2.0 pts | 2.5 pts |
| **Weather** | Not modeled | Wind, cold, precipitation, dome detection |
| **Divisional Factor** | Not modeled | 0.85x dampener for division games |
| **Pace Adjustment** | Yes (possessions) | No (fixed game structure) |
| **Altitude** | Denver +1.0 | Denver +1.0 |
| **High Signal Edge** | 5 pts | 4 pts (tighter NFL lines) |
| **Min Edge for Bet** | 8 pts | 6 pts |
| **Blowout Threshold** | Varies | 14 pts (2 TDs) |
| **Season Length** | 82 games | 17 games (higher regression) |

## Fair Line Formula

```
raw_diff    = home_rating - away_rating  (regressed, blended season + recent)
fair_line   = -(raw_diff + HFA + altitude - home_tax + away_tax
                + schedule_adj + sos_adj + motivation_adj) + weather * 0.1
```

If divisional game: `fair_line *= DIVISIONAL_RIVALRY_DAMPENER (0.85)`

Final spread = blend of fair line (35%) + market line (65%).

---

## Quick Start

```bash
# Clone
git clone https://github.com/rockit2ya/nfl_prediction_engine.git
cd nfl_prediction_engine

# Set up environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# (Optional) Set Odds API key
export THE_ODDS_API_KEY="your_key_here"

# Refresh all data
./fetch_all_nfl_data.sh

# Run the engine
python3 nfl_engine_ui.py
```

## File Reference

### Core Engine
| File | Purpose |
|---|---|
| `nfl_analytics.py` | Fair line calculation, edge/ECS scoring, guard rails |
| `nfl_engine_ui.py` | Interactive terminal UI, game analysis, bet logging |
| `model_config.json` | All tunable parameters and guard rail thresholds |
| `nfl_teams_static.py` | 32-team metadata (divisions, domes, altitude) |

### Data Fetchers
| File | Source | Output |
|---|---|---|
| `nfl_data_fetcher.py` | ESPN API | `nfl_stats_cache.json`, `nfl_stats_recent_cache.json`, `nfl_sos_cache.json` |
| `injury_scraper.py` | CBS Sports | `nfl_injuries.csv` |
| `schedule_scraper.py` | ESPN | `nfl_schedule_cache.json` |
| `odds_api.py` | The Odds API | `nfl_odds_cache.json` |
| `weather_fetcher.py` | Open-Meteo | `nfl_weather_cache.json` |

### Grading & Analysis
| File | Purpose |
|---|---|
| `update_results.py` | Fetch final scores, grade bets, track CLV |
| `post_mortem.py` | Lifetime dashboard, edge calibration, daily trends |
| `edge_analyzer.py` | Detailed edge decomposition diagnostics |
| `blowout_analysis.py` | Blowout risk scoring (14+ pt threshold) |
| `season_backtest.py` | 17-week season replay analysis |

### Utilities
| File | Purpose |
|---|---|
| `calculate_bankroll.py` | Bankroll status display |
| `snapshot_caches.py` | Archive weekly cache state |
| `fetch_all_nfl_data.sh` | Refresh all data sources |
| `bankroll.json` | Current bankroll state |

## Weekly Workflow

```
1. ./fetch_all_nfl_data.sh          # Refresh data (Tuesday/Wednesday)
2. python3 nfl_engine_ui.py         # Analyze games, log bets
3. python3 update_results.py now    # Grade after games finish (Sunday/Monday)
4. python3 post_mortem.py           # Review performance
5. python3 snapshot_caches.py       # Archive weekly state
```

## Configuration

All model parameters live in `model_config.json`. Key sections:

- **model_params**: Regression factor, blend weights, HFA, QB impact, weather thresholds, motivation
- **guard_rails**: Edge caps, minimum edge, max bets per day, injury thresholds, fade-eligible tags
- **adaptive_blend**: Auto-adjust market anchor weight based on MAE history

## Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `THE_ODDS_API_KEY` | Optional | Live odds from The Odds API (free tier: 500 req/month) |

---

## Edge Confidence Score (ECS)

Games are scored 0-100 based on:
- Edge magnitude (0-35 pts)
- Guard rail pass rate (0-25 pts)
- Injury clarity (0-15 pts)
- Weather stability (0-10 pts)
- Line movement agreement (0-15 pts)

**ECS ≥ 70** = high-confidence play. **ECS < 40** = skip.

## License

Educational and analytical purposes only. **Always bet responsibly.**

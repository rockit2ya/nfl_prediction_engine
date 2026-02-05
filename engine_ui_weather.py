import pandas as pd
from data_retrieval import get_nfl_data, get_star_injuries
from model_training import calculate_engine_metrics, predict_score_diff
from weather_engine import get_santa_clara_weather, calculate_weather_adjustment

def run_app():
    print("\n" + "="*60)
    print("--- SUPER BOWL LX PREDICTION ENGINE | WEATHER-INTEGRATED ---")
    print("="*60)

    # 1. Data Ingestion
    pbp_raw, injuries_raw = get_nfl_data()
    pbp = pbp_raw.to_pandas() if hasattr(pbp_raw, 'to_pandas') else pbp_raw
    injuries = injuries_raw.to_pandas() if hasattr(injuries_raw, 'to_pandas') else injuries_raw

    # 2. Injury Detection & Manual Overrides
    sea_stars = get_star_injuries(injuries, 'SEA')
    pat_stars = get_star_injuries(injuries, 'NE')

    print("\n[INJURY STATUS]")
    if injuries.empty:
        print("⚠️ Automated injury feed offline (Server 404).")
    
    manual_fix = input("\nAdd manual star overrides? (y/n): ").lower()
    if manual_fix == 'y':
        sea_manual = input("Additional SEA stars (comma-separated): ").split(',')
        pat_manual = input("Additional NE stars (comma-separated): ").split(',')
        sea_stars.extend([s.strip() for s in sea_manual if s.strip()])
        pat_stars.extend([p.strip() for p in pat_manual if p.strip()])

    # 3. Blended Model Calculation (Stability/Momentum)
    print("\nCalculating 70/30 Blended EPA Metrics...")
    sea_metrics = calculate_engine_metrics(pbp, 'SEA', sea_stars)
    pat_metrics = calculate_engine_metrics(pbp, 'NE', pat_stars)
    model_spread = predict_score_diff(sea_metrics, pat_metrics)

    # 4. Live Weather Adjustment
    print("\nFetching Live Weather for Santa Clara, CA...")
    rain_mm = get_santa_clara_weather()
    final_spread, pa = calculate_weather_adjustment(model_spread, rain_mm)

    # 5. Result Output & Edge Detection
    print("\n" + "—"*40)
    print(f"RAW PROJECTION:    {model_spread}")
    print(f"PRECIP ADJUST (Pa): {pa} ({rain_mm}mm rain)")
    print(f"FINAL SPREAD:      {final_spread}")
    print("—"*40)

    market_line = float(input("\nEnter Market Spread (e.g., -4.5 for SEA): "))
    edge = round(abs(final_spread - market_line), 2)

    # --- NEW: EXPLICIT BETTING RECOMMENDATION LOGIC ---
    print("\n" + "*"*20 + " FINAL VERDICT " + "*"*20)
    
    # Determine the Side
    # If model_spread (1.38) is > market_line (-4.5), the market overvalued SEA.
    if final_spread > market_line:
        recommendation = f"BET NEW ENGLAND PATRIOTS (+{abs(market_line)})"
        side_color = "🟢"
    else:
        recommendation = f"BET SEATTLE SEAHAWKS ({market_line})"
        side_color = "🔵"

    print(f"{side_color} TARGET SIDE: {recommendation}")
    print(f"📊 CALCULATED EDGE: {edge} points")
    
    if edge >= 3.0:
        print("🔥 SIGNAL STRENGTH: MASSIVE (High Confidence Value)")
        print(f"💰 STRATEGY: Take the Points and consider a ML Sprinkler (NE +195).")
    elif edge > 1.5:
        print("⚡ SIGNAL STRENGTH: MODERATE (Standard Unit)")
    else:
        print("⚪ SIGNAL STRENGTH: NO EDGE (Avoid this Market)")
    print("*"*55)

if __name__ == "__main__":
    run_app()

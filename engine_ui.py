import pandas as pd
from data_retrieval import get_nfl_data, get_star_injuries
from model_training import calculate_engine_metrics, predict_score_diff

def run_app():
    print("--- STARTING SUPER BOWL LX PREDICTION ENGINE ---")
    
    # 1. Fetch Data (Could return Polars or Pandas depending on server status)
    pbp_raw, injuries_raw = get_nfl_data([2025])
    
    # 2. Type-Aware Conversion (The 'AttributeError' Fix)
    # We only call .to_pandas() if the object actually has that method
    pbp = pbp_raw.to_pandas() if hasattr(pbp_raw, 'to_pandas') else pbp_raw
    injuries = injuries_raw.to_pandas() if hasattr(injuries_raw, 'to_pandas') else injuries_raw

    # 3. Identify Injuries (Automated Scan)
    sea_stars = get_star_injuries(injuries, 'SEA')
    pat_stars = get_star_injuries(injuries, 'NE')

    # 4. Manual Injury Override (Triggered if 404 warning occurred)
    print("\n--- INJURY ANALYSIS ---")
    if injuries.empty:
        print("Note: Automated injury data is missing (Server 404).")
    else:
        print(f"Automated Scan found stars out - SEA: {sea_stars} | NE: {pat_stars}")

    manual_fix = input("Would you like to manually add any star players to the 'Out' list? (y/n): ").lower()
    if manual_fix == 'y':
        print("\nEnter names (comma separated) or press Enter to skip.")
        sea_manual = input("Additional SEA stars (e.g., Charles Cross): ").split(',')
        pat_manual = input("Additional NE stars (e.g., Robert Spillane): ").split(',')
        
        # Clean up and append to the lists
        sea_stars.extend([name.strip() for name in sea_manual if name.strip()])
        pat_stars.extend([name.strip() for name in pat_manual if name.strip()])

    # 5. Calculate Metrics
    # Model will now run smoothly using Pandas-formatted data
    sea_epa = calculate_engine_metrics(pbp, 'SEA', sea_stars)
    pat_epa = calculate_engine_metrics(pbp, 'NE', pat_stars)

    pred_diff = predict_score_diff(sea_epa, pat_epa)
    
    # 6. Final Results & Edge Detection
    print(f"\n{'='*40}")
    print(f"MODEL PREDICTION: Seahawks by {pred_diff} points")
    print(f"{'='*40}")
    
    try:
        print("\n--- ENTER MARKET LINES ---")
        mkt_spread = float(input("Enter Patriots Spread (e.g., 4.5): "))
        
        # Calculate the 'Edge'
        edge = pred_diff - mkt_spread
        
        if abs(edge) < 0.5:
            print("\n>>> RESULT: No significant edge. The market line is efficient.")
        elif edge > 0:
            print(f"\n>>> EDGE DETECTED: Take Seahawks -{mkt_spread} (Edge: {abs(edge):.2f} pts)")
        else:
            print(f"\n>>> EDGE DETECTED: Take Patriots +{mkt_spread} (Edge: {abs(edge):.2f} pts)")
            
    except ValueError:
        print("Invalid input. Please enter numbers only for the market lines.")

if __name__ == "__main__":
    run_app()

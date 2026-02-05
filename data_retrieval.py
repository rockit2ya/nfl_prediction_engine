import nflreadpy as nfl
import pandas as pd

def get_nfl_data(years=[2025]):
    print(f"--- Fetching Play-by-Play Data for {years} ---")
    # nflreadpy is the new standard for 2025/2026 data
    pbp = nfl.load_pbp(years)
    
    print("--- Fetching Injury Reports ---")
    try:
        # Attempt to load the official injury report
        injuries = nfl.load_injuries(years)
    except Exception as e:
        print(f"⚠️  Warning: Injury data for {years} is currently unavailable on the server (404).")
        print("The engine will proceed without automated injury weights.")
        # Return an empty DataFrame with the correct column names to avoid crashing
        injuries = pd.DataFrame(columns=['team', 'position', 'report_status', 'full_name'])

    return pbp, injuries

def get_star_injuries(injuries_df, team_abbr):
    # nflreadpy uses 'team' as the column name
    critical_positions = ['QB', 'T', 'G', 'C', 'WR', 'CB', 'DE']
    stars_out = injuries_df[
        (injuries_df['team'] == team_abbr) & 
        (injuries_df['position'].isin(critical_positions)) & 
        (injuries_df['report_status'].isin(['Out', 'Doubtful']))
    ]
    return stars_out['full_name'].tolist()


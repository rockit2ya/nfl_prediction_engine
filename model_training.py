import pandas as pd

def calculate_engine_metrics(pbp_df, team_abbr, star_players_out=[]):
    """
    Calculates a blended EPA rating using a 70% weight on the 5-game window
    and a 30% weight on the 3-game window.
    """
    # 1. Filter for the team's offensive plays (Pass/Run)
    team_pbp = pbp_df[
        (pbp_df['posteam'] == team_abbr) & 
        (pbp_df['play_type'].isin(['pass', 'rush']))
    ].copy()
    
    # 2. Group by game to get average EPA per game
    # We use 'week' to ensure the data is chronologically sorted
    game_stats = team_pbp.groupby('game_id').agg({
        'epa': 'mean',
        'week': 'first'
    }).sort_values('week')

    # 3. Calculate both Rolling Windows
    # min_periods=1 ensures we get a value even if 5 games haven't been played
    game_stats['epa_5g'] = game_stats['epa'].rolling(window=5, min_periods=1).mean()
    game_stats['epa_3g'] = game_stats['epa'].rolling(window=3, min_periods=1).mean()

    # 4. Get the most recent values for the blend
    epa_5g = game_stats['epa_5g'].iloc[-1]
    epa_3g = game_stats['epa_3g'].iloc[-1]

    # 5. BLENDED CALCULATION: 70/30 Weighting
    blended_epa = (epa_5g * 0.70) + (epa_3g * 0.30)

    # 6. Apply Injury Weighting
    # Every star out subtracts a flat 0.06 from the efficiency rating
    injury_penalty = len(star_players_out) * 0.06 
    
    return blended_epa - injury_penalty

def predict_score_diff(sea_epa, pat_epa):
    """
    Converts the EPA differential into a projected scoreboard spread.
    Uses a standard scaling factor of 22.0.
    """
    # Difference in efficiency
    epa_diff = sea_epa - pat_epa
    
    # Scaling to points (e.g., +0.1 EPA diff approx. 2.2 point spread)
    projected_spread = epa_diff * 22.0
    
    return round(projected_spread, 2)

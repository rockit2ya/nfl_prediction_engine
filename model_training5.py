import pandas as pd

def calculate_engine_metrics(pbp_df, team_abbr, star_players_out=[]):
    # Filter for team's offensive plays (exclude special teams)
    team_pbp = pbp_df[
        (pbp_df['posteam'] == team_abbr) & 
        (pbp_df['play_type'].isin(['pass', 'rush']))
    ].copy()
    
    # Group by Game ID to get game-by-game efficiency
    game_stats = team_pbp.groupby('game_id').agg({
        'epa': 'mean',
        'week': 'first'
    }).sort_values('week')

    # Rolling 5-Game Average (Momentum/Heat Factor)
    game_stats['rolling_epa'] = game_stats['epa'].rolling(window=5).mean()
    current_epa = game_stats['rolling_epa'].iloc[-1]

    # Injury Weighting: Punish EPA per missing star
    # An elite LT or QB can impact efficiency by 0.05-0.10 EPA per play
    penalty = len(star_players_out) * 0.06 
    adjusted_epa = current_epa - penalty
    
    return adjusted_epa

def predict_score_diff(sea_epa, pat_epa):
    # A standard NFL scaling factor for EPA to Points is ~22.0
    epa_diff = sea_epa - pat_epa
    predicted_spread = epa_diff * 22.0
    return round(predicted_spread, 2)

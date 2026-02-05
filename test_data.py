import nfl_data_py as nfl
# Just try to pull the first 5 rows of the 2025 schedule
df = nfl.import_schedules([2025]).head()
print("Connection Successful! Here is the schedule data:")
print(df[['game_id', 'home_team', 'away_team']])

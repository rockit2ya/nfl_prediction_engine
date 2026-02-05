import requests

def get_santa_clara_weather():
    """Pulls live precipitation data for Levi's Stadium coordinates."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": 37.403, # Levi's Stadium
        "longitude": -121.970,
        "current": ["precipitation", "rain", "showers"],
        "timezone": "America/Los_Angeles"
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return data['current']['precipitation'] # Returns mm of rain
    except Exception as e:
        print(f"Error fetching weather: {e}")
        return 0.0

def calculate_weather_adjustment(model_spread, rain_mm):
    """
    Applies the Risk Analysis logic:
    - If rain > 0, apply a 5% suppression to the spread (Pa = 0.95)
    - Add a 'Surface Advantage' weight if rain is heavy (> 2mm)
    """
    # Baseline Pa is 1.0 (no change)
    pa = 1.0
    surface_adv = 0.0
    
    if rain_mm > 0:
        pa = 0.95  # 5% suppression on EPA efficiency
        
    # Heavy rain surface advantage (favouring the stable rushing team)
    if rain_mm > 2.0:
        surface_adv = 1.5 # Adjusted for the Patriots' ground-and-pound style
        
    final_spread = (model_spread * pa) + surface_adv
    return round(final_spread, 2), pa

if __name__ == "__main__":
    # Example integration test
    current_rain = get_santa_clara_weather()
    raw_spread = -1.38  # Your current ModelSpread for SB LX
    
    adjusted_line, active_pa = calculate_weather_adjustment(raw_spread, current_rain)
    
    print(f"--- Weather Adjuster Active ---")
    print(f"Current Rain: {current_rain}mm")
    print(f"Active Pa: {active_pa}")
    print(f"Final Adjusted Spread: {adjusted_line}")

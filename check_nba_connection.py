import requests
import time

def check_throttling():
    url = "https://stats.nba.com/stats/leaguedashteamstats"
    
    # These are the "Pro" headers we used in your engine
    headers = {
        'Host': 'stats.nba.com',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://www.nba.com/',
        'Connection': 'keep-alive',
    }

    # Parameters required for a valid 'leaguedashteamstats' request
    params = {
        'LastNGames': '10',
        'LeagueID': '00',
        'MeasureType': 'Advanced',
        'Month': '0',
        'OpponentTeamID': '0',
        'PaceAdjust': 'N',
        'PerMode': 'PerGame',
        'Period': '0',
        'PlusMinus': 'N',
        'Rank': 'N',
        'Season': '2025-26',
        'SeasonType': 'Regular Season',
    }

    print("🛰️  Testing connection to NBA Stats Server...")
    
    try:
        start_time = time.time()
        response = requests.get(url, headers=headers, params=params, timeout=10)
        duration = round(time.time() - start_time, 2)

        if response.status_code == 200:
            print(f"✅ SUCCESS: NBA Servers responded in {duration}s.")
            print("🚀 Your IP is clear. You can start the Pro Engine.")
        elif response.status_code == 403:
            print("❌ BLOCKED (403): Your IP is currently blacklisted/throttled.")
            print("💡 FIX: Toggle Airplane Mode on your phone to get a new IP.")
        elif response.status_code == 429:
            print("❌ RATE LIMITED (429): Too many requests.")
            print("💡 FIX: Wait 5 minutes or switch to a different Wi-Fi network.")
        else:
            print(f"⚠️  UNEXPECTED: Server returned status {response.status_code}.")
            
    except requests.exceptions.Timeout:
        print("❌ TIMEOUT: The server is too slow or dropping your packets.")
        print("💡 FIX: Check your WIFI signal strength.")
    except Exception as e:
        print(f"❌ CONNECTION ERROR: {e}")

if __name__ == "__main__":
    check_throttling()

import requests
import json
import urllib.parse
from datetime import datetime

def test_api():
    # Filter construction
    # We want games from Jan 1 2026 to Jan 10 2026
    start_date = "2026-01-01T00:00:00.000Z"
    end_date = "2026-01-10T23:59:59.999Z"
    
    # Based on previous logs: scheduleId=183360. OfficeId=6150 (seen in truncated log)
    filter_dict = {
        "order": "startTime ASC",
        "skip": 0,
        "where": {
            "and": [
                {
                    "date": {
                        "between": [start_date, end_date]
                    }
                },
                {
                    "scheduleId": 183360
                }
            ]
        }
    }
    
    filter_json = json.dumps(filter_dict)
    filter_encoded = urllib.parse.quote(filter_json)
    
    url = f"https://pub-api.play.spordle.com/api/sp/games?filter={filter_encoded}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Origin": "https://page.spordle.com",
        "Referer": "https://page.spordle.com/"
    }
    
    print(f"Requesting URL: {url[:100]}...")
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        print(f"Status: {resp.status_code}")
        print(f"Games Found: {len(data)}")
        
        for g in data:
            gid = g.get('id')
            date = g.get('date')
            status = g.get('gameStatus')
            home = g.get('homeTeam', {}).get('name', 'Unknown')
            visitor = g.get('awayTeam', {}).get('name', 'Unknown')
            score = g.get('score', {})
            print(f"ID: {gid} | Date: {date} | Status: {status} | Score: {score}")
            print(f"  {home} vs {visitor}")
            
    except Exception as e:
        print(f"Error: {e}")
        if hasattr(e, 'response') and e.response:
             print(e.response.text)

if __name__ == "__main__":
    test_api()

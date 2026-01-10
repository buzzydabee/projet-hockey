import requests
import json
import urllib.parse

def try_filter(name, f):
    url = f"https://pub-api.play.spordle.com/api/sp/games?filter={urllib.parse.quote(json.dumps(f))}"
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        print(f"[{name}] Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"  > Found {len(data)} games")
            if len(data) > 0:
                print(f"  > First: {data[0].get('date')} {data[0].get('homeTeam',{}).get('name')}")
    except Exception as e:
        print(f"[{name}] Error: {e}")

def main():
    # 7. Empty Filter
    try_filter("Empty", {})

    # 8. No Filter (different function needed, but let's try empty dict which becomes %7B%7D)
    
    # 9. Just ScheduleID top level? No, loopback uses where usually.
    
    # 10. Limit only
    try_filter("Limit", {"limit": 1})

if __name__ == "__main__":
    main()

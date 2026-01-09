import sqlite3
from datetime import datetime

DB_NAME = "hockey_stats.db"

def parse_date(date_str):
    try:
        months_map = {
            "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
            "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12
        }
        p = str(date_str).lower().split()
        # Format: "LUNDI 5 JANVIER 2026" or "5 JANVIER 2026"
        if len(p) >= 4: # LUNDI 5 JANVIER 2026
            d = int(p[1])
            m_name = p[2]
            y = int(p[3])
        elif len(p) == 3: # 5 JANVIER 2026
            d = int(p[0])
            m_name = p[1]
            y = int(p[2])
        else:
            return None
            
        m = months_map.get(m_name)
        if m:
            return datetime(y, m, d)
    except:
        return None
    return None

def verify():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT game_id, date, home_team_id, visitor_team_id, final_score_home, final_score_visitor FROM DimGame")
    rows = cursor.fetchall()
    conn.close()

    count_2026 = 0
    cutoff = datetime(2026, 1, 1)

    print(f"Total rows in DB: {len(rows)}")
    print("--- Games since Jan 1, 2026 ---")
    
    found_games = []

    for r in rows:
        gid = r[0]
        d_str = r[1]
        score_home = r[4]
        score_vis = r[5]
        
        dt = parse_date(d_str)
        if dt and dt >= cutoff:
            count_2026 += 1
            found_games.append((dt, gid, d_str, score_home, score_vis))

    # Sort by date
    found_games.sort(key=lambda x: x[0])
    
    for g in found_games:
        print(f"Date: {g[2]} | Score: {g[3]}-{g[4]}")

    print(f"-------------------------------")
    print(f"Total found: {count_2026}")

if __name__ == "__main__":
    verify()


import sqlite3
import pandas as pd
from pypdf import PdfReader
import os
from collections import Counter

conn = sqlite3.connect("hockey_stats.db")

# 1. Get Bad Games
query = '''
    SELECT game_id
    FROM DimGame
    WHERE 
        (pp_goals_home > pp_attempts_home) OR 
        (pp_goals_visitor > pp_attempts_visitor) OR
        (pp_attempts_home = 0 AND pp_goals_home > 0) OR
        (pp_attempts_visitor = 0 AND pp_goals_visitor > 0)
'''
bad_games = pd.read_sql_query(query, conn)['game_id'].tolist()
conn.close()

total_games = 0 # To calculate pct ? Need query for that but approx ok.

print(f"Found {len(bad_games)} problematic games.")

stats_tk = Counter()
stats_sc = Counter()
details = []

for gid in bad_games:
    fpath = f"downloads/game_{gid}.pdf"
    if os.path.exists(fpath):
        try:
            reader = PdfReader(fpath)
            fields = reader.get_fields()
            
            # Keys found: timeKeeper, scoreKeeper
            tk = fields.get('timeKeeper', {}).get('/V')
            sc = fields.get('scoreKeeper', {}).get('/V')
            
            tk_name = str(tk).strip().upper() if tk else "UNKNOWN"
            sc_name = str(sc).strip().upper() if sc else "UNKNOWN"
            
            stats_tk[tk_name] += 1
            stats_sc[sc_name] += 1
            details.append((gid, sc_name, tk_name))
            
        except Exception as e:
            print(f"Error reading {gid}: {e}")

print("\n--- ERREURS PAR MARQUEUR (Scorekeeper) ---")
for name, count in stats_sc.most_common():
    print(f"{name}: {count}")

print("\n--- ERREURS PAR CHRONOMÉTREUR (Timekeeper) ---")
for name, count in stats_tk.most_common():
    print(f"{name}: {count}")

print("\n--- Détails par Match ---")
for gid, sc, tk in details:
    print(f"Match {gid} | Marq: {sc} | Chrono: {tk}")


import sqlite3
import pandas as pd

conn = sqlite3.connect("hockey_stats.db")
gid = 668157

print(f"--- Detailed Events for Game {gid} ---")

# 1. Goals
print("\nGOALS:")
q_g = '''
    SELECT period, time, g.team_id, t.team_name, player_jersey
    FROM FactGoals g
    JOIN DimTeam t ON g.team_id = t.team_id
    WHERE game_id = ?
    ORDER BY period, time
'''
df_g = pd.read_sql_query(q_g, conn, params=(gid,))
print(df_g)

# 2. Penalties
print("\nPENALTIES:")
q_p = '''
    SELECT period, time, p.team_id, t.team_name, duration, code, player_jersey
    FROM FactPenalties p
    JOIN DimTeam t ON p.team_id = t.team_id
    WHERE game_id = ?
    ORDER BY period, time
'''
df_p = pd.read_sql_query(q_p, conn, params=(gid,))
print(df_p)

conn.close()

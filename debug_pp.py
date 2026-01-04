
import sqlite3
import pandas as pd

conn = sqlite3.connect("hockey_stats.db")

query = '''
    SELECT 
        game_id, 
        pp_goals_home, pp_attempts_home,
        pp_goals_visitor, pp_attempts_visitor,
        home_team_id, visitor_team_id
    FROM DimGame
    WHERE 
        (pp_goals_home > pp_attempts_home) OR 
        (pp_goals_visitor > pp_attempts_visitor)
'''

df = pd.read_sql_query(query, conn)

if not df.empty:
    print("Found games with invalid PP stats (Goals > Attempts):")
    print(df)
else:
    print("No games found with Goals > Attempts in DB.")

# Check for specific team mentioned if any (none mentioned, but checking outliers)
# Also check if attempts = 0 but goals > 0
query_zero = '''
    SELECT 
        game_id, 
        pp_goals_home, pp_attempts_home,
        pp_goals_visitor, pp_attempts_visitor
    FROM DimGame
    WHERE 
        (pp_attempts_home = 0 AND pp_goals_home > 0) OR
        (pp_attempts_visitor = 0 AND pp_goals_visitor > 0)
'''
df_z = pd.read_sql_query(query_zero, conn)
if not df_z.empty:
    print("\nFound games with Goals but 0 Attempts:")
    print(df_z)

conn.close()

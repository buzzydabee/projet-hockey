
import sqlite3
import pandas as pd

conn = sqlite3.connect("hockey_stats.db")

query = '''
    SELECT 
        game_id, 
        pp_goals_home, pp_attempts_home,
        pp_goals_visitor, pp_attempts_visitor,
        t1.team_name as home, t2.team_name as visitor
    FROM DimGame g
    JOIN DimTeam t1 ON g.home_team_id = t1.team_id
    JOIN DimTeam t2 ON g.visitor_team_id = t2.team_id
    WHERE 
        (
         (pp_goals_home > pp_attempts_home) OR
         (pp_goals_visitor > pp_attempts_visitor)
        )
        AND (t1.team_name LIKE '%RORQUALS%' OR t2.team_name LIKE '%RORQUALS%')
'''

df = pd.read_sql_query(query, conn)

print("Games with Goals > Attempts (causing negative PK for opponent):")
for _, row in df.iterrows():
    # Home PP > Attempts
    if row['pp_goals_home'] > row['pp_attempts_home']:
        diff = row['pp_attempts_home'] - row['pp_goals_home']
        # PK % might be div by 0 if attempts is 0, handle text
        denom = row['pp_attempts_home']
        print(f"Game {row['game_id']}: {row['home']} PP {row['pp_goals_home']}/{denom} -> {row['visitor']} KILLS = {diff}")
        
    # Visitor PP > Attempts
    if row['pp_goals_visitor'] > row['pp_attempts_visitor']:
        diff = row['pp_attempts_visitor'] - row['pp_goals_visitor']
        denom = row['pp_attempts_visitor']
        print(f"Game {row['game_id']}: {row['visitor']} PP {row['pp_goals_visitor']}/{denom} -> {row['home']} KILLS = {diff}")

conn.close()

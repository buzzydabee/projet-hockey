
import sqlite3
import pandas as pd
from datetime import datetime

DB_NAME = "hockey_stats.db"

def inspect_missing():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # query
    query = """
    SELECT game_id, date, home_team_id, visitor_team_id, final_score_home, final_score_visitor
    FROM DimGame
    WHERE final_score_home = 0 AND final_score_visitor = 0
    ORDER BY date
    """
    
    df = pd.read_sql_query(query, conn)
    
    # Get team names
    teams = pd.read_sql_query("SELECT team_id, team_name FROM DimTeam", conn)
    team_map = dict(zip(teams['team_id'], teams['team_name']))
    
    conn.close()
    
    with open("missing_games.txt", "w", encoding="utf-8") as f:
        f.write(f"Found {len(df)} games with 0-0 score.\n")
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        for _, row in df.iterrows():
            g_date = row['date']
            is_past = g_date < today
            status = "PAST (MISSING?)" if is_past else "FUTURE (SCHEDULED)"
            
            home = team_map.get(row['home_team_id'], "Unknown")
            vis = team_map.get(row['visitor_team_id'], "Unknown")
            
            f.write(f"[{status}] ID: {row['game_id']} Date: {g_date} | {home} vs {vis}\n")
    print("Output written to missing_games.txt")

if __name__ == "__main__":
    inspect_missing()


import sqlite3
import pandas as pd
from game_logic import GameReconstructor

def main():
    conn = sqlite3.connect("hockey_stats.db")
    
    # Load all data
    games = pd.read_sql_query("SELECT * FROM DimGame", conn)
    goals = pd.read_sql_query("SELECT * FROM FactGoals", conn)
    penalties = pd.read_sql_query("SELECT * FROM FactPenalties", conn)
    teams = pd.read_sql_query("SELECT * FROM DimTeam", conn)
    
    # Team Mapping
    team_map = dict(zip(teams['team_id'], teams['team_name']))
    
    reconstructor = GameReconstructor()
    
    # Aggregators
    # key: TeamName -> {pdf_g, pdf_att, rec_g, rec_att}
    agg = {}
    
    print(f"Analyzing {len(games)} games...")
    
    for _, row in games.iterrows():
        g_id = row['game_id']
        hid = row['home_team_id']
        vid = row['visitor_team_id']
        
        h_name = team_map.get(hid, "Unknown")
        v_name = team_map.get(vid, "Unknown")
        
        # Init agg
        for t in [h_name, v_name]:
            if t not in agg: agg[t] = {'pdf_g': 0, 'pdf_att': 0, 'rec_g': 0, 'rec_att': 0}
            
        # 1. PDF Stats (Official)
        # Note: DimGame stores integers usually.
        agg[h_name]['pdf_g'] += row.get('pp_goals_home', 0)
        agg[h_name]['pdf_att'] += row.get('pp_attempts_home', 0)
        
        agg[v_name]['pdf_g'] += row.get('pp_goals_visitor', 0)
        agg[v_name]['pdf_att'] += row.get('pp_attempts_visitor', 0)
        
        # 2. Reconstructed Stats
        g_goals = goals[goals['game_id'] == g_id]
        g_pens = penalties[penalties['game_id'] == g_id]
        
        rec = reconstructor.reconstruct_game_stats(g_id, g_goals, g_pens, hid, vid)
        
        agg[h_name]['rec_g'] += rec['pp_g_home']
        agg[h_name]['rec_att'] += rec['pp_att_home']
        
        agg[v_name]['rec_g'] += rec['pp_g_vis']
        agg[v_name]['rec_att'] += rec['pp_att_vis']
        
    conn.close()
    
    # Prepare comparison table
    results = []
    for team, stats in agg.items():
        pdf_pct = (stats['pdf_g'] / stats['pdf_att'] * 100) if stats['pdf_att'] > 0 else 0
        rec_pct = (stats['rec_g'] / stats['rec_att'] * 100) if stats['rec_att'] > 0 else 0
        
        diff = rec_pct - pdf_pct
        
        results.append({
            'Team': team,
            'PDF (G/Att)': f"{stats['pdf_g']}/{stats['pdf_att']}",
            'PDF %': pdf_pct,
            'Rec (G/Att)': f"{stats['rec_g']}/{stats['rec_att']}",
            'Rec %': rec_pct,
            'Delta %': diff
        })
        
    df_res = pd.DataFrame(results)
    
    # Sort by absolute delta to find biggest discrepancies
    df_res['AbsDelta'] = df_res['Delta %'].abs()
    df_res = df_res.sort_values(by='AbsDelta', ascending=False)
    
    print("\n--- COMPARISON: PDF (Official) vs RECONSTRUCTED (Events) ---")
    print(df_res[['Team', 'PDF (G/Att)', 'PDF %', 'Rec (G/Att)', 'Rec %', 'Delta %']].head(20).to_string(index=False))
    
if __name__ == "__main__":
    main()

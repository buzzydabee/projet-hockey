import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Hockey Stats Dashboard", layout="wide")

DB_NAME = "hockey_stats.db"

# French Month Map
MONTHS_MAP = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12
}

def parse_french_date(date_str):
    if not isinstance(date_str, str): return None
    try:
        parts = date_str.lower().split()
        if len(parts) >= 3:
            d = int(parts[0])
            m = MONTHS_MAP.get(parts[1], 1)
            y = int(parts[2])
            return datetime(y, m, d)
    except:
        pass
    return None

def load_data():
    conn = sqlite3.connect(DB_NAME)
    
    # Games (Enhanced)
    games = pd.read_sql_query('''
        SELECT g.*, t1.team_name as home, t2.team_name as visitor
        FROM DimGame g
        JOIN DimTeam t1 ON g.home_team_id = t1.team_id
        JOIN DimTeam t2 ON g.visitor_team_id = t2.team_id
    ''', conn)
    
    # Goals
    goals = pd.read_sql_query('''
        SELECT g.game_id, g.team_id, g.period, g.time, t.team_name, p.player_name, p.jersey_number, g.player_jersey, g.assist1_jersey, g.assist2_jersey
        FROM FactGoals g
        JOIN DimTeam t ON g.team_id = t.team_id
        LEFT JOIN DimPlayer p ON g.team_id = p.team_id AND g.player_jersey = p.jersey_number
    ''', conn)
    
    # Penalties
    penalties = pd.read_sql_query('''
        SELECT p.game_id, p.team_id, p.period, p.time, t.team_name, pl.player_name, p.code, p.duration, p.player_jersey
        FROM FactPenalties p
        JOIN DimTeam t ON p.team_id = t.team_id
        LEFT JOIN DimPlayer pl ON p.team_id = pl.team_id AND p.player_jersey = pl.jersey_number
    ''', conn)
    
    conn.close()
    return games, goals, penalties

def calculate_standings(games, penalties):
    # Get all teams
    all_teams = sorted(list(set(games['home']) | set(games['visitor'])))
    
    stats = []
    
    for team in all_teams:
        t_games = games[(games['home'] == team) | (games['visitor'] == team)]
        
        # Penalties
        t_pens = penalties[penalties['team_name'] == team]
        pim = 0
        for d in t_pens['duration']:
             if d:
                 try: pim += int(d.split(':')[0])
                 except: pass
        
        # Init
        s = {
            'Team': team, 'GP': len(t_games), 'W': 0, 'L': 0, 'T': 0, 
            'PTS': 0, 'GF': 0, 'GA': 0, 'FJ': 0,
            'PP_G': 0, 'PP_Att': 0, 'PK_Kills': 0, 'PK_Att': 0
        }
        
        if len(t_games) == 0:
            continue

        for _, row in t_games.iterrows():
            is_home = (row['home'] == team)
            
            s_us = row['final_score_home'] if is_home else row['final_score_visitor']
            s_them = row['final_score_visitor'] if is_home else row['final_score_home']
            
            s['GF'] += s_us
            s['GA'] += s_them
            
            # Record
            if s_us > s_them:
                s['W'] += 1
            elif s_us < s_them:
                s['L'] += 1
            else:
                s['T'] += 1
            
            # Fair Play (1 pt per game)
            fp = row['fair_play_home'] if is_home else row['fair_play_visitor']
            s['FJ'] += fp
            
            # Special Teams
            # Our PP
            s['PP_G'] += (row['pp_goals_home'] if is_home else row['pp_goals_visitor'])
            s['PP_Att'] += (row['pp_attempts_home'] if is_home else row['pp_attempts_visitor'])
            
            # Our PK (Opponent PP)
            opp_pp_g = (row['pp_goals_visitor'] if is_home else row['pp_goals_home'])
            opp_pp_att = (row['pp_attempts_visitor'] if is_home else row['pp_attempts_home'])
            s['PK_Att'] += opp_pp_att
            s['PK_Kills'] += (opp_pp_att - opp_pp_g)

        # Points Formula: W*2 + T*1 + FJ
        s['PTS'] = (s['W'] * 2) + (s['T'] * 1) + s['FJ']
        
        # Percentages
        s['PP%'] = round((s['PP_G'] / s['PP_Att'] * 100) if s['PP_Att'] > 0 else 0, 1)
        s['PK%'] = round((s['PK_Kills'] / s['PK_Att'] * 100) if s['PK_Att'] > 0 else 0, 1)
        # Format string "A/B"
        s['PP'] = f"{s['PP_G']}/{s['PP_Att']}"
        s['PK'] = f"{s['PK_Kills']}/{s['PK_Att']}"
        s['PIM'] = pim
        
        stats.append(s)
        
    df = pd.DataFrame(stats)
    # Sort by PTS desc
    if not df.empty:
        df = df.sort_values(by=['PTS', 'W', 'GF'], ascending=False).reset_index(drop=True)
        df.index += 1
    return df

def parse_time_to_seconds(period, time_str):
    try:
        parts = time_str.split(':')
        minutes = int(parts[0])
        seconds = int(parts[1])
        # Assumption: 20 minute periods
        p = int(period)
        return (p - 1) * 1200 + minutes * 60 + seconds
    except:
        return 0

def calculate_player_stats(games, goals, penalties, players):
    # Map key -> name
    # We need a robust mapping. 
    # players is a DF from DimPlayer.
    
    # Helper to get name
    def get_player_name(team_id, jersey):
        j_str = str(jersey).strip()
        # Direct Match
        row = players[(players['team_id'] == team_id) & (players['jersey_number'] == j_str)]
        if not row.empty:
            return row.iloc[0]['player_name'], row.iloc[0]['team_id']
            
        # Int Match
        if j_str.isdigit():
             for _, p_row in players[players['team_id'] == team_id].iterrows():
                pj = str(p_row['jersey_number']).strip()
                if pj.isdigit() and int(pj) == int(j_str):
                    return p_row['player_name'], p_row['team_id']
        return None, None

    # Stats Dict: Key = (Name, TeamId) -> for uniqueness across teams?
    # Or just Name if unique. Let's use Name for display, but track by Team internally?
    # User file uses Name.
    p_stats = {}
    
    def ensure(name, team, team_name):
        key = (name, team)
        if key not in p_stats:
            p_stats[key] = {
                'Name': name, 'Team': team_name, 'MJ': set(),
                'B': 0, 'A': 0, 'PTS': 0, 'PEM': 0,
                'BAN': 0, 'AAN': 0, 'PTS_AN': 0,
                'BIN': 0, 'AID': 0, 'PTS_IN': 0,
                'BG': 0, 'BE': 0
            }
        return key

    # We iterate GAMES
    for _, game in games.iterrows():
        g_id = game['game_id']
        g_goals = goals[goals['game_id'] == g_id].sort_values(by=['period', 'time'])
        g_pens = penalties[penalties['game_id'] == g_id]
        
        # Determine Winner logic
        final_h = game['final_score_home']
        final_v = game['final_score_visitor']
        winner_id = None
        target_score = 0
        if final_h > final_v:
            winner_id = game['home_team_id']
            target_score = final_v + 1
        elif final_v > final_h:
            winner_id = game['visitor_team_id']
            target_score = final_h + 1
            
        home_curr = 0
        vis_curr = 0
        
        for _, goal in g_goals.iterrows():
            # Get Context
            goal_time = parse_time_to_seconds(goal['period'], goal['time'])
            
            # Players involved
            tid = goal['team_id']
            t_name = goal['team_name']
            
            p1_name, _ = get_player_name(tid, goal['player_jersey'])
            p2_name, _ = get_player_name(tid, goal['assist1_jersey']) if goal['assist1_jersey'] else (None,None)
            p3_name, _ = get_player_name(tid, goal['assist2_jersey']) if goal['assist2_jersey'] else (None,None)
            
            k1 = ensure(p1_name, tid, t_name) if p1_name else None
            k2 = ensure(p2_name, tid, t_name) if p2_name else None
            k3 = ensure(p3_name, tid, t_name) if p3_name else None
            
            # Basic Stats
            if k1: 
                p_stats[k1]['B'] += 1; p_stats[k1]['PTS'] += 1; p_stats[k1]['MJ'].add(g_id)
            if k2: 
                p_stats[k2]['A'] += 1; p_stats[k2]['PTS'] += 1; p_stats[k2]['MJ'].add(g_id)
            if k3: 
                p_stats[k3]['A'] += 1; p_stats[k3]['PTS'] += 1; p_stats[k3]['MJ'].add(g_id)
                
            # Special Teams
            pen_home_count = 0
            pen_vis_count = 0
            for _, pen in g_pens.iterrows():
                start = parse_time_to_seconds(pen['period'], pen['time'])
                try: 
                    d_str = pen['duration'].split(':') # "2:00"
                    dur = int(d_str[0])*60 + int(d_str[1])
                except: dur = 120
                if start <= goal_time < start + dur:
                    if pen['team_id'] == game['home_team_id']: pen_home_count += 1
                    else: pen_vis_count += 1
            
            is_home_goal = (tid == game['home_team_id'])
            us = pen_home_count if is_home_goal else pen_vis_count
            them = pen_vis_count if is_home_goal else pen_home_count
            
            if them > us: # PP
                if k1: p_stats[k1]['BAN'] += 1; p_stats[k1]['PTS_AN'] += 1
                if k2: p_stats[k2]['AAN'] += 1; p_stats[k2]['PTS_AN'] += 1
                if k3: p_stats[k3]['AAN'] += 1; p_stats[k3]['PTS_AN'] += 1
            elif us > them: # SH
                if k1: p_stats[k1]['BIN'] += 1; p_stats[k1]['PTS_IN'] += 1
                if k2: p_stats[k2]['AID'] += 1; p_stats[k2]['PTS_IN'] += 1
                if k3: p_stats[k3]['AID'] += 1; p_stats[k3]['PTS_IN'] += 1
                
            # Situational (BG/BE)
            if is_home_goal:
                prev_h = home_curr; prev_v = vis_curr
                home_curr += 1
                # BE
                if prev_h < prev_v and home_curr == prev_v:
                     if k1: p_stats[k1]['BE'] += 1
                # BG
                if winner_id == tid and home_curr == target_score:
                     if k1: p_stats[k1]['BG'] += 1
            else:
                prev_h = home_curr; prev_v = vis_curr
                vis_curr += 1
                # BE
                if prev_v < prev_h and vis_curr == prev_h:
                     if k1: p_stats[k1]['BE'] += 1
                # BG
                if winner_id == tid and vis_curr == target_score:
                     if k1: p_stats[k1]['BG'] += 1

    # Penalties
    for _, pen in penalties.iterrows():
        name, tid = get_player_name(pen['team_id'], pen['player_jersey'])
        if name:
             k = ensure(name, tid, pen['team_name'])
             try: mins = int(pen['duration'].split(':')[0])
             except: mins = 0
             p_stats[k]['PEM'] += mins
             p_stats[k]['MJ'].add(pen['game_id'])

    # Finalize
    res = []
    for k, v in p_stats.items():
        row = v.copy()
        row['MJ'] = len(row['MJ']) # Convert set to count
        # PEM/MJ
        row['PEM/MJ'] = round(row['PEM']/row['MJ'], 2) if row['MJ'] else 0
        # PTS/MJ
        row['PTS/MJ'] = round(row['PTS']/row['MJ'], 2) if row['MJ'] else 0
        res.append(row)
    
    return pd.DataFrame(res)

def calculate_goalie_stats(conn, filtered_game_ids=None):
    # Fetch data
    query = '''
    SELECT 
        gs.*, 
        g.final_score_home, g.final_score_visitor, 
        g.home_team_id, g.visitor_team_id,
        t.team_name,
        p.player_name
    FROM FactGoalieStats gs
    JOIN DimGame g ON gs.game_id = g.game_id
    JOIN DimTeam t ON gs.team_id = t.team_id
    LEFT JOIN DimPlayer p ON gs.team_id = p.team_id AND gs.player_jersey = p.jersey_number
    '''
    df = pd.read_sql_query(query, conn)
    
    # Filter by date/games
    if filtered_game_ids is not None:
        df = df[df['game_id'].isin(filtered_game_ids)]
    
    res = {}
    
    for _, row in df.iterrows():
        # Name resolution
        name = row['player_name']
        if not name: name = f"#{row['player_jersey']} ({row['team_name']})"
        
        # Team
        team = row['team_name']
        
        # Init
        if name not in res:
            res[name] = {
                'Name': name, 'Team': team,
                'MJ': 0, 'MA': 0, 'V': 0, 'D': 0, 'N': 0, 'BL': 0,
                'BC': 0, 'Shots': 0, 'TG': 0.0
            }
            
        # Minutes
        try: mins = float(row['minutes_played'])
        except: mins = 0.0
        
        if mins > 0:
            res[name]['MJ'] += 1
            res[name]['TG'] += mins
            res[name]['BC'] += row['goals_against']
            res[name]['Shots'] += row['shots_against']
            res[name]['MA'] += 1 # Assumption: if played, started?
            
            # Record
            is_home = (row['team_id'] == row['home_team_id'])
            s_us = row['final_score_home'] if is_home else row['final_score_visitor']
            s_them = row['final_score_visitor'] if is_home else row['final_score_home']
            
            if mins > 20: # Decision rule
                if s_us > s_them: res[name]['V'] += 1
                elif s_us < s_them: res[name]['D'] += 1
                else: res[name]['N'] += 1
                
            if row['goals_against'] == 0 and mins >= 44:
                 res[name]['BL'] += 1

    # Finalize
    finals = []
    for k, v in res.items():
        # GAA
        v['Moy'] = round((v['BC'] * 45) / v['TG'], 2) if v['TG'] > 0 else 0.0
        # Save %
        saves = v['Shots'] - v['BC']
        v['%Arr'] = round(saves / v['Shots'], 3) if v['Shots'] > 0 else 0.0
        # Time format
        m = int(v['TG'])
        s = int((v['TG'] - m) * 60)
        v['TG_str'] = f"{m}:{s:02d}"
        finals.append(v)
        
    return pd.DataFrame(finals)

def main():
    st.title("🏒 Hockey Stats Dashboard")
    
    conn = None
    try:
        games, goals, penalties = load_data()
        
        # Need Players table too for name resolution
        conn = sqlite3.connect(DB_NAME)
        players = pd.read_sql_query("SELECT * FROM DimPlayer", conn)
        
    except Exception as e:
        st.error(f"Error loading database: {e}")
        return

    # --- DATE PARSING ---
    # Convert date strings to datetime objects for filtering
    games['date_dt'] = games['date'].apply(parse_french_date)
    # Remove invalid dates if any
    games = games.dropna(subset=['date_dt'])
    
    if not games.empty:
        min_date = games['date_dt'].min().date()
        max_date = games['date_dt'].max().date()
    else:
        min_date = datetime.now().date()
        max_date = datetime.now().date()

    # --- SIDEBAR FILTERS ---
    st.sidebar.header("Filters")
    
    # 1. Team Filter
    all_teams = sorted(list(set(games['home']) | set(games['visitor'])))
    selected_team = st.sidebar.selectbox("Select Team", ["All Teams"] + all_teams)
    
    # 2. Date Filter
    st.sidebar.divider()
    st.sidebar.subheader("Date Range")
    
    # Defaults to full range
    # Defaults to full range
    start_date, end_date = st.sidebar.slider(
        "Select Date Range",
        min_value=min_date,
        max_value=max_date,
        value=(min_date, max_date),
        format="DD MMM YYYY"
    )
    
    # --- FILTER DATA ---
    # Filter Games
    mask_date = (games['date_dt'].dt.date >= start_date) & (games['date_dt'].dt.date <= end_date)
    games = games[mask_date]
    valid_game_ids = games['game_id'].unique()
    
    # Filter Related Tables
    goals = goals[goals['game_id'].isin(valid_game_ids)]
    penalties = penalties[penalties['game_id'].isin(valid_game_ids)]
    
    # 3. Player Filter (for Advanced Player Stats)
    st.sidebar.divider()
    
    # --- DATA MANAGEMENT ---
    st.sidebar.header("Data Management")
    if st.sidebar.button("Check for Missing Games"):
        with st.spinner("Checking website for new games... (Browser may open)"):
            import subprocess
            try:
                # Run Download
                result_dl = subprocess.run(["python", "download_game_sheets.py"], capture_output=True, text=True)
                st.sidebar.success("Download check complete.")
                if result_dl.stdout:
                    with st.sidebar.expander("Download Log"):
                        st.text(result_dl.stdout)
                
                # Run Process
                with st.spinner("Processing new files..."):
                    result_proc = subprocess.run(["python", "process_gamesheets.py"], capture_output=True, text=True)
                    st.sidebar.success("Database updated.")
                    if result_proc.stdout:
                         with st.sidebar.expander("Processing Log"):
                             st.text(result_proc.stdout)
                             
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Error: {e}")

    if st.sidebar.button("Rebuild Database (Local PDFs Only)"):
        with st.spinner("Rebuilding database from local files..."):
            import subprocess
            try:
                # Run Process Script Only (It deletes DB first)
                result_rebuild = subprocess.run(["python", "process_gamesheets.py"], capture_output=True, text=True)
                st.sidebar.success("Database Rebuilt!")
                if result_rebuild.stdout:
                    with st.sidebar.expander("Rebuild Log"):
                        st.text(result_rebuild.stdout)
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Error rebuilding: {e}")
    
    # --- STANDINGS ---
    st.header("League Standings")
    standings = calculate_standings(games, penalties)
    
    cols_to_show = ['Team', 'PTS', 'GP', 'W', 'L', 'T', 'FJ', 'GF', 'GA', 'PP%', 'PK%', 'PIM']  # Simplified view
    st.dataframe(standings[cols_to_show], use_container_width=True)
    
    # --- GOALIE STATS ---
    st.header("Goalie Stats")
    gdf = calculate_goalie_stats(conn, valid_game_ids)
    if selected_team != "All Teams":
        gdf = gdf[gdf['Team'] == selected_team]
    
    if not gdf.empty:
        gdf = gdf.sort_values(by=['Moy', 'MJ'], ascending=[True, False]).reset_index(drop=True)
        gdf.index += 1
        cols = ['Name', 'Team', 'MJ', 'V', 'D', 'N', 'BL', 'BC', 'Shots', 'Moy', '%Arr', 'TG_str']
        st.dataframe(gdf[cols], use_container_width=True)
    else:
        st.info("No goalie stats available (or no games parsed for this team)")
        
    conn.close()

    # --- ADVANCED PLAYER STATS ---
    st.header("Advanced Player Stats")
    # Calculate for ALL (expensive?) or filtered?
    p_df = calculate_player_stats(games, goals, penalties, players)
    
    if selected_team != "All Teams":
        p_df = p_df[p_df['Team'] == selected_team]
        
    # Player Filter Widget
    # Now that p_df is calculated (based on filtered dates), we can list players.
    all_player_names = sorted(p_df['Name'].unique())
    selected_players = st.sidebar.multiselect("Filter Players", all_player_names)
    
    if selected_players:
        p_df = p_df[p_df['Name'].isin(selected_players)]
        
    # Sort by PTS
    if not p_df.empty:
        p_df = p_df.sort_values(by=['PTS', 'B', 'MJ'], ascending=False).reset_index(drop=True)
        p_df.index += 1
        
        # Reorder columns to match request roughly: MJ B A PTS PEM BAN AAN PTS_AN BIN AID PTS_IN BG BE
        cols = ['Name', 'Team', 'MJ', 'B', 'A', 'PTS', 'PEM', 'PEM/MJ', 'PTS/MJ', 
                'BAN', 'AAN', 'PTS_AN', 'BIN', 'AID', 'PTS_IN', 'BG', 'BE']
        st.dataframe(p_df[cols], use_container_width=True)
    else:
        st.info("No player stats found.")


    # --- TEAM METRICS ---
    if selected_team != "All Teams":
        st.divider()
        st.header(f"Team: {selected_team}")
        
        # Filter Data
        games_filtered = games[(games['home'] == selected_team) | (games['visitor'] == selected_team)]
        goals_filtered = goals[goals['team_name'] == selected_team]
        penalties_filtered = penalties[penalties['team_name'] == selected_team]
        
        team_row = standings[standings['Team'] == selected_team].iloc[0]
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Points", team_row['PTS'])
        c2.metric("Record (W-L-T)", f"{team_row['W']}-{team_row['L']}-{team_row['T']}")
        c3.metric("Goals For", team_row['GF'])
        c4.metric("Goals Against", team_row['GA'])
        
        c5, c6, c7, c8 = st.columns(4)
        c5.metric("PP %", f"{team_row['PP%']}% ({team_row['PP']})")
        c6.metric("PK %", f"{team_row['PK%']}% ({team_row['PK']})")
        c7.metric("Avg PIM/Game", round(team_row['PIM'] / team_row['GP'], 1) if team_row['GP'] else 0) 
 
        c8.metric("Fair Play Pts", team_row['FJ'])
        
        # TABS
        tab1, tab2, tab3 = st.tabs(["Game Log", "Penalties", "Raw Goals"])
        
        with tab1:
            st.subheader("Game Log")
            # Show relevant columns
            log_cols = ['date', 'home', 'visitor', 'final_score_home', 'final_score_visitor', 'arena']
            st.dataframe(games_filtered[log_cols].sort_values(by='date', ascending=False), use_container_width=True)

        with tab2:
            st.subheader("Penalties")
            st.dataframe(penalties_filtered, use_container_width=True)
            
        with tab3:
             st.dataframe(goals_filtered)

if __name__ == "__main__":
    main()

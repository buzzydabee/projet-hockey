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
        s['PK'] = f"{s['PK_Kills']}/{s['PK_Att']}"
        s['PIM'] = pim
        s['DIFF'] = s['GF'] - s['GA']
        
        stats.append(s)
        
    cols_to_show = ['Team', 'PTS', 'GP', 'W', 'L', 'T', 'FJ', 'GF', 'GA', 'DIFF', 'PP%', 'PK%', 'PIM']
    
    # Return empty if needed
    if not stats:
        return pd.DataFrame(columns=cols_to_show + ['PP', 'PK', 'PP_G', 'PP_Att', 'PK_Att', 'PK_Kills'])

    df = pd.DataFrame(stats)
    # Sort by PTS desc
    if not df.empty:
        df = df.sort_values(by=['PTS', 'W', 'GF'], ascending=False).reset_index(drop=True)
        df.index += 1
    return df

# ... (main function context)

    # --- STANDINGS ---
    st.header("League Standings")
    
    if not selected_teams:
        st.warning("Please select at least one team to view stats.")
        cols_to_show = ['Team', 'PTS', 'GP', 'W', 'L', 'T', 'FJ', 'GF', 'GA', 'PP%', 'PK%', 'PIM']
        st.dataframe(pd.DataFrame(columns=cols_to_show), use_container_width=True)
    else:
        # Filter for Standings based on SELECTED TEAMS
        # Logic: Show standings for games involving ANY of the selected teams.
        standings_games = games
        standings_penalties = penalties
        
        # Only filter if we haven't selected ALL teams (optimization)
        if len(selected_teams) < len(all_teams):
            # Keep games where Home OR Visitor is in the selection
            standings_games = games[games['home'].isin(selected_teams) | games['visitor'].isin(selected_teams)]
            s_ids = standings_games['game_id'].unique()
            standings_penalties = penalties[penalties['game_id'].isin(s_ids)]
            
        standings = calculate_standings(standings_games, standings_penalties)
        
        # If we selected specific teams, we probably only want to SEE those teams in the table?
        # Or do we want to see their opponents too?
        # Usually "Filter by Team" implies "Show me rows for these teams".
        # Let's filter the FINAL standings dataframe to only show selected teams rows.
        if not standings.empty:
             standings = standings[standings['Team'].isin(selected_teams)]
    
        cols_to_show = ['Team', 'PTS', 'GP', 'W', 'L', 'T', 'FJ', 'GF', 'GA', 'PP%', 'PK%', 'PIM']  # Simplified view
        st.dataframe(standings[cols_to_show], use_container_width=True)

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
                'B': 0, 'A': 0, 'PTS': 0, 'PEM': 0, 'PUN': 0,
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
             p_stats[k]['PUN'] += 1
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

# Divisions Map (To be populated)
DIVISIONS = {
    "Division Est": [
        "AIGLES CBIO", "WAPITIS CHARLESBOURG", "BÉLIERS QUÉBEC-CENTRE", 
        "RADISSON QUÉBEC-CENTRE", "BOUCS QUÉBEC-CENTRE", "ÉPERVIERS BEAUPORT", 
        "CARIBOUS CHARLESBOURG", "BUCKS CHARLESBOURG", "PHÉNIX CBIO", 
        "FAUCONS BEAUPORT", "FAUCONS", # Handling variations
        "RICHELIEU QUÉBEC-CENTRE", "RICHELIEU", 
        "PATRIOTES QUÉBEC-CENTRE", "PATRIOTES  QUÉBEC-CENTRE" # Double space variation
    ], 
    "Division Ouest": [
        "ROYAUX 1 CRSA", "GOUVERNEURS 2 SFSAL", "DIABLOS DPR 1", "DIABLOS DPR",
        "GOUVERNEURS 3 SFSAL", "DIABLOS DPR 2", "LYNX SAINT-RAYMOND 1", "LYNX SAINT-RAYMOND",
        "GOUVERNEURS 4 SFSAL", "LYNX SAINT-RAYMOND 2", "CHEVALIERS 1 VBVC", 
        "GOUVERNEURS 1 SFSAL", "ROYAUX 2 CRSA", "CHEVALIERS 2 VBVC"
    ]
}

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

    # --- CSS HACK FOR COMPACT INSTANCE ---
    st.markdown("""
    <style>
        /* Force smaller font in dataframes */
        [data-testid="stDataFrame"] {
            font-size: 13px !important;
        }
        /* Compacting Rows */
        div[data-testid="stDataFrame"] div[role="gridcell"] {
            padding-top: 2px !important;
            padding-bottom: 2px !important;
            line-height: 1.1 !important;
            min-height: 25px !important; 
        }
        div[data-testid="stDataFrame"] div[role="row"] {
            min-height: 25px !important;
        }
        
        /* Force Centering of Headers and Cells */
        div[data-testid="stDataFrame"] div[role="columnheader"] > div, 
        div[data-testid="stDataFrame"] div[role="gridcell"] > div {
            display: flex !important;
            justify-content: center !important;
            text-align: center !important;
        }
        
        /* Ensure the text itself is centered */
        div[data-testid="stDataFrame"] div[role="gridcell"] p,
        div[data-testid="stDataFrame"] div[role="columnheader"] p {
             text-align: center !important;
        }

        /* Exception: Team Name (First Column) usually should be Left, but 
           CSS nth-child is tricky with virtual scroll. 
           We accept centered Team Names for now to guarantee stats are centered. */
    </style>
    """, unsafe_allow_html=True)
    
    # Theme Check Warning (Removed as it is active)
    # if st.get_option("theme.primaryColor") != "#00A8E8":
    #    st.warning("⚠️ Pour voir le nouveau thème 'Bleu Glace', veuillez redémarrer l'application dans le terminal (Ctrl+C puis relancez).")

    # --- SIDEBAR FILTERS ---
    st.sidebar.header("Filtres")
    
    # 1. Team Selection
    all_teams = sorted(list(set(games['home']) | set(games['visitor'])))
    
    filter_mode = st.sidebar.radio("Mode de Sélection", ["Toutes les équipes", "Par Division", "Sélection Personnalisée"])
    
    selected_teams = []
    
    if filter_mode == "Toutes les équipes":
        selected_teams = all_teams
        st.sidebar.info(f"Affichage de {len(all_teams)} équipes")
        
    elif filter_mode == "Par Division":
        div = st.sidebar.selectbox("Choisir la Division", list(DIVISIONS.keys()))
        if div:
            selected_teams = [t for t in DIVISIONS[div] if t in all_teams]
            if not selected_teams:
                st.sidebar.warning(f"Aucune équipe trouvée pour {div}")
            else:
                st.sidebar.success(f"{len(selected_teams)} équipes dans {div}")
                
    elif filter_mode == "Sélection Personnalisée":
        selected_teams = st.sidebar.multiselect("Choisir les Équipes", all_teams, default=all_teams[:1])
    
    # --- STATS MODE ---
    stats_mode = st.sidebar.radio("Mode de Calcul", ["Stats Globales", "Un contre tous", "Face-à-Face"])

    # 2. Date Filter
    st.sidebar.divider()
    st.sidebar.subheader("Période")
    
    # Defaults to full range
    start_date, end_date = st.sidebar.slider(
        "Choisir la plage de dates",
        min_value=min_date,
        max_value=max_date,
        value=(min_date, max_date),
        format="DD MMM YYYY"
    )
    
    # --- FILTER DATA ---
    # Filter Games by Date
    mask_date = (games['date_dt'].dt.date >= start_date) & (games['date_dt'].dt.date <= end_date)
    games = games[mask_date]
    
    
    if stats_mode == "Face-à-Face":
        if len(selected_teams) < 2:
            st.warning("Le mode Face-à-Face requiert au moins 2 équipes sélectionnées.")
            # Fallback to empty
            games = pd.DataFrame(columns=games.columns)
        else:
            # Keep games where BOTH teams are in selection
            games = games[games['home'].isin(selected_teams) & games['visitor'].isin(selected_teams)]
            
    elif stats_mode == "Un contre tous":
        # Keep games where ANY selected team is involved
        games = games[games['home'].isin(selected_teams) | games['visitor'].isin(selected_teams)]
    
    valid_game_ids = games['game_id'].unique()
    
    # Filter Related Tables by Date
    goals = goals[goals['game_id'].isin(valid_game_ids)]
    penalties = penalties[penalties['game_id'].isin(valid_game_ids)]
    
    # 3. Player Filter (for Advanced Player Stats) - Moved down after Team Filter logic if needed? 
    # Actually we need filtered player list primarily for the multiselect widget which is below.
    
    # --- DATA MANAGEMENT ---
    st.sidebar.header("Gestion des Données")
    if st.sidebar.button("Vérifier nouveaux matchs"):
        with st.spinner("Vérification en cours... (Le navigateur peut s'ouvrir)"):
            import subprocess
            try:
                # Run Download
                result_dl = subprocess.run(["python", "download_game_sheets.py"], capture_output=True, text=True)
                st.sidebar.success("Vérification terminée.")
                if result_dl.stdout:
                    with st.sidebar.expander("Journal de téléchargement"):
                        st.text(result_dl.stdout)
                
                # Run Process
                with st.spinner("Traitement des nouveaux fichiers..."):
                    result_proc = subprocess.run(["python", "process_gamesheets.py"], capture_output=True, text=True)
                    st.sidebar.success("Base de données mise à jour.")
                    if result_proc.stdout:
                         with st.sidebar.expander("Journal de traitement"):
                             st.text(result_proc.stdout)
                             
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Erreur: {e}")

    if st.sidebar.button("Reconstruire la BD (Local)"):
        with st.spinner("Reconstruction de la base de données..."):
            import subprocess
            try:
                # Run Process Script Only (It deletes DB first)
                result_rebuild = subprocess.run(["python", "process_gamesheets.py"], capture_output=True, text=True)
                st.sidebar.success("Base de données reconstruite!")
                if result_rebuild.stdout:
                    with st.sidebar.expander("Journal de reconstruction"):
                        st.text(result_rebuild.stdout)
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Erreur de reconstruction: {e}")
    
    # --- STANDINGS ---
    # Custom Toggle to keep Button on Right BUT Content Full Width
    if 'leg_standings' not in st.session_state: st.session_state.leg_standings = False
    
    c_title, c_legend = st.columns([0.85, 0.15])
    with c_title:
        st.header("Classement Général")
    with c_legend:
        if st.button("Légende 📝", key="btn_leg_standings"):
            st.session_state.leg_standings = not st.session_state.leg_standings
    
    if st.session_state.leg_standings:
         with st.container():
             l1, l2, l3 = st.columns(3)
             with l1:
                 st.markdown("""<div style="font-size: 13px; line-height: 1.4;">
                 <strong>Général</strong><br>
                 <b>MJ</b>: Matchs joués, <b>V</b>: Victoires<br>
                 <b>D</b>: Défaites, <b>N</b>: Nulles<br>
                 <b>PTS</b>: Points
                 </div>""", unsafe_allow_html=True)
             with l2:
                 st.markdown("""<div style="font-size: 13px; line-height: 1.4;">
                 <strong>Buts</strong><br>
                 <b>BP</b>: Pour, <b>BC</b>: Contre<br>
                 <b>DIFF</b>: Différentiel, <b>FJ</b>: Franc-jeu
                 </div>""", unsafe_allow_html=True)
             with l3:
                 st.markdown("""<div style="font-size: 13px; line-height: 1.4;">
                 <strong>Spécial</strong><br>
                 <b>%AN</b>: % Av. Num., <b>%DN</b>: % Dés. Num.<br>
                 <b>PUN</b>: Punitions (min)
                 </div>""", unsafe_allow_html=True)
             st.markdown("---")
    
    # Filter for Standings based on SELECTED TEAMS
    # Logic: Show standings for games involving ANY of the selected teams.
    standings_games = games
    standings_penalties = penalties
    
    # Only filter if we haven't selected ALL teams (optimization)
    # BUT in "Un contre tous", games is already filtered, so we can pass it directly.
    # The optimization below is mainly for Global mode.
    # If stats_mode != 'Un contre tous' and len...
    
    standings = calculate_standings(standings_games, standings_penalties)
    
    # DISPLAY FILTERING
    # If "Globales" or "Face-à-Face", we usually only show the selected teams.
    # If "Un contre tous", we show selected teams AND their opponents (so, everyone in the standings_games).
    if not standings.empty:
         if stats_mode != "Un contre tous":
             standings = standings[standings['Team'].isin(selected_teams)]
             
         standings = standings.reset_index(drop=True)
         standings.index += 1
         
         # RENAME COLUMNS FOR DISPLAY
         standings = standings.rename(columns={
             'Team': 'Équipe', 'GP': 'MJ', 'W': 'V', 'L': 'D', 'T': 'N',
             'GF': 'BP', 'GA': 'BC', 'PP%': '%AN', 'PK%': '%DN', 'PIM': 'PUN'
         })
         
         # Force Numeric Types (Fixes Left Alignment issue)
         numeric_cols = ['PTS', 'MJ', 'V', 'D', 'N', 'BP', 'BC', 'DIFF', 'PUN']
         for c in numeric_cols:
             if c in standings.columns:
                 standings[c] = pd.to_numeric(standings[c], errors='coerce').fillna(0)
         
         # Enforce Sort explicitly on the view
         standings = standings.sort_values(by=['PTS', 'V', 'DIFF', 'BP'], ascending=False).reset_index(drop=True)
         standings.index += 1
    else:
         # Create empty with correct columns to avoid KeyError
         standings = pd.DataFrame(columns=['Équipe', 'PTS', 'MJ', 'V', 'D', 'N', 'FJ', 'BP', 'BC', 'DIFF', '%AN', '%DN', 'PUN'])

    cols_to_show = ['Équipe', 'PTS', 'MJ', 'V', 'D', 'N', 'FJ', 'BP', 'BC', 'DIFF', '%AN', '%DN', 'PUN']
    
    if not standings.empty:
        max_pts = max(standings['PTS'].max(), 10)
        
    # STYLING: Center all columns except Team
    # We use pandas Styler to enforce text-align: center
    # Note: Streamlit column_config might override data alignment, but we try our best.
    # Headers need 'th' selector.
    styler_standings = standings[cols_to_show].style.set_properties(
        subset=cols_to_show[1:], # Skip 'Équipe'
        **{'text-align': 'center'}
    ).set_table_styles([
        {'selector': 'th', 'props': [('text-align', 'center !important')]},
        {'selector': 'td', 'props': [('text-align', 'center !important')]}
    ])
    
    st.dataframe(
        styler_standings, 
        use_container_width=True,
        column_config={
            "PTS": st.column_config.ProgressColumn(
                "PTS",
                format="%d",
                min_value=0,
                max_value=int(max_pts),
            ),
            "%AN": st.column_config.NumberColumn(
                "%AN",
                format="%.1f%%"
            ),
            "%DN": st.column_config.NumberColumn(
                "%DN",
                format="%.1f%%"
            )
        }
    )
    
    # --- GOALIE STATS ---
    if 'leg_goalies' not in st.session_state: st.session_state.leg_goalies = False
    
    c_g_title, c_g_leg = st.columns([0.85, 0.15])
    with c_g_title:
        st.header("Statistiques Gardiens")
    with c_g_leg:
        if st.button("Légende 📝", key="btn_leg_goalies"):
            st.session_state.leg_goalies = not st.session_state.leg_goalies
            
    if st.session_state.leg_goalies:
        with st.container():
            g1, g2 = st.columns(2)
            with g1:
                st.markdown("""<div style="font-size: 13px; line-height: 1.4;">
                <b>MJ</b>: Matchs joués, <b>MA</b>: Matchs amorcés<br>
                <b>V</b>: Victoires, <b>D</b>: Défaites, <b>N</b>: Nulles<br>
                <b>DP</b>: Déf. Prol.
                </div>""", unsafe_allow_html=True)
            with g2:
                st.markdown("""<div style="font-size: 13px; line-height: 1.4;">
                <b>BC</b>: Buts contre, <b>Lancers</b>: Tirs (TC)<br>
                <b>%Arr</b>: % d'arrêts, <b>Moy</b>: Moyenne (GAA)<br>
                <b>BL</b>: Blanchissages, <b>TG</b>: Temps de glace
                </div>""", unsafe_allow_html=True)
            st.markdown("---")
            
    gdf = calculate_goalie_stats(conn, valid_game_ids)
    
    # Filter Goalies by Team Selection
    if not gdf.empty:
        if stats_mode != "Un contre tous":
            gdf = gdf[gdf['Team'].isin(selected_teams)]
    
    if not gdf.empty:
        gdf = gdf.sort_values(by=['Moy', 'MJ'], ascending=[True, False]).reset_index(drop=True)
        gdf.index += 1
        
        # Rename Cols
        gdf = gdf.rename(columns={'Name': 'Nom', 'Team': 'Équipe', 'Shots': 'Lancers'})
        
        cols = ['Nom', 'Équipe', 'MJ', 'MA', 'V', 'D', 'N', 'BL', 'BC', 'Lancers', 'Moy', '%Arr', 'TG_str']
        
        # STYLING
        # Center stats columns (Skip Nom, Team)
        stats_cols_g = cols[2:] 
        styler_gdf = gdf[cols].style.set_properties(
            subset=stats_cols_g,
            **{'text-align': 'center'}
        ).set_table_styles([
            {'selector': 'th', 'props': [('text-align', 'center !important')]},
            {'selector': 'td', 'props': [('text-align', 'center !important')]}
        ])
        
        st.dataframe(
            styler_gdf, 
            use_container_width=True,
            column_config={
                 "%Arr": st.column_config.NumberColumn(
                    "%Arr",
                    format="%.3f"
                ),
                "Moy": st.column_config.NumberColumn(
                    "Moy",
                    format="%.2f"
                )
            }
        )
    else:
        st.info("No goalie stats available for selected selection.")
        
    conn.close()

    # --- ADVANCED PLAYER STATS ---
    if 'leg_players' not in st.session_state: st.session_state.leg_players = False
    
    c_p_title, c_p_leg = st.columns([0.85, 0.15])
    with c_p_title:
        st.header("Statistiques Joueurs")
    with c_p_leg:
        if st.button("Légende 📝", key="btn_leg_players"):
            st.session_state.leg_players = not st.session_state.leg_players
            
    if st.session_state.leg_players:
        with st.container():
            p1, p2 = st.columns(2)
            with p1:
                st.markdown("""<div style="font-size: 13px; line-height: 1.4;">
                <strong>Offensif</strong><br>
                <b>MJ</b>: Joués, <b>B</b>: Buts, <b>A</b>: Aides<br>
                <b>PTS</b>: Points, <b>PTS/MJ</b>: Pts/Match<br>
                <b>PEM</b>: Min. Pén., <b>PUN</b>: Nbr Pén.
                </div>""", unsafe_allow_html=True)
            with p2:
                st.markdown("""<div style="font-size: 13px; line-height: 1.4;">
                <strong>Situationnel</strong><br>
                <b>BAN/AAN</b>: Av. Num., <b>PTS AN</b>: Pts AV<br>
                <b>BIN/AID</b>: Dés. Num., <b>PTS IN</b>: Pts DN<br>
                <b>BG/BE</b>: But Gagnant/Égalisateur
                </div>""", unsafe_allow_html=True)
            st.markdown("---")
    # Calculate for ALL (expensive?) or filtered?
    p_df = calculate_player_stats(games, goals, penalties, players)
    
    # Filter Players by Team Selection
    if not p_df.empty:
        if stats_mode != "Un contre tous":
            p_df = p_df[p_df['Team'].isin(selected_teams)]
    
    # Player Filter Widget (specific names)
    if not p_df.empty:
        all_player_names = sorted(p_df['Name'].unique())
        specific_players = st.sidebar.multiselect("Filtrer par Joueur", all_player_names)
        
        if specific_players:
            p_df = p_df[p_df['Name'].isin(specific_players)]
        
    # Sort by PTS
    if not p_df.empty:
        p_df = p_df.sort_values(by=['PTS', 'B', 'MJ'], ascending=False).reset_index(drop=True)
        p_df.index += 1
        
        # Rename Cols
        p_df = p_df.rename(columns={'Name': 'Nom', 'Team': 'Équipe'})
        
        # Reorder columns to match request roughly: MJ B A PTS PEM BAN AAN PTS_AN BIN AID PTS_IN BG BE
        # Reorder columns to match request roughly: MJ B A PTS PEM BAN AAN PTS_AN BIN AID PTS_IN BG BE
        cols = ['Nom', 'Équipe', 'MJ', 'B', 'A', 'PTS', 'PEM', 'PUN', 'PEM/MJ', 'PTS/MJ', 
                'BAN', 'AAN', 'PTS_AN', 'BIN', 'AID', 'PTS_IN', 'BG', 'BE']
        
        # STYLING
        stats_cols_p = cols[2:] # Skip Nom, Equipe
        styler_pdf = p_df[cols].style.set_properties(
            subset=stats_cols_p,
            **{'text-align': 'center'}
        ).set_table_styles([
            {'selector': 'th', 'props': [('text-align', 'center !important')]},
            {'selector': 'td', 'props': [('text-align', 'center !important')]}
        ])
        
        st.dataframe(
            styler_pdf, 
            use_container_width=True,
            column_config={
                "PTS": st.column_config.ProgressColumn(
                    "PTS",
                    help="Points au total",
                    format="%d",
                    min_value=0,
                    max_value=int(max(p_df['PTS'].max(), 1)),
                ),
                "PTS/MJ": st.column_config.NumberColumn(
                    "PTS/MJ",
                    format="%.2f"
                ),
                "PEM/MJ": st.column_config.NumberColumn(
                    "PEM/MJ",
                    format="%.2f"
                ),
                 "Équipe": st.column_config.TextColumn(
                    "Équipe",
                    width="medium"
                )
            }
        )
    else:
        st.info("Aucune statistique de joueur trouvée.")


    # --- TEAM METRICS (Single Team Only) ---
    # Only show detailed breakdown if EXACTLY ONE team is selected
    if len(selected_teams) == 1:
        selected_team = selected_teams[0]
        st.divider()
        st.header(f"Analyse d'Équipe : {selected_team}")
        
        # Filter Data
        games_filtered = games[(games['home'] == selected_team) | (games['visitor'] == selected_team)]
        goals_filtered = goals[goals['team_name'] == selected_team]
        penalties_filtered = penalties[penalties['team_name'] == selected_team]
        
        # Get standing row
        # Note: 'standings' DF now has French columns if calculated above.
        # But we must be careful. Variable 'standings' exists from previous block.
        # It has column 'Équipe' now, not 'Team'.
        
        # Let's re-find the row using FRENCH column names
        t_row = standings[standings['Équipe'] == selected_team]
        if not t_row.empty:
            team_row = t_row.iloc[0]
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Points", team_row['PTS'])
            c2.metric("Fiche (V-D-N)", f"{team_row['V']}-{team_row['D']}-{team_row['N']}")
            c3.metric("Buts Pour", team_row['BP'])
            c4.metric("Buts Contre", team_row['BC'])
            
            c5, c6, c7, c8 = st.columns(4)
            c5.metric("% AN", f"{team_row['%AN']}%")
            c6.metric("% DN", f"{team_row['%DN']}%")
            c7.metric("Punitions/Match", round(team_row['PUN'] / team_row['MJ'], 1) if team_row['MJ'] else 0) 
    
            c8.metric("Points Franc-Jeu", team_row['FJ'])
            
        # TABS
        tab1, tab2, tab3 = st.tabs(["Journal de Match", "Punitions", "Buts (Brut)"])
        
        with tab1:
            st.subheader("Journal de Match")
            # Show relevant columns
            log_cols = ['date', 'home', 'visitor', 'final_score_home', 'final_score_visitor', 'arena']
            st.dataframe(games_filtered[log_cols].sort_values(by='date', ascending=False), use_container_width=True)

        with tab2:
            st.subheader("Punitions")
            st.dataframe(penalties_filtered, use_container_width=True)
            
        with tab3:
             st.dataframe(goals_filtered)

if __name__ == "__main__":
    main()

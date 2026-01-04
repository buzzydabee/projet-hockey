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
        
        # PTS/MJ
        s['PTS/MJ'] = round((s['PTS'] / s['GP']) if s['GP'] > 0 else 0, 3)

        # Format string "A/B"
        s['PP'] = f"{s['PP_G']}/{s['PP_Att']}"
        s['PK'] = f"{s['PK_Kills']}/{s['PK_Att']}"
        s['PIM'] = pim
        s['DIFF'] = s['GF'] - s['GA']
        
        stats.append(s)
        
    cols_to_show = ['Team', 'PTS/MJ', 'PTS', 'GP', 'W', 'L', 'T', 'FJ', 'GF', 'GA', 'DIFF', 'PP%', 'PK%', 'PIM']
    
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
        default_t = "BÉLIERS QUÉBEC-CENTRE"
        defaults = [default_t] if default_t in all_teams else all_teams[:1]
        selected_teams = st.sidebar.multiselect("Choisir les Équipes", all_teams, default=defaults)
    
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
    
    
    # Capture Global Context (Filtered by Date, but NOT by Team/Stats Mode)
    games_global = games.copy()
    valid_global_ids = games_global['game_id'].unique()
    goals_global = goals[goals['game_id'].isin(valid_global_ids)]
    penalties_global = penalties[penalties['game_id'].isin(valid_global_ids)]
    
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
    
    # --- VIEWS ---
    view = st.sidebar.radio("Vue", ["Tableau de bord", "Évolution"], index=0)

    if view == "Tableau de bord":
        normalize = st.sidebar.checkbox("Normaliser par MJ", value=False)
        render_dashboard(games, goals, penalties, conn, selected_teams, stats_mode, players, normalize, 
                         games_global, goals_global, penalties_global)
    else:
        num_periods = st.sidebar.slider("Nombre de périodes", 1, 5, 4)
        render_evolution(games, goals, penalties, conn, selected_teams, stats_mode, players, num_periods)
        
    conn.close()

def render_dashboard(games, goals, penalties, conn, selected_teams, stats_mode, players, normalize=False,
                     games_global=None, goals_global=None, penalties_global=None):
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
    
    # Define Renaming Map (English -> French)
    col_rename_map = {
        'Team': 'Équipe', 'GP': 'MJ', 'W': 'V', 'L': 'D', 'T': 'N',
        'GF': 'BP', 'GA': 'BC', 'PP%': '%AN', 'PK%': '%DN', 'PIM': 'PUN'
    }
    
    # DISPLAY FILTERING
    # If "Globales" or "Face-à-Face", we usually only show the selected teams.
    # If "Un contre tous", we show selected teams AND their opponents (so, everyone in the standings_games).
    if not standings.empty:
         if stats_mode != "Un contre tous":
             standings = standings[standings['Team'].isin(selected_teams)]
             
         standings = standings.reset_index(drop=True)
         standings.index += 1
         
         # RENAME COLUMNS FOR DISPLAY
         standings = standings.rename(columns=col_rename_map)
         
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
         standings = pd.DataFrame(columns=['Équipe', 'PTS/MJ', 'PTS', 'MJ', 'V', 'D', 'N', 'FJ', 'BP', 'BC', 'DIFF', '%AN', '%DN', 'PUN'])

    cols_to_show = ['Équipe', 'PTS/MJ', 'PTS', 'MJ', 'V', 'D', 'N', 'FJ', 'BP', 'BC', 'DIFF', '%AN', '%DN', 'PUN']
    
    # Normalization Logic
    if normalize:
        # Calculate per-game stats
        norm_cols_map = {
            'V': 'V/MJ', 'D': 'D/MJ', 'N': 'N/MJ', 'FJ': 'FJ/MJ',
            'BP': 'BP/MJ', 'BC': 'BC/MJ', 'DIFF': 'DIFF/MJ', 'PUN': 'PUN/MJ'
        }
        for col, new_col in norm_cols_map.items():
            standings[new_col] = standings.apply(lambda r: r[col]/r['MJ'] if r['MJ'] > 0 else 0, axis=1)
            
        # Reorder: [Rank, Team] [PTS/MJ, V/MJ...] [PTS, V...]
        # PTS/MJ exists. 
        # New order: PTS/MJ, V/MJ, D/MJ, N/MJ, FJ/MJ, BP/MJ, BC/MJ, DIFF/MJ, PUN/MJ
        norm_cols_ordered = ['PTS/MJ'] + list(norm_cols_map.values())
        orig_cols = [c for c in cols_to_show if c not in norm_cols_ordered and c != 'Équipe'] # PTS is in orig, PTS/MJ is norm
        
        # PTS/MJ is already in cols_to_show, handle it carefully
        # Remove PTS/MJ from orig list if present (it is) and we treat it as normalized head.
        orig_cols = [c for c in orig_cols if c != 'PTS/MJ' and c != 'MJ']
        
        # New Request: Add MJ as first stat
        cols_to_show = ['Équipe', 'MJ'] + norm_cols_ordered + orig_cols

    # --- HEATMAP LOGIC ---
    # Define Roots
    # Positive (High=Green): PTS, V, N, FJ, BP, DIFF, %AN, %DN, BL, %Arr, B, A, MA, ...
    # Negative (High=Red): D, BC, PUN, PEM, Moy
    
    pos_roots = ['PTS', 'V', 'N', 'FJ', 'BP', 'DIFF', '%AN', '%DN', 'BL', '%Arr', 'B', 'A', 'MA', 
                 'BAN', 'AAN', 'PTS_AN', 'BIN', 'AID', 'PTS_IN', 'BG', 'BE']
    neg_roots = ['D', 'BC', 'PUN', 'PEM', 'Moy']
    
    # Custom Colormaps for Dark Mode (Red -> Black -> Green)
    try:
        from matplotlib.colors import LinearSegmentedColormap
        # Streamlit dark bg is approx #0e1117. 
        # Positive Stats (PTS, V): Low=Red, High=Green
        # Use brighter ends for visibility: #990000 (Red) and #009900 (Green)
        cmap_pos = LinearSegmentedColormap.from_list("custom_pos", ["#800000", "#0e1117", "#008000"])
        # Negative Stats (PUN, D): Low=Green, High=Red
        cmap_neg = LinearSegmentedColormap.from_list("custom_neg", ["#008000", "#0e1117", "#800000"])
    except:
        # Fallback if matplotlib not found (unlikely)
        cmap_pos = 'RdYlGn'
        cmap_neg = 'RdYlGn_r'

    def get_column_type(col_name):
        # Remove /MJ suffix for check
        root = col_name.replace('/MJ', '')
        if root in pos_roots: return 'pos'
        if root in neg_roots: return 'neg'
        return 'neu'

    # Pts/MJ max is usually 2 (win) + maybe 1 fair play / 1 game = 3 max?
    # Or standard W=2, T=1, FJ=1. Max per game = 3.
    max_pmj = 3.0
    if not standings.empty: 
        max_pmj = max(standings['PTS/MJ'].max(), 3.0)
        
    # STYLING: Center all columns except Team (which is now in Index)
    # We use pandas Styler to enforce text-align: center
    # Note: Streamlit column_config might override data alignment, but we try our best.
    # Headers need 'th' selector.
    
    # Move Team to Index for pinning
    standings.index.name = "Rang"
    standings.set_index("Équipe", append=True, inplace=True)
    
    # Filter cols_to_show to exclude Équipe since it is in index
    cols_data = [c for c in cols_to_show if c != 'Équipe']
    
    # Apply Heatmap
    # Split cols_data into pos and neg
    std_pos = [c for c in cols_data if get_column_type(c) == 'pos']
    std_neg = [c for c in cols_data if get_column_type(c) == 'neg']
    
    styler_standings = standings[cols_data].style.set_properties(
        subset=cols_data, 
        **{'text-align': 'center'}
    ).set_table_styles([
        {'selector': 'th', 'props': [('text-align', 'center !important')]},
        {'selector': 'td', 'props': [('text-align', 'center !important')]}
    ])
    
    
    # Calculate Global Standings for Heatmap Context
    if games_global is not None:
        st_global = calculate_standings(games_global, penalties_global)
        if not st_global.empty:
             # Rename Global to match French Schema for Min/Max lookup
             # Explicitly ensure the map is available or define it here if needed
             rename_map_local = {
                 'Team': 'Équipe', 'GP': 'MJ', 'W': 'V', 'L': 'D', 'T': 'N',
                 'GF': 'BP', 'GA': 'BC', 'PP%': '%AN', 'PK%': '%DN', 'PIM': 'PUN'
             }
             st_global = st_global.rename(columns=rename_map_local)
             
             # Robust calculation
             if 'MJ' in st_global.columns:
                 # Always calculate PTS/MJ as it is in the main table default
                 st_global['PTS/MJ'] = st_global.apply(lambda r: round(r['PTS']/r['MJ'], 3) if r['MJ']>0 else 0, axis=1)

                 if normalize:
                     for c, new_c in norm_cols_map.items():
                        # Verify source column exists (e.g. 'V', 'D')
                        if c in st_global.columns:
                            st_global[new_c] = st_global.apply(lambda r: r[c]/r['MJ'] if r['MJ'] > 0 else 0, axis=1)

             
    # Apply gradients with explicit vmin/vmax
    for col in std_pos:
        vmin, vmax = None, None
        if games_global is not None and not st_global.empty and col in st_global.columns:
             vmin = st_global[col].min()
             vmax = st_global[col].max()
        styler_standings = styler_standings.background_gradient(cmap=cmap_pos, subset=[col], vmin=vmin, vmax=vmax)

    for col in std_neg:
        vmin, vmax = None, None
        if games_global is not None and not st_global.empty and col in st_global.columns:
             vmin = st_global[col].min()
             vmax = st_global[col].max()
        styler_standings = styler_standings.background_gradient(cmap=cmap_neg, subset=[col], vmin=vmin, vmax=vmax)
    
    st.dataframe(
        styler_standings, 
        width="stretch",
        column_config={

            "PTS/MJ": st.column_config.ProgressColumn(
                "PTS/MJ",
                format="%.3f",
                min_value=0,
                max_value=max_pmj,
            ),
             "PTS": st.column_config.NumberColumn(
                "PTS",
                format="%d"
            ),
            "%AN": st.column_config.NumberColumn(
                "%AN",
                format="%.1f%%"
            ),
            "%DN": st.column_config.NumberColumn(
                "%DN",
                format="%.1f%%"
            ),
            # Add formats for normalized cols (defaults to %.2f usually but let's be explicit if needed or rely on default)
            **({c: st.column_config.NumberColumn(format="%.2f") for c in cols_to_show if '/MJ' in c} if normalize else {})
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
    
    # Calculate for filtered game IDs
    valid_game_ids = games['game_id'].unique()
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
        
        if normalize:
            # Map
            g_norm_map = {
                'MA': 'MA/MJ', 'V': 'V/MJ', 'D': 'D/MJ', 'N': 'N/MJ',
                'BL': 'BL/MJ', 'BC': 'BC/MJ', 'Lancers': 'Lancers/MJ'
            }
            for col, new_col in g_norm_map.items():
                gdf[new_col] = gdf.apply(lambda r: r[col]/r['MJ'] if r['MJ'] > 0 else 0, axis=1)
                
                
            norm_order = list(g_norm_map.values())
            orig_order = [c for c in cols if c not in ['Nom', 'Équipe', 'MJ']]
            
            # New request: MJ first
            cols = ['Nom', 'Équipe', 'MJ'] + norm_order + orig_order
        
        # STYLING
        # Center stats columns (Skip Nom, Team)
        stats_cols_g = cols[2:] 
        
        # Pin Nom
        gdf.index.name = "Rang"
        gdf.set_index("Nom", append=True, inplace=True)
        
        # Cols to display (excluding Nom which is in index)
        # We perform style on the remaining columns
        cols_display = [c for c in cols if c != 'Nom']
        
        styler_gdf = gdf[cols_display].style.set_properties(
            subset=list(set(cols_display) & set(stats_cols_g)), # Ensure intersection
            **{'text-align': 'center'}
        ).set_table_styles([
            {'selector': 'th', 'props': [('text-align', 'center !important')]},
            {'selector': 'td', 'props': [('text-align', 'center !important')]}
        ])
        
        g_pos = [c for c in cols_display if get_column_type(c) == 'pos']
        g_neg = [c for c in cols_display if get_column_type(c) == 'neg']
        
        g_pos = [c for c in cols_display if get_column_type(c) == 'pos']
        g_neg = [c for c in cols_display if get_column_type(c) == 'neg']
        
        # Global Context for Goalies
        df_goal_global = pd.DataFrame()
        if games_global is not None:
             g_ids_global = games_global['game_id'].unique()
             df_goal_global = calculate_goalie_stats(conn, g_ids_global)
             
             if not df_goal_global.empty:
                 # Rename Global to match French Schema
                 df_goal_global = df_goal_global.rename(columns={'Name': 'Nom', 'Team': 'Équipe', 'Shots': 'Lancers'})
             
                 if normalize:
                     for c, new_c in g_norm_map.items():
                         # Verify column exists
                         if c in df_goal_global.columns:
                             df_goal_global[new_c] = df_goal_global.apply(lambda r: r[c]/r['MJ'] if r['MJ'] > 0 else 0, axis=1)

        for col in g_pos:
            vmin, vmax = None, None
            if not df_goal_global.empty and col in df_goal_global.columns:
                 vmin = df_goal_global[col].min()
                 vmax = df_goal_global[col].max()
            styler_gdf = styler_gdf.background_gradient(cmap=cmap_pos, subset=[col], vmin=vmin, vmax=vmax)
            
        for col in g_neg:
            vmin, vmax = None, None
            if not df_goal_global.empty and col in df_goal_global.columns:
                 vmin = df_goal_global[col].min()
                 vmax = df_goal_global[col].max()
            styler_gdf = styler_gdf.background_gradient(cmap=cmap_neg, subset=[col], vmin=vmin, vmax=vmax)
        
        st.dataframe(
            styler_gdf, 
            width="stretch",
            column_config={
                 "%Arr": st.column_config.NumberColumn(
                    "%Arr",
                    format="%.3f"
                ),
                "Moy": st.column_config.NumberColumn(
                    "Moy",
                    format="%.2f"
                ),
                **({c: st.column_config.NumberColumn(format="%.2f") for c in cols if '/MJ' in c} if normalize else {})
            }
        )
    else:
        st.info("No goalie stats available for selected selection.")
        

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
        col_map_p = {
            'MJ': 'MJ', 'B': 'B', 'A': 'A', 'PTS': 'PTS', 'PEM': 'PEM', 'PUN': 'PUN',
            'PEM/MJ': 'PEM/MJ', 'PTS/MJ': 'PTS/MJ',
            'BAN': 'BAN', 'AAN': 'AAN', 'PTS_AN': 'PTS_AN', 'BIN': 'BIN', 'AID': 'AID', 
            'PTS_IN': 'PTS_IN', 'BG': 'BG', 'BE': 'BE'
        }
        
        cols = ['Nom', 'Équipe', 'MJ', 'B', 'A', 'PTS', 'PEM', 'PUN', 'PEM/MJ', 'PTS/MJ', 
                'BAN', 'AAN', 'PTS_AN', 'BIN', 'AID', 'PTS_IN', 'BG', 'BE']

        if normalize:
            # Stats to normalize
            # Already have PTS/MJ, PEM/MJ
            p_to_norm = ['B', 'A', 'PUN', 'BAN', 'AAN', 'PTS_AN', 'BIN', 'AID', 'PTS_IN', 'BG', 'BE']
            
            p_norm_cols = []
            for col in p_to_norm:
                new_col = f"{col}/MJ"
                p_df[new_col] = p_df.apply(lambda r: r[col]/r['MJ'] if r['MJ'] > 0 else 0, axis=1)
                p_norm_cols.append(new_col)
                
            # Order: [Nom, Team] [PTS/MJ, PEM/MJ] + [Other Norms] + [Originals]
            # Actually user asked: "stats normalisées ... meme ordre que stats originales, gauche du tableau"
            # Original: MJ B A PTS PEM PUN PEM/MJ PTS/MJ BAN ...
            # Normalized block: B/MJ, A/MJ, PTS/MJ, PEM/MJ, PUN/MJ ...
            
            # Let's construct a cleaner normalized block
            # Start with PTS/MJ and PEM/MJ which exist
            
            # Requested logic: Normalized versions of [B, A, PTS, PEM, PUN, BAN...]
            # Note: PTS/MJ and PEM/MJ are heavily used, put them first or with their group?
            # User said: "meme ordre que stats originales".
            # Original: B, A, PTS, PEM, PUN, BAN...
            # Norm: B/MJ, A/MJ, PTS/MJ, PEM/MJ, PUN/MJ, BAN/MJ...
            
            final_norm_ordered = ['B/MJ', 'A/MJ', 'PTS/MJ', 'PEM/MJ', 'PUN/MJ', 'BAN/MJ', 'AAN/MJ', 
                                  'PTS_AN/MJ', 'BIN/MJ', 'AID/MJ', 'PTS_IN/MJ', 'BG/MJ', 'BE/MJ']
            
            # Ensure all exist (PTS/MJ and PEM/MJ exist, others created)
            
            orig_data_cols = [c for c in cols if c not in ['Nom', 'Équipe', 'PTS/MJ', 'PEM/MJ']] # Remove existing ratios from orig block if moving them?
            # User usually wants to KEEP original stats too.
            # "apparaître à la gauche du tableau AVANT les statistiques originales."
            
            # So: [Nom, Team] [Norm Block] [Orig Block]
            orig_cols_filtered = [c for c in cols if c not in final_norm_ordered and c not in ['Nom', 'Équipe', 'MJ']]
            cols = ['Nom', 'Équipe', 'MJ'] + final_norm_ordered + orig_cols_filtered
            
            # We strictly need to ensure columns exist in DF
            # We created the loop ones. PTS/MJ and PEM/MJ exist.
            pass

        
        # STYLING
        stats_cols_p = cols[2:] # Skip Nom, Equipe
        
        # Pin Nom
        p_df.index.name = "Rang"
        p_df.set_index("Nom", append=True, inplace=True)
        
        cols_display_p = [c for c in cols if c != 'Nom']
        
        styler_pdf = p_df[cols_display_p].style.set_properties(
            subset=list(set(cols_display_p) & set(stats_cols_p)),
            **{'text-align': 'center'}
        ).set_table_styles([
            {'selector': 'th', 'props': [('text-align', 'center !important')]},
            {'selector': 'td', 'props': [('text-align', 'center !important')]}
        ])

        p_pos = [c for c in cols_display_p if get_column_type(c) == 'pos']
        p_neg = [c for c in cols_display_p if get_column_type(c) == 'neg']

        if p_pos: styler_pdf = styler_pdf.background_gradient(cmap=cmap_pos, subset=p_pos)
        if p_neg: styler_pdf = styler_pdf.background_gradient(cmap=cmap_neg, subset=p_neg)
        
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
                ),
                **({c: st.column_config.NumberColumn(format="%.2f") for c in cols if '/MJ' in c} if normalize else {})
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
        
        # Prepare Dates map
        game_dates = games[['game_id', 'date_dt']]
        
        goals_filtered = goals[goals['team_name'] == selected_team]
        goals_filtered = goals_filtered.merge(game_dates, on='game_id', how='left')
        
        penalties_filtered = penalties[penalties['team_name'] == selected_team]
        penalties_filtered = penalties_filtered.merge(game_dates, on='game_id', how='left')
        
        # Get standing row
        # Note: 'standings' DF now has French columns if calculated above.
        # But we must be careful. Variable 'standings' exists from previous block.
        # It has column 'Équipe' now, not 'Team'.
        
        # Let's re-find the row using FRENCH column names
        # Let's re-find the row using FRENCH column names (Équipe is in Index now)
        t_row = standings[standings.index.get_level_values('Équipe') == selected_team]
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
            log_cols = ['date_dt', 'home', 'visitor', 'final_score_home', 'final_score_visitor', 'arena']
            st.dataframe(
                games_filtered[log_cols].sort_values(by='date_dt', ascending=False), 
                width="stretch",
                column_config={
                    "date_dt": st.column_config.DateColumn("Date", format="DD MMMM YYYY")
                }
            )

        with tab2:
            st.subheader("Punitions")
            # Reorder: Date first, remove IDs
            cols_p = ['date_dt'] + [c for c in penalties_filtered.columns if c not in ['date_dt', 'game_id', 'team_id']]
            st.dataframe(
                penalties_filtered[cols_p].sort_values(by='date_dt', ascending=False), 
                width="stretch",
                column_config={
                    "date_dt": st.column_config.DateColumn("Date", format="DD MMMM YYYY")
                }
            )
            
        with tab3:
             # Resolve Player Names
             cols_g_show = ['date_dt', 'Buteur', 'Passeur 1', 'Passeur 2', 'period', 'time']
             
             if not goals_filtered.empty:
                 # Get Team ID (assume consistent for selected_team)
                 current_tid = goals_filtered.iloc[0]['team_id']
                 
                 # Filter players
                 t_players = players[players['team_id'] == current_tid]
                 # Map: Jersey(str) -> Name
                 p_map = dict(zip(t_players['jersey_number'].astype(str).str.strip(), t_players['player_name']))
                 
                 def resolve_name(j):
                     if pd.isna(j) or j == "": return ""
                     return p_map.get(str(j).strip(), str(j))

                 goals_filtered['Buteur'] = goals_filtered['player_jersey'].apply(resolve_name)
                 goals_filtered['Passeur 1'] = goals_filtered['assist1_jersey'].apply(resolve_name)
                 goals_filtered['Passeur 2'] = goals_filtered['assist2_jersey'].apply(resolve_name)
             else:
                 # Empty case
                 cols_g_show = [] # Clean handling if empty
             
             if not goals_filtered.empty:
                 st.dataframe(
                    goals_filtered[cols_g_show].sort_values(by='date_dt', ascending=False),
                    width="stretch",
                    column_config={
                        "date_dt": st.column_config.DateColumn("Date", format="DD MMMM YYYY")
                    }
                 )
             else:
                 st.info("Aucun but enregistré.")

def render_evolution(games, goals, penalties, conn, selected_teams, stats_mode, players, num_periods=4):
    st.header("📈 Évolution de la Saison")
    st.caption(f"Les indicateurs sont calculés sur {num_periods} périodes de durée égale, basées sur la plage de dates sélectionnée.")

    # 1. Split Time Range into N Periods
    if games.empty:
        st.warning("Aucun match dans la plage sélectionnée.")
        return

    min_date = games['date_dt'].min()
    max_date = games['date_dt'].max()
    
    # If range is too small (e.g. 1 day), just show 1 period? 
    # Or force N periods even if identical? Let's try to split by duration.
        
    total_duration = max_date - min_date
    period_duration = total_duration / num_periods
    
    periods = []
    for i in range(num_periods):
        p_start = min_date + (period_duration * i)
        p_end = min_date + (period_duration * (i + 1))
        # Ensure last period catches everything up to max_date exactly (microseconds issue)
        if i == num_periods - 1: p_end = max_date 
        
        periods.append((p_start, p_end))
        
    # 2. Calculate Stats for each Period
    # We will store results in dictionaries: Team -> {Col: [v1, v2, v3, v4]}
    
    # Init aggregators
    # Standings
    agg_standings = {} # Key: TeamName -> {Col: []}
    
    # Goalies
    agg_goalies = {} # Key: Name -> {Col: []}
    
    # Players
    agg_players = {} # Key: Name -> {Col: []}
    
    # We need a master list of all entities to ensure alignment
    # But entities might not participate in all periods. 
    # We'll collect all observed entities across all periods first? 
    # Or just iterate and fill missing later?
    # Let's use the current 'games' filter (which is the whole range) to define the Universe of entities.
    
    # Universe Standings
    # Note: calculate_standings returns "Équipe" named 'Team' initially.
    # We should normalize column names to what we want to display/graph.
    cols_std_numeric = ['PTS', 'GP', 'W', 'L', 'T', 'FJ', 'GF', 'GA']
    # Computed later: DIFF, PP%, PK%, PIM (from raw data?)
    # Re-calculating complex stats (PP%) from averages of averages is wrong.
    # We must calculate PP% for the period, then store that value.
    # So we prefer to store the FINISHED stat value for the period.
    
    cols_std_to_track = ['PTS', 'GP', 'W', 'L', 'T', 'FJ', 'GF', 'GA', 'DIFF', 'PP%', 'PK%', 'PIM']
    # Mapping to French for Display
    std_map = {
        'Team': 'Équipe', 'GP': 'MJ', 'W': 'V/MJ', 'L': 'D/MJ', 'T': 'N/MJ',
        'GF': 'BP/MJ', 'GA': 'BC/MJ', 'PP%': '%AN', 'PK%': '%DN', 'PIM': 'PUN/MJ',
        'PTS': 'PTS/MJ', 'FJ': 'FJ/MJ', 'DIFF': 'DIFF/MJ'
    }
    
    
    for i, (p_start, p_end) in enumerate(periods):
        # Filter Data for Period
        # Inclusive start, inclusive end? 
        # Overlap risk at boundaries? 
        # Let's say: >= start AND <= end. 
        # But Period 0 end == Period 1 start.
        # Use: >= start AND < end (except last period <= end)
        if i < num_periods - 1:
            mask = (games['date_dt'] >= p_start) & (games['date_dt'] < p_end)
        else:
            mask = (games['date_dt'] >= p_start) & (games['date_dt'] <= p_end)
            
        p_games = games[mask]
        p_ids = p_games['game_id'].unique()
        p_goals = goals[goals['game_id'].isin(p_ids)]
        p_penalties = penalties[penalties['game_id'].isin(p_ids)]
        
        # --- CALC STANDINGS ---
        s_games = p_games
        s_pens = p_penalties
        # Apply Selection Filter if needed (Global vs 1vsAll)
        if stats_mode != "Un contre tous" and not p_games.empty:
             # Standard: only games involving selected teams (if Custom/Div mode)
             # But 'games' acts as the base. If user filtered teams in sidebar, 'games' passed here 
             # is ALREADY filtered by Team for Global/Face-to-Face?
             # Wait, in main(), for "Global" games is NOT filtered by team, only by Date.
             # Filtering happens inside calculate_standings wrapper in Dashboard.
             
             # Replicate Logic:
             # Replicate Logic:
             # Always filter to reduce processing set if not Un contre tous
             s_games = p_games[p_games['home'].isin(selected_teams) | p_games['visitor'].isin(selected_teams)]
             s_ids = s_games['game_id'].unique()
             s_pens = p_penalties[p_penalties['game_id'].isin(s_ids)]
                 
        start_time = datetime.now()
        df_std = calculate_standings(s_games, s_pens)
        
        # Add PTS/MJ
        if not df_std.empty:
            df_std['PTS/MJ'] = round((df_std['PTS'] / df_std['GP']), 3) # GP > 0 implied by logic usually? or check
            df_std['PTS/MJ'] = df_std.apply(lambda r: round(r['PTS']/r['GP'], 3) if r['GP']>0 else 0, axis=1)
        
        # Filter rows to selected teams only
        if not df_std.empty:
            if stats_mode != "Un contre tous":
                df_std = df_std[df_std['Team'].isin(selected_teams)]
        
        # Merge into Aggregator
        for _, row in df_std.iterrows():
            t = row['Team']
            if t not in agg_standings: agg_standings[t] = {c: [0.0]*num_periods for c in cols_std_to_track}
            
            mj = float(row.get('GP', 0))
            
            # Cols to normalize by MJ
            cols_std_norm = ['PTS', 'W', 'L', 'T', 'FJ', 'GF', 'GA', 'DIFF', 'PIM']
            
            for c in cols_std_to_track:
                val = row.get(c, 0)
                try: val = float(val)
                except: val = 0.0
                
                if c in cols_std_norm and mj > 0:
                    val = round(val / mj, 2)
                    
                agg_standings[t][c][i] = val
                
        # --- CALC GOALIES ---
        g_ids = s_games['game_id'].unique()
        df_goal = calculate_goalie_stats(conn, g_ids)
        if not df_goal.empty:
            if stats_mode != "Un contre tous":
               df_goal = df_goal[df_goal['Team'].isin(selected_teams)]
               
        cols_goal_track = ['MJ', 'MA', 'V', 'D', 'N', 'BL', 'BC', 'Shots', 'Moy', '%Arr']
        
        for _, row in df_goal.iterrows():
             name = row['Name']
             # Key = Name (Unique enough?)
             if name not in agg_goalies: 
                 agg_goalies[name] = {
                     'Team': row['Team'], # Static
                     'Stats': {c: [0.0]*num_periods for c in cols_goal_track}
                 }
                 
             for c in cols_goal_track:
                 val = row.get(c, 0)
                 try: val = float(val)
                 except: val = 0.0
                 
                 # Goalies: Normalize by MJ
                 # Cols to normalize
                 cols_goal_norm = ['MA', 'V', 'D', 'N', 'BL', 'BC', 'Shots']
                 mj = float(row.get('MJ', 0))
                 
                 if c in cols_goal_norm and mj > 0:
                     val = round(val / mj, 2)

                 agg_goalies[name]['Stats'][c][i] = val

        # --- CALC PLAYERS ---
        # This might be slow... 4x calculation
        df_play = calculate_player_stats(s_games, p_goals, p_penalties, players)
        if not df_play.empty:
            if stats_mode != "Un contre tous":
                df_play = df_play[df_play['Team'].isin(selected_teams)]
        
        # Filter by specific players widget? 
        # (Technically that widget is in render_dashboard, so it's not visible here!
        #  We should arguably move specific_players filter to main() or replicate it here if we want consistency.
        #  For now, show all selected team players.)
        
        cols_play_track = ['MJ', 'B', 'A', 'PTS', 'PEM', 'PUN', 
                           'BAN', 'AAN', 'PTS_AN', 'BIN', 'AID', 'PTS_IN', 'BG', 'BE']
                           
        for _, row in df_play.iterrows():
             name = row['Name']
             if name not in agg_players:
                 agg_players[name] = {
                     'Team': row['Team_name'] if 'Team_name' in row else row.get('Team', ''),
                     'Stats': {c: [0.0]*num_periods for c in cols_play_track}
                 }
             # Player MJ for this period
             mj = float(row.get('MJ', 0))
             
             cols_play_norm = ['B', 'A', 'PTS', 'PEM', 'PUN', 'BAN', 'AAN', 'PTS_AN', 'BIN', 'AID', 'PTS_IN', 'BG', 'BE']

             for c in cols_play_track:
                 val = row.get(c, 0)
                 try: val = float(val)
                 except: val = 0.0
                 
                 if c in cols_play_norm and mj > 0:
                     val = round(val / mj, 2)
                     
                 agg_players[name]['Stats'][c][i] = val

    # 3. BUILD AND DISPLAY TABLES
    
    # helper to generate safe line chart config
    def get_safe_chart_config(df, col_name, title):
        # Default fallback
        base_min = 0.0
        base_max = 1.0
        
        try:
            # Flatten and filter for valid numbers
            all_values = []
            if col_name in df.columns:
                for val_or_list in df[col_name]:
                    # Handle both list of values (sparkline source) or single values if mixed
                    if isinstance(val_or_list, (list, tuple)):
                        for v in val_or_list:
                            try:
                                f = float(v)
                                if f == f and f != float('inf') and f != float('-inf'): # Valid finite number
                                    all_values.append(f)
                            except: pass
                    else:
                        try:
                             f = float(val_or_list)
                             if f == f and f != float('inf') and f != float('-inf'):
                                 all_values.append(f)
                        except: pass
            
            if not all_values:
                return st.column_config.LineChartColumn(title, width="small", y_min=base_min, y_max=base_max)
            
            mn = float(min(all_values))
            mx = float(max(all_values))
            
            # Policy:
            # 1. If all non-negative, anchor y_min at 0.
            if mn >= 0:
                mn = 0.0
                
            # 2. Ensure y_max > y_min
            if mx <= mn:
                mx = mn + 1.0
                
            # 3. Add a tiny buffer if range is very small (optional, but safer for rendering)
            if (mx - mn) < 1e-6:
                mx = mn + 1.0
                
            return st.column_config.LineChartColumn(
                title, 
                y_min=mn,
                y_max=mx, 
                width="small"
            )

        except Exception:
            return st.column_config.LineChartColumn(title, width="small", y_min=base_min, y_max=base_max)

    # helper
    def make_spark_df(agg_data, col_map, id_col_name='Équipe'):
        # agg_data: {Entity: {Col: [v1..v4]}} (Standings style) OR {Entity: {'Team': T, 'Stats': {Col: []}}} (Player style)
        rows = []
        for entity, data in agg_data.items():
            row = {}
            row[id_col_name] = entity
            
            # Handle Structure diff
            if 'Stats' in data: # Player/Goalie
                stats = data['Stats']
                if 'Team' in data: row['Équipe'] = data['Team']
            else: # Standings
                stats = data
                
            for c, vals in stats.items():
                disp_col = col_map.get(c, c)
                row[disp_col] = vals
            
            rows.append(row)
        return pd.DataFrame(rows)

    # --- STANDINGS TABLE ---
    if agg_standings:
        st.subheader("Classement")
        df_evo_std = make_spark_df(agg_standings, std_map, 'Équipe')
        
        # Sort by PTS sum
        col_pts = std_map.get('PTS', 'PTS')
        col_pts_mj = std_map.get('PTS/MJ', 'PTS/MJ')
        
        # Calculate Sort Keys
        # Sort by the LAST period value (most recent trend)
        df_evo_std['__SortPTS'] = df_evo_std[col_pts].apply(lambda x: x[-1] if len(x) > 0 else 0)
        # Note: If PTS is mapped to PTS/MJ, do we sort by sum of PTS/MJ? 
        # Yes, high average -> high rank usually. 
        # But wait, sum of PTS/MJ across 4 periods is a weird metric.
        # Ideally we want Total Points... but we normalized everything!
        # If we only have normalized data, Sum of PTS/MJ is a reasonable proxy for performance.
        
        # Sort Logic
        df_evo_std = df_evo_std.sort_values(by=['__SortPTS'], ascending=False).reset_index(drop=True)
        
        df_evo_std = df_evo_std.reset_index(drop=True)
        df_evo_std.index += 1
        df_evo_std.index.name = "Rang"
        df_evo_std.set_index("Équipe", append=True, inplace=True)
        
        # Config
        # All columns except Equipe are sparklines
        # We need to act on French Names
        cols_cfg = {}
        for c in cols_std_to_track:
            fr_c = std_map.get(c, c)
            cols_cfg[fr_c] = get_safe_chart_config(df_evo_std, fr_c, fr_c)
            
        st.dataframe(
            df_evo_std.drop(columns=['__SortPTS']),
            column_config=cols_cfg,
            width="stretch"
        )
    else:
        st.info("Pas de données de classement.")

    # --- GOALIES ---
    if agg_goalies:
        st.subheader("Gardiens")
        g_map = {
            'Shots': 'Lancers/MJ', 'Name': 'Nom', 'Team': 'Équipe',
            'MA': 'MA/MJ', 'V': 'V/MJ', 'D': 'D/MJ', 'N': 'N/MJ',
            'BL': 'BL/MJ', 'BC': 'BC/MJ'
        }
        df_evo_g = make_spark_df(agg_goalies, g_map, 'Nom')
        
        # Sort
        # Sort by MJ in LAST period
        df_evo_g['__MJ'] = df_evo_g['MJ'].apply(lambda x: x[-1] if len(x) > 0 else 0)
        df_evo_g = df_evo_g.sort_values(by='__MJ', ascending=False).reset_index(drop=True)
        df_evo_g.index += 1
        df_evo_g.index.name = "Rang"
        df_evo_g.set_index("Nom", append=True, inplace=True)

        cols_cfg_g = {}
        for c in cols_goal_track:
            fr_c = g_map.get(c, c)
            cols_cfg_g[fr_c] = get_safe_chart_config(df_evo_g, fr_c, fr_c)
        
        st.dataframe(
            df_evo_g.drop(columns=['__MJ']), 
            column_config=cols_cfg_g,
            width="stretch"
        )

    # --- PLAYERS ---
    if agg_players:
        st.subheader("Joueurs")
        p_map = {
            'Name': 'Nom', 'Team': 'Équipe',
            'B': 'B/MJ', 'A': 'A/MJ', 'PTS': 'PTS/MJ', 'PEM': 'PEM/MJ', 'PUN': 'PUN/MJ',
            'BAN': 'BAN/MJ', 'AAN': 'AAN/MJ', 'PTS_AN': 'PTS_AN/MJ',
            'BIN': 'BIN/MJ', 'AID': 'AID/MJ', 'PTS_IN': 'PTS_IN/MJ',
            'BG': 'BG/MJ', 'BE': 'BE/MJ'
        }
        df_evo_p = make_spark_df(agg_players, p_map, 'Nom')
        
        # Sort by PTS sum (LAST period)
        col_pts_p = p_map.get('PTS', 'PTS')
        df_evo_p['__PTS'] = df_evo_p[col_pts_p].apply(lambda x: x[-1] if len(x) > 0 else 0)
        df_evo_p = df_evo_p.sort_values(by='__PTS', ascending=False).reset_index(drop=True)
        df_evo_p.index += 1
        df_evo_p.index.name = "Rang"
        df_evo_p.set_index("Nom", append=True, inplace=True)
        
        cols_cfg_p = {}
        for c in cols_play_track:
             fr_c = p_map.get(c, c)
             cols_cfg_p[fr_c] = get_safe_chart_config(df_evo_p, fr_c, fr_c)
        
        st.dataframe(
            df_evo_p.drop(columns=['__PTS']).head(100), # Limit to top 100 to avoid lag
            column_config=cols_cfg_p,
            width="stretch"
        )

if __name__ == "__main__":
    main()

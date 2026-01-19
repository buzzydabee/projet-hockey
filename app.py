
import streamlit as st
import os
import sqlite3
import pandas as pd
import time
from datetime import datetime, timedelta
from game_logic import GameReconstructor
import streamlit.components.v1 as components
import textwrap
import altair as alt
import google.generativeai as genai
import json

st.set_page_config(page_title="Hockey Stats Dashboard", layout="wide")

DB_NAME = "hockey_stats.db"

# French Month Map
MONTHS_MAP = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12
}

def parse_french_date(date_str):
    if not isinstance(date_str, str): return None
    # 1. Try ISO Format (YYYY-MM-DD) - New Standard
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        pass
        
    # 2. Try French Text (DD month YYYY) - Legacy
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

# --- CONFIGURATION & CONSTANTS ---

# PENALTY CODES MAPPING (Spordle/Hockey Quebec Standard)
PENALTY_CODES = {
    'A1': 'Abus envers les officiels', 'A2': 'Ajustement d\'équipement', 'A3': 'Instigateur', 'A9': 'Agresseur',
    'A22': 'Inconduite', 'A25': 'Trop de joueurs', 'A37': 'Coup de tête', 'A39': 'Mise en échec par derrière',
    'D39': 'Mise en échec par derrière (Majeure)', 'A44': 'Abus verbal/gestuel', 'A47': 'Rudesse', 'A48': 'Contact à la tête',
    'B48': 'Contact à la tête (Majeure)', 'C48': 'Contact à la tête (Double-Mineure)', 'A50': 'Retenir',
    'A51': 'Rudesse', 'A52': 'Harponner', 'A53': 'Bâton élevé', 'A54': 'Obstruction', 'A55': 'Accrocher',
    'A56': 'Interférence banc/glace', 'A57': 'Trébucher', 'A59': 'Double-échec', 'A61': 'Cinglage',
    'C61': 'Cinglage (Double-Mineure)', 'D61': 'Cinglage (Majeure)', 'A76': 'Équipement non conforme', 
    'D76': 'Équipement (Majeure)', 'A81': 'Bataille', 'D81': 'Bataille (Majeure)', 'A92': 'Inconduite', 
    'A99': 'Inconduite de partie', 'E1': 'Match', 'E48': 'Match (Tête)'
}

def load_data():
    conn = sqlite3.connect(DB_NAME)
    
    # Games (Enhanced)
    games = pd.read_sql_query('''
        SELECT g.*, t1.team_name as home, t2.team_name as visitor
        FROM DimGame g
        JOIN DimTeam t1 ON g.home_team_id = t1.team_id
        JOIN DimTeam t2 ON g.visitor_team_id = t2.team_id
    ''', conn)
    
    # Ensure column exists (backward compatibility)
    if 'is_roster_incomplete' not in games.columns:
        games['is_roster_incomplete'] = 0
    
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
    
    # --- DATA NORMALIZATION (MERGE ALIASES) ---
    for alias, canonical in TEAM_ALIASES.items():
        # Games
        games['home'] = games['home'].replace(alias, canonical)
        games['visitor'] = games['visitor'].replace(alias, canonical)
        # Goals/Penalties
        goals['team_name'] = goals['team_name'].replace(alias, canonical)
        penalties['team_name'] = penalties['team_name'].replace(alias, canonical)


    
    return games, goals, penalties

    
    # Apply Mapping
    # Apply Mapping - REMOVED to show raw codes in table (Legend will explain)
    # penalties['code'] = penalties['code'].map(lambda x: PENALTY_CODES.get(str(x).upper().strip(), str(x)))
    
    return games, goals, penalties


def render_penalty_analysis_section(penalties_df, title_prefix=""):
    """
    Renders the Penalty Analysis Section (Legend + 2 Summary Tables).
    Assumes penalties_df is already filtered for the relevant team(s) and context.
    """
    # --- LEGEND (Toggle Style) ---
    if 'code' not in penalties_df.columns:
         st.warning("Données de punitions invalides (colonne 'code' manquante).")
         return
         
    params_codes = sorted(penalties_df['code'].unique())
    
    # Init Toggle State
    if 'leg_penalties' not in st.session_state: st.session_state.leg_penalties = False
    
    # Layout: Title + Button
    c_title, c_btn = st.columns([0.85, 0.15])
    with c_title:
        st.markdown(f"### 📊 Analyse des Infractions {title_prefix}")
    with c_btn:
        if st.button("Légende 📝", key=f"btn_leg_pen_{title_prefix}"):
             st.session_state.leg_penalties = not st.session_state.leg_penalties

    if st.session_state.leg_penalties:
        start_html = "<div style='display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; background-color: #1a1e24; padding: 10px; border-radius: 8px; border: 1px solid #333;'>"
        legend_chips = ""
        for c in params_codes:
            desc = PENALTY_CODES.get(str(c).upper().strip(), "N/A")
            legend_chips += f"<span style='background-color: #333; color: #ddd; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem;'><b>{c}</b> : {desc}</span>"
        end_html = "</div>"
        st.markdown(start_html + legend_chips + end_html, unsafe_allow_html=True)
    
    col_p1, col_p2 = st.columns(2)
    
    # 1. Top 5 Infractions (Équipe) - With Period Breakdown
    with col_p1:
            st.markdown("**Top 5 Infractions (Totaux & Périodes)**")
            if 'period' in penalties_df.columns:
                p_piv = penalties_df.groupby(['code', 'period']).size().unstack(fill_value=0)
                for p in [1, 2, 3]:
                    if p not in p_piv.columns: p_piv[p] = 0
                p_piv = p_piv.astype(int)
                p_piv['Total'] = p_piv.sum(axis=1)
                p_piv = p_piv.sort_values('Total', ascending=False).head(5)
                p_final = p_piv[['Total', 1, 2, 3]].reset_index()
                
                # HTML Table Generation
                html_rows = ""
                for _, row in p_final.iterrows():
                    code_clean = str(row['code']).upper().strip()
                    desc_display = PENALTY_CODES.get(code_clean, code_clean) # Show Desc, fallback to Code
                    
                    html_rows += f"""
                    <tr style="border-bottom: 1px solid #444;">
                    <td style="text-align: left; padding: 5px; font-weight: bold; color: #eee; font-size: 0.9rem;">{desc_display}</td>
                    <td style="text-align: center; color: #fff; font-weight: bold; font-size: 1.1em;">{row['Total']}</td>
                    <td style="text-align: center; color: #ccc;">{row[1]}</td>
                    <td style="text-align: center; color: #ccc;">{row[2]}</td>
                    <td style="text-align: center; color: #ccc;">{row[3]}</td>
                    </tr>"""
                
                tbl_html = f"""
                <table style="width: 100%; border-collapse: collapse; font-size: 0.9rem;">
                <thead>
                    <tr style="border-bottom: 2px solid #555; color: #aaa;">
                        <th style="text-align: left; padding-bottom: 5px;">Infraction</th>
                        <th style="text-align: center;">Total</th>
                        <th style="text-align: center;">P1</th>
                        <th style="text-align: center;">P2</th>
                        <th style="text-align: center;">P3</th>
                    </tr>
                </thead>
                <tbody>{html_rows}</tbody>
                </table>
                """
                st.markdown(tbl_html, unsafe_allow_html=True)
            else:
                st.warning("Données de période manquantes.")


    # 2. Top 5 Joueurs (With Period Breakdown)
    with col_p2:
            st.markdown("**Top 5 Joueurs les plus punis**")
            # Group by Player Name
            p_col_candidates = ['player_name', 'player_name__']
            p_col = next((c for c in p_col_candidates if c in penalties_df.columns), None)

            if p_col:
                pl_piv = penalties_df.groupby([p_col, 'period']).size().unstack(fill_value=0)
                for p in [1, 2, 3]:
                    if p not in pl_piv.columns: pl_piv[p] = 0
                pl_piv = pl_piv.astype(int)
                pl_piv['Total'] = pl_piv.sum(axis=1)
                pl_piv = pl_piv.sort_values('Total', ascending=False).head(5)
                
                # Get Top Infractions
                def get_top_infractions_html(player_name):
                    p_recs = penalties_df[penalties_df[p_col] == player_name]
                    counts = p_recs['code'].value_counts().head(3)
                    
                    items = []
                    for k, v in counts.items():
                        c_clean = str(k).upper().strip()
                        d_show = PENALTY_CODES.get(c_clean, c_clean)
                        # Truncate if too long?
                        if len(d_show) > 20: d_show = d_show[:18] + ".."
                        items.append(f"{d_show} ({v})")
                        
                    return "<br>".join(items)

                pl_final = pl_piv[['Total', 1, 2, 3]].reset_index()
                pl_final.columns = ['Joueur', 'Total', 'P1', 'P2', 'P3'] # Reset columns
                
                html_rows_2 = ""
                for _, row in pl_final.iterrows():
                    pname = row['Joueur']
                    top_inf = get_top_infractions_html(pname)
                    html_rows_2 += f"""
                    <tr style="border-bottom: 1px solid #444;">
                    <td style="text-align: left; padding: 5px; font-weight: bold; color: #eee;">{pname}</td>
                    <td style="text-align: center; color: #fff; font-weight: bold; font-size: 1.1em;">{row['Total']}</td>
                    <td style="text-align: center; color: #ccc;">{row['P1']}</td>
                    <td style="text-align: center; color: #ccc;">{row['P2']}</td>
                    <td style="text-align: center; color: #ccc;">{row['P3']}</td>
                    <td style="text-align: left; font-size: 0.75rem; line-height: 1.2; padding: 2px; color: #bbb;">{top_inf}</td>
                    </tr>"""
                
                tbl_html_2 = f"""
                <table style="width: 100%; border-collapse: collapse; font-size: 0.9rem;">
                <thead>
                    <tr style="border-bottom: 2px solid #555; color: #aaa;">
                        <th style="text-align: left; padding-bottom: 5px;">Joueur</th>
                        <th style="text-align: center;">Total</th>
                        <th style="text-align: center;">P1</th>
                        <th style="text-align: center;">P2</th>
                        <th style="text-align: center;">P3</th>
                        <th style="text-align: left;">Top Infractions</th>
                    </tr>
                </thead>
                <tbody>{html_rows_2}</tbody>
                </table>
                """
                st.markdown(tbl_html_2, unsafe_allow_html=True)
            else:
                 st.warning("Colonne joueur introuvable.")

def calculate_standings(games, penalties, goals):
    # Get all teams
    all_teams = sorted(list(set(games['home']) | set(games['visitor'])))
    
    stats = []
    reconstructor = GameReconstructor()
    
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
            'PP_G': 0, 'PP_Att': 0, 'PK_Kills': 0, 'PK_Att': 0,
            'PP_G_Rec': 0, 'PP_Att_Rec': 0, 'PK_Kills_Rec': 0, 'PK_Att_Rec': 0
        }
        
        if len(t_games) == 0:
            continue

        for _, row in t_games.iterrows():
            # FILTER: Exclude Non-Final Games (0-0 score AND 0 shots)
            # This handles "Today's Scheduled Games" which exist in DB but shouldn't count for stats.
            is_empty_stats = (
                row['final_score_home'] == 0 and 
                row['final_score_visitor'] == 0 and 
                row['shots_for_home'] == 0 and 
                row['shots_for_visitor'] == 0
            )
            if is_empty_stats:
                continue

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

            # --- RECONSTRUCTION ---
            g_id = row['game_id']
            g_goals = goals[goals['game_id'] == g_id]
            g_pens = penalties[penalties['game_id'] == g_id]
            
            # Identify IDs
            hid = row['home_team_id']
            vid = row['visitor_team_id']
            
            rec_stats = reconstructor.reconstruct_game_stats(g_id, g_goals, g_pens, hid, vid)
            
            # Add to Team Stats
            # Add to Team Stats
            if is_home:
                # My PP (Home)
                s['PP_G_Rec'] += rec_stats['pp_g_home']
                s['PP_Att_Rec'] += rec_stats['pp_att_home']
                
                # My PK (Opponent PP Visitor)
                opp_g_rec = rec_stats['pp_g_vis']
                opp_att_rec = rec_stats['pp_att_vis']
                s['PK_Att_Rec'] += opp_att_rec
                s['PK_Kills_Rec'] += (opp_att_rec - opp_g_rec)
            else:
                # My PP (Visitor)
                s['PP_G_Rec'] += rec_stats['pp_g_vis']
                s['PP_Att_Rec'] += rec_stats['pp_att_vis']
                
                # My PK (Opponent PP Home)
                opp_g_rec = rec_stats['pp_g_home']
                opp_att_rec = rec_stats['pp_att_home']
                s['PK_Att_Rec'] += opp_att_rec
                s['PK_Kills_Rec'] += (opp_att_rec - opp_g_rec)

        # Points Formula: W*2 + T*1 + FJ
        s['PTS'] = (s['W'] * 2) + (s['T'] * 1) + s['FJ']
        
        # Percentages
        # USE RECONSTRUCTED DATA FOR OFFICIAL DISPLAY AS PER USER REQUEST
        s['PP%'] = round((s['PP_G_Rec'] / s['PP_Att_Rec'] * 100) if s['PP_Att_Rec'] > 0 else 0, 1)
        s['PK%'] = round((s['PK_Kills_Rec'] / s['PK_Att_Rec'] * 100) if s['PK_Att_Rec'] > 0 else 0, 1)
        
        # Eliminated separate Rec columns
        
        # PTS/MJ
        s['PTS/MJ'] = round((s['PTS'] / s['GP']) if s['GP'] > 0 else 0, 3)

        # Format string "A/B"
        s['PP'] = f"{s['PP_G']}/{s['PP_Att']}"
        # s['PP (Rec)'] = f"{s['PP_G_Rec']}/{s['PP_Att_Rec']}" # Removed
        s['PK'] = f"{s['PK_Kills']}/{s['PK_Att']}"
        # s['PK (Rec)'] = f"{s['PK_Kills_Rec']}/{s['PK_Att_Rec']}" # Removed
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
        st.dataframe(pd.DataFrame(columns=cols_to_show))
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
            standings_goals = goals[goals['game_id'].isin(s_ids)]
        else:
            standings_goals = goals
            
        standings = calculate_standings(standings_games, standings_penalties, standings_goals)
        
        # If we selected specific teams, we probably only want to SEE those teams in the table?
        # Or do we want to see their opponents too?
        # Usually "Filter by Team" implies "Show me rows for these teams".
        # Let's filter the FINAL standings dataframe to only show selected teams rows.
        if not standings.empty:
             standings = standings[standings['Team'].isin(selected_teams)]
    
        cols_to_show = ['Team', 'PTS', 'GP', 'W', 'L', 'T', 'FJ', 'GF', 'GA', 'PP%', 'PP% Rec', 'PK%', 'PK% Rec', 'PIM']  # Simplified view
        st.dataframe(standings[cols_to_show])

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
    
    if not res:
        cols = ['Name', 'Team', 'MJ', 'B', 'A', 'PTS', 'PEM', 'PUN', 'BAN', 'AAN', 'PTS_AN', 
                'BIN', 'AID', 'PTS_IN', 'BG', 'BE', 'PEM/MJ', 'PTS/MJ']
        return pd.DataFrame(columns=cols)

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
    
    # Normalize Team Name
    for alias, canonical in TEAM_ALIASES.items():
        df['team_name'] = df['team_name'].replace(alias, canonical)
    
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
                'BC': 0, 'TG': 0.0
            }
            
        # Minutes
        try: mins = float(row['minutes_played'])
        except: mins = 0.0
        
        if mins > 0:
            res[name]['MJ'] += 1
            res[name]['TG'] += mins
            res[name]['BC'] += row['goals_against']
            # res[name]['Shots'] += row['shots_against'] # REMOVED
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
        # Save % - REMOVED due to unreliable data
        # saves = v['Shots'] - v['BC']
        # v['%Arr'] = 0.0
        # Time format
        m = int(v['TG'])
        s = int((v['TG'] - m) * 60)
        v['TG_str'] = f"{m}:{s:02d}"
        finals.append(v)
        
    if not finals:
        return pd.DataFrame(columns=['Name', 'Team', 'MJ', 'MA', 'V', 'D', 'N', 'BL', 'BC', 'TG', 'Moy', 'TG_str'])
        
    return pd.DataFrame(finals)

# Team Name Normalization (Aliases -> Canonical)
TEAM_ALIASES = {
    "FAUCONS": "FAUCONS BEAUPORT",
    "PATRIOTES  QUÉBEC-CENTRE": "PATRIOTES QUÉBEC-CENTRE", # Handle double space if needed
    "RICHELIEU": "RICHELIEU QUÉBEC-CENTRE"
}

# Divisions Map (To be populated)
DIVISIONS = {
    "Division Est": [
        "AIGLES CBIO", "WAPITIS CHARLESBOURG", "BÉLIERS QUÉBEC-CENTRE", 
        "RADISSON QUÉBEC-CENTRE", "BOUCS QUÉBEC-CENTRE", "ÉPERVIERS BEAUPORT", 
        "CARIBOUS CHARLESBOURG", "BUCKS CHARLESBOURG", "PHÉNIX CBIO", 
        "FAUCONS BEAUPORT", # Merged FAUCONS
        "RICHELIEU QUÉBEC-CENTRE", 
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
        conn.close()
        
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
        /* CSS for Custom HTML Tables */
        table.dataframe {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            font-family: sans-serif;
        }
        
        table.dataframe th, table.dataframe td {
            text-align: center !important;
            vertical-align: middle !important;
            padding: 4px 2px !important; /* Compact padding */
            border: 1px solid #2d2d2d;
            white-space: nowrap; /* Prevent wrapping for compactness */
        }
        
        table.dataframe th {
            background-color: #0e1117;
            font-weight: bold;
            color: white;
            padding-bottom: 8px !important;
            padding-top: 8px !important;
        }
        
        /* Force Streamlit DataFrame Header Alignment */
        [data-testid="stDataFrame"] th {
            text-align: center !important;
        }
        
        /* Deep selector for some Streamlit versions using Divs for headers */
        div[data-testid="stDataFrame"] div[role="columnheader"] {
            display: flex !important;
            justify-content: center !important;
            text-align: center !important;
        }
        
        div[data-testid="stDataFrame"] div[class*="stDataFrame"] {
             text-align: center !important;
        }
        
        /* Alternating rows for readability if needed, but heatmap usually covers it */
        /* table.dataframe tr:nth-child(even) { background-color: #161a24; } */
        
        /* Specific column alignments if needed (but user wants all centered) */
        
    </style>
    """, unsafe_allow_html=True)
    
    # Theme Check Warning (Removed as it is active)
    # if st.get_option("theme.primaryColor") != "#00A8E8":
    #    st.warning("⚠️ Pour voir le nouveau thème 'Bleu Glace', veuillez redémarrer l'application dans le terminal (Ctrl+C puis relancez).")

    # --- SIDEBAR FILTERS ---
    st.sidebar.header("Filtres")
    
    # 1. Team Selection
    all_teams = sorted(list(set(games['home']) | set(games['visitor'])))

    # --- ACTION HANDLER (Deep Linking) ---
    # Handle "Face to Face" requests from Journal
    # New Standard: ?selected_teams_custom=TeamA&selected_teams_custom=TeamB
    try:
        # Check for standard list param (Streamlit returns list or string)
        qt = st.query_params.get_all("selected_teams_custom") # Returns list
        if qt:
             # Robust Matching Helper
             def normalize_key(k):
                 import unicodedata
                 n = unicodedata.normalize('NFKD', str(k)).encode('ASCII', 'ignore').decode('utf-8')
                 return n.lower().strip().replace(" ", "")
                 
             # Create map of normalized -> real name
             team_map = {normalize_key(t): t for t in all_teams}
             
             valid_qt = []
             for t in qt:
                 nk = normalize_key(t)
                 if nk in team_map:
                     valid_qt.append(team_map[nk])
             
             if len(valid_qt) >= 2:
                 st.session_state["filter_mode_idx"] = 2 
                 # st.session_state["filter_mode"] = "Sélection Personnalisée" # Removed key
                 st.session_state["selected_teams_custom"] = valid_qt 
                 st.query_params.clear()
                 st.rerun()
             else:
                 # Fallback: Just log or ignore, or show subtle warning
                 pass

        # Legacy Support (if any)
        elif "action" in st.query_params and st.query_params["action"] == "face_to_face":
            t1 = st.query_params.get("t1")
            t2 = st.query_params.get("t2")
            if t1 and t2:
                 # Check existence
                 if t1 in all_teams and t2 in all_teams:
                     st.session_state["filter_mode_idx"] = 2
                     st.session_state["filter_mode"] = "Sélection Personnalisée"
                     st.session_state["selected_teams_custom"] = [t1, t2]
                     st.query_params.clear()
                     st.rerun()
    except Exception as e:
        st.error(f"Erreur param: {e}")
    
    # Init dynamic key version
    if "radio_ver" not in st.session_state:
        st.session_state["radio_ver"] = 0
        
    filter_mode = st.sidebar.radio(
        "Mode de Sélection", 
        ["Toutes les équipes", "Par Division", "Sélection Personnalisée"], 
        index=st.session_state.get("filter_mode_idx", 0),
        key=f"mode_{st.session_state['radio_ver']}"
    )
    
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
        selected_teams = st.sidebar.multiselect("Choisir les Équipes", all_teams, default=defaults, key="selected_teams_custom")
    
    # --- STATS MODE ---
    # stats_mode = st.sidebar.radio("Mode de Calcul", ["Stats Globales", "Un contre tous", "Face-à-Face"], key="calc_mode")
    stats_mode = "Stats Globales"
    
    normalize = st.sidebar.checkbox("Normaliser par MJ", value=False)
    
    # --- VIEWS ---
    view = st.sidebar.radio("Vue", ["Tableau de bord", "Évolution"], index=0)

    # Common Filter
    min_mj = st.sidebar.number_input("Min. Parties Jouées", min_value=1, value=2)


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
    
    # FILTER: "Complete" games for Statistics
    # We create a separate DataFrame for stats calculations (Standing, Players, Goalies)
    # that ONLY includes finished games.
    # The original 'games' DataFrame remains untouched so we can show Scheduled games in the Journal.
    games_complete = games.copy()
    if not games_complete.empty:
        mask_final = (games_complete['shots_for_home'] > 0) | (games_complete['shots_for_visitor'] > 0) | \
                     (games_complete['final_score_home'] > 0) | (games_complete['final_score_visitor'] > 0)
        games_complete = games_complete[mask_final]
    
    
    # Capture Global Context (Filtered by Date, but NOT by Team/Stats Mode)
    # MUST use Completed games for global stats context
    games_global = games_complete.copy()
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
    


    


    # Re-open connection for Analysis/Rendering phase
    conn = sqlite3.connect(DB_NAME)

    if view == "Tableau de bord":
        # normalize = st.sidebar.checkbox("Normaliser par MJ", value=False) # Moved up
        # Pass games_complete for Stats, but keep FULL games for Journal (Schedule)
        render_dashboard(games_complete, goals, penalties, conn, selected_teams, stats_mode, players, normalize, 
                         games_global, goals_global, penalties_global, min_mj, games_full=games, filter_mode=filter_mode)
    else:
        num_periods = st.sidebar.slider("Nombre de périodes", 1, 5, 3)
        render_evolution(games, goals, penalties, conn, selected_teams, stats_mode, players, num_periods, min_mj)
        
    # --- DATA MANAGEMENT (Moved to Bottom) ---
    st.sidebar.header("Gestion des Données")
    if st.sidebar.button("Vérifier nouveaux matchs"):
        # Create a status container
        status = st.sidebar.status("Démarrage de la vérification...", expanded=True)
        import subprocess
        import shlex
        
        try:
            # Prepare Environment to force UTF-8 output
            my_env = os.environ.copy()
            my_env["PYTHONIOENCODING"] = "utf-8"
            
            # --- 1. DOWNLOAD ---
            status.write("Lancement du téléchargement...")
            # Use 'python -u' for unbuffered output to get real-time logs
            import sys
            # Use sys.executable to ensure we use the SAME python environment (venv)
            cmd = [sys.executable, "-u", "download_game_sheets.py"]
            
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                text=True, 
                bufsize=1, 
                encoding='utf-8',
                env=my_env # Force UTF-8 environment
            )
            
            # Filter logic
            def is_user_friendly_log(text):
                # Only write "Actionable" info to the history (Downloads, Finds)
                # We do NOT write "Processing Team" to history to avoid a long list of 20 teams.
                if "Downloaded" in text or "Téléchargement terminé" in text: return True
                if "Founded" in text and "unique games" in text:
                    if " 0 unique games" in text: return False
                    return True
                # SHOW DATE RANGE
                if "PLAGE DE RECHERCHE" in text: return True
                
                # CRITICAL: Allow Errors to be seen!
                if any(x in text for x in ["Error", "Exception", "Traceback", "Fail", "CRITICAL"]): return True
                return False

            # Stream output
            full_logs = []
            for line in process.stdout:
                try:
                    line = line.strip()
                    if line:
                        full_logs.append(line)
                        # 1. Update Label (Real-time feedback)
                        if "Processing Team" in line:
                             parts = line.split("Team:")
                             if len(parts) > 1:
                                 team_name = parts[1].split("(")[0].strip()
                                 status.update(label=f"Traitement: {team_name}")
                        elif "Scanning Page" in line:
                             status.update(label=f"Scan: {line}")
                        elif "Found" in line and "unique games" in line:
                             status.update(label="Vérification des matchs...")
                        elif "Setting dates" in line:
                             pass

                        # 2. Write to Log History (Only important events)
                        if is_user_friendly_log(line):
                             status.write(line) 
                             
                except Exception:
                    continue # Skip unparseable lines
            
            process.wait()
            
            if process.returncode == 0:
                 status.update(label="Vérification terminée!", state="complete", expanded=False)
                 st.sidebar.success("Vérification terminée.")
            else:
                 status.update(label="Erreur durant le téléchargement", state="error")
                 st.sidebar.error("Erreur durant le téléchargement.")
                 with st.sidebar.expander("Voir les logs d'erreur"):
                     st.text("\n".join(full_logs[-20:])) # Show last 20 lines
                 
            # --- 2. PROCESS ---
            if process.returncode == 0:
                status_proc = st.sidebar.status("Mise à jour de la BD...", expanded=True)
                cmd_proc = [sys.executable, "-u", "process_gamesheets.py"]
                
                # ... process setup same as beform ...
                
                process_proc = subprocess.Popen(
                    cmd_proc,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    encoding='utf-8',
                    env=my_env # Force UTF-8 environment
                )
                
                for line in process_proc.stdout:
                    try:
                        line = line.strip()
                        if line:
                            # Update Label
                            if "Processing" in line and ".pdf" in line:
                                 parts = line.split("Processing")
                                 if len(parts) > 1:
                                     status_proc.update(label=f"Ajout: {parts[1].strip()}")
                            # Write critical info
                            if "Successfully processed" in line:
                                status_proc.write(line)
                    except Exception:
                        continue
                        
                process_proc.wait()
                
                if process_proc.returncode == 0:
                    status_proc.update(label="Base de données à jour!", state="complete", expanded=False)
                    st.sidebar.success("Base de données mise à jour.")
                    time.sleep(1)
                    st.rerun()
                else:
                    status_proc.update(label="Erreur de traitement", state="error")
        
        except Exception as e:
            st.sidebar.error(f"Erreur critique: {e}")
            print(e)

    if st.sidebar.button("Reconstruire la BD (Local)"):
        with st.spinner("Reconstruction de la base de données..."):
            import subprocess
            import sys
            try:
                # Run Process Script Only (It deletes DB first)
                result_rebuild = subprocess.run([sys.executable, "process_gamesheets.py"], capture_output=True, text=True)
                st.sidebar.success("Base de données reconstruite!")
                if result_rebuild.stdout:
                    with st.sidebar.expander("Journal de reconstruction"):
                        st.text(result_rebuild.stdout)
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Erreur de reconstruction: {e}")

    if st.sidebar.button("⚠️ Tout effacer et reconstruire (Local)"):
         # Progress Bar Logic
         progress_bar = st.sidebar.progress(0)
         status_text = st.sidebar.empty()
         
         import subprocess
         import sys
         
         try:
             # Use Popen to read output in real-time
             process = subprocess.Popen(
                 [sys.executable, "process_gamesheets.py", "--reset"],
                 stdout=subprocess.PIPE,
                 stderr=subprocess.PIPE,
                 text=True,
                 bufsize=1,            # Line buffered
                 encoding='utf-8'      # Ensure encoding
             )
             
             full_logs = []
             
             while True:
                 line = process.stdout.readline()
                 if not line and process.poll() is not None:
                     break
                 
                 if line:
                     full_logs.append(line)
                     if line.startswith("PROGRESS:"):
                         try:
                             # Format: PROGRESS:5/100
                             parts = line.strip().split(":")[1].split("/")
                             current = int(parts[0])
                             total = int(parts[1])
                             percent = min(current / total, 1.0)
                             progress_bar.progress(percent)
                             status_text.text(f"Traitement: {current}/{total}")
                         except:
                             pass
             
             stdout, stderr = process.communicate() # Get remaining
             if stdout: full_logs.append(stdout)
             
             if process.returncode == 0:
                 progress_bar.progress(1.0)
                 status_text.text("Terminé !")
                 st.sidebar.success("Base de données locale reconstruite!")
                 
                 # Cleanup cache
                 st.cache_data.clear()
                 time.sleep(1)
                 st.rerun()
             else:
                  st.sidebar.error("Erreur lors de la réinitialisation.")
                  if stderr:
                      st.sidebar.text(stderr)
             
             with st.sidebar.expander("Journal de reconstruction"):
                 st.text("".join(full_logs))
 
         except Exception as e:
             st.sidebar.error(f"Erreur de reconstruction: {e}")
 
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Zone de Danger ⛔")
    if st.sidebar.button("☢️ TOTAL RESET (Téléchargement Complet)"):
         import shutil
         st.sidebar.warning("Attention: Cette opération peut prendre plusieurs minutes.")
         
         status_container = st.sidebar.status("Démarrage de la réinitialisation...", expanded=True)
         
         try:
             # 1. DELETE DATA
             status_container.update(label="Suppression des données...", state="running")
             
             # CRITICAL: Close the open connection from main() before deleting the file!
             # Otherwise Windows locks the file and os.remove fails silently.
             try:
                 conn.close()
             except: pass

             if os.path.exists(DB_NAME):
                 try:
                     os.remove(DB_NAME)
                     status_container.write("Base de données supprimée.")
                 except Exception as e:
                     status_container.write(f"Echec suppression BD: {e}")

                 
             if os.path.exists("downloads"):
                 try:
                     shutil.rmtree("downloads")
                     status_container.write("Dossier téléchargements supprimé.")
                 except: pass
             
             # 2. DOWNLOAD
             # Prepare Environment to force UTF-8 output
             my_env = os.environ.copy()
             my_env["PYTHONIOENCODING"] = "utf-8"

             status_container.update(label="Téléchargement des matchs (Sept -> Aujourd'hui)...", state="running")
             import subprocess
             import sys
            
             # Run download script (will default to 2025-09-01 since DB is gone)
             proc_dl = subprocess.Popen(
                 [sys.executable, "-u", "download_game_sheets.py"],
                 stdout=subprocess.PIPE,
                 stderr=subprocess.STDOUT,
                 text=True,
                 bufsize=1,
                 encoding='utf-8',
                 env=my_env,
                 errors='replace' # Prevent crashes on decoding
             )
            
             for line in proc_dl.stdout:
                 if "Downloaded:" in line:
                      status_container.write(line.strip())
                 elif "Total Unique Games" in line:
                      status_container.write(line.strip())
                 elif "PLAGE DE RECHERCHE" in line:
                      status_container.write(line.strip())
                      
             proc_dl.wait()
            
             if proc_dl.returncode != 0:
                 status_container.update(label="Erreur téléchargement", state="error")
                 st.error("Le script de téléchargement a échoué.")
                 st.stop()
                
             # 3. REBUILD DB
             status_container.update(label="Reconstruction de la Base de Données...", state="running")
            
             proc_build = subprocess.Popen(
                 [sys.executable, "-u", "process_gamesheets.py"],
                 stdout=subprocess.PIPE,
                 stderr=subprocess.STDOUT,
                 text=True,
                 bufsize=1,
                 encoding='utf-8',
                 env=my_env,
                 errors='replace'
             )
            
             for line in proc_build.stdout:
                 if "PROGRESS:" in line:
                     pass # visual clutter
                 elif "Processing" in line:
                     # status_container.write(line.strip()) # Too verbose?
                     pass
                 elif "Successfully" in line:
                     pass
                    
             proc_build.wait()
            
             if proc_build.returncode == 0:
                 status_container.update(label="Succès ! Système remis à neuf.", state="complete", expanded=False)
                 st.sidebar.success("Tout est propre et à jour!")
                 st.cache_data.clear()
                 time.sleep(2)
                 st.rerun()
             else:
                 status_container.update(label="Erreur Reconstruction", state="error")
                 
         except Exception as e:
             st.sidebar.error(f"Erreur: {e}")
        
    conn.close()

def render_dashboard(games, goals, penalties, conn, selected_teams, stats_mode, players, normalize=False,
                     games_global=None, goals_global=None, penalties_global=None, min_mj=1, games_full=None, filter_mode=None):
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
    standings_goals = goals
    
    # Only filter if we haven't selected ALL teams (optimization)
    # BUT in "Un contre tous", games is already filtered, so we can pass it directly.
    # The optimization below is mainly for Global mode.
    # If stats_mode != 'Un contre tous' and len...
    
    standings = calculate_standings(standings_games, standings_penalties, standings_goals)
    
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
    
    pos_roots = ['PTS', 'V', 'N', 'FJ', 'BP', 'DIFF', '%AN', '%DN', '%AN (Rec)', '%DN (Rec)', 'BL', '%Arr', 'B', 'A', 'MA', 
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
    # standings.set_index("Équipe", append=True, inplace=True) # REMOVED to allow styling on Équipe column
    
    # Filter cols_to_show to exclude Équipe since it is in index -> KEEP IT
    cols_data = cols_to_show

    
    # Apply Heatmap
    # Split cols_data into pos and neg
    std_pos = [c for c in cols_data if get_column_type(c) == 'pos']
    std_neg = [c for c in cols_data if get_column_type(c) == 'neg']
    
    styler_standings = standings[cols_data].style.set_properties(
        subset=cols_data, 
        **{'text-align': 'center'}
    ).set_properties(
        subset=['Équipe'],
        **{'color': '#ffffff', 'font-weight': 'bold'}
    ).set_table_styles([
        {'selector': 'th', 'props': [('text-align', 'center !important')]},
        {'selector': 'td', 'props': [('text-align', 'center !important')]}
    ])
    
    
    # Calculate Global Standings for Heatmap Context
    if games_global is not None:
        st_global = calculate_standings(games_global, penalties_global, goals_global)
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
            # --- STYLING (Applied to Filtered Standings) ---
            # Center stats columns (Skip Team, Rang)
            
            # Convert Index to Column "Rang"
            standings.index.name = "Rang"
            standings = standings.reset_index()
            
            # Updated Cols Display: Rang + others (ensure Rang is first)
            cols_display = ['Rang'] + cols_data 
            
            # Define stats_cols for centering (exclude text columns)
            stats_cols = [c for c in cols_display if c not in ['Rang', 'Équipe']]
            
    # Styling logic removed - replaced by native st.dataframe config above
    
    # Render using Helper
    # Format for display (st.dataframe)
    # Define Column Configuration for Standings
    s_col_config = {
        "Rang": st.column_config.NumberColumn("Rang", format="%d", width="small"),
        "Équipe": st.column_config.TextColumn("Équipe", width="large"),
        "PTS/MJ": st.column_config.NumberColumn("PTS/MJ", format="%.2f"),
        "%AN": st.column_config.NumberColumn("%AN", format="%.1f%%"),
        "%DN": st.column_config.NumberColumn("%DN", format="%.1f%%"),
    }
    
    # Helper for other float columns
    for c in cols_display:
         if c not in s_col_config and c not in ['Rang', 'Équipe']:
              if '/MJ' in c: # Ratio (Normalized)
                   s_col_config[c] = st.column_config.NumberColumn(c, format="%.2f")
              elif '%' in c: # Percent
                   s_col_config[c] = st.column_config.NumberColumn(c, format="%.1f%%")
              elif normalize and c not in ['MJ', 'Rang', 'Équipe', 'FJ', 'PUN', 'V', 'D', 'N']:
                   # Conservative Check: If normalized, stick to int for known int columns
                   s_col_config[c] = st.column_config.NumberColumn(c, format="%d")
              else:
                   s_col_config[c] = st.column_config.NumberColumn(c, format="%d")
    
    # Styling: Center all columns except Team/Name
    left_align_cols = ['Équipe', 'Nom', 'Aréna']
    center_cols = [c for c in cols_display if c not in left_align_cols]
    
    
    styler_standings = standings[cols_display].style.set_properties(
        subset=center_cols,
        **{'text-align': 'center'}
    ).set_table_styles([
        {'selector': 'th:not(.index_name)', 'props': [('text-align', 'center')]},
        {'selector': 'td', 'props': [('text-align', 'center')]}
    ])

    st.dataframe(
        styler_standings,
        column_config=s_col_config,
        hide_index=True
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
                <b>BC</b>: Buts contre, <b>Moy</b>: Moyenne (GAA)<br>
                <b>BL</b>: Blanchissages, <b>TG</b>: Temps de glace
                </div>""", unsafe_allow_html=True)
            st.markdown("---")
    
    # Calculate for filtered game IDs
    valid_game_ids = games['game_id'].unique()
    gdf = calculate_goalie_stats(conn, valid_game_ids)
    # FILTER MIN MJ
    gdf = gdf[gdf['MJ'] >= min_mj]

    if gdf.empty:
        st.info("Aucune donnée de gardien.")
    else:
        # Filter Goalies by Team Selection
        if stats_mode != "Un contre tous":
            gdf = gdf[gdf['Team'].isin(selected_teams)]
        
        if not gdf.empty:
            gdf = gdf.sort_values(by=['Moy', 'MJ'], ascending=[True, False]).reset_index(drop=True)
            gdf.index += 1
            
            # Rename Cols
            gdf = gdf.rename(columns={'Name': 'Nom', 'Team': 'Équipe'})
            
            cols = ['Nom', 'Équipe', 'MJ', 'MA', 'V', 'D', 'N', 'BL', 'BC', 'Moy', 'TG_str']
            
            if normalize:
                # Map
                g_norm_map = {
                    'MA': 'MA/MJ', 'V': 'V/MJ', 'D': 'D/MJ', 'N': 'N/MJ',
                    'BL': 'BL/MJ', 'BC': 'BC/MJ'
                }
                for col, new_col in g_norm_map.items():
                    gdf[new_col] = gdf.apply(lambda r: r[col]/r['MJ'] if r['MJ'] > 0 else 0, axis=1)
                    
                    
                norm_order = list(g_norm_map.values())
                orig_order = [c for c in cols if c not in ['Nom', 'Équipe', 'MJ']]
                
                # New request: MJ first
                cols = ['Nom', 'Équipe', 'MJ'] + norm_order + orig_order
            
            # STYLING
            # Center stats columns (Skip Rang, Nom, Team)
            
            # Pin Nom: Keep it as a column instead of Index to ensure white color
            # gdf.set_index("Nom", append=True, inplace=True) # REMOVED to fix color
            gdf.index.name = "Rang"
            gdf = gdf.reset_index()
            
            # Cols to display (Nom is now included in columns)
            cols_display = ['Rang'] + cols 
            
            # Format for display (st.dataframe handles basic formatting, but we can refine)
            # We want specific column configs
            
            # Define Column Configuration
            g_col_config = {
                "Rang": st.column_config.NumberColumn("Rang", format="%d", width="small"),
                "Nom": st.column_config.TextColumn("Nom", width="medium"),
                "Équipe": st.column_config.TextColumn("Équipe", width="medium"),
                "MJ": st.column_config.NumberColumn("MJ", format="%d"),
                "MA": st.column_config.NumberColumn("MA", format="%d"),
                "V": st.column_config.NumberColumn("V", format="%d"),
                "D": st.column_config.NumberColumn("D", format="%d"),
                "N": st.column_config.NumberColumn("N", format="%d"),
                "BL": st.column_config.NumberColumn("BL", format="%d"),
                "BC": st.column_config.NumberColumn("BC", format="%d"),
                "Moy": st.column_config.NumberColumn("Moy", format="%.2f"),
                "%Arr": st.column_config.NumberColumn("%Arr", format="%.3f"),
                "TG_str": st.column_config.TextColumn("TG", width="small"),
            }
            
            # Additional Helper for Goalies
            for c in cols_display:
                if c not in g_col_config:
                    if '/MJ' in c or 'Moy' in c:
                        g_col_config[c] = st.column_config.NumberColumn(c, format="%.2f")
                    elif '%' in c:
                         g_col_config[c] = st.column_config.NumberColumn(c, format="%.3f" if '%Arr' in c else "%.1f%%")
                    else:
                        g_col_config[c] = st.column_config.NumberColumn(c, format="%d")
            
            # Adjust config for normalized columns if needed (mostly covered above)
            
            # Styling: Center all columns except Team/Name
            left_align_cols = ['Équipe', 'Nom', 'Aréna']
            center_cols_g = [c for c in cols_display if c not in left_align_cols]
            
            styler_gdf = gdf[cols_display].style.set_properties(
                subset=center_cols_g,
                **{'text-align': 'center'}
            ).set_table_styles([
                {'selector': 'th:not(.index_name)', 'props': [('text-align', 'center')]},
                {'selector': 'td', 'props': [('text-align', 'center')]}
            ])
            
            st.dataframe(
                styler_gdf,
                column_config=g_col_config,
                hide_index=True
            )
    
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
    # FILTER MIN MJ
    p_df = p_df[p_df['MJ'] >= min_mj]
    
    if p_df.empty:
        st.info("Aucune statistique de joueur trouvée.")
    else:
        # Filter Players by Team Selection
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
                
                orig_data_cols = [c for c in cols if c not in final_norm_ordered and c not in ['Nom', 'Équipe', 'PTS/MJ', 'PEM/MJ']] # Remove existing ratios from orig block if moving them?
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
            
            # Pin Nom: Keep as column
            # p_df.set_index("Nom", append=True, inplace=True) # REMOVED
            p_df.index.name = "Rang"
            p_df = p_df.reset_index()
            
            cols_display_p = ['Rang'] + cols
            
            # Recalculate stats cols for centering (exclude text cols)
            stats_cols_p = [c for c in cols_display_p if c not in ['Rang', 'Nom', 'Équipe']]
            
            styler_pdf = p_df[cols_display_p].style.set_properties(
                subset=list(set(cols_display_p) & set(stats_cols_p)),
                **{'text-align': 'center'}
            ).set_properties(
                subset=['Rang', 'Nom'],
                **{'color': '#ffffff', 'font-weight': 'bold'}
            ).set_table_styles([
                {'selector': 'th', 'props': [('text-align', 'center !important')]},
                {'selector': 'td', 'props': [('text-align', 'center !important')]}
            ]).hide(axis='index')

            p_pos = [c for c in cols_display_p if get_column_type(c) == 'pos']
            p_neg = [c for c in cols_display_p if get_column_type(c) == 'neg']

            # Format for display (st.dataframe)
            # Define Column Configuration
            p_col_config = {
                "Rang": st.column_config.NumberColumn("Rang", format="%d", width="small"),
                "Nom": st.column_config.TextColumn("Nom", width="medium"),
                "Équipe": st.column_config.TextColumn("Équipe", width="medium"),
                "MJ": st.column_config.NumberColumn("MJ", format="%d"),
                "B": st.column_config.NumberColumn("B", format="%d"),
                "A": st.column_config.NumberColumn("A", format="%d"),
                "PTS": st.column_config.NumberColumn("PTS", format="%d"),
                "PTS/MJ": st.column_config.NumberColumn("PTS/MJ", format="%.2f"),
                "PEM": st.column_config.NumberColumn("PEM", format="%d"),
                "PUN": st.column_config.NumberColumn("PUN", format="%d"),
                "PTS_AN": st.column_config.NumberColumn("PTS_AN", format="%d"),
                "PTS_IN": st.column_config.NumberColumn("PTS_IN", format="%d"),
                # Add others as needed (BAN, BP, etc.)
            }
            
            # Helper for other float columns
            for c in cols_display_p:
                 if c not in p_col_config and c not in ['Rang', 'Nom', 'Équipe']:
                      if '/MJ' in c or 'PTS' in c or 'Mo' in c: # Ratio or float
                           if c == 'PTS': # PTS is an integer raw count
                               p_col_config[c] = st.column_config.NumberColumn(c, format="%d")
                           else:
                               p_col_config[c] = st.column_config.NumberColumn(c, format="%.2f")
                      else:
                           p_col_config[c] = st.column_config.NumberColumn(c, format="%d")
            
            # Styling: Center all columns except Team/Name
            left_align_cols = ['Équipe', 'Nom', 'Aréna']
            center_cols_p = [c for c in cols_display_p if c not in left_align_cols]
            
            styler_pdf = p_df[cols_display_p].style.set_properties(
                subset=center_cols_p,
                **{'text-align': 'center'}
            ).set_table_styles([
                {'selector': 'th:not(.index_name)', 'props': [('text-align', 'center')]},
                {'selector': 'td', 'props': [('text-align', 'center')]}
            ])
            
            st.dataframe(
                styler_pdf,
                column_config=p_col_config,
                hide_index=True
            )


    # --- TEAM METRICS & JOURNAL ---
    st.divider()
    
    # 1. Filter Data for Selected Team(s)
    # Use games_full if available to show Schedule in Journal, otherwise fallback to stats games
    source_games = games_full if games_full is not None else games
    
    # Filter: Home OR Visitor in Selected Teams
    games_filtered = source_games[
        (source_games['home'].isin(selected_teams)) | 
        (source_games['visitor'].isin(selected_teams))
    ].copy()
    
    # UI TWEAK: Hide scores if 0-0 (Scheduled games)
    # Convert to string/object to allow empty strings
    games_filtered['final_score_home'] = games_filtered['final_score_home'].astype(str)
    games_filtered['final_score_visitor'] = games_filtered['final_score_visitor'].astype(str)
    
    # Loop to clear 0s if it looks initialized
    # We assume if BOTH are "0", it's a scheduled game.
    mask_scheduled = (games_filtered['final_score_home'] == '0') & (games_filtered['final_score_visitor'] == '0')
    games_filtered.loc[mask_scheduled, 'final_score_home'] = ''
    games_filtered.loc[mask_scheduled, 'final_score_visitor'] = ''

    # Feature: Alignment Status
    def alignment_status(val):
        if val == 1: return "⚠️ Provisoire"
        return "✅ Final"
    
    # Handle NaN safely
    games_filtered['is_roster_incomplete'] = games_filtered['is_roster_incomplete'].fillna(0).astype(int)
    games_filtered['Alignement'] = games_filtered['is_roster_incomplete'].apply(alignment_status)
    
    # FIX: Explicitly set Alignement to empty if game is not played (score is empty)
    # mask_scheduled is already defined above where scores are empty
    games_filtered.loc[mask_scheduled, 'Alignement'] = ""

    # Prepare Dates map (used for detailed tabs)
    game_dates = games[['game_id', 'date_dt']]

    # 2. METRICS (Single Team Only)
    # 2. METRICS (All Selected Teams)
    # 2. METRICS (Single Team Only)
    # 2. METRICS (All Selected Teams) - ONLY IF CUSTOM SELECTION
    if filter_mode == "Sélection Personnalisée":
        
        # --- COMPARATIVE ANALYSIS (2 TEAMS ONLY) ---
        if len(selected_teams) == 2:
            st.header("⚔️ Analyse Face-à-Face (Comparatif)")
            t1, t2 = selected_teams[0], selected_teams[1]
            
            # Helper to get team season stats
            def get_team_stats_season(team):
                # Filter ALL season games for this team
                t_games = games[(games['home'] == team) | (games['visitor'] == team)]
                if t_games.empty: return None
                
                # We need global stats
                g_ids = t_games['game_id'].unique()
                t_goals = goals[goals['game_id'].isin(g_ids)]
                t_pens = penalties[penalties['game_id'].isin(g_ids)]
                
                df_stats = calculate_standings(t_games, t_pens, t_goals)
                if not df_stats.empty:
                    row = df_stats[df_stats['Team'] == team]
                    if not row.empty: return row.iloc[0]
                return None
            
            s1 = get_team_stats_season(t1)
            s2 = get_team_stats_season(t2)
            
            # Helper to get period breakdowns
            def get_period_breakdown(team, games_pool):
                # Filter for games involved
                t_games = games_pool[(games_pool['home'] == team) | (games_pool['visitor'] == team)]
                g_ids = t_games['game_id'].unique()
                t_goals = goals[goals['game_id'].isin(g_ids)]
                t_pens = penalties[penalties['game_id'].isin(g_ids)]
                
                # Stats per period
                stats = {1: {}, 2: {}, 3: {}}
                
                # GP is constant for the team across periods (it's the game count)
                gp = len(t_games)
                if gp == 0: return stats
                
                def parse_pim(d):
                    try: return int(str(d).split(':')[0])
                    except: return 0
                
                # PP%: Calculate using Reconstructor
                # Initialize Reconstructor
                reconstructor = GameReconstructor()
                
                pp_stats_agg = {1: {'g': 0, 'att': 0}, 2: {'g': 0, 'att': 0}, 3: {'g': 0, 'att': 0}}
                pk_stats_agg = {1: {'g_against': 0, 'att': 0}, 2: {'g_against': 0, 'att': 0}, 3: {'g_against': 0, 'att': 0}}
                
                # Check mapping
                # We need home_team_id and visitor_team_id from t_games
                
                for _, g_row in t_games.iterrows():
                    gid = g_row['game_id']
                    hid = g_row['home_team_id']
                    vid = g_row['visitor_team_id']
                    
                    # Filter events for this game
                    g_goals = goals[goals['game_id'] == gid]
                    g_pens = penalties[penalties['game_id'] == gid]
                    
                    if not g_goals.empty or not g_pens.empty: # Optimization
                        rec = reconstructor.reconstruct_game_stats(gid, g_goals, g_pens, hid, vid)
                        
                        # Add to aggregate if period exists
                        if 'per_period' in rec:
                           # Determine if Team is Home or Visitor
                           is_home = (g_row['home'] == team)
                           
                           for p in [1, 2, 3]:
                               if p in rec['per_period']:
                                   p_data = rec['per_period'][p]
                                   # PK Stats (Opponent PP)
                                   if is_home:
                                       pp_stats_agg[p]['g'] += p_data['pp_g_home']
                                       pp_stats_agg[p]['att'] += p_data['pp_att_home']
                                       
                                       pk_stats_agg[p]['g_against'] += p_data['pp_g_vis']
                                       pk_stats_agg[p]['att'] += p_data['pp_att_vis']
                                   else:
                                       pp_stats_agg[p]['g'] += p_data['pp_g_vis']
                                       pp_stats_agg[p]['att'] += p_data['pp_att_vis']
                                       
                                       pk_stats_agg[p]['g_against'] += p_data['pp_g_home']
                                       pk_stats_agg[p]['att'] += p_data['pp_att_home']

                for p in [1, 2, 3]:
                    # GF: Goals by Team in Period P
                    gf = len(t_goals[(t_goals['team_name'] == team) & (t_goals['period'] == p)])
                    stats[p]['GF_avg'] = gf / gp
                    
                    # GA: Goals Against Team in Period P
                    ga = len(t_goals[(t_goals['team_name'] != team) & (t_goals['period'] == p)])
                    stats[p]['GA_avg'] = ga / gp
                    
                    # PIM: Penalties by Team in Period P
                    # Parse "2:00" -> 2
                    t_pens_p = t_pens[(t_pens['team_name'] == team) & (t_pens['period'] == p)].copy()
                    pim_mins = t_pens_p['duration'].apply(parse_pim).sum()
                    stats[p]['PIM_avg'] = pim_mins / gp
                    
                    # PP%
                    att = pp_stats_agg[p]['att']
                    if att > 0:
                        stats[p]['PP%'] = (pp_stats_agg[p]['g'] / att) * 100
                    else:
                        stats[p]['PP%'] = 0.0
                        
                    # PK%
                    pk_att = pk_stats_agg[p]['att']
                    if pk_att > 0:
                        # PK Kill = Att - Goals Against
                        kills = pk_att - pk_stats_agg[p]['g_against']
                        stats[p]['PK%'] = (kills / pk_att) * 100
                    else:
                        stats[p]['PK%'] = 0.0
                
                return stats

            def get_game_context_snapshot(team1, team2, games_pool, goals_pool):
                """
                Builds a rich context snapshot for the matchup.
                Includes: Triangle Logic (Common Opponents), Recent Form, Shot Volume.
                """
                ctx = {
                    't1': {'name': team1, 'matches': [], 'wins': 0, 'losses': 0, 'shots_for': 0, 'shots_against': 0, 'last_5': []},
                    't2': {'name': team2, 'matches': [], 'wins': 0, 'losses': 0, 'shots_for': 0, 'shots_against': 0, 'last_5': []},
                    'h2h': {'t1_wins': 0, 't2_wins': 0, 'ties': 0, 'games': []},
                    'triangle': {'t1_advantage': 0, 't2_advantage': 0, 'common_opps': []}
                }
                
                # 1. Direct H2H (Face to Face) - Still useful if exists
                h2h_games = games_pool[((games_pool['home'] == team1) & (games_pool['visitor'] == team2)) | 
                                       ((games_pool['home'] == team2) & (games_pool['visitor'] == team1))]
                
                for _, row in h2h_games.iterrows():
                    is_t1_home = (row['home'] == team1)
                    s_t1 = row['final_score_home'] if is_t1_home else row['final_score_visitor']
                    s_t2 = row['final_score_visitor'] if is_t1_home else row['final_score_home']
                    
                    if s_t1 > s_t2: ctx['h2h']['t1_wins'] += 1
                    elif s_t2 > s_t1: ctx['h2h']['t2_wins'] += 1
                    else: ctx['h2h']['ties'] += 1
                    
                # 2. Triangle Logic (Common Opponents)
                # Find games for T1 and T2
                t1_games_all = games_pool[(games_pool['home'] == team1) | (games_pool['visitor'] == team1)]
                t2_games_all = games_pool[(games_pool['home'] == team2) | (games_pool['visitor'] == team2)]
                
                # Extract results: {Opponent: Result(W/L)} (Simplified: Last result counts)
                def get_results_map(team, g_df):
                    res_map = {}
                    for _, r in g_df.sort_values('date_dt').iterrows(): # Sort by date asc, so last update wins
                        opp = r['visitor'] if r['home'] == team else r['home']
                        s_us = r['final_score_home'] if r['home'] == team else r['final_score_visitor']
                        s_them = r['final_score_visitor'] if r['home'] == team else r['final_score_home']
                        
                        outcome = 'T'
                        if s_us > s_them: outcome = 'W'
                        elif s_us < s_them: outcome = 'L'
                        
                        res_map[opp] = outcome
                    return res_map
                
                r1 = get_results_map(team1, t1_games_all)
                r2 = get_results_map(team2, t2_games_all)
                
                # Find Intersection
                common = set(r1.keys()) & set(r2.keys())
                ctx['triangle']['common_opps'] = list(common)
                
                for opp in common:
                    res1 = r1[opp]
                    res2 = r2[opp]
                    
                    # T1 Advantage: T1 Beat Opp, T2 Lost to Opp
                    if res1 == 'W' and res2 == 'L':
                        ctx['triangle']['t1_advantage'] += 1
                    # T2 Advantage: T2 Beat Opp, T1 Lost to Opp
                    elif res2 == 'W' and res1 == 'L':
                        ctx['triangle']['t2_advantage'] += 1
                    
                # 3. Recent Form & Shot Volume (Team 1)
                t1_games = t1_games_all.sort_values(by='date_dt', ascending=False)
                # Recent 5
                for i, (_, row) in enumerate(t1_games.head(5).iterrows()):
                    is_home = (row['home'] == team1)
                    res = 'T'
                    s_us = row['final_score_home'] if is_home else row['final_score_visitor']
                    s_them = row['final_score_visitor'] if is_home else row['final_score_home']
                    if s_us > s_them: res = 'W'
                    elif s_us < s_them: res = 'L'
                    ctx['t1']['last_5'].append(res)
                
                # Global Shots Logic
                total_shots_for = 0
                gp = len(t1_games)
                if gp > 0:
                    for _, row in t1_games.iterrows():
                        is_home = (row['home'] == team1)
                        total_shots_for += row['shots_for_home'] if is_home else row['shots_for_visitor']
                    ctx['t1']['shots_for_avg'] = total_shots_for / gp
                else:
                    ctx['t1']['shots_for_avg'] = 0

                # 4. Recent Form & Shot Volume (Team 2)
                t2_games = t2_games_all.sort_values(by='date_dt', ascending=False)
                # Recent 5
                for i, (_, row) in enumerate(t2_games.head(5).iterrows()):
                    is_home = (row['home'] == team2)
                    res = 'T'
                    s_us = row['final_score_home'] if is_home else row['final_score_visitor']
                    s_them = row['final_score_visitor'] if is_home else row['final_score_home']
                    if s_us > s_them: res = 'W'
                    elif s_us < s_them: res = 'L'
                    ctx['t2']['last_5'].append(res)

                # Global Shots Logic T2
                total_shots_for = 0
                gp = len(t2_games)
                if gp > 0:
                    for _, row in t2_games.iterrows():
                        is_home = (row['home'] == team2)
                        total_shots_for += row['shots_for_home'] if is_home else row['shots_for_visitor']
                    ctx['t2']['shots_for_avg'] = total_shots_for / gp
                else:
                    ctx['t2']['shots_for_avg'] = 0
                    
                return ctx



            def generate_game_plan_ai(s1, s2, p1_stats, p2_stats, snapshot, penalties_t1, penalties_t2, api_key, model_name='gemini-1.5-flash'):
                """Generates game plan using Google Gemini AI."""
                try:
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel(model_name)
                    
                    # Helper to map to French Labels
                    def to_french_dict(row):
                        if not hasattr(row, 'to_dict'): return str(row)
                        d = row.to_dict()
                        # Map common keys to French WITH DEFINITIONS
                        mapping = {
                            'GP': 'MJ (Matchs Joués - Total des matchs disputés)',
                            'W': 'V (Victoires - Matchs gagnés)',
                            'L': 'D (Défaites - Matchs perdus)',
                            'T': 'N (Nulles - Matchs nuls)',
                            'OTL': 'DP (Défaites en prolongation - Point bonus)',
                            'PTS': 'PTS (Points - Total au classement: V=2, N=1, +Franc-Jeu)',
                            'PTS/MJ': 'PTS/MJ (Points par match - Indice de performance)',
                            'GF': 'BP (Buts Pour - Total offensif)',
                            'GA': 'BC (Buts Contre - Total défensif)',
                            'DIFF': 'DIFF (Différentiel - BP moins BC)',
                            'FJ': 'FJ (Franc-Jeu - Points bonus pour discipline)',
                            'PP%': '%AN (Efficacité Avantage Numérique)',
                            'PP': 'AN (Unités - Buts/Tentatives)',
                            'PP_G': 'Buts AN (Total buts en avantage numérique)',
                            'PP_Att': 'Tentatives AN (Opportunités totales)',
                            'PK%': '%DN (Efficacité Désavantage Numérique)',
                            'PK': 'DN (Unités - Kills/Tentatives)',
                            'PK_Kills': 'Kills DN (Fois où l\'équipe a survécu à une punition)',
                            'PK_Att': 'Fois en DN (Nombre total de désavantages numériques)',
                            'PIM': 'PUN (Minutes de Punition - Total saison)',
                        }
                        
                        # Filter to include ONLY useful keys (remove internal IDs if any)
                        # And sort roughly by importance if possible, or just dump all
                        new_d = {}
                        for k, v in d.items():
                            if k in ['Team', 'Rang']: continue # Skip name, used elsewhere
                            key_fr = mapping.get(k, k)
                            new_d[key_fr] = v
                        return new_d

                    s1_fr = to_french_dict(s1)
                    s2_fr = to_french_dict(s2)

                    # Extract Top 3 Infractions strings
                    def get_top_inf(p_df):
                        if p_df.empty or 'code' not in p_df.columns: return "Aucune donnée"
                        counts = p_df['code'].value_counts().head(3)
                        items = []
                        for code, count in counts.items():
                            desc = PENALTY_CODES.get(str(code).upper().strip(), str(code))
                            items.append(f"{desc} ({count})")
                        return ", ".join(items) if items else "Aucune infraction majeure"

                    top_inf_t1 = get_top_inf(penalties_t1)
                    top_inf_t2 = get_top_inf(penalties_t2)


                    # Helper for Top Players
                    def get_top_players(p_df):
                        if p_df.empty: return "Aucune donnée"
                        # Determine col
                        p_col = 'player_name__' if 'player_name__' in p_df.columns else 'player_name'
                        if p_col not in p_df.columns: return "N/A"
                        
                        # Group by player
                        counts = p_df.groupby(p_col).size().sort_values(ascending=False).head(5)
                        
                        items = []
                        for player, count in counts.items():
                            # Get their top infraction
                            p_recs = p_df[p_df[p_col] == player]
                            if p_recs.empty: continue
                            
                            # Get duration sum (PIM)
                            # Parse duration "2:00" -> 2
                            # Simple approach if duration column exists
                            pim_sum = 0
                            if 'duration' in p_recs.columns:
                                 # Reuse parse_pim if available or simple split
                                 def safe_pim(x):
                                     try:
                                         parts = str(x).split(':')
                                         return int(parts[0])
                                     except: return 2 # fallback
                                 pim_sum = p_recs['duration'].apply(safe_pim).sum()
                            
                            top_code = p_recs['code'].value_counts().idxmax()
                            top_desc = PENALTY_CODES.get(str(top_code).upper().strip(), str(top_code))
                            
                            items.append(f"{player} ({pim_sum} PIM) - Principalement: {top_desc}")
                        return "\n".join([f"- {i}" for i in items]) if items else "Aucun joueur majeur"

                    top_players_t1 = get_top_players(penalties_t1)
                    top_players_t2 = get_top_players(penalties_t2)

                    prompt = f"""
                    Agis comme un coach de hockey expert (Niveau LHJMQ/M18AAA). Analyse TOUTES les données suivantes pour deux équipes et génère DEUX plans de match distincts.
                    
                    Tu disposes de tout le tableau de bord des statistiques. Utilise les termes français (BP, BC, AN, DN).
                    
                    **Contexte du Match :**
                    - Équipe 1 (Domicile): {s1.get('Team', 'Équipe 1')}
                    - Équipe 2 (Visiteur): {s2.get('Team', 'Équipe 2')}
                    
                    **1. Statistiques Saison (Globales) :**
                    - Stats Domicile : {s1_fr}
                    - Stats Visiteur : {s2_fr}
                    
                    **2. Analyse Comparative (Face-à-Face & Tendance) :**
                    - Avantage Triangle (Comparatif vs Adversaires Communs) : Domicile (+{snapshot['triangle'].get('t1_advantage',0)}) vs Visiteur (+{snapshot['triangle'].get('t2_advantage',0)})
                    - Volume de Tirs (Offensif Domicile) : {snapshot['t1'].get('shots_for_avg', 0):.1f} tirs/match
                    - Forme Récente (Visiteur - 5 derniers matchs) : {', '.join(snapshot['t2'].get('last_5', []))}
                    
                    **3. Détails par Période (Moyennes par match) :**
                    *P1 (1ère Période)*
                    - Buts Pour (BP) : Dom {p1_stats[1]['GF_avg']:.2f} vs Vis {p2_stats[1]['GF_avg']:.2f}
                    - Buts Contre (BC) : Dom {p1_stats[1]['GA_avg']:.2f} vs Vis {p2_stats[1]['GA_avg']:.2f}
                    
                    *P2 (2ème Période - Le long changement)*
                    - BP : Dom {p1_stats[2]['GF_avg']:.2f} vs Vis {p2_stats[2]['GF_avg']:.2f}
                    - BC : Dom {p1_stats[2]['GA_avg']:.2f} vs Vis {p2_stats[2]['GA_avg']:.2f}
                    - Punitions (PUN) : Dom {p1_stats[2]['PIM_avg']:.1f} vs Vis {p2_stats[2]['PIM_avg']:.1f}
                    
                    *P3 (3ème Période - Fin de match)*
                    - BP : Dom {p1_stats[3]['GF_avg']:.2f} vs Vis {p2_stats[3]['GF_avg']:.2f} 
                    - BC : Dom {p1_stats[3]['GA_avg']:.2f} vs Vis {p2_stats[3]['GA_avg']:.2f}
                    
                    **4. Discipline & Tendances (Infractions) :**
                    *DOMICILE (Top Infractions)*
                    {top_inf_t1}
                    
                    *DOMICILE (Joueurs à surveiller)*
                    {top_players_t1}
                    
                    *VISITEUR (Top Infractions)*
                    {top_inf_t2}
                    
                    *VISITEUR (Joueurs à surveiller)*
                    {top_players_t2}
                    
                    **TACHE :**
                    Génère un objet JSON stricte avec 2 clés principales : "team1_plan" et "team2_plan".
                    
                    Pour CHAQUE plan :
                    1. "global": Analyse générale DÉTAILLÉE. "text" doit être un paragraphe étoffé (plus long, environ 40-50 mots) expliquant le narratif du match, les enjeux et la stratégie globale.
                    2. "1", "2", "3": Conseils tactiques spécifiques à chaque période basés sur les stats ci-dessus.
                    
                    **Format JSON Attendu :**
                    {{
                        "team1_plan": {{
                            "global": {{"title": "...", "icon": "EMOJI_HERE (e.g. 🧊,🔥,🛡️)", "text": "...", "prediction": "..."}},
                            "1": {{"title": "...", "color": "green/red/blue/orange", "icon": "EMOJI_HERE", "text": "..."}},
                            "2": {{"title": "...", "color": "...", "icon": "...", "text": "..."}},
                            "3": {{"title": "...", "color": "...", "icon": "...", "text": "..."}}
                        }},
                        "team2_plan": {{
                            "global": {{"title": "...", "icon": "EMOJI_HERE", "text": "...", "prediction": "..."}},
                            "1": {{"title": "...", "color": "...", "icon": "...", "text": "..."}},
                            "2": {{"title": "...", "color": "...", "icon": "...", "text": "..."}},
                            "3": {{"title": "...", "color": "...", "icon": "...", "text": "..."}}
                        }}
                    }}
                    """
                    
                    response = model.generate_content(prompt)
                    txt = response.text.replace('```json', '').replace('```', '').strip()
                    return json.loads(txt)
                except Exception as e:
                    st.error(f"Erreur IA : {e}")
                    try:
                        # Attempt to list models to help debug
                        models = list(genai.list_models())
                        model_names = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
                        st.warning(f"Modèles disponibles détectés avec votre clé : {', '.join(model_names)}")
                    except Exception as e2:
                        st.error(f"Impossible de lister les modèles : {e2}")
                    return None

            def generate_game_plan(s1, s2, p1_stats, p2_stats, snapshot=None):
                """Generates rich narrative cards for P1, P2, P3 based on detailed complex stats analysis."""
                plan = {}
                
                # --- Unpack Snapshot if available ---
                # Defaults
                t1_shots_for = 0
                tri_adv_t1 = 0
                tri_adv_t2 = 0
                t2_recent_losses = 0
                
                if snapshot:
                    t1_shots_for = snapshot['t1'].get('shots_for_avg', 0)
                    
                    # Triangle Logic
                    tri_adv_t1 = snapshot['triangle'].get('t1_advantage', 0)
                    tri_adv_t2 = snapshot['triangle'].get('t2_advantage', 0)
                    
                    # Recent Form Analysis
                    last5_t2 = snapshot['t2'].get('last_5', [])
                    for r in last5_t2:
                        if r == 'L': t2_recent_losses += 1
                        else: break

                # --- Global Context ---
                us_gf = p1_stats[1]['GF_avg']
                them_gf = p2_stats[1]['GF_avg']
                them_ga = p2_stats[1]['GA_avg']
                us_pim_total = sum(p1_stats[p]['PIM_avg'] for p in [1,2,3])
                
                # --- [NEW] Global Component (Rule-based) ---
                # A simple synthesis
                g_title = "Match à Enjeu"
                g_text = "Les statistiques suggèrent un affrontement serré."
                g_icon = "🏒"
                
                if snapshot and tri_adv_t2 >= (tri_adv_t1 + 2):
                    g_title = "Défi Difficile (Outsider)"
                    g_text = "L'adversaire a l'avantage sur les adversaires communs. Il faudra jouer intelligemment."
                    g_icon = "🛡️"
                elif snapshot and tri_adv_t1 >= (tri_adv_t2 + 2):
                    g_title = "Avantage Théorique"
                    g_text = "Vous avez l'avantage statistique. Imposez votre rythme."
                    g_icon = "⭐"
                
                plan['global'] = {
                    'title': g_title,
                    'icon': g_icon,
                    'text': g_text,
                    'prediction': "Analyse basée sur les règles."
                }
                
                # --- P1: L'ENTAME ---
                
                # [NEW] Complex Scenario: The Bogey Team (Triangle Logic - Indirect Superiority)
                # If T2 has significantly better performance vs common opponents (e.g. +2 adv)
                if snapshot and tri_adv_t2 >= (tri_adv_t1 + 2):
                     plan[1] = {
                        'title': "P1 : Déjouer les Pronostics 🎱",
                        'color': 'red',
                        'icon': "🔮",
                        'text': f"**L'Outsider.** Ils ont battu {tri_adv_t2} équipes contre lesquelles vous avez perdu. <br>👉 *Stratégie :* Jouez sans complexe. Les mathématiques sont contre vous, alors changez l'équation."
                    }
                elif snapshot and tri_adv_t1 >= (tri_adv_t2 + 2):
                     plan[1] = {
                        'title': "P1 : Confiance Logique 🧠",
                        'color': 'green',
                        'icon': "📈",
                        'text': f"**L'Avantage Comparatif.** Vous battez régulièrement les équipes qui les battent (+{tri_adv_t1}). <br>👉 *Stratégie :* Imposez votre hiérarchie dès la mise au jeu initiale."
                    }
                # [NEW] Complex Scenario: The Shooting Gallery
                elif snapshot and t1_shots_for > 25.0 and us_gf < 0.8: 
                     plan[1] = {
                        'title': "P1 : Galerie de Tir 🎯",
                        'color': 'blue',
                        'icon': "🏒",
                        'text': f"**Manque de Finition.** Vous lancez beaucoup ({t1_shots_for:.1f}/m) mais ça ne rentre pas. <br>👉 *Stratégie :* Arrêtez de viser les lucarnes. Visez les jambières pour des retours. Trafic obligatoire."
                    }
                # [NEW] Complex Scenario: Cold Streak
                elif snapshot and t2_recent_losses >= 3:
                     plan[1] = {
                        'title': "P1 : Confiance Brisée 💔",
                        'color': 'green',
                        'icon': "📉",
                        'text': f"**Opposant Fragile.** Ils viennent de perdre {t2_recent_losses} matchs de suite. <br>👉 *Stratégie :* Marquez dans les 5 premières minutes. Ils vont s'effondrer mentalement."
                    }

                # Standard Scenarios
                elif them_gf < 0.8 and them_ga < 0.8 and us_pim_total > 8.0:
                    plan[1] = {
                            'title': "P1 : Le Piège 🕸️",
                            'color': 'red',
                            'icon': "🪤",
                            'text': f"**Ne tombez pas dans le panneau.** Ils jouent la tortue (BP: {them_gf:.1f}) pour vous frustrer. <br>👉 *Stratégie :* Aucun risque inutile. Discipline monacale requise."
                        }
                elif them_gf > 1.8 and them_ga > 1.8:
                    plan[1] = {
                        'title': "P1 : Canon de Verre 💥",
                        'color': 'orange',
                        'icon': "🔫",
                        'text': f"**Tout pour l'attaque.** Ils marquent beaucoup ({them_gf:.1f}) mais c'est une passoire derrière. <br>👉 *Stratégie :* Shootout mode. Saturez l'enclave, ça va rentrer."
                    }
                elif (p1_stats[1]['GF_avg'] > 1.25) and them_ga > 1.25:
                    plan[1] = {
                        'title': "P1 : Départ Canon 🚀", 
                        'color': 'green', 
                        'icon': "⚡",
                        'text': f"**Blitzkrieg.** Vous marquez beaucoup en 1re et ils sont fragiles. <br>👉 *Stratégie :* Forecheck agressif dès la première seconde."
                    }
                else:
                    plan[1] = {
                        'title': "P1 : Mise en Place ♟️", 
                        'color': 'blue', 
                        'icon': "⏱️",
                        'text': f"**Jeu Équilibré.** Stats similaires en début de match. <br>👉 *Stratégie :* Le premier but dictera le ton pour le reste du match."
                    }


                # --- P2: LE CHANGEMENT (The Grind) ---
                us_pim = p1_stats[2]['PIM_avg']
                them_pim = p2_stats[2]['PIM_avg']
                them_ga_p2 = p2_stats[2]['GA_avg']
                us_pp_perc = s1.get('%AN', 0) if s1 is not None else 0
                
                # Complex Scenario: Bully Victim (High PIM Opp + High PP Us)
                if them_pim > 5.0 and us_pp_perc > 20.0:
                     plan[2] = {
                        'title': "P2 : Revanche Glacée ❄️", 
                        'color': 'green', 
                        'icon': "⚖️",
                        'text': f"**Punissez les Brutes.** Ils sont indisciplinés ({them_pim:.1f} PIM) et votre AN est performant. <br>👉 *Stratégie :* Provoquez les fautes, ne répondez pas aux coups. Faites-les payer au tableau d'affichage."
                    }
                elif them_pim > 4.0:
                     plan[2] = {
                        'title': "P2 : Guerre des Nerfs 🤬", 
                        'color': 'green', 
                        'icon': "👮",
                        'text': f"**Provoquez-les.** C'est leur période la plus indisciplinée ({them_pim:.1f} PIM). <br>👉 *Stratégie :* Mettez du trafic devant le filet et faites-les disjoncter. Le match se gagne en Power Play ici."
                    }
                elif us_pim > 4.0:
                    plan[2] = {
                        'title': "P2 : Discipline de Fer ⛓️", 
                        'color': 'red', 
                        'icon': "🤐",
                        'text': f"**Danger Punitions.** C'est votre talon d'Achille ({us_pim:.1f} PIM). <br>👉 *Stratégie :* Patinez au lieu d'accrocher. Le long changement rend les désavantages numériques épuisants."
                    }
                elif (us_pim + them_pim) > 6.0:
                     plan[2] = {
                        'title': "P2 : Unités Spéciales ⚖️",
                        'color': 'orange',
                        'icon': "👮",
                        'text': f"**Bataille d'AN/DN.** Le match va se jouer à 4 contre 5 (Total PIM: {us_pim+them_pim:.0f}). <br>👉 *Stratégie :* Soyez disciplinés. Provoquez les fautes. Vos unités spéciales doivent faire la différence."
                    }
                elif them_ga_p2 < 0.5:
                    plan[2] = {
                        'title': "P2 : Le Mur 🧱",
                        'color': 'red',
                        'icon': "🛑",
                        'text': f"**Hermétique.** Ils ne donnent rien en 2e ({them_ga_p2:.1f} BC). <br>👉 *Stratégie :* Oubliez les beaux jeux. Il faudra un but 'sale' : trafic, déviations, retours de lancer."
                    }
                elif them_ga_p2 > 1.5:
                    plan[2] = {
                        'title': "P2 : Le Ventre Mou 🦈", 
                        'color': 'green', 
                        'icon': "🎯",
                        'text': f"**Opportunité.** Ils encaissent énormément en période médiane ({them_ga_p2:.1f} BC). <br>👉 *Stratégie :* Étirez le jeu et profitez de la fatigue causée par le long changement pour les piéger."
                    }
                elif (p1_stats[2]['GF_avg'] + them_ga_p2) > 3.5:
                    plan[2] = {
                        'title': "P2 : Portes Ouvertes 🎪", 
                        'color': 'orange', 
                        'icon': "🥅",
                        'text': "**Festival Offensif.** Les stats prédisent beaucoup de buts ici.<br>👉 *Stratégie :* Si vous menez, verrouillez. Si vous perdez, c'est le moment de tout lâcher en attaque."
                    }
                else:
                    plan[2] = {
                        'title': "P2 : Bataille de Tranchées 🛡️", 
                        'color': 'blue', 
                        'icon': "⚔️",
                        'text': f"**Défense Serrée.** Peu d'ouverture probable (PIM: {them_pim:.1f}, BC: {them_ga_p2:.1f}). <br>👉 *Stratégie :* Les changements de lignes seront cruciaux. Ne restez pas coincés trop longtemps."
                    }

                # --- P3: LA FINITION (The Close) ---
                us_ga_p3 = p1_stats[3]['GA_avg']
                them_gf_p3 = p2_stats[3]['GF_avg']
                them_ga_p3 = p2_stats[3]['GA_avg']
                them_pp = s2['%AN'] if '%AN' in s2 else (s2['%AN (Rec)'] if '%AN (Rec)' in s2 else 0)
                diff_clutch = (p1_stats[3]['GF_avg'] - p1_stats[3]['GA_avg']) - (p2_stats[3]['GF_avg'] - p2_stats[3]['GA_avg'])
                
                # Complex Scenario: Turtle Mode
                if them_ga_p3 < 0.6 and them_gf_p3 < 0.6:
                     plan[3] = {
                        'title': "P3 : La Tortue 🐢", 
                        'color': 'orange', 
                        'icon': "🔒",
                        'text': f"**Casser la Coquille.** Ils ferment le jeu en 3e (Total Buts ~{them_ga_p3+them_gf_p3:.1f}). <br>👉 *Stratégie :* Dump and Chase obligatoire. Échec avant agressif pour forcer l'erreur."
                    }
                elif us_ga_p3 > 1.35:
                    plan[3] = {
                        'title': "P3 : Zone de Danger ⚠️", 
                        'color': 'red', 
                        'icon': "🧱",
                        'text': f"**Risque d'Effondrement.** Vous accordez trop de buts en fin de match ({us_ga_p3:.1f}). <br>👉 *Stratégie :* Simplifiez la sortie de zone. Pas de passes risquées dans l'axe. Jouez la montre."
                    }
                elif us_ga_p3 > 2.0:
                     plan[3] = {
                        'title': "P3 : Sauvés par le Gong 🔔",
                        'color': 'red',
                        'icon': "🆘",
                        'text': f"**Fin de Match Fragile.** Vous encaissez trop en fin de match ({us_ga_p3:.1f} BC). <br>👉 *Stratégie :* Si vous menez, ne reculez pas. Jouez dans LEUR zone pour écouler le temps."
                    }
                elif them_ga_p3 > 1.4:
                    plan[3] = {
                        'title': "P3 : L'Estocade 🗡️", 
                        'color': 'green', 
                        'icon': "🩸",
                        'text': f"**Ils craquent.** L'adversaire s'écroule souvent en 3e ({them_ga_p3:.1f} BC). <br>👉 *Stratégie :* Même si le score est serré, continuez à pousser. Ils vont finir par faire une erreur fatale."
                    }
                elif them_pp > 25.0 and p1_stats[3]['PIM_avg'] > 2.0:
                    plan[3] = {
                        'title': "P3 : Discipline Mortelle ☠️", 
                        'color': 'red', 
                        'icon': "🚫",
                        'text': f"**Alerte Spéciale.** Leur Power Play est létal ({them_pp:.0f}%) et vous prenez des pénalités tardives. <br>👉 *Stratégie :* Aucune punition en zone offensive. Bâton sur la glace."
                    }
                elif diff_clutch > 0.5:
                    plan[3] = {
                        'title': "P3 : Avantage Physique 💪", 
                        'color': 'green', 
                        'icon': "🔋",
                        'text': "**Finisseurs.** Vous finissez vos matchs beaucoup plus fort qu'eux. <br>👉 *Stratégie :* Imposez votre rythme. Plus le match avance, plus vous avez l'avantage."
                    }
                else:
                    plan[3] = {
                        'title': "P3 : Money Time 💰", 
                        'color': 'blue', 
                        'icon': "🧊",
                        'text': f"**Tout se joue maintenant.** Stats équilibrées en fin de match ({them_ga_p3:.1f} BC). <br>👉 *Stratégie :* Sang-froid absolu. Le travail fera la différence."
                    }
                    
                return plan



            if s1 is not None and s2 is not None:
                 # 1. TALE OF THE TAPE (Choc des Forces)
                 st.subheader("🥊 Choc des Forces")
                 
                 p_stats1 = get_period_breakdown(t1, games)
                 p_stats2 = get_period_breakdown(t2, games)
                 
                 # Helper for Color Gradient
                 def get_gradient_color(delta, limit, is_inverse=False):
                     # Determine polarity
                     # Good for us: delta > 0 (Green) unless inverse (Red)
                     # Bad for us: delta < 0 (Red) unless inverse (Green)
                     
                     val = max(min(delta, limit), -limit) # Clamp
                     ratio = abs(val) / limit
                     
                     # Colors (RGB)
                     # White: 255, 255, 255 (at ratio 0)
                     # Green: 76, 175, 80 (#4caf50)
                     # Red: 255, 75, 75 (#ff4b4b)
                     
                     # Determine target color based on "Goodness"
                     is_good = (delta > 0 and not is_inverse) or (delta < 0 and is_inverse)
                     
                     if is_good:
                         # Mix White -> Green
                         r = int(255 + (76 - 255) * ratio)
                         g = int(255 + (175 - 255) * ratio)
                         b = int(255 + (80 - 255) * ratio)
                     else:
                         # Mix White -> Red
                         r = int(255 + (255 - 255) * ratio)
                         g = int(255 + (75 - 255) * ratio)
                         b = int(255 + (75 - 255) * ratio)
                         
                     return f"rgb({r}, {g}, {b})"

                 # --- NARRATIVE / GAME PLAN GENERATOR ---
                 # --- NARRATIVE / GAME PLAN GENERATOR ---



                 # HTML Component for Metric + MiniTable
                 def render_stat_card(label, val_main, delta, p_data, p_data_opp, key_suffix, is_inverse=False, is_perc=False, val_fmt="{:.2f}", show_table=True):
                     # Determine Limit based on metric type
                     limit = 1.5 # Default (Goals)
                     if is_perc: limit = 15.0 # Percentages (PP/PK)
                     elif 'PIM' in key_suffix: limit = 6.0 # PIM
                     
                     color = get_gradient_color(delta, limit, is_inverse)
                     
                     table_html = ""
                     if show_table:
                         def fmt_mini(val):
                             if is_perc: return f"{val:.0f}%" # Compact %
                             return f"{val:.1f}" # Compact float
                         
                         # P1
                         v_p1_raw = p_data[1][key_suffix]
                         v_p1_opp = p_data_opp[1][key_suffix]
                         d_p1 = v_p1_raw - v_p1_opp
                         c_p1 = get_gradient_color(d_p1, limit, is_inverse)
                         v_p1 = fmt_mini(v_p1_raw)
                         
                         # P2
                         v_p2_raw = p_data[2][key_suffix]
                         v_p2_opp = p_data_opp[2][key_suffix]
                         d_p2 = v_p2_raw - v_p2_opp
                         c_p2 = get_gradient_color(d_p2, limit, is_inverse)
                         v_p2 = fmt_mini(v_p2_raw)

                         # P3
                         v_p3_raw = p_data[3][key_suffix]
                         v_p3_opp = p_data_opp[3][key_suffix]
                         d_p3 = v_p3_raw - v_p3_opp
                         c_p3 = get_gradient_color(d_p3, limit, is_inverse)
                         v_p3 = fmt_mini(v_p3_raw)
                         
                         table_html = (
                             '<div style="margin-left: 5px;">'
                             '<table style="font-size: 1.1rem; text-align: center; border-collapse: collapse;">'
                             '<tr style="color: #666; border-bottom: 1px solid #444;"><td>P1</td><td>P2</td><td>P3</td></tr>'
                             '<tr style="color: #ccc;">'
                             f'<td style="padding: 2px 8px; color: {c_p1}; font-weight: bold;">{v_p1}</td>'
                             f'<td style="padding: 2px 8px; color: {c_p2}; font-weight: bold;">{v_p2}</td>'
                             f'<td style="padding: 2px 8px; color: {c_p3}; font-weight: bold;">{v_p3}</td>'
                             '</tr></table></div>'
                         )
                     
                     label_html = f'<div style="font-size: 0.8rem; color: #888; margin-bottom: 4px;">{label}</div>' if label else ''
                     
                     html = (
                         '<div style="background-color: #1a1e24; border-radius: 8px; padding: 10px; margin-bottom: 10px; border: 1px solid #333;">'
                         f'{label_html}'
                         '<div style="display: flex; align-items: flex-end; gap: 15px;">'
                         '<div>'
                         f'<div style="font-size: 1.8rem; font-weight: bold; color: {color};">{val_main}</div>'
                         '</div>'
                         '</div>'
                         f'{table_html}'
                         '</div></div>'
                     )
                     return html

                 # --- LAYOUT REFACTORING (Matrix Style) ---
                 
                 # 1. Pre-calculate all metrics and deltas to decouple from rendering order
                 # Offense (GF/GP)
                 off_v1 = round(s1['GF']/s1['GP'], 1) if s1['GP'] else 0
                 off_v2 = round(s2['GF']/s2['GP'], 1) if s2['GP'] else 0
                 off_d = off_v1 - off_v2
                 
                 # Defense (GA/GP)
                 def_v1 = round(s1['GA']/s1['GP'], 1) if s1['GP'] else 0
                 def_v2 = round(s2['GA']/s2['GP'], 1) if s2['GP'] else 0
                 def_d = def_v1 - def_v2
                 
                 # Power Play (PP%)
                 pp_v1 = int(round(s1['PP%']))
                 pp_v2 = int(round(s2['PP%']))
                 pp_d = pp_v1 - pp_v2
                 
                 # Discipline (PIM/GP)
                 pim_v1 = round(s1['PIM']/s1['GP'], 1) if s1['GP'] else 0
                 pim_v2 = round(s2['PIM']/s2['GP'], 1) if s2['GP'] else 0
                 pim_d = pim_v1 - pim_v2

                 # PK (Total)
                 pk_v1 = int(round(s1['PK%']))
                 pk_v2 = int(round(s2['PK%']))
                 pk_d = pk_v1 - pk_v2

                 # 2. Render Header Row
                 h_cols = st.columns([1.5, 2, 2, 2, 2, 2])
                 
                 def render_header(title, subtitle):
                     return f"""<div style='text-align: center; margin-bottom: 10px;'>
                         <div style='color: #bbb; text-transform: uppercase; font-size: 0.9rem; font-weight: bold; padding-bottom: 2px;'>{title}</div>
                         <div style='color: #fff; font-size: 0.85rem; border-top: 1px solid #444; padding-top: 2px;'>{subtitle}</div>
                     </div>"""
                 
                 with h_cols[1]: st.markdown(render_header("Attaque", "Buts Pour / Match"), unsafe_allow_html=True)
                 with h_cols[2]: st.markdown(render_header("Défense", "Buts Contre / Match"), unsafe_allow_html=True)
                 with h_cols[3]: st.markdown(render_header("Avantage Num.", "% Efficacité"), unsafe_allow_html=True)
                 with h_cols[4]: st.markdown(render_header("Désavantage Num.", "% Efficacité"), unsafe_allow_html=True)
                 with h_cols[5]: st.markdown(render_header("Discipline", "PUN / Match"), unsafe_allow_html=True)
                 
                 def render_team_label(name):
                     return f"<div style='display: flex; align-items: center; height: 100%; font-weight: bold; font-size: 1.3rem; color: #00A8E8; padding-top: 25px; line-height: 1.2;'>{name}</div>"

                 # 3. Render Team Rows
                 # Team 1
                 r1_cols = st.columns([1.5, 2, 2, 2, 2, 2])
                 with r1_cols[0]:
                     st.markdown(render_team_label(t1), unsafe_allow_html=True)
                 with r1_cols[1]:
                     st.markdown(render_stat_card("", off_v1, off_d, p_stats1, p_stats2, 'GF_avg'), unsafe_allow_html=True)
                 with r1_cols[2]:
                     st.markdown(render_stat_card("", def_v1, def_d, p_stats1, p_stats2, 'GA_avg', is_inverse=True), unsafe_allow_html=True)
                 with r1_cols[3]:
                     st.markdown(render_stat_card("", f"{pp_v1}%", pp_d, p_stats1, p_stats2, 'PP%', is_perc=True, show_table=True), unsafe_allow_html=True)
                 with r1_cols[4]:
                     st.markdown(render_stat_card("", f"{pk_v1}%", pk_d, p_stats1, p_stats2, 'PK%', is_perc=True, show_table=True), unsafe_allow_html=True)
                 with r1_cols[5]:
                     st.markdown(render_stat_card("", pim_v1, pim_d, p_stats1, p_stats2, 'PIM_avg', is_inverse=True), unsafe_allow_html=True)

                 # Team 2
                 r2_cols = st.columns([1.5, 2, 2, 2, 2, 2])
                 with r2_cols[0]:
                      st.markdown(render_team_label(t2), unsafe_allow_html=True)
                 with r2_cols[1]:
                     st.markdown(render_stat_card("", off_v2, -off_d, p_stats2, p_stats1, 'GF_avg'), unsafe_allow_html=True)
                 with r2_cols[2]:
                     st.markdown(render_stat_card("", def_v2, -def_d, p_stats2, p_stats1, 'GA_avg', is_inverse=True), unsafe_allow_html=True)
                 with r2_cols[3]:
                     st.markdown(render_stat_card("", f"{pp_v2}%", -pp_d, p_stats2, p_stats1, 'PP%', is_perc=True, show_table=True), unsafe_allow_html=True)
                 with r2_cols[4]:
                     st.markdown(render_stat_card("", f"{pk_v2}%", -pk_d, p_stats2, p_stats1, 'PK%', is_perc=True, show_table=True), unsafe_allow_html=True)
                 with r2_cols[5]:
                     st.markdown(render_stat_card("", pim_v2, -pim_d, p_stats2, p_stats1, 'PIM_avg', is_inverse=True), unsafe_allow_html=True)
            
            st.divider()

            # --- GAME PLAN SECTION ---
            st.subheader("📋 Plan de Match & Clés du Succès")
            
            # --- AI TOGGLE ---
            ai_mode = st.sidebar.toggle("🤖 Mode IA Générative (Gemini)", value=True)
            api_key = None
            if ai_mode:
                # Try to get from secrets first
                try:
                    if "GEMINI_API_KEY" in st.secrets:
                        api_key = st.secrets["GEMINI_API_KEY"]
                except (FileNotFoundError, Exception):
                    # Secrets file doesn't exist or other error, fallback to manual input
                    pass
                
                if not api_key:
                    api_key = st.sidebar.text_input("Clé API Gemini", type="password")
                
                # Model Selection (Locked to Flash)
                model_name = "gemini-3-flash-preview"
            
            # --- NEW: Get Context Snapshot ---
            snapshot = get_game_context_snapshot(t1, t2, games, goals)
            
            plan = {}
            if ai_mode and api_key:
                with st.spinner(f"L'IA ({model_name}) analyse le match..."):
                     # Prepare Penalties
                     t1_name = s1.get('Team', s1.get('Équipe', ''))
                     t2_name = s2.get('Team', s2.get('Équipe', ''))
                     pens_t1 = penalties[penalties['team_name'] == t1_name]
                     pens_t2 = penalties[penalties['team_name'] == t2_name]
                     
                     plan = generate_game_plan_ai(s1, s2, p_stats1, p_stats2, snapshot, pens_t1, pens_t2, api_key, model_name)
            
            # Fallback (or if AI not active/failed)
            if not plan:
                 # Generate Rule-Based for T1
                 p1 = generate_game_plan(s1, s2, p_stats1, p_stats2, snapshot)
                 # Generate Rule-Based for T2 (Use S2 as primary)
                 # Note: Snapshot T1/T2 keys might need swapping conceptually, but simpler to just pass original
                 # For a quick fix, we just generate T1's perspective. Ideally we'd swap snapshot too.
                 # Let's try to generate T2 perspective simply:
                 s2_snapshot = snapshot # In a real implementation we'd flip the snapshot logic
                 p2 = generate_game_plan(s2, s1, p_stats2, p_stats1, s2_snapshot)
                 
                 plan = {
                     "team1_plan": p1,
                     "team2_plan": p2
                 }

            # --- RENDER DUAL COLUMNS (ROW BY ROW ALIGNMENT) ---
            t1_plan = plan.get('team1_plan', {})
            t2_plan = plan.get('team2_plan', {})

            # CSS for Vertical Label
            st.markdown("""
            <style>
                .vertical-text {
                    writing-mode: vertical-rl;
                    text-orientation: mixed;
                    transform: rotate(180deg);
                    text-align: center;
                    font-weight: bold;
                    font-size: 1.2rem;
                    color: #888;
                    height: 100%;
                    max-height: 150px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    border-right: 2px solid #444;
                }
                .row-label-container {
                     display: flex; 
                     align-items: center; 
                     justify-content: center; 
                     height: 100%; 
                     min-height: 120px;
                }
            </style>
            """, unsafe_allow_html=True)

            # Header Row (Skip label for header)
            c_label, c_h1, c_h2 = st.columns([0.1, 1, 1])
            with c_h1: st.markdown(f"<h3 style='text-align: center; color: #00A8E8;'>Plan pour {t1}</h3>", unsafe_allow_html=True)
            with c_h2: st.markdown(f"<h3 style='text-align: center; color: #00A8E8;'>Plan pour {t2}</h3>", unsafe_allow_html=True)
            
            # Helper to render a generic card
            def render_card_html(item, is_global=False):
                if not item: return ""
                if is_global:
                    return f"""
                        <div style="background-color: #2c2f38; border-left: 5px solid #00A8E8; padding: 15px; margin-bottom: 20px; border-radius: 5px; min-height: 180px;">
                            <div style="font-size: 1.1rem; font-weight: bold; color: #fff; display: flex; align-items: center;">
                                <span style="font-size: 1.4rem; margin-right: 10px;">{item.get('icon', '🧠')}</span> {item.get('title', 'Global')}
                            </div>
                            <div style="margin-top: 5px; font-size: 0.95rem; color: #ddd;">{item.get('text', '')}</div>
                            <div style="margin-top: 8px; font-size: 0.9rem; color: #00A8E8; font-weight: bold;">🔮 {item.get('prediction', '')}</div>
                        </div>
                    """
                else:
                    color_map = {'green': '#1f4025', 'red': '#521d1d', 'blue': '#1a2e40', 'orange': '#5c3a00'}
                    bg = color_map.get(item.get('color'), '#1a2e40')
                    return f"""
                        <div style="background-color: {bg}; border-radius: 8px; padding: 10px; margin-bottom: 15px; border: 1px solid #444; min-height: 120px;">
                           <div style="font-weight: bold; font-size: 1rem; margin-bottom: 5px;">{item.get('icon','')} {item.get('title','')}</div>
                           <div style="font-size: 0.9rem; line-height: 1.3;">{item.get('text','')}</div>
                        </div>
                    """

            def render_label(text):
                 return f"""
                 <div class="row-label-container">
                    <div style="writing-mode: vertical-rl; transform: rotate(180deg); font-weight: bold; font-size: 1.1rem; color: #aaa; letter-spacing: 2px;">
                        {text}
                    </div>
                 </div>
                 """

            # 1. Global Analysis Row
            r_l, r_g1, r_g2 = st.columns([0.1, 1, 1])
            with r_l: st.markdown(render_label("MATCH"), unsafe_allow_html=True)
            with r_g1: st.markdown(render_card_html(t1_plan.get('global'), is_global=True), unsafe_allow_html=True)
            with r_g2: st.markdown(render_card_html(t2_plan.get('global'), is_global=True), unsafe_allow_html=True)
            
            st.divider() # Clear separation
            
            # 2. Periods Rows (P1, P2, P3)
            def get_p_item(plan_dict, pid):
                return plan_dict.get(str(pid)) or plan_dict.get(pid)

            # P1 Row
            r_p1_l, r_p1_1, r_p1_2 = st.columns([0.1, 1, 1])
            with r_p1_l: st.markdown(render_label("PERIODE 1"), unsafe_allow_html=True)
            with r_p1_1: st.markdown(render_card_html(get_p_item(t1_plan, 1)), unsafe_allow_html=True)
            with r_p1_2: st.markdown(render_card_html(get_p_item(t2_plan, 1)), unsafe_allow_html=True)
            
            # P2 Row
            r_p2_l, r_p2_1, r_p2_2 = st.columns([0.1, 1, 1])
            with r_p2_l: st.markdown(render_label("PERIODE 2"), unsafe_allow_html=True)
            with r_p2_1: st.markdown(render_card_html(get_p_item(t1_plan, 2)), unsafe_allow_html=True)
            with r_p2_2: st.markdown(render_card_html(get_p_item(t2_plan, 2)), unsafe_allow_html=True)
            
            # P3 Row
            r_p3_l, r_p3_1, r_p3_2 = st.columns([0.1, 1, 1])
            with r_p3_l: st.markdown(render_label("PERIODE 3"), unsafe_allow_html=True)
            with r_p3_1: st.markdown(render_card_html(get_p_item(t1_plan, 3)), unsafe_allow_html=True)
            with r_p3_2: st.markdown(render_card_html(get_p_item(t2_plan, 3)), unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            st.divider()
            
            # 2. ZONE DE DANGER (Period Analysis)
            # Calculate Goals per period for each team season-wide (For vs Against)
            # We can use our SQL/Data or recalculate quick.
            # Using 'goals' DF:
            # T1 Goals
            def get_period_diffs(team):
                # Goals FOR
                g_for = goals[goals['team_name'] == team]
                gf_p = g_for.groupby('period').size() # 1, 2, 3...
                
                # Goals AGAINST (Games involved but team_name != team)
                # Need games involved
                g_team_games = games[(games['home'] == team) | (games['visitor'] == team)]['game_id']
                g_against = goals[(goals['game_id'].isin(g_team_games)) & (goals['team_name'] != team)]
                ga_p = g_against.groupby('period').size()
                
                diffs = {}
                for p in [1, 2, 3]:
                    f = gf_p.get(p, 0)
                    a = ga_p.get(p, 0)
                    diffs[p] = f - a
                return diffs
            
            d1 = get_period_diffs(t1)
            d2 = get_period_diffs(t2)
            
            c_zone, c_common = st.columns([0.4, 0.6])
            
            with c_zone:
                st.subheader("⚠️ Zone de Danger")
                st.caption("Différentiel Buts Pour / Buts Contre par période (Saison)")
                
                # Simple HTML Table
                # Simple HTML Table
                z_html = (
                    '<table style="width:100%; text-align:center; border-collapse: collapse;">'
                    f'<tr style="border-bottom:1px solid #444; color:#888;"><th>Période</th><th>{t1}</th><th>{t2}</th></tr>'
                    f'<tr><td>1ère</td><td style="color:{"#4caf50" if d1[1]>0 else "#ff4b4b"}">{d1[1]:+d}</td><td style="color:{"#4caf50" if d2[1]>0 else "#ff4b4b"}">{d2[1]:+d}</td></tr>'
                    f'<tr><td>2e</td><td style="color:{"#4caf50" if d1[2]>0 else "#ff4b4b"}">{d1[2]:+d}</td><td style="color:{"#4caf50" if d2[2]>0 else "#ff4b4b"}">{d2[2]:+d}</td></tr>'
                    f'<tr><td>3e</td><td style="color:{"#4caf50" if d1[3]>0 else "#ff4b4b"}">{d1[3]:+d}</td><td style="color:{"#4caf50" if d2[3]>0 else "#ff4b4b"}">{d2[3]:+d}</td></tr>'
                    '</table>'
                )
                st.markdown(z_html, unsafe_allow_html=True)
                
            # 3. COMMON OPPONENTS (Triangle)
            with c_common:
                st.subheader("🔺 Le Triangle (Adversaires Communs)")
                # Find opponents t1 has played
                g1 = games[(games['home'] == t1) | (games['visitor'] == t1)]
                opp1 = set(g1['home']).union(set(g1['visitor'])) - {t1}
                
                g2 = games[(games['home'] == t2) | (games['visitor'] == t2)]
                opp2 = set(g2['home']).union(set(g2['visitor'])) - {t2}
                
                common = list(opp1.intersection(opp2))
                
                if common:
                    # Build table data
                    rows = []
                    for opp in common:
                        # Res T1 vs Opp
                        # Find game
                        game_1 = g1[(g1['home'] == opp) | (g1['visitor'] == opp)].sort_values('date_dt').iloc[-1] # LATEST
                        # Result T1
                        s_t1_us = game_1['final_score_home'] if game_1['home'] == t1 else game_1['final_score_visitor']
                        s_t1_them = game_1['final_score_visitor'] if game_1['home'] == t1 else game_1['final_score_home']
                        res1 = f"G {s_t1_us}-{s_t1_them}" if s_t1_us > s_t1_them else (f"P {s_t1_us}-{s_t1_them}" if s_t1_us < s_t1_them else f"N {s_t1_us}-{s_t1_them}")
                        color1 = "#4caf50" if s_t1_us > s_t1_them else ("#ff4b4b" if s_t1_us < s_t1_them else "#ffa726")
                        
                        # Res T2 vs Opp
                        game_2 = g2[(g2['home'] == opp) | (g2['visitor'] == opp)].sort_values('date_dt').iloc[-1]
                        s_t2_us = game_2['final_score_home'] if game_2['home'] == t2 else game_2['final_score_visitor']
                        s_t2_them = game_2['final_score_visitor'] if game_2['home'] == t2 else game_2['final_score_home']
                        res2 = f"G {s_t2_us}-{s_t2_them}" if s_t2_us > s_t2_them else (f"P {s_t2_us}-{s_t2_them}" if s_t2_us < s_t2_them else f"N {s_t2_us}-{s_t2_them}")
                        color2 = "#4caf50" if s_t2_us > s_t2_them else ("#ff4b4b" if s_t2_us < s_t2_them else "#ffa726")
                        
                        # Use clean string concatenation to avoid indentation issues in Markdown
                        rows.append(f"<tr><td style='text-align:left; padding-left:10px;'>{opp}</td><td style='color:{color1}; font-weight:bold;'>{res1}</td><td style='color:{color2}; font-weight:bold;'>{res2}</td></tr>")
                    
                    rows_html = "".join(rows)
                    tbl = (
                        '<table style="width:100%; text-align:center; border-collapse: collapse; font-size: 0.9rem;">'
                        '<tr style="border-bottom:1px solid #444; color:#888;">'
                        '<th style="text-align:left; padding-left:10px;">Adversaire</th>'
                        f'<th>Résultat {t1}</th>'
                        f'<th>Résultat {t2}</th>'
                        '</tr>'
                        f'{rows_html}'
                        '</table>'
                    )
                    st.markdown(tbl, unsafe_allow_html=True)
                else:
                    st.info("Aucun adversaire commun trouvé pour l'instant.")
            
            st.divider()

        for selected_team in selected_teams:
            st.header(f"📊 Analyse d'Équipe : {selected_team}")
            
            # Helper to get stats for N games
            def get_trend_row(team, n_games, games_pool, all_goals, all_pens):
                # Filter for team
                t_games = games_pool[(games_pool['home'] == team) | (games_pool['visitor'] == team)].copy()
                # Sort Date DESC
                t_games = t_games.sort_values(by='date_dt', ascending=False)
                # Take Top N
                if n_games:
                    t_games = t_games.head(n_games)
                
                if t_games.empty:
                    return None

                # Calculate Stats using standard function?
                # It returns a DF.
                # We need to filter goals/pens for these specific games
                g_ids = t_games['game_id'].unique()
                t_goals = all_goals[all_goals['game_id'].isin(g_ids)]
                t_pens = all_pens[all_pens['game_id'].isin(g_ids)]
                
                df_stats = calculate_standings(t_games, t_pens, t_goals)
                if not df_stats.empty:
                     # Filter just in case
                     row = df_stats[df_stats['Team'] == team]
                     if not row.empty:
                         return row.iloc[0]
                return None

            # Data Sources
            # We need "Completed" games for accurate stats (scores/shots confirmed)
            # games_complete is filtered by date and checked for completion
            # goals, penalties are filtered by date
            
            # 1. Total (Selected Period)
            row_total = get_trend_row(selected_team, None, games, goals, penalties)
            
            # 2. Last 10
            row_10 = get_trend_row(selected_team, 10, games, goals, penalties)
            
            # 3. Last 5
            row_5 = get_trend_row(selected_team, 5, games, goals, penalties)
            
            if row_total is not None:
                # Generate HTML Table for perfect alignment

                
                # Styles
                table_style = """
                <style>
                  .trend-table { width: 100%; border-collapse: separate; border-spacing: 0 4px; }
                  .trend-table th { text-align: center; font-size: 1.25rem !important; color: #bbb !important; font-weight: normal; padding-bottom: 5px; border-bottom: 1px solid #444; }
                  .trend-table td { text-align: center; padding: 4px 0; font-family: sans-serif; font-size: 1.4rem !important; }
                  .trend-table td.row-label { text-align: left; font-weight: bold; padding-right: 15px; width: 15%; font-size: 1.1rem !important; }
                  .trend-row-total { color: #ffffff; font-weight: 700; font-size: 1.5rem !important; }
                  .trend-row-10 { color: #B0B0B0; font-weight: 500; font-size: 1.35rem !important; }
                  .trend-row-5 { color: #707070; font-weight: 500; font-size: 1.35rem !important; }
                </style>
                """
                
                # Header - Usage of dedent to avoid Markdown Code Block interpretation
                html_header = textwrap.dedent(f"""
                {table_style}
                <table class="trend-table">
                  <thead>
                    <tr>
                       <th style="text-align: left;">Période</th>
                       <th>PTS/MJ</th>
                       <th>Fiche</th>
                       <th>BP/MJ</th>
                       <th>BC/MJ</th>
                       <th>% AN</th>
                       <th>% DN</th>
                       <th>PUN/MJ</th>
                       <th>FJ/MJ</th>
                    </tr>
                  </thead>
                  <tbody>
                """)
                
                html = html_header
                
                # Helper to format row
                def make_html_row(row, label, css_class):
                    pun = round(row['PIM'] / row['GP'], 1) if row['GP'] else 0
                    pts_pg = round(row['PTS'] / row['GP'], 1) if row['GP'] else 0.0
                    gf_pg = round(row['GF'] / row['GP'], 1) if row['GP'] else 0.0
                    ga_pg = round(row['GA'] / row['GP'], 1) if row['GP'] else 0.0
                    fj_pg = round(row['FJ'] / row['GP'], 1) if row['GP'] else 0.0
                    
                    return textwrap.dedent(f"""
                    <tr class="{css_class}">
                       <td class="row-label">{label}</td>
                       <td>{pts_pg}</td>
                       <td>{row['W']}-{row['L']}-{row['T']}</td>
                       <td>{gf_pg}</td>
                       <td>{ga_pg}</td>
                       <td>{row['PP%']}%</td>
                       <td>{row['PK%']}%</td>
                       <td>{pun}</td>
                       <td>{fj_pg}</td>
                    </tr>
                    """)

                # Row 1: Total
                html += make_html_row(row_total, "Global", "trend-row-total")
                
                # Row 2: Last 10
                if row_10 is not None:
                    html += make_html_row(row_10, "10 derniers", "trend-row-10")
                    
                # Row 3: Last 5
                if row_5 is not None:
                    html += make_html_row(row_5, "5 derniers", "trend-row-5")
                    
                html += "</tbody></table>"
                
                st.markdown(html, unsafe_allow_html=True)

            st.divider()

        # Re-calc for tabs if necessary (only needed for len=1 case, logical fall-through works)
        if len(selected_teams) == 1:
             goals_filtered = goals[goals['team_name'] == selected_team].merge(game_dates, on='game_id', how='left')
             penalties_filtered = penalties[penalties['team_name'] == selected_team].merge(game_dates, on='game_id', how='left')


    # 3. TABS (Logic)
    # If Single Team: Show Journal + Details (Punitions, Buts)
    # If Multiple: Show Journal Only
    
    if len(selected_teams) == 1:
        tab1, tab2, tab3 = st.tabs(["Journal de Match", "Punitions", "Buts (Brut)"])
    else:
        tab1 = st.container() # Just a container, no tabs UI for single item? Or stick to 1 tab?
        # st.tabs with 1 item nice for title?
        t_list = st.tabs(["Journal de Match"])
        tab1 = t_list[0]
        tab2, tab3 = None, None

    # French Date Helper
    MONTHS_FR = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    
    def format_date_fr(dt_val):
         if pd.isna(dt_val): return ""
         # dt_val is datetime
         day = dt_val.day
         month = MONTHS_FR[dt_val.month]
         year = dt_val.year
         return f"{day} {month} {year}"

    with tab1:
        # Journal Layout
        if len(selected_teams) == 2: 
             st.subheader("Analyse des Punitions")
             # Sort teams alphabetically or use selected_teams order
             ts = selected_teams
             
             # Pen Analysis for Team 1
             t1 = ts[0]
             st.markdown(f"#### {t1}")
             # Filter penalties for T1 in these games?
             # 'penalties' passed to render_dashboard contains ALL penalties or filtered?
             # 'penalties' arg usually contains filtered penalties if stats_mode != Un contre tous.
             # If Un contre tous, it has all.
             p1 = penalties[penalties['team_name'] == t1]
             render_penalty_analysis_section(p1, f"- {t1}")
             
             # Pen Analysis for Team 2
             t2 = ts[1]
             st.divider()
             st.markdown(f"#### {t2}")
             p2 = penalties[penalties['team_name'] == t2]
             render_penalty_analysis_section(p2, f"- {t2}")
             
             st.divider()
             st.subheader("Liste des Matchs")
        
        # Add Link
        # Prepare Data for Interactive Table
        # We need to keep track of the original teams/game_info for the click event.
        # But we only want to show specific columns.
        
        # 1. Format URL for LinkColumn (Just the URL, not HTML)
        games_filtered['pdf_url'] = games_filtered['game_id'].apply(lambda x: f"https://pdf.play.spordle.com/game/{x}?locale=fr")
        
        # 2. Format Date (Standard)
        games_filtered['Date_fmt'] = games_filtered['date_dt'].apply(format_date_fr)

        # 3. Add Face-à-Face Status Column (First Column)
        def get_f2f_status(r):
            if r['final_score_home'] == "" and r['final_score_visitor'] == "":
                return "à venir"
            return "" # Empty for completed games ("petites cases")
            
        games_filtered['Status_F2F'] = games_filtered.apply(get_f2f_status, axis=1)
        
        # 4. Select Display Columns
        # Order: Status_F2F (Face à Face), date_dt (Actual Date), home, scores...
        display_cols = ['Status_F2F', 'date_dt', 'home', 'final_score_home', 'final_score_visitor', 'visitor', 'arena', 'pdf_url']
        
        # Sort by actual date FIRST, then pick display columns (Preserves Chronological Order)
        df_display = games_filtered.sort_values(by='date_dt', ascending=False)[display_cols].copy().reset_index(drop=True)
        
        # Rename for UI
        df_display.columns = ['Face à Face', 'Date', 'Domicile', 'Score Dom.', 'Score Vis.', 'Visiteur', 'Aréna', 'Feuille']
        
        # interactive Dataframe
        event = st.dataframe(
            df_display,
            column_config={
                "Feuille": st.column_config.LinkColumn(
                    "Feuille", display_text="📄 PDF"
                ),
                "Score Dom.": st.column_config.TextColumn("Score Dom.", width="small"),
                "Score Vis.": st.column_config.TextColumn("Score Vis.", width="small"),
                "Face à Face": st.column_config.TextColumn("Face à Face", width="small"),
                "Date": st.column_config.DateColumn("Date", format="YYYY-MM-DD", width="small"),
            },
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row"
        )
        
        # --- HANDLE SELECTION ---
        if event.selection.rows:
            # Get the selected row index
            idx = event.selection.rows[0]
            # Get the actual data from the dataframe (using iloc on the sorted df_display)
            selected_row = df_display.iloc[idx]
            
            # Extract Teams
            t1 = selected_row['Domicile']
            t2 = selected_row['Visiteur']
            
            # Check if game is played (Optional: Only switch if Scheduled? Or allow for Played too?)
            # User wants to analyze specific matchup. Let's allow it for ANY game.
            
            # Update Session State to Switch View
            # We use the same logic as the "Sélection Personnalisée" filter
            
            # CHECK: Only update and rerun if not already in this state
            current_teams = st.session_state.get("selected_teams_custom", [])
            # Current mode from widget selection (or session state if we track it specifically, but widget value is safest source of truth for display)
            # Use index based check since we are resetting index
            
            # Sort lists to ensure order doesn't matter for comparison
            target_teams = sorted([t1, t2])
            current_teams_sorted = sorted(current_teams) if current_teams else []
            
            # If we are NOT in Custom Mode OR the teams are different -> Trigger update
            if filter_mode != "Sélection Personnalisée" or current_teams_sorted != target_teams:
                st.session_state["filter_mode_idx"] = 2 
                st.session_state["selected_teams_custom"] = [t1, t2]
                st.session_state["radio_ver"] += 1 # Force widget reset
                
                # Force Rerun to apply
                st.rerun()

    # Details (Single Team Only)
    if len(selected_teams) == 1 and tab2 and tab3:
        with tab2:
            st.subheader("Punitions")
            penalties_filtered['Date'] = penalties_filtered['date_dt'].apply(format_date_fr)
            
            # --- NEW ANALYSIS TABLES ---
            render_penalty_analysis_section(penalties_filtered)

            st.divider()
            st.markdown("### 📝 Liste Complète")

            cols_p = ['Date', 'period', 'time', 'team_name', 'player_name', 'code', 'duration', 'player_jersey']
            # Reorder for display (remove Date if redundant, but keep just in case)
            # Standard order: Date, Period, Time, Team (Filtered out?), Player, Code, Duration, Jersey
            
            # Since single team, team_name is redundant
            p_display = penalties_filtered.sort_values(by='date_dt', ascending=False)[cols_p]
            p_display = p_display.rename(columns={
                'period': 'Période', 'time': 'Temps', 'player_name': 'Joueur', 
                'code': 'Infraction', 'duration': 'Durée', 'player_jersey': '#'
            })
            
            st.dataframe(
                p_display[['Date', 'Période', 'Temps', 'Joueur', 'Infraction', 'Durée', '#']],
                use_container_width=True,
                hide_index=True,
                height=500
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
                 cols_g_show = []
             
             if not goals_filtered.empty:
                 goals_filtered['Date'] = goals_filtered['date_dt'].apply(format_date_fr)
                 cols_g_show = ['Date', 'Buteur', 'Passeur 1', 'Passeur 2', 'period', 'time']
                 
                 # Fix: Sort by original date_dt then drop it / select cols
                 g_display = goals_filtered.sort_values(by='date_dt', ascending=False)[cols_g_show]
                 
                 styler_g = g_display.style.set_properties(
                    **{'text-align': 'center'}
                 ).set_table_styles([
                    {'selector': 'th', 'props': [('text-align', 'center !important')]},
                    {'selector': 'td', 'props': [('text-align', 'center !important')]}
                 ]).hide(axis='index')
                 
                 # render_scrollable_table(styler_g, height=500)
                 st.dataframe(
                      g_display,
                      column_config={
                           "Date": st.column_config.TextColumn("Date", width="small"),
                           "Buteur": st.column_config.TextColumn("Buteur", width="medium"),
                           "Passeur 1": st.column_config.TextColumn("Passeur 1", width="small"),
                           "Passeur 2": st.column_config.TextColumn("Passeur 2", width="small"),
                      },
                      use_container_width=True,
                      hide_index=True,
                      height=500
                 )
             else:
                 st.info("Aucun but enregistré.")

def render_evolution(games, goals, penalties, conn, selected_teams, stats_mode, players, num_periods=4, min_mj=1):
    st.header("📈 Évolution de la Saison")
    st.caption("Les indicateurs sont calculés sur 4 périodes de durée égale, basées sur la plage de dates sélectionnée.")

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
    
    cols_std_to_track = ['PTS', 'GP', 'W', 'L', 'T', 'FJ', 'GF', 'GA', 'DIFF', 'PP%', 'PP% Rec', 'PK%', 'PK% Rec', 'PIM']
    # Mapping to French for Display
    std_map = {
        'Team': 'Équipe', 'GP': 'MJ', 'W': 'V/MJ', 'L': 'D/MJ', 'T': 'N/MJ',
        'GF': 'BP/MJ', 'GA': 'BC/MJ', 'PP%': '%AN', 'PK%': '%DN', 'PIM': 'PUN/MJ',
        'PTS': 'PTS/MJ', 'FJ': 'FJ/MJ', 'DIFF': 'DIFF/MJ', 'PP% Rec': '%AN (Rec)', 'PK% Rec': '%DN (Rec)'
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
             s_goals = p_goals[p_goals['game_id'].isin(s_ids)]
                 
        start_time = datetime.now()
        df_std = calculate_standings(s_games, s_pens, s_goals)
        
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
               
        cols_goal_track = ['MJ', 'MA', 'V', 'D', 'N', 'BL', 'BC', 'Moy']
        
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
                 cols_goal_norm = ['MA', 'V', 'D', 'N', 'BL', 'BC']
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
                # REVERSE order: Index 0 = Newest Period (for sorting)
                row[disp_col] = vals[::-1] if isinstance(vals, list) else vals
            
            rows.append(row)
        return pd.DataFrame(rows)

    # --- STANDINGS TABLE ---
    if agg_standings:
        st.subheader("Classement")
        st.caption("⬅️ **Gauche** : Plus Récent | **Droite** ➡️ : Plus Ancien (Le tri par clic se fait sur la valeur la plus récente)")
        df_evo_std = make_spark_df(agg_standings, std_map, 'Équipe')
        
        # Sort by PTS sum
        col_pts = std_map.get('PTS', 'PTS')
        col_pts_mj = std_map.get('PTS/MJ', 'PTS/MJ')
        
        # Calculate Sort Keys
        # Sort by the NEWEST period value (Index 0 due to reversal)
        df_evo_std['__SortPTS'] = df_evo_std[col_pts].apply(lambda x: x[0] if len(x) > 0 else 0)
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
        # FILTER BY MIN MJ
        # agg_goalies = {Name: {'Stats': {Col: [list]}, 'Team': T}}
        # We need to verify if MJ exists in stats. Assuming it does as per standard calculator.
        agg_goalies = {
            k: v for k, v in agg_goalies.items() 
            if sum(v['Stats'].get('MJ', [0])) >= min_mj
        }

    if agg_goalies:
        st.subheader("Gardiens")
        g_map = {
            'Shots': 'Lancers/MJ', 'Name': 'Nom', 'Team': 'Équipe',
            'MA': 'MA/MJ', 'V': 'V/MJ', 'D': 'D/MJ', 'N': 'N/MJ',
            'BL': 'BL/MJ', 'BC': 'BC/MJ'
        }
        df_evo_g = make_spark_df(agg_goalies, g_map, 'Nom')
        
        # Sort
        # Sort by MJ in NEWEST period
        df_evo_g['__MJ'] = df_evo_g['MJ'].apply(lambda x: x[0] if len(x) > 0 else 0)
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
        # FILTER BY MIN MJ
        agg_players = {
            k: v for k, v in agg_players.items() 
            if sum(v['Stats'].get('MJ', v['Stats'].get('GP', [0]))) >= min_mj
        }

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
        
        # Sort by PTS sum (NEWEST period)
        col_pts_p = p_map.get('PTS', 'PTS')
        df_evo_p['__PTS'] = df_evo_p[col_pts_p].apply(lambda x: x[0] if len(x) > 0 else 0)
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

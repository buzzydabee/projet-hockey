import os
import sqlite3
import re
from pypdf import PdfReader
from datetime import datetime

# Configuration
DB_NAME = "hockey_stats.db"
# TARGET_FILE = "downloads/game_654709.pdf" 
# User want validation on this file, but we can iterate checks.
DOWNLOAD_DIR = "downloads"
# PROCESSING ALL FILES
TARGET_FILES = [f for f in os.listdir(DOWNLOAD_DIR) if f.endswith(".pdf")]

def create_schema(cursor):
    # DimTeam
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS DimTeam (
            team_id INTEGER PRIMARY KEY,
            team_name TEXT UNIQUE
        )
    ''')
    
    # DimPlayer
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS DimPlayer (
            player_key INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER,
            jersey_number TEXT,
            player_name TEXT,
            FOREIGN KEY(team_id) REFERENCES DimTeam(team_id),
            UNIQUE(team_id, jersey_number, player_name)
        )
    ''')
    
    # DimGame
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS DimGame (
            game_id INTEGER PRIMARY KEY,
            date TEXT,
            arena TEXT,
            home_team_id INTEGER,
            visitor_team_id INTEGER,
            final_score_home INTEGER,
            final_score_visitor INTEGER,
            shots_for_home INTEGER,
            shots_for_visitor INTEGER,
            pp_goals_home INTEGER,
            pp_attempts_home INTEGER,
            pp_goals_visitor INTEGER,
            pp_attempts_visitor INTEGER,
            fair_play_home INTEGER,
            fair_play_visitor INTEGER,
            is_overtime BOOLEAN,
            is_shootout BOOLEAN,
            FOREIGN KEY(home_team_id) REFERENCES DimTeam(team_id),
            FOREIGN KEY(visitor_team_id) REFERENCES DimTeam(team_id)
        )
    ''')
    
    # FactGoals
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS FactGoals (
            goal_id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER,
            team_id INTEGER,
            period INTEGER,
            time TEXT,
            player_jersey TEXT, -- Storing jersey to link later if needed, or we resolve player_key
            assist1_jersey TEXT,
            assist2_jersey TEXT,
            FOREIGN KEY(game_id) REFERENCES DimGame(game_id),
            FOREIGN KEY(team_id) REFERENCES DimTeam(team_id)
        )
    ''')
    
    # FactPenalties
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS FactPenalties (
            penalty_id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER,
            team_id INTEGER,
            period INTEGER,
            time TEXT,
            player_jersey TEXT,
            code TEXT,
            duration TEXT,
            FOREIGN KEY(game_id) REFERENCES DimGame(game_id),
            FOREIGN KEY(team_id) REFERENCES DimTeam(team_id)
        )
    ''') 
    
    # FactGoalieStats
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS FactGoalieStats (
            stats_id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER,
            team_id INTEGER,
            player_jersey TEXT,
            minutes_played TEXT, -- Keeping raw text first, e.g. "60.0" or "41.9"
            shots_against INTEGER,
            goals_against INTEGER,
            FOREIGN KEY(game_id) REFERENCES DimGame(game_id),
            FOREIGN KEY(team_id) REFERENCES DimTeam(team_id)
        )
    ''')

def process_goalies(cursor, game_id, team_id, side_prefix, fields):
    # Goalie Fields: goalerNumLoc{1,2}, totalMinLoc{1,2}, totalShotLoc{1,2}, totalGoalLoc{1,2}
    # These contain the summary for the game.
    
    for i in range(1, 4): # Max 3 goalies usually
        num_key = f"goalerNum{side_prefix}{i}"
        
        # Check if goalie exists
        num = fields.get(num_key, {}).get('/V')
        if not num:
            continue
            
        min_key = f"totalMin{side_prefix}{i}"
        shot_key = f"totalShot{side_prefix}{i}"
        goal_key = f"totalGoal{side_prefix}{i}"
        
        m = fields.get(min_key, {}).get('/V', '0')
        s = fields.get(shot_key, {}).get('/V', '0')
        g = fields.get(goal_key, {}).get('/V', '0')
        
        # Clean numeric
        try: s_int = int(s)
        except: s_int = 0
        try: g_int = int(g)
        except: g_int = 0
            
        cursor.execute('''
            INSERT INTO FactGoalieStats (game_id, team_id, player_jersey, minutes_played, shots_against, goals_against)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (game_id, team_id, str(num).strip(), str(m), s_int, g_int))

def get_or_create_team(cursor, team_name):
    # Simple hash or auto-id. Let's use auto-id
    cursor.execute("SELECT team_id FROM DimTeam WHERE team_name = ?", (team_name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    else:
        cursor.execute("INSERT INTO DimTeam (team_name) VALUES (?)", (team_name,))
        return cursor.lastrowid

def process_roster(cursor, team_id, side_prefix, fields):
    # side_prefix is 'Loc' or 'Vis'
    # Roster fields like: LocNum1, LocName1, LocNum2, LocName2...
    # We scan up to 30 (arbitrary max, likely less)
    
    for i in range(1, 30):
        # Field names are like playerNumLoc1, playerNameLoc1
        num_key = f"playerNum{side_prefix}{i}"
        name_key = f"playerName{side_prefix}{i}"
        
        num = fields.get(num_key, {}).get('/V')
        name = fields.get(name_key, {}).get('/V')
        
        if num and name:
            # Clean up
            num = str(num).strip()
            name = str(name).strip().upper() # standardized uppercase
            
            # Insert if not exists
            cursor.execute('''
                INSERT OR IGNORE INTO DimPlayer (team_id, jersey_number, player_name)
                VALUES (?, ?, ?)
            ''', (team_id, num, name))
            
    # Also scan Goalies (often separate)
    # goalerNumLoc1, goalerNameLoc1
    for i in range(1, 4):
        num_key = f"goalerNum{side_prefix}{i}"
        name_key = f"goalerName{side_prefix}{i}"
        
        num = fields.get(num_key, {}).get('/V')
        name = fields.get(name_key, {}).get('/V')
        
        if num and name:
             num = str(num).strip()
             name = str(name).strip().upper().replace('*', '').strip() # Remove starter asterisk
             
             cursor.execute('''
                INSERT OR IGNORE INTO DimPlayer (team_id, jersey_number, player_name)
                VALUES (?, ?, ?)
            ''', (team_id, num, name))

def process_goals(cursor, game_id, team_id, side_prefix, fields):
    # Goals: goalPeriodLocX, goalTimeLocX, scoreLocX (this is jersey?), assistOneLocX, assistTwoLocX
    # Note: 'scoreLocX' likely holds the jersey number of the scorer based on field dump analysis (e.g. scoreLoc1: 22)
    
    # We loop until we find empty fields
    for i in range(1, 20):
        period_key = f"goalPeriod{side_prefix}{i}"
        time_key = f"goalTime{side_prefix}{i}"
        if side_prefix == "Loc":
            scorer_key = f"score{side_prefix}{i}"
        else:
            scorer_key = f"scorer{side_prefix}{i}"
        # Some fields usually called scoreLocX seem to be the scorer jersey number
        # Let's verify with field dump: scoreLoc1: 22. playerNumLocX has 22. Yes.
        
        ass1_key = f"assistOne{side_prefix}{i}"
        ass2_key = f"assistTwo{side_prefix}{i}"
        
        p = fields.get(period_key, {}).get('/V')
        t = fields.get(time_key, {}).get('/V')
        s = fields.get(scorer_key, {}).get('/V')
        
        if not (p and t and s):
            # Try to see if it's just a gap? usually sequential.
            continue
            
        a1 = fields.get(ass1_key, {}).get('/V', '')
        a2 = fields.get(ass2_key, {}).get('/V', '')
        
        cursor.execute('''
            INSERT INTO FactGoals (game_id, team_id, period, time, player_jersey, assist1_jersey, assist2_jersey)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (game_id, team_id, p, t, s, a1, a2))

def process_penalties(cursor, game_id, team_id, side_prefix, fields):
    # Penalties: minorPenLocPeriodX, minorPenLocTimeX, minorPenLocNumX (jersey), minorPenLocCodeX
    # There are also 'otherPenLoc...' fields for major penalties?
    # Let's handle 'minorPen' set first as it's the most common.
    
    prefixes = ['minorPen', 'otherPen']
    
    for pen_type in prefixes:
        for i in range(1, 20):
            # Keys ref: minorPenLocPeriod1
            base = f"{pen_type}{side_prefix}"
            
            per_key = f"{base}Period{i}"
            time_key = f"{base}Time{i}"
            num_key = f"{base}Num{i}" # Jersey
            code_key = f"{base}Code{i}"
            
            p = fields.get(per_key, {}).get('/V')
            t = fields.get(time_key, {}).get('/V')
            n = fields.get(num_key, {}).get('/V')
            c = fields.get(code_key, {}).get('/V')
            
            if not (p and n):
                continue
                
            duration = "2:00" if pen_type == "minorPen" else "5:00" # Assumption for now, TODO: refine
            
            cursor.execute('''
                INSERT INTO FactPenalties (game_id, team_id, period, time, player_jersey, code, duration)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (game_id, team_id, p, t, n, c, duration))

def parse_x_en_y(val):
    # Format: "A.N: 1 en 4" -> (1, 4)
    if not val:
        return 0, 0
    try:
        # Regex to find two numbers separating by 'en' or '/' or space
        # We look for (\d+) ... (\d+)
        match = re.search(r"(\d+)\s*(?:en|/)\s*(\d+)", str(val), re.IGNORECASE)
        if match:
             return int(match.group(1)), int(match.group(2))
    except:
        pass
    return 0, 0

def sum_shots(fields, prefix):
    # Sum goalerPeriod{One,Two,Three,Overtime}Shot{Prefix}{1,2}
    # Prefix here is "Loc" or "Vis". 
    # BUT, to get Home Shots (Loc), we must sum VISITOR Goalies' shots received.
    # So if we want Team Shots For, we pass the Opponent Prefix.
    
    total = 0
    periods = ["One", "Two", "Three", "Overtime"]
    for p in periods:
        for i in range(1, 3): # Goalie 1 and 2
            key = f"goalerPeriod{p}Shot{prefix}{i}"
            val = fields.get(key, {}).get('/V')
            if val and str(val).isdigit():
                total += int(val)
    return total

def check_ot_so(fields):
    # Check for shootout fields or OT goalie stats
    is_so = False
    is_ot = False
    
    # Shootout check
    # shootoutLoc1...
    for i in range(1, 10):
        if fields.get(f"shootoutLoc{i}", {}).get('/V') or fields.get(f"shootoutVis{i}", {}).get('/V'):
            is_so = True
            is_ot = True # SO implies OT played usually
            break
            
    # OT Check (if not SO)
    if not is_so:
        # Check OT goals or shots
        if (fields.get("goalerOvertimeGoalLoc1", {}).get('/V') or 
            fields.get("goalerOvertimeShotLoc1", {}).get('/V') or
            fields.get("goalerOvertimeGoalVis1", {}).get('/V') or 
            fields.get("goalerOvertimeShotVis1", {}).get('/V')):
            is_ot = True
            
    # Check Goal Periods > 3
    # We'd need to parse the FactGoals or check fields...
    # Easier to rely on the goalie OT fields which are summarized.
    
    return is_ot, is_so



def main():
    import sys
    if "--reset" in sys.argv:
        print("RESET MODE: Deleting existing database...")
        if os.path.exists(DB_NAME):
            try:
                os.remove(DB_NAME)
                print("Database deleted.")
            except PermissionError:
                print("Could not delete DB file (in use). Aborting reset.")
                sys.exit(1)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    create_schema(cursor)
    
    skipped_count = 0
    total_files = len(TARGET_FILES)
    deferred_deletes = []  # List of PDFs to delete AFTER processing (e.g. today's scheduled games)
    
    for idx, filename in enumerate(TARGET_FILES, 1):
        # Print progress marker for Streamlit
        print(f"PROGRESS:{idx}/{total_files}", flush=True)

        filepath = os.path.join(DOWNLOAD_DIR, filename)
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}")
            continue
            
        # print(f"Processing {filename}...")
        
        try:
            # Extract Game Info
            # Extract ID from filename or field? filename is safer: game_654709.pdf
            try:
                game_id = int(re.search(r"game_(\d+)", filename).group(1))
            except:
                print(f"Skipping file {filename}: Invalid format")
                continue
            
            # --- CHECK EXISTING ---
            cursor.execute("SELECT 1 FROM DimGame WHERE game_id=?", (game_id,))
            if cursor.fetchone():
                skipped_count += 1
                # print(f"Skipping existing game {game_id} (already in DB)")
                continue
            # ----------------------

            print(f"Processing new file: {filename}...")
            
            reader = PdfReader(filepath)
            fields = reader.get_fields()
            
            # --- IDEMPOTENCY CHECK ---
            # If game exists, remove it first (redundant now with above check, but safe for updates if we remove the check later)
            cursor.execute("DELETE FROM FactGoalieStats WHERE game_id = ?", (game_id,))
            cursor.execute("DELETE FROM FactPenalties WHERE game_id = ?", (game_id,))
            cursor.execute("DELETE FROM FactGoals WHERE game_id = ?", (game_id,))
            cursor.execute("DELETE FROM DimGame WHERE game_id = ?", (game_id,))
            # -------------------------
            
            game_date_str = fields.get('gameDate', {}).get('/V')
            
            # --- DATE VALIDATION ---
            # Parse date to ensure it is not in the future
            is_future = False
            if game_date_str:
                try:
                    # Map French months
                    months_map = {
                        "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
                        "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12
                    }
                    p = str(game_date_str).lower().split()
                    if len(p) >= 3:
                        d, m_name, y = int(p[0]), p[1], int(p[2])
                        m = months_map.get(m_name)
                        if m:
                            g_date = datetime(y, m, d)
                            if g_date > datetime.now():
                                is_future = True
                except:
                    pass
            
            if is_future:
                print(f"Skipping future game: {filename} ({game_date_str})")
                try:
                    reader.stream.close() # Ensure handle is closed before delete
                    os.remove(filepath)
                    print(f"Deleted invalid future file: {filename}")
                except Exception as e:
                    print(f"Could not delete {filename}: {e}")
                continue
            # -----------------------
            
            # -----------------------
            # Date Conversion: French Text -> ISO 8601 (YYYY-MM-DD)
            # "21 octobre 2025" -> "2025-10-21"
            def french_to_iso(d_str):
                MONTHS = {
                    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
                    "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12
                }
                try:
                    parts = d_str.lower().split()
                    day = int(parts[0])
                    month = MONTHS.get(parts[1], 1)
                    year = int(parts[2])
                    return f"{year}-{month:02d}-{day:02d}"
                except:
                    return d_str # Fallback to original if parsing fails

            game_date = french_to_iso(game_date_str)
            arena = fields.get('locationName', {}).get('/V')
            
            team_loc_name = str(fields.get('TeamNameLoc', {}).get('/V')).replace('**', '').strip()
            team_vis_name = str(fields.get('TeamNameVis', {}).get('/V')).replace('**', '').strip()
            
            score_loc = int(fields.get('scoreLoc', {}).get('/V', 0) or 0)
            score_vis = int(fields.get('scoreVis', {}).get('/V', 0) or 0)
            
            # Advanced Stats
            # Shots: Home Shots = Sum of Visitor Goalie Shots
            shots_home = sum_shots(fields, "Vis")
            shots_vis = sum_shots(fields, "Loc")
            
            # PP: PPLoc = Home PP
            pp_g_home, pp_att_home = parse_x_en_y(fields.get('PPLoc', {}).get('/V'))
            pp_g_vis, pp_att_vis = parse_x_en_y(fields.get('PPVis', {}).get('/V'))
            
            # Fair Play: 1 = Yes, 0 = No/Empty. Usually "1" if fair play point earned.
            fp_home = 1 if str(fields.get('fairPlayLoc', {}).get('/V')).strip() == '1' else 0
            fp_vis = 1 if str(fields.get('fairPlayVis', {}).get('/V')).strip() == '1' else 0
            
            # OT/SO
            is_ot, is_so = check_ot_so(fields)
            
            # --- VALIDATION: Check for empty games ---
            # If 0 shots recorded and 0-0 score, it's likely an empty/pre-game sheet.
            # EXCEPTION: If the game is TODAY, we keep it (Scheduled game).
            # "game_date" is already in "YYYY-MM-DD" format (ISO).
            
            from datetime import datetime
            today_iso = datetime.now().date().strftime("%Y-%m-%d")
            
            is_empty_stats = (shots_home == 0 and shots_vis == 0 and score_loc == 0 and score_vis == 0)
            
            if is_empty_stats:
                if game_date == today_iso:
                     # Keep it in DB (so we see it in Schedule if we had one), 
                     # BUT delete the PDF so 'download_game_sheets.py' fetches the update tomorrow.
                     print(f"Keeping TODAY's scheduled/empty game in DB: {filename}")
                     try:
                         # We must verify if 'reader' stream is closed? 
                         # pypdf usually closes if we read it all, but let's be safe.
                         # Only delete if we are NOT on Windows locking... 
                         # Actually, process_gamesheets opens it. We need to be careful.
                         # We can't delete it while it's open.
                         # We'll add it to a list to delete AFTER the loop or explicitly close here?
                         # The loop structure: 'with open(...) as f' isn't used?
                         # Let's check how it opens.
                         pass 
                     except: pass
                     
                     # We will mark it for deletion?
                     # Let's see the open code... line 348: reader = PdfReader(filepath)
                     # pypdf PdfReader holds the file open? 
                     # We might need to defer deletion.
                     deferred_deletes.append(filepath)
                else:
                    print(f"Skipping past incomplete game: {filename}")
                    try:
                        # Optional: Verify if we should delete the PDF too?
                        # User said "removed from DB", implies PDF might stay or go.
                        # Using 'continue' skips DB insertion.
                        pass
                    except: pass
                    continue
            
            # If score not tied, but is_ot false? Regulation result.
            
            # If score not tied, but is_ot false? Regulation result.
            
            # Get Team IDs
            loc_id = get_or_create_team(cursor, team_loc_name)
            vis_id = get_or_create_team(cursor, team_vis_name)
            
            # Insert Game
            cursor.execute('''
                INSERT INTO DimGame (game_id, date, arena, home_team_id, visitor_team_id, final_score_home, final_score_visitor,
                                     shots_for_home, shots_for_visitor, pp_goals_home, pp_attempts_home, pp_goals_visitor, pp_attempts_visitor,
                                     fair_play_home, fair_play_visitor, is_overtime, is_shootout)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (game_id, game_date, arena, loc_id, vis_id, score_loc, score_vis, 
                  shots_home, shots_vis, pp_g_home, pp_att_home, pp_g_vis, pp_att_vis,
                  fp_home, fp_vis, is_ot, is_so))
            
            # Process Rosters
            process_roster(cursor, loc_id, "Loc", fields)
            process_roster(cursor, vis_id, "Vis", fields)
            
            # Process Goals
            process_goals(cursor, game_id, loc_id, "Loc", fields)
            process_goals(cursor, game_id, vis_id, "Vis", fields)
            
            # Process Penalties
            process_penalties(cursor, game_id, loc_id, "Loc", fields)
            process_penalties(cursor, game_id, vis_id, "Vis", fields)
            
            # Process Goalies
            process_goalies(cursor, game_id, loc_id, "Loc", fields)
            process_goalies(cursor, game_id, vis_id, "Vis", fields)
            
            conn.commit()
            print(f"Successfully processed {filename}")
            
        except Exception as e:
            print(f"Error processing {filename}: {e}")
            import traceback
            traceback.print_exc()
            conn.commit()
    
    # --- CLEANUP ROUTINE ---
    # Remove any existing games in DB that are:
    # 1. Incomplete (0 shots, 0-0 score)
    # 2. AND Older than TODAY (keeping today's scheduled games)
    try:
        from datetime import datetime
        today_iso = datetime.now().date().strftime("%Y-%m-%d")
        
        # We need to join Fact tables or use a heuristic. 
        # Since DimGame stores aggregated scores/shots, we can use that.
        cursor.execute(f'''
            DELETE FROM DimGame 
            WHERE shots_for_home = 0 
              AND shots_for_visitor = 0 
              AND final_score_home = 0 
              AND final_score_visitor = 0
              AND date < '{today_iso}'
        ''')
        deleted = cursor.rowcount
        conn.commit()
        if deleted > 0:
            print(f"Cleanup: Removed {deleted} old incomplete games from DB.")
    except Exception as e:
        print(f"Cleanup Error: {e}")

    # --- DEFERRED DELETION ---
    # Delete temporary PDFs for today's scheduled games so they can be re-downloaded later.
    for fpath in deferred_deletes:
        try:
            if os.path.exists(fpath):
                os.remove(fpath)
                print(f"Deferred Cleanup: Deleted temporary PDF {os.path.basename(fpath)}")
        except Exception as e:
            print(f"Could not delete {os.path.basename(fpath)}: {e}")

    conn.close()
    print(f"Done. Processed {len(TARGET_FILES)} files. Skipped {skipped_count}.")
    
if __name__ == "__main__":
    main()

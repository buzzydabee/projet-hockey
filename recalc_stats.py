
import sqlite3
import pandas as pd
import math

class GameSimulator:
    def __init__(self, game_id, metrics):
        self.game_id = game_id
        self.metrics = metrics # Dict of goals, penalties
        self.log = []
        
        # Stats
        self.stats = {
            'home': {'pp_goals': 0, 'pp_opps': 0, 'name': 'Home'},
            'visitor': {'pp_goals': 0, 'pp_opps': 0, 'name': 'Visitor'}
        }
        
    def parse_time(self, period, time_str):
        # Time format in DB usually MM:SS elapsed or remaining?
        # In Quebec minor hockey, usually "Time Remaining" on scoreboard, 
        # BUT the sheet might record "Time of Day" or "Elapsed".
        # Let's inspect raw values. 
        # Inspect script showed: "09:07", "14:10". 
        # Usually Elapsed. Let's assume Elapsed.
        # If Elapsed: 
        # P1: 0 + time
        # P2: 20*60 + time
        
        try:
            m, s = map(int, time_str.split(':'))
            total_s = m * 60 + s
            return (period - 1) * 1200 + total_s
        except:
            return 0

    def run(self):
        # 1. Prepare Events
        events = []
        
        # Goals
        for _, g in self.metrics['goals'].iterrows():
            t = self.parse_time(g['period'], g['time'])
            events.append({
                'time': t, 'type': 'GOAL', 'team_id': g['team_id']
            })
            
        # Penalties
        for _, p in self.metrics['penalties'].iterrows():
            t = self.parse_time(p['period'], p['time'])
            try:
                # Duration "2:00" -> 120
                dm, ds = map(int, p['duration'].split(':'))
                dur = dm * 60 + ds
            except:
                dur = 120 # Default minor
            
            is_major = (dur >= 300)
            
            events.append({
                'time': t, 'type': 'PENALTY', 'team_id': p['team_id'],
                'duration': dur, 'is_major': is_major,
                'code': p['code']
            })
            
        # Sort events
        # If Goal and Penalty at same time?
        # Goal usually happens, then Penalty? Or Penalty causes stoppage?
        # If Goal scored, time stops. Penalty recorded at that time.
        # Usually Penalty starts sequence.
        events.sort(key=lambda x: (x['time'], 0 if x['type'] == 'PENALTY' else 1)) 
        
        # Simulation Loop (Event based + State)
        # We need to track Active Penalties to know On-Ice Strength
        
        # State:
        # active_penalties = { team_id: [ {end_time, is_major, id} ] }
        
        # Actually, simpler:
        # We just need to know if it's a Power Play when a Goal happens.
        # And count Opportunities.
        
        # Opportunity Logic:
        # Complex. "1 en 4" -> 4 Opportunities.
        # Every time a MINOR/MAJOR starts, check strength.
        # If (My Players > Opp Players) -> Opportunity++?
        # Or if (My Players == Opp Players) AND Opp takes penalty -> Strength becomes 5v4 -> Opportunity++
        
        # Let's refine Opportunity counting later. First, PP Goals.
        
        active_penalties = {} # team_id -> list of penalty objects
        
        # Get Team IDs
        t_ids = list(set([e['team_id'] for e in events]))
        if not t_ids: return
        t1, t2 = t_ids[0], t_ids[1] if len(t_ids) > 1 else -1
        active_penalties[t1] = []
        active_penalties[t2] = []
        
        # Identify Home/Vis for stats
        # We need mapping team_id -> 'home'/'visitor'
        # Can assume from input df
        
        for e in events:
            curr_time = e['time']
            current_team = e['team_id']
            other_team = t2 if current_team == t1 else t1
            
            # Clean expired penalties
            for tid in [t1, t2]:
                active_penalties[tid] = [p for p in active_penalties[tid] if p['end_time'] > curr_time]
            
            # Count strength (Base 5)
            # Max 2 taken off?
            # Strength = 5 - len(active_penalties[tid]) (clamped at 3?)
            s1 = max(3, 5 - len(active_penalties[t1]))
            s2 = max(3, 5 - len(active_penalties[t2]))
            
            if e['type'] == 'GOAL':
                # Is PP?
                # If I scored (current_team), and My Strength > Opp Strength
                my_str = s1 if current_team == t1 else s2
                opp_str = s2 if current_team == t1 else s1
                
                opp_pens = active_penalties[other_team]
                
                if my_str > opp_str:
                    # PP GOAL!
                    # Record
                    self.record_pp_goal(current_team)
                    
                    # Terminate Minor Penalty?
                    # Find earliest ending Minor
                    minors = sorted([p for p in opp_pens if not p['is_major']], key=lambda x: x['end_time'])
                    if minors:
                        # Remove first one
                        to_remove = minors[0]
                        active_penalties[other_team].remove(to_remove)
                        print(f"Goal at {e['time']}s ends penalty ending at {to_remove['end_time']}s")

            elif e['type'] == 'PENALTY':
                # Add to active
                # Check for Coincidental? 
                # If both teams get penalty at Exact Same Time -> usually 4v4, no PP opp?
                # Logic: If I take penalty, check strength.
                
                # Naive Opp Count: Every penalty adds an Opp for OTHER team?
                # self.record_opp(other_team)
                
                p = {
                    'start_time': curr_time,
                    'end_time': curr_time + e['duration'],
                    'is_major': e['is_major']
                }
                active_penalties[current_team].append(p)
                
                # Detect Opportunity Creation
                # If after adding this penalty, Opp Strength > My Strength, then New Opportunity?
                # Need refined logic.
                # Simple Proxy: Count every non-coincidental minor/major.
                self.record_opp(other_team) # Determine "Attempts" later
                
    def record_pp_goal(self, team_id):
        # We need to map ID to home/vis
        # Hacky: use known IDs
        print(f"PP Goal for Team {team_id}")
        
    def record_opp(self, team_id):
        print(f"PP Opp for Team {team_id}")

# --- Execution ---
conn = sqlite3.connect("hockey_stats.db")
gid = 668157

# Load Data
q_g = '''SELECT period, time, g.team_id, t.team_name FROM FactGoals g JOIN DimTeam t ON g.team_id = t.team_id WHERE game_id = ?'''
q_p = '''SELECT period, time, p.team_id, t.team_name, duration, code FROM FactPenalties p JOIN DimTeam t ON p.team_id = t.team_id WHERE game_id = ?'''

goals = pd.read_sql_query(q_g, conn, params=(gid,))
pens = pd.read_sql_query(q_p, conn, params=(gid,))
conn.close()

sim = GameSimulator(gid, {'goals': goals, 'penalties': pens})
sim.run()

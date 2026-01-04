
import pandas as pd

class GameReconstructor:
    def __init__(self):
        pass

    def parse_time(self, period, time_str):
        try:
            m, s = map(int, str(time_str).split(':'))
            return (int(period) - 1) * 1200 + m * 60 + s
        except:
            return 0

    def reconstruct_game_stats(self, game_id, game_goals, game_penalties, home_id, visitor_id):
        """
        Reconstructs Special Teams stats for a single game.
        Returns dictionary with keys: 
        pp_g_home, pp_att_home, pp_g_vis, pp_att_vis, 
        pk_k_home, pk_att_home, ...
        """
        
        # 1. Prepare Events
        events = []
        
        # Goals
        for _, g in game_goals.iterrows():
            t = self.parse_time(g['period'], g['time'])
            events.append({
                'time': t, 'type': 'GOAL', 'team_id': g['team_id']
            })
            
        # Penalties
        for _, p in game_penalties.iterrows():
            t = self.parse_time(p['period'], p['time'])
            try:
                dm, ds = map(int, str(p['duration']).split(':'))
                dur = dm * 60 + ds
            except:
                dur = 120 # Default 2m
            
            # Identify Major/Coincidental?
            # Simplified: >= 5m is Major
            is_major = (dur >= 300)
            
            events.append({
                'time': t, 'type': 'PENALTY', 'team_id': p['team_id'],
                'duration': dur, 'is_major': is_major, 'end_time': t + dur,
                'id': _ # index
            })
            
        # Sort: Time asc. Priority: Penalty starts (0) before Goal (1) ?
        # Actually usually Goal ends penalty technically before penalty starts? No.
        # If Goal at 10:00. Penalty at 10:00.
        # It implies stopped play.
        # If Goal scored, maybe penalty called?
        # Let's use strict time.
        events.sort(key=lambda x: (x['time'], 0 if x['type'] == 'PENALTY' else 1))
        
        active_penalties = {home_id: [], visitor_id: []}
        
        stats = {
            'pp_g_home': 0, 'pp_att_home': 0,
            'pp_g_vis': 0, 'pp_att_vis': 0
        }
        
        # Helper to get Opponent ID
        def get_opp(tid): return visitor_id if tid == home_id else home_id
        
        # Opp Tracking (To avoid duplicate counting for same overlap)
        # We count "Power Play Opportunities". 
        # Definition: A situation where Team A has more players than Team B.
        # Each distinct continuous interval of advantage is 1 Opp?
        # OR: Standard logic: Every penalty counts as an opportunity (unless coincidental).
        # And if 5v3, it counts as 2?
        # NHL Rule: "Power-play opportunities are the number of times a team has the man advantage."
        
        # Let's use the Counting Events method:
        # When a Minor/Major Penalty starts for Team A:
        #   If Team B is not already short-handed? Or always +1?
        #   Usually: Count every penalty call that creates/maintains advantage.
        #   Exception: Coincidental minors (4v4) do NOT create PP opp.
        
        # Simplified logic for prototype:
        # Count every non-coincidental penalty as an attempt for the opponent.
        
        for e in events:
            curr_time = e['time']
            
            # Cleanup expired
            for tid in [home_id, visitor_id]:
                active_penalties[tid] = [p for p in active_penalties[tid] if p['end_time'] > curr_time]
                
            if e['type'] == 'PENALTY':
                p_team = e['team_id']
                opp = get_opp(p_team)
                
                # Check for Coincidental? (Penalty on Opp at same time)
                # Hard with second-resolution.
                # Heuristic: If Opp has penalty starting within +/- 2 seconds?
                # Let's ignore coincidental complexity for now to fix the "0 opps" bug.
                
                # Add penalty
                active_penalties[p_team].append(e)
                
                # Record Attempt for OPPONENT
                if opp == home_id: stats['pp_att_home'] += 1
                else: stats['pp_att_vis'] += 1
                
            elif e['type'] == 'GOAL':
                scoring_team = e['team_id']
                defending_team = get_opp(scoring_team)
                
                # Calculate Strength
                # Base 5. 
                # Note: Penalties reduce strength.
                
                def_pens = active_penalties[defending_team]
                att_pens = active_penalties[scoring_team]
                
                def_strength = max(3, 5 - len(def_pens))
                att_strength = max(3, 5 - len(att_pens))
                
                if att_strength > def_strength:
                    # PP GOAL
                    if scoring_team == home_id: stats['pp_g_home'] += 1
                    else: stats['pp_g_vis'] += 1
                    
                    # Terminate Minor
                    # Find earliest ending Minor on Defending Team
                    minors = sorted([p for p in def_pens if not p['is_major']], key=lambda x: x['end_time'])
                    if minors:
                        removed = minors[0]
                        active_penalties[defending_team].remove(removed)
                        # We don't change 'stats' counts, just internal state
                        
        return stats


import pypdf
import os

def check_pdf(game_id):
    path = f"downloads/game_{game_id}.pdf"
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return

    try:
        reader = pypdf.PdfReader(path)
        fields = reader.get_fields()
        if not fields:
            print(f"No fields found for {game_id}")
            return

        print(f"\n--- Game {game_id} ---")
        
        # Check standard shot fields (shotsHome1..3, shotsVis1..3)
        shot_keys = ['shotsHome1', 'shotsHome2', 'shotsHome3', 'shotsHome4', 'shotsHomeTotal',
                     'shotsVis1', 'shotsVis2', 'shotsVis3', 'shotsVis4', 'shotsVisTotal',
                     'shotsLoc1', 'shotsLoc2', 'shotsLoc3',  # Sometimes 'Loc' instead of 'Home'
                     'shotsVisitor1', 'shotsVisitor2']       # Variations
        
        found_any = False
        for k in fields.keys():
            if 'shots' in k.lower() or 'lancer' in k.lower():
                val = fields[k].get('/V')
                print(f"{k}: '{val}'")
                found_any = True
        
        if not found_any:
            print("No 'shots' or 'lancer' fields found.")
            
    except Exception as e:
        print(f"Error reading {game_id}: {e}")

# Check the games identified earlier with 0 shots
target_games = [654705, 654706, 654707, 654708, 654710]
for gid in target_games:
    check_pdf(gid)

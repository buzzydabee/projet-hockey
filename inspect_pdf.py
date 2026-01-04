
from pypdf import PdfReader
import os

# Inspect Game 668157 (from debug output)
target = "downloads/game_668157.pdf" 

if os.path.exists(target):
    try:
        reader = PdfReader(target)
        fields = reader.get_fields()
        
        print(f"--- Fields for {target} ---")
        print(f"PPLoc raw: '{fields.get('PPLoc', {}).get('/V')}'")
        print(f"PPVis raw: '{fields.get('PPVis', {}).get('/V')}'")
        
        # Check scores too
        print(f"ScoreLoc: {fields.get('scoreLoc', {}).get('/V')}")
        print(f"ScoreVis: {fields.get('scoreVis', {}).get('/V')}")
        
    except Exception as e:
        print(f"Error reading PDF: {e}")
else:
    print(f"File {target} not found. Please ensure it is downloaded.")

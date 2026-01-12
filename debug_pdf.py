
import os
from pypdf import PdfReader

GAME_ID = 654709
FILENAME = f"downloads/game_{GAME_ID}.pdf"

def debug_pdf():
    if not os.path.exists(FILENAME):
        print(f"File {FILENAME} not found.")
        return

    print(f"Inspecting {FILENAME}...")
    try:
        reader = PdfReader(FILENAME)
        fields = reader.get_fields()
        
        # Dump ALL keys to see what we have
        print(f"Total Fields Found: {len(fields)}")
        print("Keys:", list(fields.keys()))
        
        # Check specific keys
        if 'scoreVis' in fields:
             print(f"scoreVis: {fields['scoreVis'].get('/V')}")
        else:
             print("scoreVis NOT FOUND")
             
        if 'scoreLoc' in fields:
             print(f"scoreLoc: {fields['scoreLoc'].get('/V')}")
            
        # Check Shots
        s_home = 0
        s_vis = 0
        for i in range(1, 4):
            k = f"goalerPeriodOneShotLoc{i}"
            v = fields.get(k, {}).get('/V')
            if v: s_vis += int(v) # Note logic inversion in main script?
            print(f"Shot Debug {k}: {v}")
            
        print("Done.")

    except Exception as e:
        print(f"Error reading PDF: {e}")

if __name__ == "__main__":
    debug_pdf()


from pypdf import PdfReader
import os

target = "downloads/game_667401.pdf"

if os.path.exists(target):
    reader = PdfReader(target)
    fields = reader.get_fields()
    
    keys_to_check = ['scorerName', 'scoreKeeper', 'marqueur', 'marqueurName', 'timeKeeper', 'chronometreur', 'officiel1', 'official1']
    print("Checking specific name fields:")
    for k in keys_to_check:
        val = fields.get(k, {}).get('/V')
        print(f"{k}: {val}")
        
    print("\n--- All keys containing 'Name' ---")
    for k in fields.keys():
        if "Name" in k and "player" not in k and "goaler" not in k and "Team" not in k and "Coach" not in k:
             print(f"{k}: {fields[k].get('/V')}")

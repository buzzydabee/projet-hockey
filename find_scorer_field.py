
from pypdf import PdfReader
import os

target = "downloads/game_668157.pdf"

if os.path.exists(target):
    reader = PdfReader(target)
    fields = reader.get_fields()
    
    print(f"--- All Fields in {target} ---")
    # Print keys that might be related to names or officials
    for k in fields.keys():
        if "name" in k.lower() or "sign" in k.lower():
            print(f"{k}: {fields[k].get('/V')}")
else:
    print(f"File {target} not found.")

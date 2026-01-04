
from pypdf import PdfReader
import os

target = "downloads/game_668157.pdf"

if os.path.exists(target):
    reader = PdfReader(target)
    page = reader.pages[0] # Usually 1 page
    
    if "/Annots" in page:
        for annot in page["/Annots"]:
            obj = annot.get_object()
            if "/T" in obj:
                name = obj["/T"]
                if name in ["PPLoc", "PPVis"]:
                    rect = obj["/Rect"]
                    print(f"Field: {name}")
                    print(f"Coordinates (Bottom-Left to Top-Right): {rect}")
                    # Provide context on page size
                    print(f"Page MediaBox: {page.mediabox}")
                    
                    # Calculate rough position
                    x = rect[0]
                    y = rect[1]
                    w = page.mediabox.width
                    h = page.mediabox.height
                    
                    print(f"Position: X={x:.1f}/{w}, Y={y:.1f}/{h}")
                    if y > h/2: print("-> Top Half")
                    else: print("-> Bottom Half")
                    if x > w/2: print("-> Right Side")
                    else: print("-> Left Side")
                    
else:
    print("File not found.")

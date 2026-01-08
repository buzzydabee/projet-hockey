import os
import time
import requests
from playwright.sync_api import sync_playwright

# Configuration
TEAMS = [
  {"name": "BÉLIERS QUÉBEC-CENTRE", "id": "126544"},
  {"name": "AIGLES CBIO", "id": "126148"},
  {"name": "BUCKS CHARLESBOURG", "id": "126412"},
  {"name": "ÉPERVIERS BEAUPORT", "id": "126549"},
  {"name": "BOUCS QUÉBEC-CENTRE", "id": "126540"},
  {"name": "RADISSON QUÉBEC-CENTRE", "id": "126543"},
  {"name": "RICHELIEU", "id": "145572"},
  {"name": "CARIBOUS CHARLESBOURG", "id": "126550"},
  {"name": "PATRIOTES  QUÉBEC-CENTRE", "id": "126539"},
  {"name": "FAUCONS", "id": "145567"},
  {"name": "RORQUALS CHARLEVOIX", "id": "126143"},
  {"name": "WAPITIS CHARLESBOURG", "id": "126413"},
  {"name": "ROYAUX 2 CRSA", "id": "141478"},
  {"name": "LYNX SAINT-RAYMOND", "id": "126542"},
  {"name": "CHEVALIERS 2 VBVC", "id": "126537"},
  {"name": "DIABLOS DPR", "id": "126536"},
  {"name": "ROYAUX 1 CRSA", "id": "141479"},
  {"name": "CHEVALIERS 1 VBVC", "id": "126538"},
  {"name": "GOUVERNEURS 3 SFSAL", "id": "141324"},
  {"name": "GOUVERNEURS 1 SFSAL", "id": "126541"},
  {"name": "GOUVERNEURS 2 SFSAL", "id": "126414"}
]
TEAM_SCHEDULE_URL_TEMPLATE = "https://page.spordle.com/fr/ligue-hockey-mineur-capitale-nationale/teams/{team_id}?tab=schedule"
DOWNLOAD_DIR = "downloads"
PDF_BASE_URL = "https://pdf.play.spordle.com/game/{game_id}?locale=fr"

def ensure_download_dir():
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)
        print(f"Created download directory: {DOWNLOAD_DIR}")

def download_pdf(game_id):
    url = PDF_BASE_URL.format(game_id=game_id)
    file_path = os.path.join(DOWNLOAD_DIR, f"game_{game_id}.pdf")
    
    if os.path.exists(file_path):
        print(f"File already exists: {file_path}. Skipping.")
        return True
        
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"Downloaded: game_{game_id}.pdf")
            return True
        else:
            print(f"Failed to download Game {game_id} (Status: {response.status_code})")
            return False
    except Exception as e:
        print(f"Error downloading Game {game_id}: {e}")
        return False

def process_team_schedule(page, team_id, team_name):
    print(f"\n--- Processing Team: {team_name} (ID: {team_id}) ---")
    url = TEAM_SCHEDULE_URL_TEMPLATE.format(team_id=team_id)
    print(f"Navigating to {url}...")
    page.goto(url)

    # Capture network responses to find the API call returning the schedule
    intercepted_ids = set()
    
    def handle_response(response):
        try:
            # We are looking for JSON responses that might contain schedule data
            if "json" in response.headers.get("content-type", ""):
                try:
                    data = response.json()
                    # Search for IDs in this JSON
                    def search_json_recursively(obj):
                        found = set()
                        if isinstance(obj, dict):
                            # Check if this object represents a game with an ID and status
                            # We look for ID keys: id, _id, gameId, game_id
                            # And Status keys: status, gameStatus
                            
                            game_id = None
                            for k in ["id", "_id", "gameId", "game_id"]:
                                if k in obj and isinstance(obj[k], (str, int)):
                                    s_v = str(obj[k])
                                    if s_v.isdigit() and len(s_v) == 6 and s_v[0] in ['5', '6', '7', '8', '9']:
                                        game_id = s_v
                                        break
                            
                            if game_id:
                                # We found a potential Game ID. Now check specific game logic.
                                # Check for status. 
                                # Common fields: "status": "Final", "gameStatus": "Final", "played": true
                                status = None
                                if "status" in obj: status = obj["status"]
                                elif "gameStatus" in obj: status = obj["gameStatus"]
                                
                                # If status is explicit, use it.
                                if status:
                                    if str(status).lower() in ["final", "terminé", "complete", "played"]:
                                        found.add(game_id)
                                    # else: Skip non-final games
                                else:
                                    # If no status field, we might be looking at a simple ref.
                                    # But usually the schedule API returns full objects.
                                    # Fallback: if 'score' is present and not null?
                                    pass

                            # Continue recursion for nested objects (e.g. list of games)
                            for k, v in obj.items():
                                found.update(search_json_recursively(v))
                                
                        elif isinstance(obj, list):
                            for item in obj:
                                found.update(search_json_recursively(item))
                        return found

                    ids = search_json_recursively(data)
                    if ids:
                        # print(f"Captured {len(ids)} potential IDs from: {response.url}")
                        intercepted_ids.update(ids)
                        
                except Exception:
                    pass
        except Exception:
            pass

    # Note: Adding listener inside loop might stack them? 
    # Better to keep listener global or remove it. 
    # For simplicity, we just add it, duplicate handlers are harmless here or we can remove logic if complex.
    # Actually, Playwright event listeners stack. Let's clear listeners or just use a shared 'current_ids' set?
    # Simple fix: Re-use the page object but we need to reset intercepted_ids.
    # The listener is attached to PAGE. 
    # Let's attach listener ONCE in main and key off a global/shared set, OR remove listener.
    # page.remove_listener not easy in sync api?
    # Let's simple redefine the callback to write to a LIST passed in args?
    # Optimization: Just define handle_response globally or inline and attach once. 
    # But here we want to scope to this team.
    # Let's just Add/Remove listener.
    page.on("response", handle_response)

    # --- COOKIE CONSENT ---
    try:
        # Look for common cookie consent buttons at the bottom of the page
        # print("Checking for cookie consent...")
        cookie_btn = page.locator("button:has-text('Tout accepter'), button:has-text('Accepter'), button:has-text('Autoriser')").first
        if cookie_btn.is_visible(timeout=3000):
            cookie_btn.click()
            print("Accepted cookies.")
            time.sleep(1) 
    except Exception:
        pass

    # --- AUTOMATION START ---
    print("Automating filters...")
    
    # 1. Open Date Picker (Click directly on date display)
    try:
        # print("Opening date picker...")
        date_range_btn = page.locator("button.btn-outline-primary.w-100").first
        date_range_btn.wait_for(state="visible", timeout=10000)
        date_range_btn.click()
        time.sleep(1) 
    except Exception as e:
        print(f"Error opening date picker: {e}")
        page.remove_listener("response", handle_response)
        return

    # 2. Set Dates
    print("Setting dates: 2025-09-01 to 2026-04-30")
    try:
        # Start Date
        page.locator("#date-picker-start").click(click_count=3, force=True)
        page.keyboard.press("Backspace") 
        page.fill("#date-picker-start", "2025-09-01")
        time.sleep(1)
        
        # End Date
        page.locator("#date-picker-end").click(click_count=3, force=True)
        page.keyboard.press("Backspace")
        page.fill("#date-picker-end", "2026-04-30")
        time.sleep(1)
        
        # Click "Appliquer" button
        print("Clicking 'Appliquer'...")
        apply_btn = page.locator("button:has-text('Appliquer')").first
        apply_btn.click()
        
        # Wait for reload
        print("Waiting for page to reload...")
        time.sleep(4) 
        
    except Exception as e:
        print(f"Error setting dates: {e}")
        page.remove_listener("response", handle_response)
        return

    # 3. Pagination Loop
    print("Scanning pages...")
    page_num = 1
    consecutive_no_new_data = 0
    consecutive_empty_msg = 0
    last_id_count = 0
    
    while True:
        # Scroll to bottom
        page.mouse.wheel(0, 1000)
        time.sleep(2) 
        
        current_id_count = len(intercepted_ids)
        print(f"Scanned Page {page_num}. Total captured IDs: {current_id_count}")
        
        # Check for "No games" indicators
        no_games_msg = page.locator("text='Aucun événement trouvé'").or_(page.locator("text='Aucune partie'")).or_(page.locator("text='Aucun match'"))
        
        if no_games_msg.is_visible():
            consecutive_empty_msg += 1
        else:
            consecutive_empty_msg = 0
            
        if consecutive_empty_msg > 2:
            print("No games message found for more than 2 consecutive pages. Stopping.")
            break

        # --- DATE CHECK OPTIMIZATION ---
        # The user requested to stop if we go beyond May 30, 2026.
        # Headers on Spordle are like: "VENDREDI 9 JANVIER 2026".
        try:
            # We look for headers containing a year
            # Javascript to extract all headers text
            headers_text = page.eval_on_selector_all("h2, h3, h4, h5, div", "elements => elements.map(e => e.innerText)")
            
            # Regex to find French data: (JANVIER|FÉVRIER|...) \d{4}
            # Actually, simpler: just look for months and years.
            
            months_map = {
                "JANVIER": 1, "FÉVRIER": 2, "FEVRIER": 2, "MARS": 3, "AVRIL": 4, "MAI": 5, "JUIN": 6,
                "JUILLET": 7, "AOÛT": 8, "AOUT": 8, "SEPTEMBRE": 9, "OCTOBRE": 10, "NOVEMBRE": 11, "DÉCEMBRE": 12, "DECEMBRE": 12
            }
            
            stopped_by_date = False
            for text in headers_text:
                text = text.upper()
                # Find year 20xx
                # Check for "JUIN 2026" or later, or "2027"
                # If we see 2027, stop.
                if "2027" in text or "2028" in text:
                     print(f"Found future date header: '{text}'. Stopping pagination.")
                     stopped_by_date = True
                     break
                
                # If 2026, check month
                if "2026" in text:
                    for mon_name, mon_num in months_map.items():
                        if mon_name in text:
                            # If Month >= 6 (June), stop.
                            if mon_num >= 6:
                                print(f"Found date header beyond cutoff (May 2026): '{text}'. Stopping pagination.")
                                stopped_by_date = True
                                break
                    if stopped_by_date: break
            
            if stopped_by_date:
                break
                
        except Exception as e:
            print(f"Date check warning: {e}")
        # -------------------------------

        # Safety Break
        if current_id_count == last_id_count:
            consecutive_no_new_data += 1
        else:
            consecutive_no_new_data = 0
        
        last_id_count = current_id_count
        
        if consecutive_no_new_data >= 3 and consecutive_empty_msg == 0:
            print("No new games found for 3 consecutive checks. Stopping.")
            break

        # Check for 'Next' button
        next_btn = page.query_selector("button.btn-outline-primary.btn-block:has-text('Suivant')")
        
        if next_btn and next_btn.is_visible() and next_btn.is_enabled():
            # print("Clicking 'Suivant'...")
            next_btn.click()
            page_num += 1
            time.sleep(3) 
        else:
            print("No more pages (or 'Suivant' not found).")
            break
    
    page.remove_listener("response", handle_response)
    
    print("Automation complete. Processing captured data...")
    # --- AUTOMATION END ---

    # Strategy 1: Regex search
    import re
    html_content = page.content()
    raw_regex_ids = re.findall(r"schedule/(\d{6})", html_content)
    regex_ids = {rid for rid in raw_regex_ids if rid[0] in ['5', '6', '7', '8', '9']}
    
    # Merge intercepted IDs
    regex_ids.update(intercepted_ids)
    
    # Strategy 1.5: Frames
    for frame in page.frames:
        try:
            frame_content = frame.content()
            frame_ids = re.findall(r"schedule/(\d{6})", frame_content)
            if frame_ids:
                valid_frame_ids = {fid for fid in frame_ids if fid[0] in ['5', '6', '7', '8', '9']}
                if valid_frame_ids:
                    regex_ids.update(valid_frame_ids)
        except Exception:
            pass
    
    # Strategy 2: Links
    links = page.eval_on_selector_all("a[href*='schedule']", "elements => elements.map(e => e.getAttribute('href'))")
    for link in links:
        match = re.search(r"schedule/(\d{6})", link)
        if match:
            regex_ids.add(match.group(1))

    game_ids = regex_ids
    
    # Strategy 3: __NEXT_DATA__
    try:
        import json
        next_data_script = page.query_selector("script[id='__NEXT_DATA__']")
        if next_data_script:
            json_content = next_data_script.text_content()
            data = json.loads(json_content)
            
            found_ids = set()
            def search_json(obj):
                if isinstance(obj, dict):
                    # Check for ID and Status in the same object
                    game_id = None
                    for k in ["id", "_id", "gameId", "game_id"]:
                        if k in obj and isinstance(obj[k], (str, int)):
                            s_v = str(obj[k])
                            if s_v.isdigit() and len(s_v) == 6 and s_v[0] in ['5', '6', '7', '8', '9']:
                                game_id = s_v
                                break
                    
                    if game_id:
                        # Check status
                        status = None
                        if "status" in obj: status = obj["status"]
                        elif "gameStatus" in obj: status = obj["gameStatus"]
                        
                        if status and str(status).lower() in ["final", "terminé", "complete", "played"]:
                            found_ids.add(game_id)
                    
                    # Recurse
                    for k, v in obj.items():
                        search_json(v)
                elif isinstance(obj, list):
                    for item in obj:
                        search_json(item)
            
            search_json(data)
            regex_ids.update(found_ids)
    except Exception as e:
        print(f"Error parsing JSON data: {e}")

    game_ids = regex_ids
    print(f"Found {len(game_ids)} unique games for {team_name}.")
    
    if len(game_ids) > 0:
        print("Starting downloads...")
        for game_id in game_ids:
            download_pdf(game_id)
            time.sleep(0.5)

def main():
    ensure_download_dir()
    
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(viewport={'width': 1280, 'height': 800})
            page = context.new_page()

            for team in TEAMS:
                try:
                    process_team_schedule(page, team['id'], team['name'])
                except Exception as e:
                    print(f"Critical error processing team {team['name']}: {e}")

            print("\nAll teams processed!")
            print(f"Check the '{DOWNLOAD_DIR}' folder for PDF files.")
        
        finally:
            print("Closing browser...")
            browser.close()

if __name__ == "__main__":
    main()

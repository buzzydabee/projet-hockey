import os
import time
import requests
import sqlite3
import re
import subprocess
import shutil
import sys
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

# Configuration
DB_NAME = "hockey_stats.db"
DOWNLOAD_DIR = "downloads"
PDF_BASE_URL = "https://pdf.play.spordle.com/game/{game_id}?locale=fr"

def get_optimal_start_date():
    try:
        if not os.path.exists(DB_NAME):
            return "2025-10-21"
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        # FIX: Ignore future "Scheduled" games (score=0) when calculating start date.
        # Otherwise, if we have games until April, we'll never re-check last week's games.
        cursor.execute("SELECT MAX(date) FROM DimGame WHERE (final_score_home > 0 OR final_score_visitor > 0)")
        row = cursor.fetchone()
        conn.close()

        if row and row[0]:
            # "2025-10-21" or "21 octobre 2025" (legacy)
            # If legacy, we might still have issues, but assuming rebuild...
            last_date_str = row[0]
            
            # Simple check: is it ISO?
            if "-" in last_date_str:
                last_date = datetime.strptime(last_date_str, "%Y-%m-%d")
            else:
                # Fallback for legacy data if user didn't rebuild
                # (Re-using the parsing logic or just defaulting)
                return "2025-10-21" 
            
            start_date = last_date - timedelta(days=7)
            return start_date.strftime("%Y-%m-%d")

        return "2025-10-21"
    except:
        return "2025-10-21"

def ensure_download_dir():
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

def download_pdf(game_id):
    url = PDF_BASE_URL.format(game_id=game_id)
    file_path = os.path.join(DOWNLOAD_DIR, f"game_{game_id}.pdf")
    if os.path.exists(file_path):
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
            return False
    except Exception as e:
        print(f"Error downloading Game {game_id}: {e}")
        return False

def process_global_schedule(page, date_from):
    print("--- Processing Team: Horaire Global (ID: 0) ---")
    url = "https://page.spordle.com/fr/ligue-hockey-mineur-capitale-nationale/schedule-stats-standings/4db0bd5f-6773-4a84-9ff6-661863a5c069"
    
    unique_ids = set()

    try:
        # Use 'commit' to prevent Playwright from hanging on 3rd party tracker/ads loading.
        # We manually wait for the game components anyway.
        page.goto(url, timeout=60000, wait_until="commit")
        time.sleep(4) # Let React initialize
        try:
             # Look for typical dynamic elements or UI pieces
             page.wait_for_selector("img", timeout=15000) # Simple visual check
        except:
             print("Warning: Game rows not found immediately on land. Advancing anyway.")
             pass
             
        page.screenshot(path="debug_page_load.png")
        print("Page loaded (domcontentloaded). Screenshot saved.")
    except Exception as e:
        print(f"Error opening page: {e}")
        return

    # Handle Cookies
    try:
        page.locator("#onetrust-accept-btn-handler").click(timeout=3000)
        print("Cookies accepted.")
    except:
        pass

    # --- FILTER ATTEMPT ---
    try:
        # Dates
        start_date = datetime.strptime(date_from, "%Y-%m-%d")
        # FIX: S'assurer d'avoir toujours la saison au complet (jusqu'au 11 avril 2026)
        end_date = datetime(2026, 4, 11)
        
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        
        print(f"PLAGE DE RECHERCHE: {start_str} à {end_str}")
        # Open Date Range Menu
        # Screenshot 1: The user highlights the bar showing "30 prochains jours" or "Saison ...".
        # It's usually a button or div with a calendar icon.
        # We'll try to find it by the unique dynamic text or class structure.
        print("Opening Date Range Picker...")
        try:
            # Common Spordle Date Picker trigger
            # The date dropdown defaults to "7 prochains jours". 
            # DONT match "Saison" because it clicks the League Season dropdown instead!
            # Use visible=true to completely ignore hidden privacy/cookie policy texts.
            date_trigger = page.locator("text=/7 prochains jours|30 prochains jours|Personnalisé/i >> visible=true").first
            
            date_trigger.click(timeout=5000)
            time.sleep(1)
        except Exception as e:
            print(f"Could not click date trigger: {e}")

        # Select 'Personnalisé'
        print("Selecting 'Personnalisé'...")
        try:
            # Click the dropdown item, using last() visible element to avoid hidden cookie banner text completely
            page.locator("text=/Personnalisé/i >> visible=true").last.click(timeout=5000)
            time.sleep(1)
        except Exception as e:
            print(f"Could not find 'Personnalisé': {e}")

        # Override Dates
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        print(f"Applying Filters: {start_str} to {end_str}")

        def robust_fill(selector, value):
             loc = page.locator(selector)
             for i in range(3):
                 try:
                     # Focus and clear the underlying native input to trigger Vue/React states
                     loc.focus()
                     page.keyboard.press("Control+A")
                     page.keyboard.press("Backspace")
                     time.sleep(0.1)
                     
                     # Type it like a human
                     page.keyboard.type(value, delay=50)
                     page.keyboard.press("Tab")
                     time.sleep(0.5)
                     
                     current_val = loc.input_value()
                     if current_val == value:
                         return True
                     print(f"Retry {i+1} for {selector}: Got '{current_val}', wanted '{value}'")
                 except Exception as e:
                     print(f"Error filling {selector}: {e}")
             return False

        if robust_fill("#date-picker-start", start_str):
             print(f"Start Date set to: {start_str}")
        else:
             print("WARNING: Failed to set Start Date.")

        if robust_fill("#date-picker-end", end_str):
             print(f"End Date set to: {end_str}")
        else:
             try:
                 print(f"WARNING: Failed to set End Date. It remains: {page.locator('#date-picker-end').input_value()}")
             except:
                 print("WARNING: Failed to set End Date.")

        # CAPTURE SCREENSHOT AS REQUESTED
        try:
            debug_shot = "debug_dates_submitted.png"
            page.screenshot(path=debug_shot)
            print(f"Screenshot saved for verification: {debug_shot}")
        except: pass

        time.sleep(1)

        # Apply
        apply_btn = page.locator("button:has-text('Appliquer')").last
        
        all_games = []
        def intercept_api(response):
            if "api/sp/games" in response.url and response.request.method == "GET" and response.status == 200:
                try:
                    data = response.json()
                    games_list = data.get("data", []) if isinstance(data, dict) else data
                    if isinstance(games_list, list) and len(games_list) > 0:
                        all_games.extend(games_list)
                        print(f"Intercepted {len(games_list)} games from {response.url[:100]}...")
                except:
                    pass
        
        page.on("response", intercept_api)
        
        try:
            apply_btn.click(timeout=5000)
            print("Clicked Appliquer. Waiting up to 30 seconds for all fragmented API calls...")
        except Exception as e:
            print(f"Failed to click Appliquer: {e}")
            
        # Spordle sends APIs in fragments, AND implements "Infinite Scroll" (paginated lazy-loading).
        # We must scroll to the bottom repeatedly to trigger all API fetches for the whole date range.
        last_height = 0
        no_change_count = 0
        
        # Click center of page to ensure focus for keyboard events
        try:
             page.mouse.click(960, 500)
        except: pass
        
        # L'utilisateur a confirmé voir un bouton "Suivant" pour charger les prochains matchs.
        for _ in range(60):  # 60 essais de clics maximum (120 sec totales)
            page.wait_for_timeout(2000) # Pause de 2 secondes
            
            # EARLY EXIT : Vérifier si l'API a déjà retourné un match touchant ou dépassant la Date de Fin
            # Si oui, on coupe de force pour ne pas cliquer 'Suivant' de trop et vider la liste !
            reached_end = False
            for g in all_games:
                val = str(g.get('date', g.get('startTime', '')))[:10]
                if val and val >= end_str:
                    reached_end = True
                    break
                    
            if reached_end:
                print(f"Date de fin ({end_str}) détectée dans les données. Arrêt volontaire des clics 'Suivant'.")
                break
            
            # Chercher le bouton Suivant / Afficher plus
            try:
                # Tente de trouver tout élément cliquable contenant "Suivant" (ou des variantes Spordle)
                next_btn = page.locator("text=/Suivant|Afficher plus|Load more|Next/i >> visible=true").last
                
                if next_btn.is_visible(timeout=1000):
                    next_btn.scroll_into_view_if_needed()
                    page.wait_for_timeout(500)
                    next_btn.click(force=True)
                    print("Bouton 'Suivant' détecté et cliqué!")
                    no_change_count = 0  # Recommencer le compteur car l'écran charge!
                    continue
            except:
                pass
            
            # Si aucun bouton 'Suivant' n'est cliqué, on évalue si de nouvelles données API rentrent seules
            current_games_count = len(all_games)
            
            if current_games_count == last_height:
                no_change_count += 1
            else:
                no_change_count = 0
                last_height = current_games_count
                
            # Au bout de 5 vérifications sans changement (20 secondes sans bouton et sans API)
            if no_change_count >= 10:
                print("Plus aucun bouton 'Suivant' ni données recues (20 secondes d'attente maximum atteintes). Tous les matchs chargés.")
                break
                # Give it one last big scroll attempt via JS just in case
                page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                page.wait_for_timeout(1000)
                if len(all_games) == last_height:
                     print("Reached end of infinite scroll. All games loaded.")
                     break
                
        # Let it settle for 2 more seconds for any final straggler API calls
        page.wait_for_timeout(2000)
            
        # De-duplicate games by ID in case we caught multiples
        unique_games = {}
        for g in all_games:
            if 'id' in g: unique_games[g['id']] = g
            
        games_list = list(unique_games.values())
        print(f"DEBUG: Selected {len(games_list)} total unique games from API.")
        
        # SAVE SCHEDULE JSON for metadata ingestion
        if len(games_list) > 0:
            try:
                import json
                schedule_path = os.path.join(os.getcwd(), "scraped_schedule.json")
                with open(schedule_path, "w", encoding="utf-8") as f:
                    json.dump(games_list, f, ensure_ascii=False, indent=2)
                print(f"Saved schedule metadata to: {schedule_path}")
            except Exception as e:
                print(f"Warning: Could not save schedule JSON: {e}")

            for g in games_list:
                unique_ids.add(str(g.get("id")))

            print("Swapping to fallback DOM scan...")

    except Exception as e:
        print(f"Filter Logic Error: {e}")

    # --- FALLBACK: DOM SCAN ---
    # Even if API worked, we double check the DOM if count is 0, just in case.
    if len(unique_ids) == 0:
        print("API returned 0 games or failed. Scanning page HTML for game links...")
        try:
            # Wait for grid to load - INCREASED TIMEOUT due to slow loading indicator
            print("Waiting for game rows to appear in DOM (up to 45 seconds)...")
            page.wait_for_selector("a[href*='/game/']", timeout=45000)
            
            dom_ids = page.evaluate("""() => {
                const ids = new Set();
                document.querySelectorAll('a[href*="/game/"]').forEach(a => {
                    const m = a.getAttribute('href').match(/\/game\/(\d+)/);
                    if(m) ids.add(m[1]);
                });
                return Array.from(ids);
            }""")
            print(f"DOM Scan found: {len(dom_ids)} games.")
            for i in dom_ids:
                unique_ids.add(str(i))
        except Exception as e:
            print(f"DOM Scan failed or no games visible: {e}")

    print(f"Total Unique Games Found: {len(unique_ids)}")
    
    if len(unique_ids) == 0:
        print("WARNING: No games found to download. Check filters on screen?")
    else:
        # --- AGGRESSIVE UPDATE LOGIC ---
        # User Request: "For the selected period, all games must be deleted from DB and PDF deleted."
        # This ensures we re-download everything to catch stat updates.
        print(f"Purging {len(unique_ids)} games from DB and Disk to force fresh update...")
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            
            ids_list = list(unique_ids)
            # SQLite limit is usually 999 vars. Chunk it just in case.
            chunk_size = 500
            for i in range(0, len(ids_list), chunk_size):
                chunk = ids_list[i:i+chunk_size]
                placeholders = ','.join('?' * len(chunk))
                
                cursor.execute(f"DELETE FROM FactGoalieStats WHERE game_id IN ({placeholders})", chunk)
                cursor.execute(f"DELETE FROM FactPenalties WHERE game_id IN ({placeholders})", chunk)
                cursor.execute(f"DELETE FROM FactGoals WHERE game_id IN ({placeholders})", chunk)
                cursor.execute(f"DELETE FROM DimGame WHERE game_id IN ({placeholders})", chunk)
            
            conn.commit()
            conn.close()
            print("DB entries deleted.")
        except Exception as e:
            print(f"Error purging DB: {e}")

        # Delete Files
        for gid in unique_ids:
            p = os.path.join(DOWNLOAD_DIR, f"game_{gid}.pdf")
            if os.path.exists(p):
                try:
                    os.remove(p)
                    # print(f"Deleted cache: {p}")
                except: pass
        print("Local PDF cache cleared for these games.")

    
    for gid in unique_ids:
        download_pdf(gid)

def install_browsers():
    """
    Check if Playwright browsers are installed. If not, install them.
    This is critical for Streamlit Cloud where the environment is ephemeral.
    """
    print("Checking Playwright browsers...")
    # Check if chromium is roughly available or if we are in a non-local env
    # Simple strategy: Just try to run the install command. It handles "already installed" gracefully.
    try:
        # Check if we can execute the command
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        print("Playwright browsers installed (or already present).")
    except Exception as e:
        print(f"Error installing browsers: {e}")

def main():
    print("Starting Main...")
    install_browsers()
    ensure_download_dir()
    with sync_playwright() as p:
        # Test du mode 'Sans Tête' (Fantôme) en arrière-plan
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        start = get_optimal_start_date()
        process_global_schedule(page, start)
    print("Done.")

if __name__ == "__main__":
    main()

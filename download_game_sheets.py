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
            return "2025-09-01"
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        # With ISO dates (YYYY-MM-DD), lexical sort IS chronological sort
        cursor.execute("SELECT MAX(date) FROM DimGame")
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
                return "2025-09-01" 
            
            start_date = last_date - timedelta(days=7)
            return start_date.strftime("%Y-%m-%d")

        return "2025-09-01"
    except:
        return "2025-09-01"

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
    url = "https://page.spordle.com/fr/ligue-hockey-mineur-capitale-nationale/schedule-stats-standings/4db0bd5f-6773-4a84-9ff6-661863a5c069?scheduleId=183360"
    
    unique_ids = set()

    try:
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
        try:
             page.wait_for_selector(".game-row, .game-card", timeout=10000)
        except:
             print("Warning: Game rows not found immediately.")
             
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
        end_date = datetime(2026, 4, 30)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        # Open Date Range Menu
        # Screenshot 1: The user highlights the bar showing "30 prochains jours" or "Saison ...".
        # It's usually a button or div with a calendar icon.
        # We'll try to find it by the unique dynamic text or class structure.
        print("Opening Date Range Picker...")
        
        # Strategy: Find the button that contains year/date text.
        try:
            # Common Spordle Date Picker trigger
            # It's often a button with class w-100 or similar. 
            # We look for the one containing "2025" or "jours".
            date_trigger = page.locator("button").filter(has_text=re.compile(r"Saison|jours|Date")).first
            if not date_trigger.is_visible():
                 # Fallback to div if it's not a button
                 date_trigger = page.locator(".sp-date-picker, .date-picker-container").first
            
            date_trigger.click()
            time.sleep(1)
        except Exception as e:
            print(f"Could not click date trigger: {e}")
            # Bruteforce: Click top-center element?
            page.mouse.click(960, 400) # Risky guess
            time.sleep(1)

        # Select '7 derniers jours' as base
        # User tip: selecting this sets end date correctly and initializes inputs.
        print("Selecting '7 derniers jours'...")
        try:
            # We look for the exact text.
            page.locator("text=7 derniers jours").click()
            time.sleep(1)
        except Exception as e:
            print(f"Could not find '7 derniers jours': {e}")
            print("Trying to force 'Personnalisé'...")
            try: page.locator("text=Personnalisé").click()
            except: pass

        # Override Dates
        # Now that inputs are active/initlized, we overwrite them.
        print(f"Overriding dates: {start_str} to {end_str}")
        try:
             # START DATE
             page.fill("#date-picker-start", start_str)
             # Force events to ensure React/Angular app picks it up
             page.evaluate("document.getElementById('date-picker-start').dispatchEvent(new Event('input', {bubbles: true}))")
             page.evaluate("document.getElementById('date-picker-start').dispatchEvent(new Event('change', {bubbles: true}))")
             page.evaluate("document.getElementById('date-picker-start').dispatchEvent(new Event('blur', {bubbles: true}))")
             
             # END DATE
             # User said end date is auto-set by '7 days', but we want to ensure we catch TODAY.
             # If '7 days' excludes today, we might miss it.
             # Safest is to overwrite it only if needed, OR just overwrite it always to be sure.
             page.fill("#date-picker-end", end_str)
             page.evaluate("document.getElementById('date-picker-end').dispatchEvent(new Event('input', {bubbles: true}))")
             page.evaluate("document.getElementById('date-picker-end').dispatchEvent(new Event('change', {bubbles: true}))")
             page.evaluate("document.getElementById('date-picker-end').dispatchEvent(new Event('blur', {bubbles: true}))")
             
             # Retrieve values to verify
             actual_start = page.input_value("#date-picker-start")
             print(f"DEBUG: Input Start Date is now: {actual_start}")
             
        except Exception as e:
             print(f"Error filling inputs: {e}")

        time.sleep(1)

        # Apply
        # Screenshot 3: Black 'Appliquer' button inside the dropdown.
        apply_btn = page.locator("button:has-text('Appliquer')").last
        try:
            with page.expect_response(lambda r: "api/sp/games" in r.url and r.status == 200, timeout=10000) as response_info:
                apply_btn.click()
                print("Clicked Appliquer. Waiting for API...")
            
            data = response_info.value.json()
            print(f"DEBUG: API Request URL: {response_info.value.url}")
            print(f"DEBUG: API Returned {len(data)} games.")
            for g in data:
                unique_ids.add(str(g.get("id")))

        except Exception as e:
            print(f"API Intercept Warning: {e}")
            print("Swapping to fallback DOM scan...")

    except Exception as e:
        print(f"Filter Logic Error: {e}")

    # --- FALLBACK: DOM SCAN ---
    # Even if API worked, we double check the DOM if count is 0, just in case.
    if len(unique_ids) == 0:
        print("API returned 0 games. Scanning page HTML for game links...")
        try:
            # Wait for grid to load
            page.wait_for_selector("a[href*='/game/']", timeout=5000)
            
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
        # headless=False so the user can see the browser actions
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        start = get_optimal_start_date()
        process_global_schedule(page, start)
    print("Done.")

if __name__ == "__main__":
    main()

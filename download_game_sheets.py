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
        cursor.execute("SELECT date FROM DimGame")
        rows = cursor.fetchall()
        conn.close()

        if not rows:
             return "2025-09-01"

        # French Month Map
        MONTHS_MAP = {
            "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
            "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12
        }

        def parse_date(d_str):
            try:
                parts = d_str.lower().split()
                # 21 octobre 2025
                day = int(parts[0])
                month = MONTHS_MAP.get(parts[1], 1)
                year = int(parts[2])
                return datetime(year, month, day)
            except:
                return datetime(2000, 1, 1)

        dates = [parse_date(r[0]) for r in rows if r[0]]
        if not dates:
             return "2025-09-01"
        
        max_date = max(dates)
        # Go back 7 days for safety
        start_date = max_date - timedelta(days=7)
        return start_date.strftime("%Y-%m-%d")
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
        
        print(f"Applying filters (Attempt 1): {start_str}")

        # Open Filter Menu
        filter_btn = page.locator("button:has-text('Filtres')").first
        filter_btn.wait_for(state="visible", timeout=10000)
        filter_btn.click(force=True)
        time.sleep(1)

        # Personnalise
        page.locator("li").filter(has_text="Personnalisé").first.click()
        time.sleep(1)

        # Fill
        page.fill("#date-picker-start", start_str)
        page.evaluate("document.getElementById('date-picker-start').dispatchEvent(new Event('input', {bubbles: true}))")
        page.fill("#date-picker-end", end_str)
        page.evaluate("document.getElementById('date-picker-end').dispatchEvent(new Event('input', {bubbles: true}))")
        
        time.sleep(1)

        # Apply & Intercept
        apply_btn = page.locator("button:has-text('Appliquer')").last
        
        with page.expect_response(lambda r: "api/sp/games" in r.url and r.status == 200, timeout=10000) as response_info:
            apply_btn.click()
            print("Clicked Appliquer.")
        
        data = response_info.value.json()
        print(f"API Returned {len(data)} games.")
        for g in data:
            unique_ids.add(str(g.get("id")))

    except Exception as e:
        print(f"Filter/API Error: {e}")
        try:
            page.screenshot(path="debug_filter_fail.png")
        except: pass

    # --- DOM SCAN ---
    try:
        print("Scanning DOM...")
        # Check if we need to expand or scroll?
        # Just scan what's there
        dom_ids = page.evaluate(r"""
            () => {
                const ids = new Set();
                document.querySelectorAll('a[href*="/game/"]').forEach(a => {
                    const m = a.getAttribute('href').match(/\/game\/(\d+)/);
                    if(m) ids.add(m[1]);
                });
                return Array.from(ids);
            }
        """)
        print(f"DOM Scan found: {len(dom_ids)}")
        for i in dom_ids:
            unique_ids.add(str(i))
            
    except Exception as e:
        print(f"DOM Scan Error: {e}")

    print(f"Total Unique Games: {len(unique_ids)}")
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
        # headless=True for Streamlit Cloud / Production
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        start = get_optimal_start_date()
        process_global_schedule(page, start)
    print("Done.")

if __name__ == "__main__":
    main()

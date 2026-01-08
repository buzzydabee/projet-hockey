import os
import time
import requests
import sqlite3
import re
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
        # Fetch ALL dates because MAX() on text "9 novembre" > "21 octobre" is wrong.
        cursor.execute("SELECT date FROM DimGame")
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return "2025-09-01"

        months_map = {
            "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
            "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12
        }

        parsed_dates = []
        for r in rows:
            date_str = r[0]
            try:
                parts = date_str.lower().split()
                # Format: "SAMEDI 1 NOVEMBRE 2025" or "1 NOVEMBRE 2025"
                if len(parts) >= 4:
                    d = int(parts[1])
                    m = months_map.get(parts[2], 9)
                    y = int(parts[3])
                    parsed_dates.append(datetime(y, m, d))
                elif len(parts) == 3: 
                    d = int(parts[0])
                    m = months_map.get(parts[1], 9)
                    y = int(parts[2])
                    parsed_dates.append(datetime(y, m, d))
            except:
                continue
        
        if parsed_dates:
            last_date = max(parsed_dates)
            # Buffer of 7 days
            start_date = last_date - timedelta(days=7)
            # Ensure we don't go before season start? Not strictly necessary but cleaner.
            season_start = datetime(2025, 9, 1)
            if start_date < season_start:
                start_date = season_start
                
            return start_date.strftime("%Y-%m-%d")
            
        return "2025-09-01"
    except Exception as e:
        print(f"Error getting start date from DB: {e}")
        return "2025-09-01"

def ensure_download_dir():
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)
        print(f"Created download directory: {DOWNLOAD_DIR}")

def download_pdf(game_id):
    url = PDF_BASE_URL.format(game_id=game_id)
    file_path = os.path.join(DOWNLOAD_DIR, f"game_{game_id}.pdf")
    
    if os.path.exists(file_path):
        # print(f"File already exists: {file_path}. Skipping.")
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
            # Silent fail for non-existent games (common)
            # print(f"Failed to download Game {game_id} (Status: {response.status_code})")
            return False
    except Exception as e:
        print(f"Error downloading Game {game_id}: {e}")
        return False

def process_global_schedule(page, date_from):
    """
    Process the global schedule page for the entire league.
    URL: https://page.spordle.com/fr/ligue-hockey-mineur-capitale-nationale/schedule-stats-standings/4db0bd5f-6773-4a84-9ff6-661863a5c069?scheduleId=183360
    """
    # UI Compatibility Log
    print("--- Processing Team: Horaire Global (ID: 0) ---")
    
    url = "https://page.spordle.com/fr/ligue-hockey-mineur-capitale-nationale/schedule-stats-standings/4db0bd5f-6773-4a84-9ff6-661863a5c069?scheduleId=183360"
    print(f"Navigating to Global Schedule...")
    
    # --- BLOCK ADS / REDIRECTS ---
    try:
        def block_ads(route):
            req_url = route.request.url.lower()
            block_list = [
                "doubleclick", "adsystem", "analytics", "facebook", "twitter", 
                "tracepath", "antitrojan", "googlesyndication", "adnxs", 
                "smartadserver", "criteo", "pubmatic", "rubicon", "openx"
            ]
            if any(x in req_url for x in block_list):
                # print(f"Blocking: {req_url}")
                route.abort()
            else:
                route.continue_()
        
        page.route("**/*", block_ads)
        
        # Close popups immediately
        page.on("popup", lambda p: p.close())
    except:
        pass

    try:
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
    except Exception as e:
        print(f"Error opening page: {e}")
        return

    # --- 1. HANDLE COOKIES ---
    try:
        page.wait_for_selector("#onetrust-accept-btn-handler", timeout=5000)
        page.click("#onetrust-accept-btn-handler", force=True)
        print("Cookies accepted.")
    except:
        pass 

    # --- 2. SET DATE FILTERS ---
    try:
        print("Automating filters...")
        time.sleep(3) # Wait for initial load/ads
        
        # Open Dropdown (JS Force)
        page.evaluate("document.querySelector('button.btn-outline-primary.w-100')?.click()")
        time.sleep(2)
        
        # Click "Personnalisé" (JS Find & Click)
        clicked = page.evaluate("""
            () => {
                const options = Array.from(document.querySelectorAll('li'));
                const target = options.find(el => el.innerText && el.innerText.includes('Personnalisé'));
                if(target) {
                    target.click();
                    return true;
                }
                return false;
            }
        """)
        
        if not clicked:
            print("Warning: Could not find 'Personnalisé' option via JS. Trying standard locator...")
            page.locator("li:has-text('Personnalisé')").click(force=True)
            
        time.sleep(1)
        
        # Calculate Date Range
        start_date = datetime.strptime(date_from, "%Y-%m-%d")
        end_date = datetime(2026, 4, 30) # End of season
        
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        
        print(f"Setting dates: {start_str} to {end_str}")
        
        # Fill Inputs
        page.wait_for_selector("#date-picker-start", timeout=10000)
        page.locator("#date-picker-start").click(click_count=3)
        page.keyboard.press("Backspace")
        page.fill("#date-picker-start", start_str)
        # Do NOT press Enter here, it might close the popup
        time.sleep(0.5)
        
        page.wait_for_selector("#date-picker-end", timeout=10000)
        page.locator("#date-picker-end").click(click_count=3)
        page.keyboard.press("Backspace")
        page.fill("#date-picker-end", end_str)
        page.press("#date-picker-end", "Enter") # Press Enter to Submit/Close
        time.sleep(1)
        
        # Click Apply if still visible, otherwise assume Enter worked
        try:
             if page.locator("text=Appliquer").is_visible(timeout=2000):
                 print("Clicking 'Appliquer'...")
                 page.locator("text=Appliquer").click(force=True)
        except:
             pass
        
        # Wait for reload - verify 'scheduleId' is still there or check for spinner
        time.sleep(4) 
        
    except Exception as e:
        print(f"Error setting dates: {e}")
        # Continue anyway, defaults might be okay-ish or we catch errors later
    
    # --- 3. SCROLL & CAPTURE GAMES ---
    print("Scanning Page for Games...")
    
    # Scroll to bottom to ensure dynamic loading
    # In global schedule, it can be long.
    # We scroll until height doesn't change
    last_height = page.evaluate("document.body.scrollHeight")
    retries = 0
    while True:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)
        new_height = page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            retries += 1
            if retries >= 2: # Double check
                break
        else:
            retries = 0
        last_height = new_height
        
    # Extract Links
    # Game links usually look like: /fr/.../schedule/123456
    # We want unique IDs.
    
    unique_ids = set()
    
    try:
        # Get all hrefs from anchors
        links = page.evaluate("""
            () => {
                return Array.from(document.querySelectorAll('a')).map(a => a.href)
            }
        """)
        
        for link in links:
            # Pattern: .../schedule/123456
            match = re.search(r"schedule/(\d{6})", link)
            if match:
                game_id = match.group(1)
                unique_ids.add(game_id)
                
    except Exception as e:
        print(f"Error extracting game links: {e}")

    print(f"Found {len(unique_ids)} unique games for the selected period.")
    
    # --- 4. DOWNLOAD LOOP ---
    if unique_ids:
        print("Starting downloads...")
        for game_id in unique_ids:
            # print(f"Checking Game {game_id}...")
            download_pdf(game_id)

def main():
    print("Starting Global Game Sheet Download Process...")
    ensure_download_dir()
    
    with sync_playwright() as p:
        # headless=True for Streamlit Cloud
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        page = context.new_page()

        try:
            # Calculate Date Once
            start_date = get_optimal_start_date()
            print(f"Smart Optimization: Starting search from {start_date}")

            # Single Global Process
            process_global_schedule(page, date_from=start_date)
            
        except Exception as e:
            print(f"Critical error in main loop: {e}")
        finally:
            browser.close()
            print("Browser closed.")

if __name__ == "__main__":
    main()

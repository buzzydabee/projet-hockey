from playwright.sync_api import sync_playwright
import re
import time

def inspect():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://page.spordle.com/fr/ligue-hockey-mineur-capitale-nationale/schedule-stats-standings/4db0bd5f-6773-4a84-9ff6-661863a5c069?scheduleId=183360")
        
        try:
            # Open Filter
            page.locator("button", has_text=re.compile(r"Filtres", re.IGNORECASE)).first.click()
            page.locator("li").filter(has_text="Personnalisé").first.click()
            time.sleep(1)
            
            # Inspect
            html = page.locator("#date-picker-start").evaluate("el => el.outerHTML")
            val = page.locator("#date-picker-start").evaluate("el => el.value")
            print(f"Input HTML: {html}")
            print(f"Input Value: {val}")
            
        except Exception as e:
            print(f"Error: {e}")
            
        browser.close()

if __name__ == "__main__":
    inspect()

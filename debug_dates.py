
import os
import sys
import datetime
from playwright.sync_api import sync_playwright

def debug_date_filter_interaction():
    url = "https://page.spordle.com/fr/ligue-hockey-mineur-capitale-nationale/schedule-stats-standings/4db0bd5f-6773-4a84-9ff6-661863a5c069?scheduleId=183360"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        
        print(f"Navigating to {url}...")
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
        
        # Handle Cookies
        try:
            page.locator("#onetrust-accept-btn-handler").click(timeout=3000)
            print("Accepted cookies.")
        except:
            pass
            
        # Target Date Logic
        # Let's use a fixed date range to test formatting
        start_str = "2025-09-01" 
        end_str = "2025-10-01" # Short range
        
        print(f"Attempting to set range: {start_str} to {end_str}")
        
        # Open Picker
        try:
            # Try to find the date trigger button
            import re
            date_trigger = page.locator("button").filter(has_text=re.compile(r"Saison|jours|Date")).first
            if not date_trigger.is_visible():
                 date_trigger = page.locator(".sp-date-picker, .date-picker-container").first
            
            if date_trigger.is_visible():
                date_trigger.click()
                print("Opened date picker.")
            else:
                print("Could not find date picker trigger.")
        except Exception as e:
            print(f"Error opening picker: {e}")
            
        # Select Custom
        try:
            # Wait for dropdown
            page.wait_for_selector("text=Personnalisé", timeout=5000)
            page.locator("text=Personnalisé").click()
            print("Selected 'Personnalisé'.")
        except Exception as e:
             print(f"Error selecting custom: {e}")
             
        # Fill Dates
        try:
             # Try filling with YYYY-MM-DD
             print(f"Filling start: {start_str}")
             page.fill("#date-picker-start", start_str)
             page.evaluate("document.getElementById('date-picker-start').dispatchEvent(new Event('input', {bubbles: true}))")
             page.evaluate("document.getElementById('date-picker-start').dispatchEvent(new Event('change', {bubbles: true}))")
             
             print(f"Filling end: {end_str}")
             page.fill("#date-picker-end", end_str)
             page.evaluate("document.getElementById('date-picker-end').dispatchEvent(new Event('input', {bubbles: true}))")
             page.evaluate("document.getElementById('date-picker-end').dispatchEvent(new Event('change', {bubbles: true}))")
             
             # Capture Screenshot BEFORE Apply
             screenshot_path = os.path.abspath("debug_dates_before_apply.png")
             page.screenshot(path=screenshot_path)
             print(f"Screenshot saved to: {screenshot_path}")
             
             # Read back values
             val_start = page.input_value("#date-picker-start")
             val_end = page.input_value("#date-picker-end")
             print(f"READ BACK VALUES: Start='{val_start}', End='{val_end}'")
             
        except Exception as e:
             print(f"Error filling dates: {e}")
             page.screenshot(path="debug_error.png")

        browser.close()

if __name__ == "__main__":
    debug_date_filter_interaction()

from playwright.sync_api import sync_playwright
import time

def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        c = b.new_context()
        page = c.new_page()
        page.goto('https://page.spordle.com/fr/ligue-hockey-mineur-capitale-nationale/schedule-stats-standings/6f5f76d7-150f-4568-a479-6daf4cf1ab93', wait_until='commit')
        time.sleep(4)
        print("Page loaded.")
        
        try: page.locator('#onetrust-accept-btn-handler').click(timeout=3000)
        except: pass
        
        # Open Dropdown
        page.locator('text=/7 prochains|30 prochains|Personnalisé/i >> visible=true').first.click(timeout=5000)
        time.sleep(1)
        # Select Personnalisé
        page.locator('text=/Personnalisé/i >> visible=true').last.click(timeout=5000)
        time.sleep(1)
        
        # Focus and Type (simulating real user to trigger React/Vue bindings)
        l1 = page.locator('#date-picker-start')
        l1.click(force=True)
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.keyboard.type('2025-09-01', delay=30)
        l1.evaluate("el => el.dispatchEvent(new Event('input', {bubbles: true}))")
        l1.evaluate("el => el.dispatchEvent(new Event('change', {bubbles: true}))")
        l1.evaluate("el => el.dispatchEvent(new Event('blur', {bubbles: true}))")
        
        l2 = page.locator('#date-picker-end')
        l2.click(force=True)
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.keyboard.type('2026-04-06', delay=30)
        l2.evaluate("el => el.dispatchEvent(new Event('input', {bubbles: true}))")
        l2.evaluate("el => el.dispatchEvent(new Event('change', {bubbles: true}))")
        l2.evaluate("el => el.dispatchEvent(new Event('blur', {bubbles: true}))")
        time.sleep(1.5)
        
        # Generic network listener to find the new API endpoint
        def log_api(response):
            if response.request.resource_type in ["xhr", "fetch", "document"] and "http" in response.url:
                print("URL:", response.url, "Status:", response.status)
        
        page.on("response", log_api)
        
        page.locator('button', has_text='Appliquer').last.click()
        print("Applied.")
        time.sleep(15) # Wait for network
        print("Done.")

if __name__ == "__main__":
    main()

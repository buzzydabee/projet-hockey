import os
import requests
import time

DOWNLOAD_DIR = "downloads"
PDF_BASE_URL = "https://pdf.play.spordle.com/game/{game_id}?locale=fr"

def ensure_download_dir():
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

def download_pdf(game_id):
    url = PDF_BASE_URL.format(game_id=game_id)
    file_path = os.path.join(DOWNLOAD_DIR, f"game_{game_id}.pdf")
    
    # Always try to download if checking for missing games, even if exists (optional)
    # But usually skip if exists to save time.
    if os.path.exists(file_path):
        print(f"File exists: game_{game_id}.pdf")
        return True
        
    try:
        response = requests.get(url, stream=True, timeout=10)
        if response.status_code == 200:
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"Downloaded: game_{game_id}.pdf")
            return True
        else:
            print(f"Game {game_id} not found (Status: {response.status_code})")
            return False
    except Exception as e:
        print(f"Error downloading Game {game_id}: {e}")
        return False

def main():
    ensure_download_dir()
    # Range based on Browser Subagent findings (720418, 720419, 720420...)
    # We'll scan a bit wider around 720400-720450 to be safe.
    start_id = 720400
    end_id = 720450
    
    print(f"Brute forcing download for Game IDs {start_id} to {end_id}...")
    
    success_count = 0
    for gid in range(start_id, end_id + 1):
        if download_pdf(gid):
            success_count += 1
        time.sleep(0.1)
        
    print(f"Download complete. Successfully downloaded {success_count} PDFs.")

if __name__ == "__main__":
    main()

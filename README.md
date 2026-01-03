# Hockey Stats Dashboard

Automated dashboard for tracking stats in the "Junior C Mixte" league.

## Features
- **Auto-Download**: Fetches ONLY final game sheets from Spordle.
- **Data Processing**: Parses PDFs to extract goals, assists, penalties, and goalkeeper stats.
- **Interactive Dashboard**: Streamlit app with date filtering, player comparisons, and standings..

## Setup

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   playwright install
   ```

2. **Run the Dashboard**
   ```bash
   streamlit run app.py
   ```

## Usage
- Click **"Check for Missing Games"** in the sidebar to download new scoresheets.
- Use the **Date Range Slider** to filter stats by specific periods.
- Use **"Rebuild Database"** if you want to reset stats based on local files.

## Files
- `app.py`: The dashboard application.
- `download_game_sheets.py`: Script to scrape and download PDFs.
- `process_gamesheets.py`: ETL script to parse PDFs into `hockey_stats.db`.
- `downloads/`: Folder storing game sheets.

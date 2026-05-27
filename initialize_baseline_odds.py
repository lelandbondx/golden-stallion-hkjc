import os
from scraper import get_live_meeting_data
from odds_tracker import get_baseline_odds

def initialize_baseline():
    print("=== INITIALIZING BASELINE ODDS ===")
    data = get_live_meeting_data()
    
    if data.get('status') != 'success' or not data.get('meetings'):
        print("[ERROR] Failed to fetch live meeting data for baseline odds initialization.")
        return
        
    meeting = data['meetings'][0]
    date_str = meeting.get('date')
    venue = meeting.get('venue')
    
    if not date_str or not venue:
        print("[ERROR] Date or Venue is missing from live meeting data.")
        return
        
    filename = f"data/baseline_odds_{date_str.replace('-', '')}.json"
    print(f"Raceday Date: {date_str}")
    print(f"Venue: {venue}")
    print(f"Target Baseline File: {filename}")
    
    # Check if baseline file already exists
    file_exists = os.path.exists(filename)
    if file_exists:
        print(f"[INFO] Baseline file {filename} already exists. Appending any missing runners without overwriting existing ones.")
    else:
        print(f"[INFO] Creating new baseline file {filename}.")
        
    initialized_count = 0
    skipped_count = 0
    
    for race in meeting.get('races', []):
        race_no = race.get('race_no')
        for runner in race.get('runners', []):
            horse_no = runner.get('no')
            current_odds = runner.get('win_odds', 0.0)
            
            # get_baseline_odds will load the file, check if key exists, write if missing, and return
            val = get_baseline_odds(date_str, venue, race_no, horse_no, current_odds)
            
            # If the current odds were written, or if we checked it
            initialized_count += 1
            
    print(f"[OK] Completed initialization. Checked/initialized {initialized_count} runners.")

if __name__ == '__main__':
    initialize_baseline()

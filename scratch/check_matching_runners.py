import pandas as pd
from scraper import get_live_meeting_data

# Load live runners
data = get_live_meeting_data()
if data and data.get('meetings'):
    meeting = data['meetings'][0]
    live_horses = []
    for r in meeting.get('races', []):
        for runner in r.get('runners', []):
            live_horses.append(runner.get('name').upper().strip())
    
    print(f"Total live horses: {len(live_horses)}")
    
    # Load historical database
    try:
        results = pd.read_csv('data/results.csv', usecols=['horse'])
        results['clean_name'] = results['horse'].str.extract(r'^(.*?)\(')[0].str.strip().str.upper()
        hist_names = set(results['clean_name'].dropna().tolist())
        
        matches = [h for h in live_horses if h in hist_names]
        print(f"Live horses found in historical results.csv: {len(matches)} / {len(live_horses)}")
        if matches:
            print("Matched horses:", matches[:10])
        else:
            print("No matches found! Checking if format of horse names matches.")
            print("Sample historical names:", list(hist_names)[:5])
            print("Sample live names:", live_horses[:5])
    except Exception as e:
        print("Error checking matches:", e)

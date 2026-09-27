import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
from scraper import get_live_meeting_data

data = get_live_meeting_data()
if not data.get('meetings'):
    print("No active meetings.")
    exit(0)

m = data['meetings'][0]
print(f"Venue: {m.get('venue')}, Date: {m.get('date')}, Going: {m.get('going')}")
for r in m.get('races', []):
    r_no = r.get('race_no')
    runners = r.get('runners', [])
    odds_list = [f"#{runner.get('no')}:{runner.get('odds')}" for runner in runners if runner.get('odds')]
    print(f"Race {r_no} ({r.get('class_dist')}, {r.get('track')}): {len(runners)} runners, {len(odds_list)} with odds. Sample: {odds_list[:4]}")

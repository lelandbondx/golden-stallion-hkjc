import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import scraper
import json

data = scraper.get_live_meeting_data()
# Print structure
print("KEYS:", data.keys())
if 'meetings' in data:
    print(f"Number of meetings: {len(data['meetings'])}")
    for i, m in enumerate(data['meetings']):
        print(f"\nMeeting {i}:")
        print(f"Venue: {m.get('venue')}")
        print(f"Date: {m.get('date')}")
        print(f"Going: {m.get('going')}")
        print(f"Races count: {len(m.get('races', []))}")
        if m.get('races'):
            r = m['races'][0]
            print("First race keys:", r.keys())
            print("First race no:", r.get('race_no'))
            print("First race class_dist:", r.get('class_dist'))
            print("First race runners count:", len(r.get('runners', [])))
            if r.get('runners'):
                print("First runner sample:", r['runners'][0])
else:
    print("No meetings key in data!")

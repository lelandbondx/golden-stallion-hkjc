import os
import sys
import json
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import requests
# Monkeypatch requests to bypass SSL verification
original_get = requests.get
original_post = requests.post
requests.get = lambda *args, **kwargs: original_get(*args, **{**kwargs, 'verify': False})
requests.post = lambda *args, **kwargs: original_post(*args, **{**kwargs, 'verify': False})

from scraper import get_live_meeting_data

def main():
    print("Fetching live results from HKJC GraphQL API...")
    res = get_live_meeting_data()
    print("GraphQL status:", res.get("status"))
    if res.get("status") == "success":
        meetings = res.get("meetings", [])
        print(f"Number of meetings: {len(meetings)}")
        for m in meetings:
            print(f"Meeting: {m.get('date')} - {m.get('venue')} - Status: {m.get('status')}")
            for race in m.get('races', []):
                print(f"Race {race.get('race_no')}: {len(race.get('runners', []))} runners")
                # print top 3 positions
                runners = sorted(race.get('runners', []), key=lambda x: int(x.get('final_position') or 99))
                top_3 = [f"#{r.get('no')} {r.get('name')} (Pos: {r.get('final_position')})" for r in runners[:3]]
                print("  Top 3:", ", ".join(top_3))
    else:
        print("Failed to get live meeting data.")

if __name__ == '__main__':
    main()

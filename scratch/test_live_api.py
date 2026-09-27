import os
import sys

# Add parent directory to sys.path so we can import scraper
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import requests
# Monkeypatch requests to disable SSL verification
original_get = requests.get
original_post = requests.post
requests.get = lambda *args, **kwargs: original_get(*args, **{**kwargs, 'verify': False})
requests.post = lambda *args, **kwargs: original_post(*args, **{**kwargs, 'verify': False})

from scraper import get_live_meeting_data, get_live_tips_index

def main():
    print("Testing get_live_meeting_data() with verification disabled...")
    try:
        res = get_live_meeting_data()
        print("Success! Status:", res.get("status"))
        if res.get("status") == "success":
            meetings = res.get("meetings", [])
            print(f"Number of meetings: {len(meetings)}")
            for m in meetings:
                print(f"Meeting date: {m.get('date')} - venue: {m.get('venue')} - status: {m.get('status')}")
                print(f"Races count: {len(m.get('races', []))}")
        else:
            print("Response did not have status success")
    except Exception as e:
        print("Exception during get_live_meeting_data():", e)

    print("\nTesting get_live_tips_index() with verification disabled...")
    try:
        tips = get_live_tips_index()
        print("Tips keys (races):", list(tips.keys()))
    except Exception as e:
        print("Exception during get_live_tips_index():", e)

if __name__ == '__main__':
    main()

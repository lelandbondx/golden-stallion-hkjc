import sys
sys.path.append('.')
import requests
import json
from scraper import GRAPHQL_QUERY

url = "https://info.cld.hkjc.com/graphql/base/"
headers = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json"
}

# First get active meetings
res = requests.post(url, json={"query": GRAPHQL_QUERY, "variables": {}}, headers=headers, timeout=10)
if res.status_code == 200:
    data = res.json()
    active_meetings = data.get("data", {}).get("activeMeetings", [])
    for m in active_meetings:
        date = m.get("date")
        venue = m.get("venueCode")
        if venue in ["ST", "HV"]:
            print(f"Active Meeting: Venue={venue}, Date={date}")
            # Query detailed races
            var = {"date": date, "venueCode": venue}
            det_res = requests.post(url, json={"query": GRAPHQL_QUERY, "variables": var}, headers=headers, timeout=10)
            det_data = det_res.json()
            races = det_data.get("data", {}).get("raceMeetings", [{}])[0].get("races", [])
            for r in races:
                track = r.get("raceTrack", {}).get("description_en")
                course = r.get("raceCourse", {}).get("description_en")
                going = r.get("go_en")
                print(f"  Race {r.get('no')}: Dist: {r.get('distance')}m, Going: {going}, Track: {track}, Course: {course}")
else:
    print(f"Failed to query active meetings: {res.status_code}")

import os
import sys
sys.path.append(os.getcwd())

import requests
import json
from scraper import GRAPHQL_QUERY

url = "https://info.cld.hkjc.com/graphql/base/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/json"
}

try:
    res = requests.post(url, json={"query": GRAPHQL_QUERY, "variables": {}}, headers=headers, timeout=10)
    data = res.json()
    meetings = data["data"].get("activeMeetings", [])
    
    if meetings:
        m = meetings[0]
        variables = {"date": m.get("date"), "venueCode": m.get("venueCode")}
        detail_res = requests.post(url, json={"query": GRAPHQL_QUERY, "variables": variables}, headers=headers, timeout=10)
        detail_data = detail_res.json()
        
        meeting_detail = detail_data.get("data", {}).get("raceMeetings", [{}])[0]
        races = meeting_detail.get("races", [])
        
        print("Checking winOdds for all races:")
        for r in races:
            runners = r.get('runners', [])
            if runners:
                first_runner = runners[0]
                val = first_runner.get('winOdds')
                print(f"  Race {r.get('no')} - Runner #{first_runner.get('no')} ({first_runner.get('name_en')}): winOdds = {repr(val)} (type: {type(val)})")
            else:
                print(f"  Race {r.get('no')}: No runners.")
    else:
        print("No active meetings found.")
except Exception as e:
    print("Error:", e)

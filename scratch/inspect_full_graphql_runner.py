import os
import sys
sys.path.append(os.getcwd())

import requests
from scraper import GRAPHQL_QUERY

url = "https://info.cld.hkjc.com/graphql/base/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/json"
}

try:
    res = requests.post(url, json={"query": GRAPHQL_QUERY, "variables": {}}, headers=headers, timeout=10)
    meetings = res.json()["data"].get("activeMeetings", [])
    
    if meetings:
        m = meetings[0]
        variables = {"date": m.get("date"), "venueCode": m.get("venueCode")}
        detail_res = requests.post(url, json={"query": GRAPHQL_QUERY, "variables": variables}, headers=headers, timeout=10)
        meeting_detail = detail_res.json().get("data", {}).get("raceMeetings", [{}])[0]
        races = meeting_detail.get("races", [])
        
        if races:
            runner = races[0].get('runners', [])[0]
            print("Full Runner Keys:")
            for k, v in runner.items():
                try:
                    val_str = str(v)[:50]
                    # Encode/decode to ignore characters that can't be represented in stdout encoding
                    val_str = val_str.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding)
                    print(f"  {k}: {val_str} (type: {type(v)})")
                except Exception as ex:
                    print(f"  {k}: [unprintable value] (type: {type(v)})")
except Exception as e:
    print("Error:", e)

import requests
import json
from scraper import GRAPHQL_QUERY

def analyze():
    url = "https://info.cld.hkjc.com/graphql/base/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type": "application/json"
    }

    print("Fetching live data...")
    res = requests.post(url, json={"query": GRAPHQL_QUERY, "variables": {}}, headers=headers, timeout=10)
    data = res.json()
    meetings = data.get("data", {}).get("activeMeetings", [])
    
    if not meetings:
        print("No active meetings found.")
        return
        
    for m in meetings:
        venueCode = m.get("venueCode")
        date = m.get("date")
        print(f"Meeting: {venueCode} on {date}")
        
        detail_res = requests.post(url, json={"query": GRAPHQL_QUERY, "variables": {"date": date, "venueCode": venueCode}}, headers=headers, timeout=10)
        detail_data = detail_res.json()
        
        meeting_detail = detail_data.get("data", {}).get("raceMeetings", [{}])[0]
        races = meeting_detail.get("races", [])
        
        going = races[0].get("go_en", "UNKNOWN") if races else "UNKNOWN"
        print(f"Track Condition (Going): {going}")
        
        scratched = []
        for r in races:
            for runner in r.get("runners", []):
                status = runner.get("status")
                name = runner.get("name_en")
                if status in ["Standby", "Scratched", "Withdrawn"]:
                    scratched.append(f"Race {r.get('no')}: #{runner.get('no')} {name} ({status})")
        
        print(f"Scratched/Withdrawn/Standby Horses ({len(scratched)}):")
        for s in scratched:
            print(" -", s)
            
        print("Odds Check (Race 1):")
        if races:
            for runner in races[0].get("runners", []):
                if runner.get("status") not in ["Standby", "Scratched", "Withdrawn"]:
                    print(f" #{runner.get('no')} {runner.get('name_en')}: Odds {runner.get('winOdds')}")

if __name__ == "__main__":
    analyze()

import sys
sys.path.append('.')
import os
import json
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from scraper import GRAPHQL_QUERY

url = "https://info.cld.hkjc.com/graphql/base/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/json"
}

def query_meeting(date_str):
    for venue in ["ST", "HV"]:
        variables = {"date": date_str, "venueCode": venue}
        try:
            res = requests.post(url, json={"query": GRAPHQL_QUERY, "variables": variables}, headers=headers, timeout=10, verify=False)
            if res.status_code == 200:
                data = res.json()
                if "data" in data and "raceMeetings" in data["data"]:
                    meetings = data["data"]["raceMeetings"]
                    if meetings and meetings[0].get("races"):
                        return meetings[0]
        except Exception as e:
            print(f"Error querying {date_str} {venue}: {e}")
    return None

def populate_file(filename):
    filepath = os.path.join('data', filename)
    date_part = filename.replace("frozen_predictions_", "").replace(".json", "")
    date_str = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
    
    print(f"\nProcessing {filename} (Date: {date_str})...")
    
    # Query CLD HKJC for this date
    meeting = query_meeting(date_str)
    if not meeting:
        print(f"  Could not find results on CLD HKJC for {date_str}. Keeping existing.")
        return
        
    venue = "Sha Tin" if meeting.get("venueCode") == "ST" else "Happy Valley"
    going = meeting.get("going_en", "GOOD")
    print(f"  Found meeting at {venue}. Going: {going}")
    
    # Map results
    results_map = {} # (race_no, runner_no) -> final_position
    for race in meeting.get("races", []):
        race_no = race.get("no")
        for runner in race.get("runners", []):
            runner_no = runner.get("no")
            pos = runner.get("finalPosition")
            if pos is not None:
                try:
                    results_map[(race_no, int(runner_no))] = int(pos)
                except:
                    pass
                    
    with open(filepath, 'r', encoding='utf-8') as f:
        frozen_data = json.load(f)
        
    # Update frozen predictions unconditionally
    updated_count = 0
    missing_count = 0
    for r_key, runners in frozen_data.items():
        try:
            race_no = int(r_key.split("_R")[1])
        except Exception as e:
            print(f"  Error parsing race no from {r_key}: {e}")
            continue
            
        for r in runners:
            runner_no = int(r.get("no", 0))
            pos = results_map.get((race_no, runner_no))
            if pos is not None:
                r["final_position"] = pos
                updated_count += 1
            else:
                r["final_position"] = 0
                missing_count += 1
                
    # Save back
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(frozen_data, f, indent=4)
        
    print(f"  Successfully updated {updated_count} runners with final positions. {missing_count} runners set to 0.")

def main():
    files = [f for f in os.listdir('data') if f.startswith('frozen_predictions_') and f.endswith('.json')]
    for fn in sorted(files):
        populate_file(fn)
        
if __name__ == '__main__':
    main()

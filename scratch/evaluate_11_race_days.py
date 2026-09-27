import sys
sys.path.append('.')
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import json
import pandas as pd
import numpy as np
import os
from scraper import GRAPHQL_QUERY
from model import predict_probabilities, load_model

url = "https://info.cld.hkjc.com/graphql/base/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/json"
}

# Load model
load_model()

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
            pass
    return None

dates = ["2026-05-24", "2026-05-31", "2026-06-07", "2026-06-13", "2026-06-21", "2026-06-27", "2026-07-01", "2026-07-04", "2026-07-12"]

for date_str in dates:
    meeting = query_meeting(date_str)
    if not meeting:
        continue
        
    races = meeting.get("races", [])
    if len(races) != 11:
        continue
        
    # Check if we have frozen predictions or simulate them
    frozen_fn = f"frozen_predictions_{date_str.replace('-', '')}.json"
    frozen_path = os.path.join('data', frozen_fn)
    
    top5_hits = 0
    valid_races = 0
    
    # Load precomputed features if we need to simulate
    # But wait, let's see if we can load the frozen file
    has_frozen = os.path.exists(frozen_path)
    
    if has_frozen:
        with open(frozen_path, 'r', encoding='utf-8') as f:
            frozen_data = json.load(f)
            
        for r_key, runners in frozen_data.items():
            if not runners:
                continue
            df = pd.DataFrame(runners).sort_values(by='gs_score', ascending=False).reset_index(drop=True)
            if 1 in df['final_position'].values:
                valid_races += 1
                top5_pos = df.iloc[:5]['final_position'].tolist()
                if 1 in top5_pos:
                    top5_hits += 1
    else:
        # Simulate predictions using baseline odds and scraped features
        # Actually, let's see if we can just query the results and check if we have a matching frozen file.
        # If we don't have a frozen file, we might not be able to easily predict without precomputed features.
        pass
        
    if valid_races > 0:
        print(f"Date: {date_str} (Frozen File) - Valid Races: {valid_races} - Top 5 Hits: {top5_hits}/{valid_races} ({top5_hits/valid_races:.1%})")

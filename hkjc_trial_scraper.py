import os
import sys
import re
import urllib3
import requests
import pandas as pd
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Monkeypatch requests to bypass SSL certificate issues
_orig_get = requests.get
requests.get = lambda *args, **kwargs: _orig_get(*args, **{**kwargs, 'verify': False})

def parse_trial_string(trial_str):
    """
    Parses a single trial string like:
    "02/07: Group 1 1200 CONGHUA AWT 5/7(S Shafrizal) 24.5 22.3 23.5 (1.10.30)"
    Returns a dictionary of parsed features.
    """
    trial_str = str(trial_str).strip()
    if not trial_str or trial_str.lower() == 'nan':
        return None
        
    try:
        # Regex to parse components
        # Pattern handles: Date: Group X Distance Course Pos/Total(Jockey) [splits] (TotalTime)
        pattern = r"^(\d{2}/\d{2}):\s+Group\s+(\d+)\s+(\d+)\s+([A-Z\s]+)\s+(\d+)/(\d+)\(([^)]+)\)\s+(.*?)\s+\((.*?)\)$"
        match = re.match(pattern, trial_str)
        if not match:
            # Fallback pattern if splits are missing or structure is slightly different
            fallback_pattern = r"^(\d{2}/\d{2}):\s+Group\s+(\d+)\s+(\d+)\s+([A-Z\s]+)\s+(\d+)/(\d+)\(([^)]+)\)\s+\((.*?)\)$"
            match = re.match(fallback_pattern, trial_str)
            if not match:
                return None
            
            date, group, dist, track, pos, total, jockey, total_time = match.groups()
            splits_str = ""
        else:
            date, group, dist, track, pos, total, jockey, splits_str, total_time = match.groups()
            
        return {
            "date": date,
            "group": int(group),
            "distance": int(dist),
            "track": track.strip(),
            "position": int(pos),
            "total_runners": int(total),
            "jockey": jockey.strip().upper(),
            "splits": splits_str.strip(),
            "total_time": total_time.strip()
        }
    except Exception as e:
        return None

def scrape_trials_for_meeting(racedate="2026/07/15", venue="HV"):
    """
    Scrapes barrier trials from the trackwork tables of all races in a meeting.
    racedate: YYYY/MM/DD
    venue: HV or ST
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    all_trials = []
    
    # Clean venue code
    venue_code = "HV" if "VALLEY" in venue.upper() or venue.upper() == "HV" else "ST"
    
    print(f"Scraping barrier trials for meeting: {racedate} at {venue_code}...")
    
    # Query up to 12 races (standard meeting sizes)
    consecutive_failures = 0
    for race_no in range(1, 13):
        url = f"https://racing.hkjc.com/en-us/local/information/localtrackwork?racedate={racedate}&Racecourse={venue_code}&RaceNo={race_no}"
        try:
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code != 200:
                consecutive_failures += 1
                if consecutive_failures >= 2:
                    break
                continue
                
            dfs = pd.read_html(res.content)
            
            # Find the correct trackwork table (headers must include 'Barrier Trial')
            trackwork_df = None
            for df in dfs:
                if df.shape[1] >= 3 and any("Barrier Trial" in str(col) for col in df.columns):
                    trackwork_df = df
                    break
                    
            if trackwork_df is None:
                consecutive_failures += 1
                if consecutive_failures >= 2:
                    break
                continue
            
            consecutive_failures = 0
            print(f"Race {race_no}: Found trackwork table with {len(trackwork_df)} runners.")
            
            # Find the correct column names
            name_col = None
            trial_col = None
            for col in trackwork_df.columns:
                col_str = str(col)
                if "Name of Horse" in col_str:
                    name_col = col
                elif "Barrier Trial" in col_str:
                    trial_col = col
                    
            if name_col is None or trial_col is None:
                # Fallback to column indices
                name_col = trackwork_df.columns[1]
                trial_col = trackwork_df.columns[2]
                
            for idx, row in trackwork_df.iterrows():
                # Extract clean horse name
                raw_name = str(row[name_col])
                # Name cell contains Name, Trainer, and Last 6 Runs, let's extract the name line
                name_lines = [l.strip() for l in raw_name.split('\n') if l.strip()]
                if not name_lines:
                    continue
                horse_name = name_lines[0]
                # Strip training info or spaces
                horse_name = re.sub(r'\s{2,}.*$', '', horse_name).strip().upper()
                
                # Check barrier trials cell
                raw_trials = str(row[trial_col]).strip()
                if not raw_trials or raw_trials.lower() == 'nan':
                    continue
                    
                # Split multiple trials by double spaces
                trial_parts = [t.strip() for t in raw_trials.split('  ') if t.strip()]
                
                for t_str in trial_parts:
                    parsed = parse_trial_string(t_str)
                    if parsed:
                        parsed["horse_name"] = horse_name
                        parsed["race_no"] = race_no
                        all_trials.append(parsed)
                        
        except Exception as e:
            print(f"Failed to scrape Race {race_no}: {e}")
            
    # Compile into DataFrame
    if all_trials:
        df = pd.DataFrame(all_trials)
        os.makedirs("data", exist_ok=True)
        df.to_csv("data/latest_trial_stats.csv", index=False)
        print(f"Saved {len(df)} trials to data/latest_trial_stats.csv")
        return df
    else:
        print("No trials scraped.")
        return pd.DataFrame()

if __name__ == "__main__":
    df = scrape_trials_for_meeting("2026/07/15", "HV")
    if not df.empty:
        print(df.head(10).to_string())

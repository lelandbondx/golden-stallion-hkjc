import os
import json
import pandas as pd
import numpy as np
from datetime import datetime

def time_str_to_seconds(t_str):
    """
    Converts a time string like "1.10.95" or "0.58.24" or "47.45" to float seconds.
    """
    t_str = str(t_str).strip()
    if not t_str or t_str.lower() == 'nan':
        return None
    try:
        parts = t_str.split('.')
        if len(parts) == 3:
            # Format: M.S.F (e.g., 1.10.95)
            mins, secs, hundredths = parts
            return int(mins) * 60 + int(secs) + int(hundredths) / 100.0
        elif len(parts) == 2:
            # Format: S.F (e.g., 58.24 or 47.45)
            # Check if first part could be minutes (unlikely for < 1000m trials but good to check)
            secs, hundredths = parts
            val = float(secs) + float(hundredths) / 100.0
            return val
        else:
            return float(t_str)
    except Exception:
        return None

def process_trials(meeting_date_str="2026-07-15"):
    """
    Processes raw trial stats from data/latest_trial_stats.csv
    and engineers features for prediction.
    """
    trial_csv = "data/latest_trial_stats.csv"
    if not os.path.exists(trial_csv):
        print(f"Error: {trial_csv} does not exist.")
        return {}
        
    df = pd.read_csv(trial_csv)
    if df.empty:
        return {}
        
    meeting_date = datetime.strptime(meeting_date_str, "%Y-%m-%d") if isinstance(meeting_date_str, str) else meeting_date_str
    
    # Track standard times dictionary (approximate class-neutral baselines)
    STANDARD_TIMES = {
        ("SHA TIN AWT", 1200): 70.0,
        ("SHA TIN AWT", 1050): 61.5,
        ("SHA TIN TURF", 1000): 57.0,
        ("SHA TIN TURF", 1600): 95.0,
        ("CONGHUA TURF", 1000): 58.5,
        ("CONGHUA TURF", 1200): 72.0,
        ("CONGHUA TURF", 800): 47.0,
        ("CONGHUA AWT", 1200): 72.0,
    }
    
    # Group trials by horse
    horse_features = {}
    
    for horse_name, group in df.groupby("horse_name"):
        trials_list = []
        
        for _, row in group.iterrows():
            trial_date_str = str(row["date"])
            # Format is DD/MM, let's assume current year (2026)
            try:
                t_date = datetime.strptime(f"{trial_date_str}/2026", "%d/%m/%Y")
            except Exception:
                continue
                
            days_since = (meeting_date - t_date).days
            if days_since < 0 or days_since > 45:
                # Ignore trials too far in the past or future relative to meeting
                continue
                
            # Compute position ratio
            pos = float(row["position"])
            tot = float(row["total_runners"])
            pos_ratio = pos / tot if tot > 0 else 1.0
            
            # Compute speed diff
            track = str(row["track"]).upper().strip()
            dist = int(row["distance"])
            trial_sec = time_str_to_seconds(row["total_time"])
            
            speed_diff = 0.0
            std_time = STANDARD_TIMES.get((track, dist))
            if std_time and trial_sec:
                speed_diff = std_time - trial_sec
                
            jockey_name = str(row["jockey"]).strip().upper()
            top_jockeys = ['Z PURTON', 'H BOWMAN', 'J MOREIRA', 'C Y HO', 'K TEETAN', 'A ATZENI']
            is_elite_jockey_trial = any(tj in jockey_name for tj in top_jockeys)
            
            trials_list.append({
                "days_since": days_since,
                "pos_ratio": pos_ratio,
                "speed_diff": speed_diff,
                "jockey": jockey_name,
                "is_elite_jockey": is_elite_jockey_trial
            })
            
        if not trials_list:
            continue
            
        # Engineer horse-level trial aggregates
        # 1. Trial count in last 30 days
        trials_30d = [t for t in trials_list if t["days_since"] <= 30]
        trial_count_30d = len(trials_30d)
        
        # 2. Best position ratio in last 30 days
        best_pos_ratio = min([t["pos_ratio"] for t in trials_30d]) if trials_30d else 1.0
        
        # 3. Best speed diff in last 30 days
        best_speed_diff = max([t["speed_diff"] for t in trials_30d]) if trials_30d else 0.0
        
        # 4. Trial jockeys list
        trial_jockeys = [t["jockey"] for t in trials_30d]
        
        # 5. Elite trial flag: Top 30% position, positive speed diff, ridden by elite jockey
        high_quality_trial = any(t["pos_ratio"] <= 0.35 and t["is_elite_jockey"] for t in trials_30d)
        
        horse_features[horse_name.strip().upper()] = {
            "trial_count_30d": trial_count_30d,
            "best_trial_pos_ratio": float(best_pos_ratio),
            "best_trial_speed_diff": float(best_speed_diff),
            "trial_jockeys": trial_jockeys,
            "high_quality_trial": high_quality_trial
        }
        
    # Save to file
    with open("data/engineered_trial_features.json", "w", encoding="utf-8") as f:
        json.dump(horse_features, f, indent=4)
        
    print(f"Engineered trial features for {len(horse_features)} horses and saved to data/engineered_trial_features.json")
    return horse_features

if __name__ == "__main__":
    from datetime import datetime
    process_trials("2026-07-15")

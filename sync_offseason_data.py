import os
import sys
import pandas as pd
from datetime import datetime

from hkjc_trial_scraper import scrape_trials_for_meeting
from process_trials import process_trials
from hkjc_profile_scraper import update_latest_stats
from harvest_offseason_telemetry import run_offseason_harvest

def sync_all_offseason_telemetry(limit=50):
    """
    Executes a complete off-season telemetry sync:
    1. Scrapes off-season barrier trial records from HKJC.
    2. Runs trial feature engineering (speed diffs, trial position ratios, elite jockey commitments).
    3. Updates latest horse profiles and vet records.
    4. Gathers 30-day trackwork gallops, swim conditioning, Conghua movements, and weight updates.
    """
    print("=== GOLDEN STALLION AI — OFF-SEASON TELEMETRY SYNC ===")
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # 1. Scrape barrier trials
    print("\n[Step 1/4] Fetching Barrier Trial Telemetry from HKJC...")
    df_trials = pd.DataFrame()
    try:
        df_trials = scrape_trials_for_meeting("2026/07/15", "HV")
        print(f"Scraped {len(df_trials)} total trial records.")
    except Exception as e:
        print(f"Warning: Trial scrape notice: {e}")
        
    # 2. Process trial features
    print("\n[Step 2/4] Processing Trial Features & Opponent Quality...")
    try:
        trial_features = process_trials(today_str)
        print(f"Processed trial features for {len(trial_features)} horses.")
    except Exception as e:
        print(f"Warning: Trial feature processing notice: {e}")
        
    # 3. Update horse stats & vet history
    print("\n[Step 3/4] Updating Horse Profile Stats & Vet Records...")
    try:
        update_latest_stats()
        print("Horse stats and vet records successfully synchronized.")
    except Exception as e:
        print(f"Warning: Horse stats update notice: {e}")

    # 4. Harvest active trackwork & conditioning telemetry
    print("\n[Step 4/4] Harvesting Active Trackwork, Swims, Movements & Weights...")
    try:
        run_offseason_harvest(limit=limit)
        print("Off-season trackwork and conditioning telemetry successfully synchronized.")
    except Exception as e:
        print(f"Warning: Off-season harvest notice: {e}")
        
    print("\n=== TELEMETRY SYNC COMPLETE ===")

if __name__ == '__main__':
    limit_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    sync_all_offseason_telemetry(limit=limit_arg)

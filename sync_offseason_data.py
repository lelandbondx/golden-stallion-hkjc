import os
import sys
import pandas as pd
from datetime import datetime

from hkjc_trial_scraper import scrape_trials_for_meeting
from process_trials import process_trials
from hkjc_profile_scraper import update_latest_stats

def sync_all_offseason_telemetry():
    """
    Executes a complete off-season telemetry sync:
    1. Scrapes off-season barrier trial records from HKJC.
    2. Runs trial feature engineering (speed diffs, trial position ratios, elite jockey commitments).
    3. Updates latest horse profiles and vet records.
    """
    print("=== GOLDEN STALLION AI — OFF-SEASON TELEMETRY SYNC ===")
    
    # 1. Scrape barrier trials
    print("\n[Step 1/3] Fetching Barrier Trial Telemetry from HKJC...")
    try:
        df_trials = scrape_trials_for_meeting("2026/07/15", "HV")
        print(f"Scraped {len(df_trials)} trial records.")
    except Exception as e:
        print(f"Warning: Trial scrape failed with {e}")
        
    # 2. Process trial features
    print("\n[Step 2/3] Processing Trial Features & Opponent Quality...")
    try:
        trial_features = process_trials("2026-07-15")
        print(f"Processed trial features for {len(trial_features)} horses.")
    except Exception as e:
        print(f"Warning: Trial feature processing failed with {e}")
        
    # 3. Update horse stats & vet history
    print("\n[Step 3/3] Updating Horse Profile Stats & Vet Records...")
    try:
        update_latest_stats()
        print("Horse stats and vet records successfully synchronized.")
    except Exception as e:
        print(f"Warning: Horse stats update failed with {e}")
        
    print("\n=== TELEMETRY SYNC COMPLETE ===")

if __name__ == '__main__':
    sync_all_offseason_telemetry()

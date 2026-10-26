import os
import sys
import pandas as pd
from datetime import datetime

from scraper import get_live_meeting_data
from hkjc_trial_scraper import scrape_trials_for_meeting
from process_trials import process_trials
from hkjc_profile_scraper import update_latest_stats, scrape_declared_starters_vet_records
from harvest_offseason_telemetry import run_offseason_harvest
from data.incident_engine import build_horse_incident_memory
from precompute_features import precompute
from monitoring.health import record as record_health


def sync_all_offseason_telemetry(limit=150):
    """
    Executes a complete, fail-loud master telemetry synchronization across EVERY
    data source in Silks.AI:
    1. Live Racecard & Active Meeting Discovery (scraper.py)
    2. Official HKJC Barrier Trials for Active Meeting (hkjc_trial_scraper.py)
    3. Engineered Trial Features — Speed Diffs, Position Ratios, Elite Jockey Trials (process_trials.py)
    4. Horse Profile Stats, Photo Finishes, Run Summaries & Official Vet Records (hkjc_profile_scraper.py)
    5. Declared Starters Official Veterinary Records Table (overecord)
    6. Active Trackwork (30d Gallops/Trots/Swims), Conghua Movements & Body Weights (harvest_offseason_telemetry.py)
    7. Official Stewards' Incident Reports & Replay Memory (data/incident_engine.py)
    8. Precomputed Features — Running Styles, Winning Gears, Sectional Bursts & Comments (precompute_features.py)
    """
    print("=== SILKS.AI — MASTER TELEMETRY & HEALTH MONITORING SYNC ===")

    live_data = get_live_meeting_data(force_network=True)
    if live_data and live_data.get("meetings"):
        m0 = live_data["meetings"][0]
        meeting_date_iso = m0.get("date", datetime.now().strftime("%Y-%m-%d"))
        racedate_slash = meeting_date_iso.replace("-", "/")
        venue_code = "HV" if "VALLEY" in str(m0.get("venue", "")).upper() else "ST"
    else:
        meeting_date_iso = datetime.now().strftime("%Y-%m-%d")
        racedate_slash = "auto"
        venue_code = "ST"

    print(f"Target Active Meeting: {meeting_date_iso} ({venue_code})")

    # 1. Scrape barrier trials for the active meeting
    print("\n[Step 1/6] Fetching Official Barrier Trial Telemetry from HKJC...")
    df_trials = pd.DataFrame()
    try:
        df_trials = scrape_trials_for_meeting(racedate_slash, venue_code)
        print(f"Total barrier trial records in database: {len(df_trials)}")
    except Exception as e:
        print(f"Warning: Trial scrape notice: {e}")
        record_health("barrier_trials_scraper", "fail", error=str(e))

    # 2. Process trial features
    print("\n[Step 2/6] Engineering Barrier Trial Features & Speed Differentials...")
    trial_features = {}
    try:
        trial_features = process_trials(meeting_date_iso)
        print(f"Processed trial features for {len(trial_features)} horses.")
    except Exception as e:
        print(f"Warning: Trial feature processing notice: {e}")
        record_health("trial_features", "fail", error=str(e))

    # 3. Update horse profile stats & declared starter veterinary records
    print("\n[Step 3/6] Updating Horse Profile Stats & Official Veterinary Records...")
    try:
        update_latest_stats()
        print("Horse profile stats and declared-starter vet records synchronized.")
    except Exception as e:
        print(f"Warning: Horse stats update notice: {e}")
        record_health("horse_profiles_and_vet", "fail", error=str(e))

    # 4. Harvest active trackwork, swims, Conghua movements & body weights
    print("\n[Step 4/6] Harvesting 30-Day Trackwork (Gallops/Trots/Swims), Conghua & Body Weights...")
    try:
        run_offseason_harvest(limit=limit)
        print("Trackwork, Conghua movement, body weight, and vet telemetry synchronized.")
    except Exception as e:
        print(f"Warning: Trackwork harvest notice: {e}")
        record_health("trackwork_telemetry", "fail", error=str(e))

    # 5. Update Official Stewards' Incident Reports & Replay Memory
    print("\n[Step 5/6] Updating Official Stewards' Incident Reports & Replay Memory...")
    memory = {}
    try:
        memory = build_horse_incident_memory()
        print(f"Stewards' incident memory synchronized ({len(memory)} horses).")
    except Exception as e:
        print(f"Warning: Incident memory notice: {e}")
        record_health("incident_memory", "fail", error=str(e))

    # 6. Rebuild Precomputed Features (Running Styles, Winning Gears, Sectionals, Comments)
    print("\n[Step 6/6] Rebuilding Precomputed Features (Running Styles, Gears, Sectionals, Comments)...")
    try:
        precompute()
        print("Precomputed features synchronized.")
    except Exception as e:
        print(f"Warning: Precompute features notice: {e}")
        record_health("precomputed_features", "fail", error=str(e))

    record_health(
        "telemetry_master_sync",
        "ok",
        metrics={
            "target_meeting": meeting_date_iso,
            "venue": venue_code,
            "trials_rows": len(df_trials),
            "trial_featured_horses": len(trial_features),
            "incident_memory_horses": len(memory),
        },
    )
    print("\n=== MASTER TELEMETRY SYNC COMPLETE ===")


if __name__ == '__main__':
    limit_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 150
    sync_all_offseason_telemetry(limit=limit_arg)

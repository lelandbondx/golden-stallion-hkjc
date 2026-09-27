import sys
import os
import pandas as pd
import numpy as np

# Ensure root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper import get_live_meeting_data, get_live_tips_index
from model import load_model, predict_probabilities
import odds_tracker

def run_diagnostics():
    print("==================================================")
    print("🛡️  GOLDEN STALLION AI - RUNNING PRE-RACE DIAGNOSTICS")
    print("==================================================")
    
    # 1. Check Data Files
    print("\n[1] Checking core database files...")
    data_files = [
        'data/results.csv',
        'data/latest_horse_stats.csv',
        'data/jockey_win_rates.csv',
        'data/trainer_win_rates.csv',
        'data/gear_win_rates.csv',
        'data/course_standard_times.csv'
    ]
    for file in data_files:
        if os.path.exists(file):
            size = os.path.getsize(file)
            print(f"  ✅ {file} exists ({size} bytes)")
        else:
            print(f"  ❌ WARNING: {file} is missing!")

    # 2. Check Model Load
    print("\n[2] Checking machine learning model...")
    try:
        model = load_model()
        if model:
            print("  ✅ model.joblib loaded successfully.")
            print(f"  Model type: {type(model)}")
        else:
            print("  ❌ ERROR: Model failed to load (returned None).")
    except Exception as e:
        print(f"  ❌ ERROR: Exception loading model: {e}")

    # 3. Check Live HKJC API Connection
    print("\n[3] Testing live HKJC GraphQL scraper...")
    try:
        meeting_data = get_live_meeting_data()
        if meeting_data and meeting_data.get('status') == 'success' and meeting_data.get('meetings'):
            meeting = meeting_data['meetings'][0]
            print(f"  ✅ Live HKJC API connection successful.")
            print(f"  Meeting Date: {meeting.get('date')}")
            print(f"  Venue: {meeting.get('venue')}")
            print(f"  Going: {meeting.get('going')}")
            print(f"  Number of Races Scraped: {len(meeting.get('races', []))}")
        else:
            print("  ❌ ERROR: GraphQL scraper returned invalid data format or no active meetings.")
    except Exception as e:
        print(f"  ❌ ERROR: Exception testing GraphQL scraper: {e}")

    # 4. Check Tips Index Scraper
    print("\n[4] Testing HKJC Tips Index scraper...")
    try:
        tips = get_live_tips_index()
        if tips:
            print(f"  ✅ Tips Index scraped successfully for {len(tips)} races.")
            first_race = list(tips.keys())[0] if tips else None
            if first_race:
                print(f"  Sample tip data (Race {first_race}): {tips[first_race]}")
        else:
            print("  ⚠️  WARNING: Tips Index returned empty dict (normal if no tip data is posted yet).")
    except Exception as e:
        print(f"  ❌ ERROR: Exception testing Tips Index scraper: {e}")

    # 5. Test Prediction Flow
    print("\n[5] Testing prediction generation flow...")
    try:
        if 'meeting_data' in locals() and meeting_data.get('meetings'):
            meeting = meeting_data['meetings'][0]
            races = meeting.get('races', [])
            if races:
                test_race = races[0]
                runners = test_race.get('runners', [])
                if runners:
                    df_runners = pd.DataFrame(runners)
                    # Prepare mock win_odds
                    if 'win_odds' not in df_runners.columns:
                        df_runners['win_odds'] = 20.0
                    df_runners['scraped_win_odds'] = df_runners['win_odds'].copy()
                    df_runners['consensus_score'] = 0.0
                    
                    # Test predictions
                    class_str = test_race.get("class_dist", "")
                    class_int = 4
                    if "Class 1" in class_str: class_int = 1
                    elif "Class 2" in class_str: class_int = 2
                    elif "Class 3" in class_str: class_int = 3
                    elif "Class 4" in class_str: class_int = 4
                    elif "Class 5" in class_str: class_int = 5
                    
                    race_going = test_race.get('going', meeting.get('going', 'GOOD'))
                    
                    probs, df_out = predict_probabilities(
                        df_runners, 
                        venue=meeting.get('venue'), 
                        going=race_going, 
                        race_date=meeting.get('date'), 
                        race_class_int=class_int
                    )
                    print(f"  ✅ Prediction pipeline executed successfully without crash.")
                    print(f"  Scored {len(probs)} runners. Sum of probabilities: {probs.sum():.4f}")
                else:
                    print("  ❌ ERROR: No runners found in the test race.")
            else:
                print("  ❌ ERROR: No races found in the scraped meeting.")
        else:
            print("  ❌ ERROR: Cannot test prediction flow due to earlier scraper error.")
    except Exception as e:
        print(f"  ❌ ERROR: Exception testing prediction flow: {e}")
        import traceback
        traceback.print_exc()

    print("\n==================================================")
    print("🛡️  DIAGNOSTICS COMPLETE")
    print("==================================================")

if __name__ == '__main__':
    run_diagnostics()

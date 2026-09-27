import os
import sys
import pandas as pd
import numpy as np
import traceback

sys.path.append(os.getcwd())

from model import predict_probabilities, load_model
import scraper
import odds_tracker

def test_predictions():
    print("=================== PREDICTIONS DIAGNOSTIC ===================")
    
    # 1. Test Model Loading
    print("\n[1] Testing load_model()...")
    try:
        model = load_model()
        if model is not None:
            print("Model loaded successfully!")
        else:
            print("Warning: load_model() returned None.")
    except Exception as e:
        print("Error loading model:")
        traceback.print_exc()
        return

    # 2. Setup dummy/sample race data to test pipeline
    print("\n[2] Testing prediction processing pipeline with mock data...")
    try:
        mock_runners = [
            {"no": 1, "name": "KASA PAPA", "jockey": "Z Purton", "trainer": "A S Cruz", "draw": 4, "actual_weight": 135, "declared_weight": 1100, "rtg": 60, "win_odds": 2.5},
            {"no": 2, "name": "ON THE LASH", "jockey": "H Bowman", "trainer": "P C Ng", "draw": 7, "actual_weight": 133, "declared_weight": 1050, "rtg": 58, "win_odds": 5.0},
            {"no": 3, "name": "CONSPIRACY", "jockey": "K Teetan", "trainer": "D A Hayes", "draw": 2, "actual_weight": 132, "declared_weight": 1120, "rtg": 57, "win_odds": 8.0},
            {"no": 4, "name": "SPEEDY DRAGON", "jockey": "C L Chau", "trainer": "J Size", "draw": 3, "actual_weight": 131, "declared_weight": 1080, "rtg": 56, "win_odds": 12.0},
            {"no": 5, "name": "PERFECT PAIRING", "jockey": "A Atzeni", "trainer": "P F Yiu", "draw": 11, "actual_weight": 131, "declared_weight": 1150, "rtg": 56, "win_odds": 15.0},
        ]
        df_runners = pd.DataFrame(mock_runners)
        df_runners['scraped_win_odds'] = df_runners['win_odds'].copy()
        df_runners['consensus_score'] = 0
        
        # Call predict_probabilities
        probs, df_runners = predict_probabilities(
            df_runners, 
            venue="Sha Tin", 
            going="GOOD TO FIRM", 
            race_date="2026-05-31", 
            race_class_int=4
        )
        
        # Verify predictions output
        print(f"Probabilities length: {len(probs)}")
        df_runners['model_prob'] = probs
        
        # Apply standout boost logic from app.py
        recent_pos = pd.to_numeric(df_runners.get('recent_avg_pos', 7.0), errors='coerce').fillna(7.0)
        track_match = (df_runners.get('ST_vs_HV_pref', 'Neutral') == "Sha Tin").astype(int)
        going_match = (df_runners.get('last_form_going', 'Unknown') == "GOOD TO FIRM").astype(int)
        vet_issue = pd.to_numeric(df_runners.get('prev_run_vet_finding', 0), errors='coerce').fillna(0)
        class_drop = pd.to_numeric(df_runners.get('class_diff', 0), errors='coerce').fillna(0)
        
        is_super_standout = (recent_pos <= 3.5) & ((track_match == 1) | (going_match == 1)) & (vet_issue == 0)
        is_class_dropper_standout = (class_drop > 0) & (recent_pos <= 5.0) & (vet_issue == 0)
        
        standout_boost = np.where(is_super_standout, 0.08, 0.0)
        standout_boost += np.where(is_class_dropper_standout, 0.05, 0.0)
        
        recent_win = pd.to_numeric(df_runners.get('recent_win_rate', 0.0), errors='coerce').fillna(0.0)
        is_debutant = (recent_pos == 7.0) & (recent_win == 0.0)
        debutant_penalty = np.where(is_debutant, -0.05, 0.0)
        
        df_runners['implied_raw'] = 1 / df_runners['win_odds'].replace(0, 1.0)
        sum_implied = df_runners['implied_raw'].sum()
        df_runners['implied_prob'] = df_runners['implied_raw'] / sum_implied if sum_implied > 0 else (1/len(df_runners))
        
        false_fav_penalty = np.where((df_runners['implied_prob'] > 0.20) & (recent_pos > 6.0), -0.15, 0.0)
        
        consensus = pd.to_numeric(df_runners.get('consensus_score', 0), errors='coerce').fillna(0)
        consensus_boost = np.where(consensus > 0, 0.01 * np.minimum(consensus, 2), 0.0)
        
        multiplier = 1.0 + standout_boost + consensus_boost + false_fav_penalty + debutant_penalty
        multiplier = np.maximum(multiplier, 0.1)
        
        df_runners['model_prob'] = df_runners['model_prob'] * multiplier
        df_runners['model_prob'] /= df_runners['model_prob'].sum()
        
        # Kelly stake
        b = df_runners['win_odds'] - 1
        p = df_runners['model_prob']
        q = 1.0 - p
        f = np.where(b > 0, (b * p - q) / b, 0)
        df_runners['kelly_stake'] = np.clip(f * 0.25, 0, 1)
        
        df_runners['value_diff'] = df_runners['model_prob'] - df_runners['implied_prob']
        
        # Odds tracker / baseline odds
        df_runners['baseline_odds'] = df_runners.apply(lambda row: odds_tracker.get_baseline_odds(
            "2026-05-31", "Sha Tin", 1, row['no'], row['scraped_win_odds']), axis=1)

        df_runners['shift_bonus'] = df_runners.apply(lambda row: odds_tracker.calculate_odds_shift_bonus(
            row['baseline_odds'], row['scraped_win_odds'], pd.to_numeric(row.get('recent_avg_pos', 7.0)), 
            pd.to_numeric(row.get('prev_run_vet_finding', 0))), axis=1)
        
        # GS score
        df_runners['gs_score'] = (df_runners['model_prob'] * 100) + np.where(df_runners['value_diff'] > 0, df_runners['value_diff'] * 20, 0) + df_runners['shift_bonus']
        
        # AI confidence
        p_min = df_runners['model_prob'].min()
        p_max = df_runners['model_prob'].max()
        if p_max > p_min:
            df_runners['confidence'] = (15.0 + ((df_runners['model_prob'] - p_min) / (p_max - p_min)) * 70).round(0).astype(int)
        else:
            df_runners['confidence'] = 50
            
        print("Mock race prediction test succeeded!")
        print(df_runners[['no', 'name', 'model_prob', 'implied_prob', 'kelly_stake', 'gs_score', 'confidence']])
    except Exception as e:
        print("Error during mock prediction test:")
        traceback.print_exc()

    # 3. Test prediction with live data
    print("\n[3] Testing pipeline with actual live scraped data...")
    try:
        data = scraper.get_live_meeting_data()
        meetings = data.get("meetings", [])
        if not meetings:
            print("No live meetings found. Skipping live predictions test.")
        else:
            m = meetings[0]
            print(f"Testing live predictions for meeting: {m.get('date')} - {m.get('venue')}")
            races = m.get('races', [])
            if not races:
                print("No races found in live meeting.")
            else:
                race = races[0]
                df_runners = pd.DataFrame(race['runners'])
                df_runners['scraped_win_odds'] = df_runners['win_odds'].copy()
                df_runners['consensus_score'] = 0
                
                class_str = race.get("class_dist", "")
                class_int = 4
                if "Class 1" in class_str: class_int = 1
                elif "Class 2" in class_str: class_int = 2
                elif "Class 3" in class_str: class_int = 3
                elif "Class 4" in class_str: class_int = 4
                elif "Class 5" in class_str: class_int = 5
                elif "Group" in class_str or "G" in class_str: class_int = 0
                
                probs, df_runners = predict_probabilities(
                    df_runners, 
                    venue=m.get('venue'), 
                    going=m.get('going'), 
                    race_date=m.get('date'), 
                    race_class_int=class_int
                )
                print(f"Live race prediction test succeeded! Number of predictions: {len(probs)}")
    except Exception as e:
        print("Error during live prediction test:")
        traceback.print_exc()

    print("\n==============================================================")

if __name__ == "__main__":
    test_predictions()

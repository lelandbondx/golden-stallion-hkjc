import os
import pandas as pd
import numpy as np
import json
import odds_tracker
from scraper import get_live_meeting_data, get_live_tips_index
from model import predict_probabilities, load_model

def run_diagnostic():
    print("=== STARTING GOLDEN STALLION AI DIAGNOSTIC ===")
    
    # 1. Scrape Live Data
    data = get_live_meeting_data()
    tips_data = get_live_tips_index()
    
    if data.get('status') != 'success' or not data.get('meetings'):
        print("[ERROR] Scraper failed to fetch live data.")
        return
        
    meeting = data['meetings'][0]
    print(f"Meeting Date: {meeting.get('date')}")
    print(f"Venue: {meeting.get('venue')}")
    print(f"Going: {meeting.get('going')}")
    print(f"Number of Races: {len(meeting.get('races', []))}")
    
    # 2. Check Model Path
    model = load_model()
    if model is None:
        print("[ERROR] Model file model.joblib could not be loaded.")
        return
    print("[OK] XGBoost model loaded successfully.")
    
    # 3. Check CSV integrity
    if not os.path.exists('data/latest_horse_stats.csv'):
        print("[ERROR] latest_horse_stats.csv does not exist.")
        return
    stats_df = pd.read_csv('data/latest_horse_stats.csv')
    print(f"[OK] latest_horse_stats.csv found with {len(stats_df)} records.")
    
    # Check for NaN values in key stats
    for col in ['HV_win_rate', 'recent_avg_pos', 'prev_run_vet_finding']:
        nans = stats_df[col].isna().sum()
        if nans > 0:
            print(f"[WARNING] Column {col} has {nans} missing values in latest_horse_stats.csv.")
        else:
            print(f"[OK] Column {col} has 0 missing values.")
            
    # Check value count of vet findings
    vet_count = stats_df['prev_run_vet_finding'].value_counts()
    print(f"[INFO] Vet finding distribution in CSV: {dict(vet_count)}")
    
    # 4. Perform Race-by-Race Analysis
    issues = 0
    total_runners_checked = 0
    race_summaries = []
    
    for race in meeting.get('races', []):
        race_no = int(race.get('race_no'))
        class_str = race.get("class_dist", "")
        runners = race.get('runners', [])
        
        if not runners:
            print(f"[WARNING] Race {race_no} has no active runners.")
            issues += 1
            continue
            
        df_runners = pd.DataFrame(runners)
        total_runners_checked += len(df_runners)
        
        # Format odds
        if 'win_odds' in df_runners.columns:
            df_runners['scraped_win_odds'] = df_runners['win_odds'].copy()
        else:
            df_runners['scraped_win_odds'] = 0.0
            
        # Parse class
        class_int = 4
        if "Class 1" in class_str: class_int = 1
        elif "Class 2" in class_str: class_int = 2
        elif "Class 3" in class_str: class_int = 3
        elif "Class 4" in class_str: class_int = 4
        elif "Class 5" in class_str: class_int = 5
        elif "Group" in class_str or "G" in class_str: class_int = 0
        
        # Predict Win Probabilities
        probs, df_feats = predict_probabilities(df_runners, venue=meeting.get('venue'), going=meeting.get('going'), race_date=meeting.get('date'), race_class_int=class_int, track_type=race.get('track', 'TURF'))
        
        # Check for NaNs in predicted probabilities
        if np.isnan(probs).any():
            print(f"[ERROR] Race {race_no} predictions contain NaN values.")
            issues += 1
            
        # Verify feature columns are present and clean
        for col in ['recent_avg_pos', 'prev_run_vet_finding', 'jockey_win_rate', 'trainer_win_rate', 'norm_implied_prob']:
            if col not in df_feats.columns:
                print(f"[ERROR] Feature column {col} missing in prepared dataframe for Race {race_no}.")
                issues += 1
            elif df_feats[col].isna().any():
                print(f"[ERROR] Feature column {col} has NaN values in prepared dataframe for Race {race_no}.")
                issues += 1
                
        # Simulate stands and penalties
        df_runners['model_prob'] = probs
        df_runners['implied_raw'] = 1 / df_runners['win_odds'].replace(0, 1.0)
        sum_implied = df_runners['implied_raw'].sum()
        df_runners['implied_prob'] = df_runners['implied_raw'] / sum_implied if sum_implied > 0 else (1/len(df_runners))
        
        recent_pos = pd.to_numeric(df_feats['recent_avg_pos']).fillna(7.0)
        recent_win = pd.to_numeric(df_feats['recent_win_rate']).fillna(0.0)
        track_match = (df_feats['ST_vs_HV_pref'] == meeting.get('venue')).astype(int)
        going_match = (df_feats['last_form_going'] == meeting.get('going', 'UNKNOWN')).astype(int)
        vet_issue = pd.to_numeric(df_feats['prev_run_vet_finding']).fillna(0)
        class_drop = pd.to_numeric(df_feats['class_diff']).fillna(0)
        
        is_super_standout = (recent_pos <= 3.5) & ((track_match == 1) | (going_match == 1)) & (vet_issue == 0)
        is_class_dropper_standout = (class_drop > 0) & (recent_pos <= 5.0) & (vet_issue == 0)
        is_debutant = (recent_pos == 7.0) & (recent_win == 0.0)
        false_fav_penalty = np.where((df_runners['implied_prob'] > 0.20) & (recent_pos > 6.0), -0.15, 0.0)
        
        standout_boost = np.where(is_super_standout, 0.08, 0.0)
        standout_boost += np.where(is_class_dropper_standout, 0.05, 0.0)
        debutant_penalty = np.where(is_debutant, -0.05, 0.0)
        
        consensus_score = df_runners['no'].map(lambda x: tips_data.get(race_no, {}).get(x, 0))
        consensus_boost = np.where(consensus_score > 0, 0.01 * np.minimum(consensus_score, 2), 0.0)
        
        multiplier = 1.0 + standout_boost + consensus_boost + false_fav_penalty + debutant_penalty
        multiplier = np.maximum(multiplier, 0.1)
        df_runners['model_prob'] = df_runners['model_prob'] * multiplier
        
        # Re-normalize
        total_b = df_runners['model_prob'].sum()
        if total_b > 0:
            df_runners['model_prob'] = df_runners['model_prob'] / total_b
            
        df_runners['value_diff'] = df_runners['model_prob'] - df_runners['implied_prob']
        
        df_runners['baseline_odds'] = df_runners.apply(lambda row: odds_tracker.get_baseline_odds(
            meeting.get('date', 'today'), meeting.get('venue', 'HK'), race_no, row['no'], row['scraped_win_odds']), axis=1)

        df_runners['shift_bonus'] = df_runners.apply(lambda row: odds_tracker.calculate_odds_shift_bonus(
            row['baseline_odds'], row['scraped_win_odds'], pd.to_numeric(row.get('recent_avg_pos', 7.0)), 
            pd.to_numeric(row.get('prev_run_vet_finding', 0))), axis=1)

        df_runners['gs_score'] = (df_runners['model_prob'] * 100) + np.where(df_runners['value_diff'] > 0, df_runners['value_diff'] * 20, 0) + df_runners['shift_bonus']
        
        p_min = df_runners['model_prob'].min()
        p_max = df_runners['model_prob'].max()
        if p_max > p_min:
            df_runners['confidence'] = (15.0 + ((df_runners['model_prob'] - p_min) / (p_max - p_min)) * 70).round(0).astype(int)
        else:
            df_runners['confidence'] = 50
            
        race_picks = df_runners.sort_values(by='gs_score', ascending=False)
        top_pick = race_picks.iloc[0]
        
        # Log race summary details with clean python types
        race_summaries.append({
            "race_no": int(race_no),
            "class_dist": str(class_str),
            "runners_count": int(len(df_runners)),
            "top_no": int(top_pick['no']),
            "top_name": str(top_pick['name']),
            "top_jockey": str(top_pick['jockey']),
            "top_trainer": str(top_pick['trainer']),
            "top_draw": int(top_pick['draw']),
            "top_confidence": int(top_pick['confidence']),
            "top_recent_pos": float(df_feats.loc[df_feats['clean_name'] == top_pick['name'].upper().strip(), 'recent_avg_pos'].values[0]),
            "top_vet_issue": int(df_feats.loc[df_feats['clean_name'] == top_pick['name'].upper().strip(), 'prev_run_vet_finding'].values[0]),
            "top_track_pref": str(df_feats.loc[df_feats['clean_name'] == top_pick['name'].upper().strip(), 'ST_vs_HV_pref'].values[0])
        })
        
    print(f"Checked {total_runners_checked} runners across {len(meeting.get('races', []))} races.")
    print(f"Total issues found: {issues}")
    
    if issues == 0:
        print("[OK] DIAGNOSTIC PASSED: 100% Data Integrity Verified.")
    else:
        print("[ERROR] DIAGNOSTIC FAILED with issues.")
        
    # Write summary report to JSON
    with open('scratch/diagnostic_report.json', 'w') as f:
        json.dump({
            "status": "success" if issues == 0 else "failed",
            "date": meeting.get('date'),
            "venue": meeting.get('venue'),
            "going": meeting.get('going'),
            "runners_checked": total_runners_checked,
            "races": race_summaries
        }, f, indent=4)
        
    print("=== DIAGNOSTIC REPORT WRITTEN TO scratch/diagnostic_report.json ===")

if __name__ == '__main__':
    run_diagnostic()

import os
import pandas as pd
import numpy as np
import json
import odds_tracker

from scraper import get_live_meeting_data, get_live_tips_index
from model import predict_probabilities, load_model

def run():
    data = get_live_meeting_data()
    tips_data = get_live_tips_index()
    
    try:
        with open('data/gemini_intel.json', 'r') as f:
            intel_data = json.load(f)
            key_runners = [runner['horse_name'].upper() for runner in intel_data.get('key_runners', [])]
    except Exception:
        key_runners = []
    
    if data.get('status') != 'success' or not data.get('meetings'):
        print("Failed to get live meeting data.")
        return
        
    meeting = data['meetings'][0]
    load_model()
    
    global_best_bets = []
    
    for race in meeting.get('races', []):
        if not race.get('runners'): continue
        
        df_runners = pd.DataFrame(race['runners'])
        if 'win_odds' in df_runners.columns:
            df_runners['scraped_win_odds'] = df_runners['win_odds'].copy()
        else:
            df_runners['scraped_win_odds'] = 0.0
        
        current_race_tips = tips_data.get(race.get('race_no', 0), {})
        df_runners['consensus_score'] = df_runners['no'].map(lambda x: current_race_tips.get(x, 0))
        
        class_str = race.get("class_dist", "")
        class_int = 4
        if "Class 1" in class_str: class_int = 1
        elif "Class 2" in class_str: class_int = 2
        elif "Class 3" in class_str: class_int = 3
        elif "Class 4" in class_str: class_int = 4
        elif "Class 5" in class_str: class_int = 5
        elif "Group" in class_str or "G" in class_str: class_int = 0
            
        probs, df_runners = predict_probabilities(df_runners, venue=meeting.get('venue'), going=meeting.get('going'), race_date=meeting.get('date'), race_class_int=class_int)
        
        df_runners['model_prob'] = probs
        df_runners['implied_raw'] = 1 / df_runners['win_odds'].replace(0, 1.0)
        sum_implied = df_runners['implied_raw'].sum()
        df_runners['implied_prob'] = df_runners['implied_raw'] / sum_implied if sum_implied > 0 else (1/len(df_runners))
        
        if key_runners:
            df_runners['consensus_score'] += np.where(df_runners['name'].str.upper().isin(key_runners), 10, 0)

        recent_pos = pd.to_numeric(df_runners.get('recent_avg_pos', 7.0), errors='coerce').fillna(7.0)
        recent_win = pd.to_numeric(df_runners.get('recent_win_rate', 0.0), errors='coerce').fillna(0.0)
        track_match = (df_runners.get('ST_vs_HV_pref', 'Neutral') == meeting.get('venue')).astype(int)
        going_match = (df_runners.get('last_form_going', 'Unknown') == meeting.get('going', 'UNKNOWN')).astype(int)
        vet_issue = pd.to_numeric(df_runners.get('prev_run_vet_finding', 0), errors='coerce').fillna(0)
        class_drop = pd.to_numeric(df_runners.get('class_diff', 0), errors='coerce').fillna(0)
        
        # Super Standout condition: 
        is_super_standout = (recent_pos <= 3.5) & ((track_match == 1) | (going_match == 1)) & (vet_issue == 0)
        
        # Secondary edge: Class droppers who are in decent form (<= 5.0) and healthy
        is_class_dropper_standout = (class_drop > 0) & (recent_pos <= 5.0) & (vet_issue == 0)
        
        # Moderate debutant penalty
        is_debutant = (recent_pos == 7.0) & (recent_win == 0.0)

        # False Favorite Penalty: If a horse is favored (implied prob > 20%) but has terrible recent form (avg pos > 6)
        false_fav_penalty = np.where((df_runners['implied_prob'] > 0.20) & (recent_pos > 6.0), -0.15, 0.0)
        
        standout_boost = np.where(is_super_standout, 0.08, 0.0)
        standout_boost += np.where(is_class_dropper_standout, 0.05, 0.0)
        debutant_penalty = np.where(is_debutant, -0.05, 0.0)
        
        # Consensus intel boost (gentle tie breaker)
        consensus = pd.to_numeric(df_runners.get('consensus_score', 0), errors='coerce').fillna(0)
        consensus_boost = np.where(consensus > 0, 0.01 * np.minimum(consensus, 2), 0.0)
        
        multiplier = 1.0 + standout_boost + consensus_boost + false_fav_penalty + debutant_penalty
        multiplier = np.maximum(multiplier, 0.1)
        df_runners['model_prob'] = df_runners['model_prob'] * multiplier
            
        total_b = df_runners['model_prob'].sum()
        if total_b > 0:
            df_runners['model_prob'] = df_runners['model_prob'] / total_b
            
        df_runners['value_diff'] = df_runners['model_prob'] - df_runners['implied_prob']
        
        df_runners['baseline_odds'] = df_runners.apply(lambda row: odds_tracker.get_baseline_odds(
            meeting.get('date', 'today'), meeting.get('venue', 'HK'), race.get('race_no', 0), row['no'], row['scraped_win_odds']), axis=1)

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
        
        best = race_picks.iloc[0].to_dict()
        best.update({"race_no": race.get("race_no"), "class_dist": class_str})
        global_best_bets.append(best)

    global_best_bets = sorted(global_best_bets, key=lambda x: x.get('gs_score', 0), reverse=True)
    
    print("TOP 5 DETAILED PICKS:")
    for i in range(min(5, len(global_best_bets))):
        bb = global_best_bets[i]
        print(f"\n--- PICK {i+1} : Race {bb['race_no']} - {bb['name']} ---")
        for k in ['no', 'name', 'jockey', 'trainer', 'draw', 'actual_weight', 'horse_rating', 'win_odds', 'confidence', 'value_diff', 'jockey_win_rate', 'trainer_win_rate', 'recent_avg_pos', 'ST_vs_HV_pref', 'last_form_going', 'track_pref_match', 'going_pref_match']:
            if k in bb:
                print(f"{k}: {bb[k]}")

if __name__ == '__main__':
    run()

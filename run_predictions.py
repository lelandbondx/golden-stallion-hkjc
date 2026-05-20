import os
import pandas as pd
import numpy as np

from scraper import get_live_meeting_data, get_live_tips_index
from model import predict_probabilities, load_model

import json

def run():
    print("Loading data...")
    data = get_live_meeting_data()
    tips_data = get_live_tips_index()
    
    # Load private expert intel
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
    print(f"Meeting: {meeting['venue']} - {meeting['date']} - Going: {meeting['going']}")
    
    # Load model
    load_model()
    
    global_best_bets = []
    
    for race in meeting.get('races', []):
        if not race.get('runners'): continue
        
        df_runners = pd.DataFrame(race['runners'])
        current_race_tips = tips_data.get(race.get('race_no', 0), {})
        df_runners['consensus_score'] = df_runners['no'].map(lambda x: current_race_tips.get(x, 0))
        if key_runners:
            df_runners['consensus_score'] += np.where(df_runners['name'].str.upper().isin(key_runners), 10, 0)
        
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
        
        # Targeted Standout Boost: Only boost if there is a confluence of strong indicators
        recent_pos = pd.to_numeric(df_runners.get('recent_avg_pos', 7.0), errors='coerce').fillna(7.0)
        recent_win = pd.to_numeric(df_runners.get('recent_win_rate', 0.0), errors='coerce').fillna(0.0)
        track_match = pd.to_numeric(df_runners.get('track_pref_match', 0), errors='coerce').fillna(0)
        going_match = pd.to_numeric(df_runners.get('going_pref_match', 0), errors='coerce').fillna(0)
        vet_issue = pd.to_numeric(df_runners.get('prev_run_vet_finding', 0), errors='coerce').fillna(0)
        class_drop = pd.to_numeric(df_runners.get('class_diff', 0), errors='coerce').fillna(0)
        
        # Super Standout condition: 
        # Extremely good recent form (<= 3.5 avg pos) AND proven at this track/going AND healthy
        is_super_standout = (recent_pos <= 3.5) & ((track_match == 1) | (going_match == 1)) & (vet_issue == 0)
        
        # Secondary edge: Class droppers who are in decent form (<= 5.0) and healthy
        is_class_dropper_standout = (class_drop > 0) & (recent_pos <= 5.0) & (vet_issue == 0)
        
        # Moderate debutant penalty
        is_debutant = (recent_pos == 7.0) & (recent_win == 0.0)
        
        standout_boost = np.where(is_super_standout, 0.08, 0.0) # 8% boost for true standouts
        standout_boost += np.where(is_class_dropper_standout, 0.05, 0.0) # 5% boost for dangerous class droppers
        debutant_penalty = np.where(is_debutant, -0.05, 0.0) # 5% penalty for debutants
        
        # Consensus intel boost (gentle tie breaker)
        consensus = pd.to_numeric(df_runners.get('consensus_score', 0), errors='coerce').fillna(0)
        consensus_boost = np.where(consensus > 0, 0.01 * np.minimum(consensus, 2), 0.0)
        
        multiplier = 1.0 + standout_boost + consensus_boost + debutant_penalty
        # Ensure multiplier doesn't go below 0.1
        multiplier = np.maximum(multiplier, 0.1)
        df_runners['model_prob'] = df_runners['model_prob'] * multiplier
        
        total_b = df_runners['model_prob'].sum()
        if total_b > 0:
            df_runners['model_prob'] = df_runners['model_prob'] / total_b
            
        df_runners['value_diff'] = df_runners['model_prob'] - df_runners['implied_prob']
        df_runners['gs_score'] = (df_runners['model_prob'] * 100) + np.where(df_runners['value_diff'] > 0, df_runners['value_diff'] * 20, 0)
        
        p_min = df_runners['model_prob'].min()
        p_max = df_runners['model_prob'].max()
        if p_max > p_min:
            df_runners['confidence'] = (15.0 + ((df_runners['model_prob'] - p_min) / (p_max - p_min)) * 70).round(0).astype(int)
        else:
            df_runners['confidence'] = 50
            
        race_picks = df_runners.sort_values(by='gs_score', ascending=False)
        print(f"\n--- RACE {race.get('race_no')} : {class_str} ---")
        
        for i in range(min(5, len(race_picks))):
            pick = race_picks.iloc[i]
            print(f"{i+1}st Pick: #{pick['no']} {pick['name']} (Odds: {pick['win_odds']:.1f}) - Conf: {pick['confidence']}% - EV: {pick['value_diff']:.3f} - Jockey: {pick['jockey']}")
            
        best = race_picks.iloc[0].to_dict()
        best.update({"race_no": race.get("race_no"), "class_dist": class_str})
        global_best_bets.append(best)

    global_best_bets = sorted(global_best_bets, key=lambda x: x.get('gs_score', 0), reverse=True)
    
    print("\n\n--- OVERALL GLOBAL BEST BETS ---")
    for i in range(min(3, len(global_best_bets))):
        bb = global_best_bets[i]
        print(f"Top Pick {i+1}: Race {bb['race_no']} - #{bb['no']} {bb['name']} (Odds: {bb['win_odds']:.1f}, Conf: {bb['confidence']}%, EV: {bb['value_diff']:.3f})")

if __name__ == '__main__':
    run()

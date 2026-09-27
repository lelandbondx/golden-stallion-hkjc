import os
import json
import pandas as pd
import numpy as np
import sys

# Add root directory to python path
sys.path.append(os.getcwd())

from model import predict_probabilities, load_model
import odds_tracker

def simulate():
    print("Loading June 3rd meeting from cache...")
    with open('data/last_scraped_meeting.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    meeting = data['meetings'][0]
    print(f"Meeting Date: {meeting['date']}, Venue: {meeting['venue']}, Going: {meeting['going']}")
    
    # Load private expert intel (if any)
    try:
        with open('data/gemini_intel.json', 'r') as f:
            intel_data = json.load(f)
            key_runners = [runner['horse_name'].upper() for runner in intel_data.get('key_runners', [])]
    except Exception:
        key_runners = []
        
    # Get tips data (mocking or loading if possible)
    # Since tips index scrapes from the live HKJC site and the meeting is over,
    # let's see if there is any tips data. We will fetch if possible or default to 0
    from scraper import get_live_tips_index
    tips_data = get_live_tips_index()
    
    load_model()
    
    results = []
    
    for race in meeting.get('races', []):
        race_no = race.get('race_no')
        class_dist = race.get('class_dist')
        
        df_runners = pd.DataFrame(race['runners'])
        if 'win_odds' in df_runners.columns:
            df_runners['scraped_win_odds'] = df_runners['win_odds'].copy()
        else:
            df_runners['scraped_win_odds'] = 0.0
            
        current_race_tips = tips_data.get(race_no, {})
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
        
        # Predict base probabilities
        probs, df_runners = predict_probabilities(
            df_runners, 
            venue=meeting.get('venue'), 
            going=meeting.get('going'), 
            race_date=meeting.get('date'), 
            race_class_int=class_int
        )
        
        df_runners['model_prob'] = probs
        df_runners['implied_raw'] = 1 / df_runners['win_odds'].replace(0, 1.0)
        sum_implied = df_runners['implied_raw'].sum()
        df_runners['implied_prob'] = df_runners['implied_raw'] / sum_implied if sum_implied > 0 else (1/len(df_runners))
        
        # Targeted Standout Boost Logic
        recent_pos = pd.to_numeric(df_runners.get('recent_avg_pos', 7.0), errors='coerce').fillna(7.0)
        recent_win = pd.to_numeric(df_runners.get('recent_win_rate', 0.0), errors='coerce').fillna(0.0)
        track_match = (df_runners.get('ST_vs_HV_pref', 'Neutral') == meeting.get('venue')).astype(int)
        going_match = (df_runners.get('last_form_going', 'Unknown') == meeting.get('going', 'UNKNOWN')).astype(int)
        vet_issue = pd.to_numeric(df_runners.get('prev_run_vet_finding', 0), errors='coerce').fillna(0)
        class_drop = pd.to_numeric(df_runners.get('class_diff', 0), errors='coerce').fillna(0)
        
        is_super_standout = (recent_pos <= 3.5) & ((track_match == 1) | (going_match == 1)) & (vet_issue == 0)
        is_class_dropper_standout = (class_drop > 0) & (recent_pos <= 5.0) & (vet_issue == 0)
        is_debutant = (recent_pos == 7.0) & (recent_win == 0.0)
        false_fav_penalty = np.where((df_runners['implied_prob'] > 0.20) & (recent_pos > 6.0), -0.15, 0.0)
        
        standout_boost = np.where(is_super_standout, 0.08, 0.0)
        standout_boost += np.where(is_class_dropper_standout, 0.05, 0.0)
        debutant_penalty = np.where(is_debutant, -0.05, 0.0)
        
        consensus = pd.to_numeric(df_runners.get('consensus_score', 0), errors='coerce').fillna(0)
        consensus_boost = np.where(consensus > 0, 0.01 * np.minimum(consensus, 12), 0.0)
        
        multiplier = 1.0 + standout_boost + consensus_boost + false_fav_penalty + debutant_penalty
        multiplier = np.maximum(multiplier, 0.1)
        
        df_runners['model_prob'] = df_runners['model_prob'] * multiplier
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
            
        df_runners['is_super_standout'] = is_super_standout
        df_runners['is_class_dropper_standout'] = is_class_dropper_standout
        df_runners['false_fav_penalty'] = false_fav_penalty
        df_runners['is_debutant'] = is_debutant
        df_runners['standout_boost'] = standout_boost
        df_runners['consensus_boost'] = consensus_boost
        
        # Sort by gs_score descending
        race_picks = df_runners.sort_values(by='gs_score', ascending=False)
        
        print(f"\n==========================================")
        print(f"RACE {race_no} ({class_dist})")
        print(f"==========================================")
        for rank in range(min(5, len(race_picks))):
            runner = race_picks.iloc[rank]
            print(f"{rank+1}st Pick: #{runner['no']} {runner['name']}")
            print(f"   Win Odds: {runner['win_odds']} | Baseline Odds: {runner['baseline_odds']}")
            print(f"   GS Score: {runner['gs_score']:.1f} | Conf: {runner['confidence']}% | EV: {runner['value_diff']:.3f} | Shift Bonus: {runner['shift_bonus']:.1f}")
            print(f"   Model Prob: {runner['model_prob']:.3f} | Implied Prob: {runner['implied_prob']:.3f}")
            print(f"   Draw: {runner['draw']} | Jockey: {runner['jockey']} | Trainer: {runner['trainer']}")
            print(f"   Boosts: Super={runner['is_super_standout']}, ClassDrop={runner['is_class_dropper_standout']}, FalseFavPen={runner['false_fav_penalty']:.2f}, Debutant={runner['is_debutant']}")
            print(f"   Standout Boost: {runner['standout_boost']:.2f} | Consensus Boost: {runner['consensus_boost']:.2f}")
            
if __name__ == '__main__':
    simulate()

import os
import pandas as pd
import numpy as np
import json

from scraper import get_live_meeting_data, get_live_tips_index
from model import predict_probabilities, load_model

def run():
    data = get_live_meeting_data()
    tips_data = get_live_tips_index()
    
    if data.get('status') != 'success' or not data.get('meetings'):
        print("Failed to get live meeting data.")
        return
        
    meeting = data['meetings'][0]
    load_model()
    
    global_best_bets = []
    
    for race in meeting.get('races', []):
        if not race.get('runners'): continue
        
        df_runners = pd.DataFrame(race['runners'])
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
        
        # Caspar Fownes Picks
        FOWNES_PICKS = {
            1: [7, 9, 3, 2, 1],
            2: [4, 2, 1, 7, 8],
            3: [13, 1, 2, 6, 10],
            4: [4, 8, 14, 6, 7],
            5: [3, 1, 2, 9, 6],
            6: [7, 8, 6, 11, 3],
            7: [9, 4, 5, 7, 10],
            8: [3, 4, 10, 7, 11],
            9: [13, 5, 4, 10, 1],
            10: [4, 3, 2, 5, 6],
            11: [6, 11, 4, 5, 2]
        }
        
        race_no_int = int(race.get('race_no', 0))
        
        def get_fownes_pts(horse_no, r_no):
            try:
                h_no = int(horse_no)
                if r_no in FOWNES_PICKS:
                    picks = FOWNES_PICKS[r_no]
                    if h_no in picks:
                        return 5 - picks.index(h_no)
            except:
                pass
            return 0
            
        df_runners['fownes_pts'] = df_runners['no'].map(lambda x: get_fownes_pts(x, race_no_int))
        
        df_runners['form_speed_pts'] = 0
        if 'draw' in df_runners.columns and 'recent_avg_pos' in df_runners.columns:
            draw_num = pd.to_numeric(df_runners['draw'], errors='coerce')
            recent_pos = pd.to_numeric(df_runners['recent_avg_pos'], errors='coerce')
            recent_win = pd.to_numeric(df_runners.get('recent_win_rate', 0), errors='coerce')
            
            # Massive debutant penalty to remove blindspots
            is_debutant = (recent_pos == 7.0) & (recent_win == 0.0)
            debutant_penalty = np.where(is_debutant, -15, 0)
            
            speed_pts = np.where(recent_pos <= 4.5, 4, 0)
            form_pts = np.where(recent_win >= 0.1, 2, 0)
            df_runners['form_speed_pts'] = speed_pts + form_pts + debutant_penalty

        # Gemini Intel points for specifically named in-form horses
        intel_horses = ["HOT DELIGHT", "GOLD PATCH", "AMAZING PARTNERS"]
        df_runners['intel_pts'] = df_runners['name'].str.upper().apply(lambda x: 4 if any(ih in str(x) for ih in intel_horses) else 0)

        consensus = df_runners.get('consensus_score', 0).fillna(0)
        total_boost_pts = consensus + df_runners['fownes_pts'] + df_runners['form_speed_pts'] + df_runners['intel_pts']
        df_runners['model_prob'] = df_runners['model_prob'] * (1 + (total_boost_pts * 0.03))
            
        total_b = df_runners['model_prob'].sum()
        if total_b > 0:
            df_runners['model_prob'] = df_runners['model_prob'] / total_b
            
        df_runners['value_diff'] = df_runners['model_prob'] - df_runners['implied_prob']
        
        p_min = df_runners['model_prob'].min()
        p_max = df_runners['model_prob'].max()
        if p_max > p_min:
            df_runners['confidence'] = (15.0 + ((df_runners['model_prob'] - p_min) / (p_max - p_min)) * 70).round(0).astype(int)
        else:
            df_runners['confidence'] = 50
            
        race_picks = df_runners.sort_values(by='model_prob', ascending=False)
        
        best = race_picks.iloc[0].to_dict()
        best.update({"race_no": race.get("race_no"), "class_dist": class_str})
        global_best_bets.append(best)

    global_best_bets = sorted(global_best_bets, key=lambda x: x.get('value_diff', 0), reverse=True)
    
    print("TOP 5 DETAILED PICKS:")
    for i in range(min(5, len(global_best_bets))):
        bb = global_best_bets[i]
        print(f"\n--- PICK {i+1} : Race {bb['race_no']} - {bb['name']} ---")
        for k in ['no', 'name', 'jockey', 'trainer', 'draw', 'actual_weight', 'horse_rating', 'win_odds', 'confidence', 'value_diff', 'jockey_win_rate', 'trainer_win_rate', 'recent_avg_pos', 'ST_vs_HV_pref', 'last_form_going', 'track_pref_match', 'going_pref_match']:
            if k in bb:
                print(f"{k}: {bb[k]}")

if __name__ == '__main__':
    run()

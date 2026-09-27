import json
import pandas as pd
import numpy as np
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from model import predict_probabilities, load_model

def check_exotics():
    with open('data/last_scraped_meeting.json', 'r') as f:
        meeting_data = json.load(f)
    
    meeting = meeting_data['meetings'][0]
    races = meeting['races']
    
    # Load frozen predictions
    frozen_path = 'data/frozen_predictions_20260610.json'
    frozen_data = {}
    if os.path.exists(frozen_path):
        with open(frozen_path, 'r') as f:
            frozen_data = json.load(f)
            
    load_model()
    
    print("STABLE FROZEN HIGH-CONVEXITY OPPORTUNITIES:")
    print("=========================================")
    
    for race in races:
        race_no = race['race_no']
        runners = race['runners']
        if not runners:
            continue
            
        # Actual positions
        pos_map = {r['no']: r.get('final_position', 99) for r in runners}
        odds_map = {r['no']: r.get('win_odds', 99.0) for r in runners}
        name_map = {r['no']: r['name'] for r in runners}
        
        # Get actual winner, 2nd, 3rd
        winner_no = [no for no, pos in pos_map.items() if pos == 1]
        second_no = [no for no, pos in pos_map.items() if pos == 2]
        third_no = [no for no, pos in pos_map.items() if pos == 3]
        
        # Frozen
        key = f"Happy Valley_R{race_no}"
        if key in frozen_data:
            df_frozen = pd.DataFrame(frozen_data[key])
            df_frozen_sorted = df_frozen.sort_values(by='gs_score', ascending=False).reset_index(drop=True)
            
            best = df_frozen_sorted.iloc[0]
            # Get high convexity outlier (win_odds >= 12.0 and no != best['no'], highest value_diff)
            longshots = df_frozen_sorted[(df_frozen_sorted['win_odds'] >= 12.0) & (df_frozen_sorted['no'] != best['no'])].sort_values(by='value_diff', ascending=False)
            if not longshots.empty:
                bold_pick = longshots.iloc[0]
                
                bold_no = bold_pick['no']
                bold_name = bold_pick['name']
                bold_odds = bold_pick['win_odds']
                bold_pos = pos_map.get(bold_no, 99)
                
                # Check hits
                # 1. Did the longshot win or place?
                placed = bold_pos in [1, 2, 3]
                
                # 2. Did Quinella/Exacta hit with Best? (best won/2nd and bold won/2nd)
                best_no = best['no']
                best_pos = pos_map.get(best_no, 99)
                best_name = best['name']
                best_odds = best['win_odds']
                
                exotic_hit = False
                hit_desc = []
                if placed:
                    hit_desc.append(f"Outlier placed {bold_pos}rd/nd/st!")
                    
                # Exacta/Quinella
                if (best_pos in [1, 2]) and (bold_pos in [1, 2]):
                    exotic_hit = True
                    hit_desc.append("⭐ Quinella/Exacta Hit!")
                # Trifecta
                if (best_pos in [1, 2, 3]) and (bold_pos in [1, 2, 3]):
                    exotic_hit = True
                    hit_desc.append("⭐ Trifecta legs hit (both in top 3)!")
                    
                if placed or exotic_hit:
                    print(f"Race {race_no}:")
                    print(f"  Primary Best: #{best_no} {best_name} (Odds: {best_odds:.1f}, Finished: {best_pos})")
                    print(f"  Outlier Pick: #{bold_no} {bold_name} (Odds: {bold_odds:.1f}, Finished: {bold_pos})")
                    print(f"  Actual Winner: #{winner_no[0]} {name_map[winner_no[0]]} (Odds: {odds_map[winner_no[0]]})")
                    print(f"  HIT: {', '.join(hit_desc)}")
                    print()

    print("\nLEGACY LIVE HIGH-CONVEXITY OPPORTUNITIES:")
    print("=========================================")
    for race in races:
        race_no = race['race_no']
        runners = race['runners']
        if not runners:
            continue
            
        pos_map = {r['no']: r.get('final_position', 99) for r in runners}
        odds_map = {r['no']: r.get('win_odds', 99.0) for r in runners}
        name_map = {r['no']: r['name'] for r in runners}
        
        winner_no = [no for no, pos in pos_map.items() if pos == 1]
        
        # Live
        df_live = pd.DataFrame(runners)
        df_live['win_odds'] = df_live['win_odds'].replace(0.0, 20.0).fillna(20.0)
        df_live['scraped_win_odds'] = df_live['win_odds'].copy()
        df_live['consensus_score'] = 0.0
        class_str = race.get("class_dist", "")
        class_int = 4
        if "Class 1" in class_str: class_int = 1
        elif "Class 2" in class_str: class_int = 2
        elif "Class 3" in class_str: class_int = 3
        elif "Class 4" in class_str: class_int = 4
        elif "Class 5" in class_str: class_int = 5
        
        try:
            probs, df_live = predict_probabilities(df_live, venue=meeting.get('venue'), going=meeting.get('going'), race_date=meeting.get('date'), race_class_int=class_int)
        except Exception as e:
            probs = np.ones(len(df_live)) / len(df_live)
            
        df_live['model_prob'] = probs
        df_live['implied_raw'] = 1 / df_live['win_odds'].replace(0, 1.0)
        sum_implied = df_live['implied_raw'].sum()
        df_live['implied_prob'] = df_live['implied_raw'] / sum_implied if sum_implied > 0 else (1/len(df_live))
        df_live['value_diff'] = df_live['model_prob'] - df_live['implied_prob']
        df_live['shift_bonus'] = 0.0
        df_live['gs_score'] = (df_live['model_prob'] * 100) + np.where(df_live['value_diff'] > 0, df_live['value_diff'] * 10, 0) + df_live['shift_bonus']
        df_live_sorted = df_live.sort_values(by='gs_score', ascending=False).reset_index(drop=True)
        
        best = df_live_sorted.iloc[0]
        longshots = df_live_sorted[(df_live_sorted['win_odds'] >= 12.0) & (df_live_sorted['no'] != best['no'])].sort_values(by='value_diff', ascending=False)
        if not longshots.empty:
            bold_pick = longshots.iloc[0]
            
            bold_no = bold_pick['no']
            bold_name = bold_pick['name']
            bold_odds = bold_pick['win_odds']
            bold_pos = pos_map.get(bold_no, 99)
            
            placed = bold_pos in [1, 2, 3]
            
            best_no = best['no']
            best_pos = pos_map.get(best_no, 99)
            best_name = best['name']
            best_odds = best['win_odds']
            
            exotic_hit = False
            hit_desc = []
            if placed:
                hit_desc.append(f"Outlier placed {bold_pos}rd/nd/st!")
                
            if (best_pos in [1, 2]) and (bold_pos in [1, 2]):
                exotic_hit = True
                hit_desc.append("⭐ Quinella/Exacta Hit!")
            if (best_pos in [1, 2, 3]) and (bold_pos in [1, 2, 3]):
                exotic_hit = True
                hit_desc.append("⭐ Trifecta legs hit (both in top 3)!")
                
            if placed or exotic_hit:
                print(f"Race {race_no}:")
                print(f"  Primary Best: #{best_no} {best_name} (Odds: {best_odds:.1f}, Finished: {best_pos})")
                print(f"  Outlier Pick: #{bold_no} {bold_name} (Odds: {bold_odds:.1f}, Finished: {bold_pos})")
                print(f"  Actual Winner: #{winner_no[0]} {name_map[winner_no[0]]} (Odds: {odds_map[winner_no[0]]})")
                print(f"  HIT: {', '.join(hit_desc)}")
                print()

if __name__ == '__main__':
    check_exotics()

import json
import pandas as pd
import numpy as np
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from model import predict_probabilities

with open('data/last_scraped_meeting.json', 'r') as f:
    meeting_data = json.load(f)

meeting = meeting_data['meetings'][0]
races = meeting['races']

with open('data/frozen_predictions_20260610.json', 'r') as f:
    frozen = json.load(f)

print("ACTUAL RACE WINNERS VS PREDICTIONS")
print("==================================")

for race in races:
    race_no = race['race_no']
    runners = race['runners']
    
    winner = None
    for r in runners:
        pos = r.get('final_position')
        if pos == 1 or pos == '1' or str(pos).strip() == '1':
            winner = r
            break
            
    if not winner:
        for r in runners:
            if r.get('final_position') == 1:
                winner = r
                break
                
    if not winner:
        continue
        
    winner_no = winner['no']
    winner_name = winner['name']
    winner_odds = winner.get('win_odds', 0.0)
    
    # 1. Get rank in Frozen
    key = f"Happy Valley_R{race_no}"
    frozen_list = frozen.get(key, [])
    frozen_rank = "N/A"
    frozen_gs = 0.0
    if frozen_list:
        df_f = pd.DataFrame(frozen_list).sort_values(by='gs_score', ascending=False).reset_index()
        for idx, row in df_f.iterrows():
            if row['no'] == winner_no:
                frozen_rank = idx + 1
                frozen_gs = row['gs_score']
                break
                
    # 2. Re-calculate Live rank
    df_l = pd.DataFrame(runners)
    if 'win_odds' in df_l.columns:
        df_l['win_odds'] = df_l['win_odds'].replace(0.0, 20.0).fillna(20.0)
    else:
        df_l['win_odds'] = 20.0
        
    class_str = race.get("class_dist", "")
    class_int = 4
    if "Class 1" in class_str: class_int = 1
    elif "Class 2" in class_str: class_int = 2
    elif "Class 3" in class_str: class_int = 3
    elif "Class 4" in class_str: class_int = 4
    elif "Class 5" in class_str: class_int = 5
    
    try:
        probs, df_l = predict_probabilities(df_l, venue=meeting.get('venue'), going=meeting.get('going'), race_date=meeting.get('date'), race_class_int=class_int)
    except:
        probs = [1.0/len(df_l)] * len(df_l)
        
    df_l['model_prob'] = probs
    df_l['implied_raw'] = 1 / df_l['win_odds']
    sum_implied = df_l['implied_raw'].sum()
    df_l['implied_prob'] = df_l['implied_raw'] / sum_implied
    df_l['value_diff'] = df_l['model_prob'] - df_l['implied_prob']
    df_l['gs_score'] = (df_l['model_prob'] * 100) + np.where(df_l['value_diff'] > 0, df_l['value_diff'] * 10, 0)
    
    df_l = df_l.sort_values(by='gs_score', ascending=False).reset_index()
    live_rank = "N/A"
    live_gs = 0.0
    for idx, row in df_l.iterrows():
        if row['no'] == winner_no:
            live_rank = idx + 1
            live_gs = row['gs_score']
            break
            
    print(f"RACE {race_no}: Winner was #{winner_no} {winner_name} (Odds: {winner_odds})")
    print(f"  - Frozen Rank (Correct):  {frozen_rank} (GS Score: {frozen_gs:.2f})")
    print(f"  - Live Rank (What client saw): {live_rank} (GS Score: {live_gs:.2f})")

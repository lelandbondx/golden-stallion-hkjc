import json
import pandas as pd
import numpy as np
import os

def simulate():
    meeting_file = 'data/last_scraped_meeting.json'
    frozen_file = 'data/frozen_predictions_20260712.json'
    
    if not os.path.exists(meeting_file) or not os.path.exists(frozen_file):
        print("Missing data files.")
        return
        
    with open(meeting_file, 'r', encoding='utf-8') as f:
        meeting_data = json.load(f)
    with open(frozen_file, 'r', encoding='utf-8') as f:
        frozen_data = json.load(f)
        
    meeting = meeting_data['meetings'][0]
    venue = meeting.get('venue', 'Sha Tin')
    races = meeting.get('races', [])
    
    # 1. Flat betting Rank 1
    spend_flat = 0
    ret_flat = 0
    
    # 2. Betting Rank 1 ONLY if Value Diff > 0 (Positive EV)
    spend_ev = 0
    ret_ev = 0
    
    # 3. Betting Rank 1 and Rank 5
    spend_both = 0
    ret_both = 0
    
    for race in races:
        race_no = race.get('race_no')
        runners = race.get('runners', [])
        if not runners:
            continue
            
        runner_pos = {r.get('no'): r.get('final_position') for r in runners}
        
        key = f"{venue}_R{race_no}"
        predictions = frozen_data.get(key, [])
        if not predictions:
            key_alt = f"Sha Tin_R{race_no}"
            predictions = frozen_data.get(key_alt, [])
            
        if not predictions:
            continue
            
        df = pd.DataFrame(predictions).sort_values(by='gs_score', ascending=False).reset_index(drop=True)
        
        # Rank 1 pick
        pick_1 = df.iloc[0]
        p1_no = pick_1['no']
        p1_odds = float(pick_1['scraped_win_odds']) if 'scraped_win_odds' in pick_1 else float(pick_1['win_odds'])
        p1_ev = float(pick_1['value_diff'])
        p1_pos = int(runner_pos.get(p1_no, 99))
        
        spend_flat += 10
        if p1_pos == 1:
            ret_flat += 10 * p1_odds
            
        # EV Filtered
        if p1_ev > 0:
            spend_ev += 10
            if p1_pos == 1:
                ret_ev += 10 * p1_odds
                
        # Rank 1 and Rank 5
        pick_5 = df.iloc[4] if len(df) > 4 else None
        spend_both += 10
        if p1_pos == 1:
            ret_both += 10 * p1_odds
            
        if pick_5 is not None:
            p5_no = pick_5['no']
            p5_odds = float(pick_5['scraped_win_odds']) if 'scraped_win_odds' in pick_5 else float(pick_5['win_odds'])
            p5_pos = int(runner_pos.get(p5_no, 99))
            
            spend_both += 10
            if p5_pos == 1:
                ret_both += 10 * p5_odds
                
    print("BETTING STRATEGY COMPARISON:")
    print("===========================")
    print(f"1. Flat Rank 1 Win Betting:")
    print(f"   Spend: ${spend_flat:.2f} | Return: ${ret_flat:.2f} | ROI: {((ret_flat-spend_flat)/spend_flat)*100:+.1f}%")
    print(f"2. Positive EV Only Rank 1 win Betting:")
    print(f"   Spend: ${spend_ev:.2f} | Return: ${ret_ev:.2f} | ROI: {((ret_ev-spend_ev)/spend_ev)*100:+.1f}%" if spend_ev > 0 else "   No bets placed")
    print(f"3. Rank 1 + Rank 5 Win Betting:")
    print(f"   Spend: ${spend_both:.2f} | Return: ${ret_both:.2f} | ROI: {((ret_both-spend_both)/spend_both)*100:+.1f}%")

if __name__ == '__main__':
    simulate()

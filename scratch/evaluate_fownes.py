import json
import pandas as pd
import os

def evaluate_fownes():
    meeting_file = 'data/last_scraped_meeting.json'
    frozen_file = 'data/frozen_predictions_20260712.json'
    
    if not os.path.exists(meeting_file):
        print("Scraped meeting data not found.")
        return
        
    with open(meeting_file, 'r', encoding='utf-8') as f:
        meeting_data = json.load(f)
        
    frozen_data = {}
    if os.path.exists(frozen_file):
        with open(frozen_file, 'r', encoding='utf-8') as f:
            frozen_data = json.load(f)
            
    meeting = meeting_data['meetings'][0]
    venue = meeting.get('venue', 'Sha Tin')
    races = meeting.get('races', [])
    
    fownes_runners = []
    
    for race in races:
        race_no = race.get('race_no')
        runners = race.get('runners', [])
        
        # Load predictions to find AI rank
        key = f"{venue}_R{race_no}"
        predictions = frozen_data.get(key, [])
        if not predictions:
            key_alt = f"Sha Tin_R{race_no}"
            predictions = frozen_data.get(key_alt, [])
            
        pred_ranks = {}
        if predictions:
            df_pred = pd.DataFrame(predictions).sort_values(by='gs_score', ascending=False).reset_index(drop=True)
            for idx, row in df_pred.iterrows():
                pred_ranks[int(row['no'])] = idx + 1
                
        for r in runners:
            trainer = r.get('trainer', '')
            if 'fownes' in str(trainer).lower():
                no = r.get('no')
                name = r.get('name')
                pos = r.get('final_position')
                odds = r.get('win_odds')
                ai_rank = pred_ranks.get(int(no), "N/A")
                
                fownes_runners.append({
                    "race_no": race_no,
                    "no": no,
                    "name": name,
                    "final_pos": pos,
                    "win_odds": odds,
                    "ai_rank": ai_rank
                })
                
    print(f"CASPAR FOWNES RUNNERS FOR {meeting.get('date')}:")
    print("=" * 60)
    for runner in fownes_runners:
        pos_str = f"Finished: {runner['final_pos']}"
        if runner['final_pos'] == 1:
            pos_str = "🏆 WINNER"
        elif runner['final_pos'] == 2:
            pos_str = "🥈 2nd"
        elif runner['final_pos'] == 3:
            pos_str = "🥉 3rd"
            
        print(f"Race {runner['race_no']} - #{runner['no']} {runner['name']}: {pos_str} (Odds: {runner['win_odds']}, AI Rank: {runner['ai_rank']})")

if __name__ == '__main__':
    evaluate_fownes()

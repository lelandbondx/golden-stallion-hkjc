import json
import pandas as pd
import numpy as np
import os

def evaluate():
    meeting_file = 'data/last_scraped_meeting.json'
    frozen_file = 'data/frozen_predictions_20260712.json'
    
    if not os.path.exists(meeting_file):
        print("Scraped meeting data not found.")
        return
    if not os.path.exists(frozen_file):
        print("Frozen predictions file not found.")
        return
        
    with open(meeting_file, 'r', encoding='utf-8') as f:
        meeting_data = json.load(f)
    with open(frozen_file, 'r', encoding='utf-8') as f:
        frozen_data = json.load(f)
        
    meeting = meeting_data['meetings'][0]
    venue = meeting.get('venue', 'Sha Tin')
    races = meeting.get('races', [])
    
    print(f"EVALUATING PERFORMANCE FOR MEETING: {meeting.get('date')} at {venue}")
    print("=" * 60)
    
    hits = 0
    top_3_hits = 0
    top_5_hits = 0
    total_races = 0
    
    quinella_hits = 0
    exacta_hits = 0
    trifecta_hits = 0
    
    for race in races:
        race_no = race.get('race_no')
        runners = race.get('runners', [])
        if not runners:
            continue
            
        total_races += 1
        
        # Sort runners by final position
        def get_pos(r):
            pos = r.get('final_position')
            if pos is None: return 99
            try: return int(pos)
            except: return 99
        
        sorted_runners = sorted(runners, key=get_pos)
        winner = sorted_runners[0] if sorted_runners else None
        
        # Find predictions for this race in frozen_data
        key = f"{venue}_R{race_no}"
        predictions = frozen_data.get(key, [])
        if not predictions:
            # try backup keys
            key_alt = f"Sha Tin_R{race_no}"
            predictions = frozen_data.get(key_alt, [])
            
        if not predictions:
            print(f"No predictions found for Race {race_no}")
            continue
            
        df_pred = pd.DataFrame(predictions).sort_values(by='gs_score', ascending=False).reset_index(drop=True)
        
        # Match runner final position in predictions
        runner_pos_map = {r.get('no'): get_pos(r) for r in runners}
        df_pred['final_pos'] = df_pred['no'].map(runner_pos_map)
        
        winner_no = winner.get('no') if winner else None
        winner_name = winner.get('name') if winner else "Unknown"
        winner_odds = winner.get('win_odds', 0.0) if winner else 0.0
        
        # Get AI ranking of the winner
        winner_rank = df_pred[df_pred['no'] == winner_no].index[0] + 1 if winner_no in df_pred['no'].values else "N/A"
        
        # Evaluate Top Picks
        pick_1 = df_pred.iloc[0].to_dict() if len(df_pred) > 0 else {}
        pick_2 = df_pred.iloc[1].to_dict() if len(df_pred) > 1 else {}
        pick_3 = df_pred.iloc[2].to_dict() if len(df_pred) > 2 else {}
        pick_4 = df_pred.iloc[3].to_dict() if len(df_pred) > 3 else {}
        pick_5 = df_pred.iloc[4].to_dict() if len(df_pred) > 4 else {}
        
        is_hit = pick_1.get('final_pos') == 1
        is_top_3_hit = pick_1.get('final_pos') in [1, 2, 3]
        
        if is_hit:
            hits += 1
        if pick_1.get('final_pos') in [1, 2, 3]:
            top_3_hits += 1
        if pick_1.get('final_pos') in [1, 2, 3, 4, 5]:
            top_5_hits += 1
            
        # Exotic checks
        top_2_nos = [pick_1.get('no'), pick_2.get('no')]
        top_3_nos = [pick_1.get('no'), pick_2.get('no'), pick_3.get('no')]
        
        actual_1st = sorted_runners[0].get('no') if len(sorted_runners) > 0 else None
        actual_2nd = sorted_runners[1].get('no') if len(sorted_runners) > 1 else None
        actual_3rd = sorted_runners[2].get('no') if len(sorted_runners) > 2 else None
        
        # Exacta: 1st and 2nd in exact order
        if actual_1st == pick_1.get('no') and actual_2nd == pick_2.get('no'):
            exacta_hits += 1
            
        # Quinella: 1st and 2nd in any order
        if actual_1st in top_2_nos and actual_2nd in top_2_nos:
            quinella_hits += 1
            
        # Trifecta: 1st, 2nd, and 3rd in exact order
        if actual_1st == pick_1.get('no') and actual_2nd == pick_2.get('no') and actual_3rd == pick_3.get('no'):
            trifecta_hits += 1
            
        print(f"RACE {race_no}:")
        print(f"  AI Rank 1: #{pick_1.get('no')} {pick_1.get('name')} (Odds: {pick_1.get('win_odds')}) -> Finished: {pick_1.get('final_pos')}")
        print(f"  AI Rank 2: #{pick_2.get('no')} {pick_2.get('name')} (Odds: {pick_2.get('win_odds')}) -> Finished: {pick_2.get('final_pos')}")
        print(f"  AI Rank 3: #{pick_3.get('no')} {pick_3.get('name')} (Odds: {pick_3.get('win_odds')}) -> Finished: {pick_3.get('final_pos')}")
        print(f"  AI Rank 4: #{pick_4.get('no')} {pick_4.get('name')} (Odds: {pick_4.get('win_odds')}) -> Finished: {pick_4.get('final_pos')}")
        print(f"  AI Rank 5: #{pick_5.get('no')} {pick_5.get('name')} (Odds: {pick_5.get('win_odds')}) -> Finished: {pick_5.get('final_pos')}")
        print(f"  --> Winner was #{winner_no} {winner_name} (Odds: {winner_odds}) (AI Rank: {winner_rank})")
        print("-" * 50)
        
    print("\nOVERALL METRICS SUMMARY:")
    print("=========================")
    print(f"Total Races Evaluated: {total_races}")
    print(f"Direct Winner Hits (Rank 1): {hits} / {total_races} ({hits/total_races * 100:.1f}%)")
    print(f"Rank 1 Finished Top 3 (Place): {top_3_hits} / {total_races} ({top_3_hits/total_races * 100:.1f}%)")
    print(f"Quinella Hits (Top 2 in Top 2): {quinella_hits}")
    print(f"Exacta Hits (Top 2 in exact order): {exacta_hits}")
    print(f"Trifecta Hits (Top 3 in exact order): {trifecta_hits}")

if __name__ == '__main__':
    evaluate()

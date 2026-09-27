import json
import pandas as pd
import numpy as np
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from model import predict_probabilities, load_model
import odds_tracker

def generate_report():
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
    
    report_data = []
    
    for race in races:
        race_no = race['race_no']
        runners = race['runners']
        if not runners:
            continue
            
        # Get winner
        winner = None
        for r in runners:
            if r.get('final_position') == 1:
                winner = r
                break
                
        # Reconstruct live predictions (old formula)
        df_live = pd.DataFrame(runners)
        if 'win_odds' in df_live.columns:
            df_live['win_odds'] = df_live['win_odds'].replace(0.0, 20.0).fillna(20.0)
            df_live['scraped_win_odds'] = df_live['win_odds'].copy()
        else:
            df_live['win_odds'] = 20.0
            df_live['scraped_win_odds'] = 20.0
            
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
        
        # Old live formula had EV bias
        df_live['gs_score'] = (df_live['model_prob'] * 100) + np.where(df_live['value_diff'] > 0, df_live['value_diff'] * 10, 0) + df_live['shift_bonus']
        df_live_sorted = df_live.sort_values(by='gs_score', ascending=False).reset_index(drop=True)
        
        # Get frozen predictions
        key = f"Happy Valley_R{race_no}"
        df_frozen_sorted = None
        if key in frozen_data:
            df_frozen = pd.DataFrame(frozen_data[key])
            # Our updated logic: sorted by gs_score (which is model_prob * 100 + shift_bonus)
            # Or if it was cached before the fix, let's sort it by gs_score
            df_frozen_sorted = df_frozen.sort_values(by='gs_score', ascending=False).reset_index(drop=True)
            
        # Find winner ranks
        winner_rank_frozen = None
        winner_rank_live = None
        if winner:
            w_no = winner['no']
            if df_frozen_sorted is not None:
                frozen_match = df_frozen_sorted[df_frozen_sorted['no'] == w_no]
                if not frozen_match.empty:
                    winner_rank_frozen = int(frozen_match.index[0] + 1)
            
            live_match = df_live_sorted[df_live_sorted['no'] == w_no]
            if not live_match.empty:
                winner_rank_live = int(live_match.index[0] + 1)
                
        # Top 3 picks lists
        top_3_frozen = []
        if df_frozen_sorted is not None:
            top_3_frozen = [f"#{row['no']} {row['name']} ({row['win_odds']:.1f})" for _, row in df_frozen_sorted.head(3).iterrows()]
            
        top_3_live = [f"#{row['no']} {row['name']} ({row['win_odds']:.1f})" for _, row in df_live_sorted.head(3).iterrows()]
        
        report_data.append({
            "race_no": race_no,
            "class_dist": class_str,
            "winner_no": winner['no'] if winner else None,
            "winner_name": winner['name'] if winner else "Unknown/Not Run",
            "winner_odds": winner['win_odds'] if winner else None,
            "winner_rank_frozen": winner_rank_frozen,
            "winner_rank_live": winner_rank_live,
            "top_3_frozen": top_3_frozen,
            "top_3_live": top_3_live
        })
        
    # Calculate statistics for completed races
    completed = [r for r in report_data if r['winner_no'] is not None]
    
    frozen_top_1_wins = sum(1 for r in completed if r['winner_rank_frozen'] == 1)
    frozen_top_3_wins = sum(1 for r in completed if r['winner_rank_frozen'] is not None and r['winner_rank_frozen'] <= 3)
    frozen_top_5_wins = sum(1 for r in completed if r['winner_rank_frozen'] is not None and r['winner_rank_frozen'] <= 5)
    
    live_top_1_wins = sum(1 for r in completed if r['winner_rank_live'] == 1)
    live_top_3_wins = sum(1 for r in completed if r['winner_rank_live'] is not None and r['winner_rank_live'] <= 3)
    live_top_5_wins = sum(1 for r in completed if r['winner_rank_live'] is not None and r['winner_rank_live'] <= 5)
    
    # Calculate profits (flat $10 stake)
    frozen_profit = 0.0
    live_profit = 0.0
    for r in completed:
        if r['winner_rank_frozen'] == 1:
            frozen_profit += (r['winner_odds'] * 10) - 10
        else:
            frozen_profit -= 10
            
        if r['winner_rank_live'] == 1:
            live_profit += (r['winner_odds'] * 10) - 10
        else:
            live_profit -= 10
            
    print("==================================================")
    print("      GOLDEN STALLION AI PERFORMANCE REPORT       ")
    print("      Happy Valley Meeting - June 10, 2026       ")
    print("==================================================")
    print(f"Completed Races Evaluated: {len(completed)}")
    print("\nOVERALL ACCURACY COMPARISON:")
    print("--------------------------------------------------")
    print(f"Metrics                Frozen (Locked)   Live (Old Code)")
    print(f"Top 1 (Winners Picked):  {frozen_top_1_wins} / {len(completed)} ({(frozen_top_1_wins/len(completed))*100:.1f}%)    {live_top_1_wins} / {len(completed)} ({(live_top_1_wins/len(completed))*100:.1f}%)")
    print(f"Top 3 (Podium Rate):     {frozen_top_3_wins} / {len(completed)} ({(frozen_top_3_wins/len(completed))*100:.1f}%)    {live_top_3_wins} / {len(completed)} ({(live_top_3_wins/len(completed))*100:.1f}%)")
    print(f"Top 5 Accuracy:          {frozen_top_5_wins} / {len(completed)} ({(frozen_top_5_wins/len(completed))*100:.1f}%)    {live_top_5_wins} / {len(completed)} ({(live_top_5_wins/len(completed))*100:.1f}%)")
    print(f"Flat Bet Net Profit:    ${frozen_profit:+.2f}            ${live_profit:+.2f}")
    print("--------------------------------------------------")
    
    print("\nRACE-BY-RACE BREAKDOWN:")
    for r in report_data:
        print(f"\nRace {r['race_no']} ({r['class_dist']}):")
        if r['winner_no'] is None:
            print("  Status: Not completed yet")
            continue
        print(f"  Actual Winner: #{r['winner_no']} {r['winner_name']} (Odds: {r['winner_odds']:.1f})")
        print(f"  Frozen Rank:   {r['winner_rank_frozen'] if r['winner_rank_frozen'] else 'Not ranked'} (Top 3: {r['top_3_frozen']})")
        print(f"  Live Rank:     {r['winner_rank_live'] if r['winner_rank_live'] else 'Not ranked'} (Top 3: {r['top_3_live']})")
        
if __name__ == '__main__':
    generate_report()

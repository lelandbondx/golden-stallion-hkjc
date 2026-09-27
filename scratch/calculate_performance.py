import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import scraper
import json
import pandas as pd
import numpy as np

# Load predictions that were frozen for 2026-07-01
predictions_file = 'data/frozen_predictions_20260701.json'
with open(predictions_file, 'r', encoding='utf-8') as f:
    preds_data = json.load(f)

live_data = scraper.get_live_meeting_data()
meeting = live_data['meetings'][0]

results = []

for r in meeting.get('races', []):
    race_no = r.get('race_no')
    key = f"Sha Tin_R{race_no}"
    if key not in preds_data:
        continue
    
    # Live runners with results
    live_runners = {runner['no']: runner for runner in r.get('runners', [])}
    
    # Predicted runners
    pred_runners = preds_data[key]
    # Sort by gs_score descending
    pred_runners = sorted(pred_runners, key=lambda x: x.get('gs_score', 0), reverse=True)
    
    # Find actual results
    print(f"\nRace {race_no}:")
    for rank, p in enumerate(pred_runners):
        no = p.get('no')
        live_info = live_runners.get(no, {})
        fin_pos = live_info.get('final_position')
        odds = live_info.get('win_odds', p.get('win_odds', 20.0))
        
        # Parse final position
        pos_int = 99
        if fin_pos is not None and fin_pos != '' and fin_pos != 0 and fin_pos != '0':
            try:
                pos_int = int(fin_pos)
            except:
                pass
        
        p['final_position'] = pos_int
        p['win_odds_result'] = odds
        
        if rank < 5:
            print(f"  Rank {rank+1}: #{no} {p.get('name')} -> Finished {pos_int} (Odds: {odds})")
    
    results.append({
        "race_no": race_no,
        "runners": pred_runners
    })

# Compute overall stats
total_races = len(results)
top1_wins = 0
top2_wins = 0
top3_wins = 0
top5_wins = 0

flat_win_spend = 0
flat_win_return = 0

exacta_wins = 0 # 1st and 2nd in top 5

print("\n--- STATS SUMMARY ---")
for res in results:
    runners = res['runners']
    win_runner = [r for r in runners if r.get('final_position') == 1]
    if not win_runner:
        continue
    win_no = win_runner[0]['no']
    win_odds = win_runner[0]['win_odds_result']
    
    # Check predictions rank of the winner
    winner_rank = -1
    for rank, r in enumerate(runners):
        if r['no'] == win_no:
            winner_rank = rank + 1
            break
            
    print(f"Race {res['race_no']} Winner #{win_no} was ranked {winner_rank} (Odds: {win_odds})")
    
    flat_win_spend += 10 # $10 on each race's 1st Pick
    # If 1st Pick won
    if winner_rank == 1:
        top1_wins += 1
        flat_win_return += 10 * win_odds
        
    if winner_rank <= 2:
        top2_wins += 1
    if winner_rank <= 3:
        top3_wins += 1
    if winner_rank <= 5:
        top5_wins += 1
        
    # Check Quinella / Exacta in top 5
    pos2_runner = [r for r in runners if r.get('final_position') == 2]
    if pos2_runner:
        pos2_no = pos2_runner[0]['no']
        pos2_rank = -1
        for rank, r in enumerate(runners):
            if r['no'] == pos2_no:
                pos2_rank = rank + 1
                break
        if winner_rank <= 5 and pos2_rank <= 5:
            exacta_wins += 1

print(f"\nTop 1 Pick Wins: {top1_wins} / {total_races} ({top1_wins/total_races*100:.1f}%)")
print(f"Top 2 Pick Wins: {top2_wins} / {total_races} ({top2_wins/total_races*100:.1f}%)")
print(f"Top 3 Pick Wins: {top3_wins} / {total_races} ({top3_wins/total_races*100:.1f}%)")
print(f"Top 5 Pick Wins: {top5_wins} / {total_races} ({top5_wins/total_races*100:.1f}%)")

print(f"Flat Win Staking Spend: ${flat_win_spend}")
print(f"Flat Win Staking Return: ${flat_win_return:.2f}")
print(f"Flat Win Staking Profit: ${flat_win_return - flat_win_spend:.2f} (ROI: {(flat_win_return - flat_win_spend)/flat_win_spend*100:.1f}%)")

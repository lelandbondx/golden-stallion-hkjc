import json
import pandas as pd

with open('data/last_scraped_meeting.json', 'r') as f:
    meeting_data = json.load(f)

meeting = meeting_data['meetings'][0]
races = meeting['races']

with open('data/frozen_predictions_20260610.json', 'r') as f:
    frozen = json.load(f)

global_best_bets = []

for race in races:
    race_no = race['race_no']
    key = f"Happy Valley_R{race_no}"
    if key in frozen:
        runners = frozen[key]
        df_runners = pd.DataFrame(runners)
        # Sort by value_diff to match app.py correction
        race_picks = df_runners.sort_values(by='value_diff', ascending=False)
        best = race_picks.iloc[0].to_dict()
        best.update({"race_no": race_no})
        global_best_bets.append(best)

print("Global Best Bets:")
for b in global_best_bets:
    print(f"Race {b['race_no']} - #{b['no']} {b['name']} - GS: {b.get('gs_score'):.2f}, EV: {b.get('value_diff'):.4f}, Odds: {b.get('win_odds')}")

print("\nSorted by EV (Highest EV Selection):")
global_best_bets_sorted_by_ev = sorted(global_best_bets, key=lambda x: x.get('value_diff', 0), reverse=True)
for i, b in enumerate(global_best_bets_sorted_by_ev):
    print(f"  {i+1}: Race {b['race_no']} - #{b['no']} {b['name']} - EV: {b.get('value_diff'):.4f}, GS: {b.get('gs_score'):.2f}, Odds: {b.get('win_odds')}")

print("\nSorted by GS (Strongest Confidence Selection):")
global_best_bets_sorted_by_gs = sorted(global_best_bets, key=lambda x: x.get('gs_score', 0), reverse=True)
for i, b in enumerate(global_best_bets_sorted_by_gs):
    print(f"  {i+1}: Race {b['race_no']} - #{b['no']} {b['name']} - GS: {b.get('gs_score'):.2f}, EV: {b.get('value_diff'):.4f}, Odds: {b.get('win_odds')}")

import os
import json
import pandas as pd

files = sorted([f for f in os.listdir('data') if f.startswith('frozen_predictions_') and f.endswith('.json')])

print("Checking all frozen predictions for odds >= 20.0 winners:")
for fn in files:
    with open(os.path.join('data', fn), 'r', encoding='utf-8') as f:
        data = json.load(f)
    for r_key, runners in data.items():
        if not runners: continue
        df = pd.DataFrame(runners)
        if 'final_position' not in df.columns: continue
        df = df[df['final_position'].notna() & (df['final_position'] != 0)].sort_values(by='gs_score', ascending=False).reset_index(drop=True)
        df['rank'] = range(1, len(df)+1)
        winners = df[df['final_position'] == 1]
        for _, w in winners.iterrows():
            odds = float(w.get('win_odds', w.get('odds', 0)))
            if odds >= 15.0 or w['rank'] <= 5:
                print(f"File: {fn} | Race: {r_key} | Winner: {w.get('name', w.get('horse'))} | Odds: {odds} | AI Rank: #{w['rank']}")

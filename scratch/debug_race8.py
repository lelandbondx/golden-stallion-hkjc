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

# Find Race 8
race8_scraped = [r for r in races if r['race_no'] == 8][0]
race8_frozen = frozen.get('Happy Valley_R8', [])

print("RACE 8 DETAILED DIAGNOSTIC")
print("=========================")

print("\n--- FROZEN (CORRECT) DETAILS ---")
df_f = pd.DataFrame(race8_frozen)
df_f_sorted = df_f.sort_values(by='gs_score', ascending=False)
for i, (_, r) in enumerate(df_f_sorted.iterrows()):
    print(f"Rank {i+1}: #{r['no']} {r['name']} - GS: {r.get('gs_score'):.2f}, Prob: {r.get('model_prob'):.4f}, Odds: {r.get('win_odds')}, EV: {r.get('value_diff'):.4f}")

# Re-run live calculation with final scraped data
df_l = pd.DataFrame(race8_scraped['runners'])
# Map tips consensus
tips_data = {}
try:
    with open('data/gemini_intel.json', 'r', encoding='utf-8') as f:
        tips_data = json.load(f)
except:
    pass

current_race_tips = tips_data.get(8, {})
df_l['consensus_score'] = df_l['no'].map(lambda x: current_race_tips.get(x, 0))

# Predict
class_dist = race8_scraped.get("class_dist", "")
class_int = 3
probs, df_l = predict_probabilities(df_l, venue=meeting.get('venue'), going=meeting.get('going'), race_date=meeting.get('date'), race_class_int=class_int)
df_l['model_prob'] = probs

# Let's check with actual live win odds (scraped at post-time)
df_l['win_odds'] = df_l['win_odds'].replace(0.0, 20.0).fillna(20.0)
df_l['implied_raw'] = 1 / df_l['win_odds']
sum_implied = df_l['implied_raw'].sum()
df_l['implied_prob'] = df_l['implied_raw'] / sum_implied
df_l['value_diff'] = df_l['model_prob'] - df_l['implied_prob']
df_l['shift_bonus'] = 0.0
df_l['gs_score'] = (df_l['model_prob'] * 100) + np.where(df_l['value_diff'] > 0, df_l['value_diff'] * 10, 0)

print("\n--- LIVE (OLD CALCULATIONS) DETAILS ---")
df_l_sorted = df_l.sort_values(by='gs_score', ascending=False)
for i, (_, r) in enumerate(df_l_sorted.iterrows()):
    print(f"Rank {i+1}: #{r['no']} {r['name']} - GS: {r.get('gs_score'):.2f}, Prob: {r.get('model_prob'):.4f}, Odds: {r.get('win_odds')}, EV: {r.get('value_diff'):.4f}")

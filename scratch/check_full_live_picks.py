import json
import pandas as pd
import numpy as np
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from model import predict_probabilities

running_styles = {}
if os.path.exists('data/runs.csv'):
    try:
        df_styles = pd.read_csv('data/runs.csv', usecols=['horse', 'first_pos'])
        df_styles['clean_name'] = df_styles['horse'].str.extract(r'^(.*?)\(')[0].str.strip().str.upper()
        running_styles = df_styles.groupby('clean_name')['first_pos'].mean().to_dict()
    except:
        pass

with open('data/last_scraped_meeting.json', 'r') as f:
    meeting_data = json.load(f)

meeting = meeting_data['meetings'][0]
races = meeting['races']

with open('data/frozen_predictions_20260610.json', 'r') as f:
    frozen = json.load(f)

race = [r for r in races if r['race_no'] == 8][0]

df_runners = pd.DataFrame(race['runners'])

# Load win_odds from cache if scraper returns 0.0
if 'win_odds' in df_runners.columns:
    df_runners['win_odds'] = df_runners['win_odds'].replace(0.0, 20.0).fillna(20.0)
    df_runners['scraped_win_odds'] = df_runners['win_odds'].copy()
else:
    df_runners['win_odds'] = 20.0
    df_runners['scraped_win_odds'] = 20.0

tips_data = {}
try:
    with open('data/gemini_intel.json', 'r', encoding='utf-8') as f:
        tips_data = json.load(f)
except:
    pass

current_race_tips = tips_data.get(8, {})
df_runners['consensus_score'] = df_runners['no'].map(lambda x: current_race_tips.get(x, 0))

# Exact app.py prediction logic
class_str = race.get("class_dist", "")
class_int = 3

probs, df_runners = predict_probabilities(df_runners, venue=meeting.get('venue'), going=meeting.get('going', 'GOOD'), race_date=meeting.get('date'), race_class_int=class_int)
df_runners['model_prob'] = probs

df_runners['implied_raw'] = 1 / df_runners['win_odds'].replace(0, 1.0)
sum_implied = df_runners['implied_raw'].sum()
df_runners['implied_prob'] = df_runners['implied_raw'] / sum_implied if sum_implied > 0 else (1/len(df_runners))

# Multiplier boosts from app.py
recent_pos = pd.to_numeric(df_runners.get('recent_avg_pos', 7.0), errors='coerce').fillna(7.0)
track_match = (df_runners.get('ST_vs_HV_pref', 'Neutral') == meeting.get('venue')).astype(int)
going_match = (df_runners.get('last_form_going', 'Unknown') == meeting.get('going', 'GOOD')).astype(int)
vet_issue = pd.to_numeric(df_runners.get('prev_run_vet_finding', 0), errors='coerce').fillna(0)

standout_boost = np.where((recent_pos <= 4.0) & (track_match == 1) & (going_match == 1) & (vet_issue == 0), 0.05, 0.0)

consensus = pd.to_numeric(df_runners.get('consensus_score', 0), errors='coerce').fillna(0)
consensus_boost = np.where(consensus > 0, 0.01 * np.minimum(consensus, 12), 0.0)

false_fav_penalty = np.where((df_runners['win_odds'] <= 2.5) & (recent_pos > 5.5), -0.05, 0.0)

is_debutant = (df_runners.get('days_since_last_run', 999) > 200).astype(int)
debutant_penalty = np.where(is_debutant == 1, -0.03, 0.0)

# Pace Pressure Index
if 'clean_name' not in df_runners.columns:
    df_runners['clean_name'] = df_runners['name'].str.upper().str.strip()
df_runners['avg_first_pos'] = df_runners['clean_name'].map(running_styles).fillna(6.0)
speed_count = (df_runners['avg_first_pos'] <= 3.5).sum()

closer_pace_boost = 0.0
closer_pace_penalty = 0.0
lone_speed_boost = 0.0
on_speed_wet_boost = 0.0
yielding_form_boost = 0.0

is_wet_turf = (str(meeting.get('going')).upper() in ["YIELDING", "GOOD TO YIELDING", "SOFT", "HEAVY"])

if is_wet_turf:
    on_speed_wet_boost = np.where(df_runners['avg_first_pos'] <= 4.5, 0.04, 0.0)
    has_yielding_form = df_runners['last_form_going'].astype(str).str.upper().str.contains("YIELD|SOFT|HEAVY|WET")
    yielding_form_boost = np.where(has_yielding_form, 0.03, 0.0)

if speed_count >= 3:
    on_speed_wet_boost = 0.0
    closer_pace_boost = np.where((df_runners['avg_first_pos'] > 5.5) & (recent_pos <= 5.5), 0.04, 0.0)
elif speed_count <= 1:
    lone_speed_boost = np.where(df_runners['avg_first_pos'] <= 3.5, 0.04, 0.0)
    closer_pace_penalty = np.where(df_runners['avg_first_pos'] > 6.0, -0.04, 0.0)

multiplier = 1.0 + standout_boost + consensus_boost + false_fav_penalty + debutant_penalty + on_speed_wet_boost + yielding_form_boost + closer_pace_boost + closer_pace_penalty + lone_speed_boost
multiplier = np.maximum(multiplier, 0.1)

# Apply multiplier
df_runners['model_prob'] = df_runners['model_prob'] * multiplier

# Re-normalize
sum_prob = df_runners['model_prob'].sum()
df_runners['model_prob'] = df_runners['model_prob'] / sum_prob if sum_prob > 0 else (1/len(df_runners))

# Calculate value_diff
df_runners['value_diff'] = df_runners['model_prob'] - df_runners['implied_prob']
df_runners['shift_bonus'] = 0.0

# Calculate gs_score (using Dampened Value Multiplier of 10)
df_runners['gs_score'] = (df_runners['model_prob'] * 100) + np.where(df_runners['value_diff'] > 0, df_runners['value_diff'] * 10, 0) + df_runners['shift_bonus']

# Normalize GS score to 15-85 range
p_min = df_runners['model_prob'].min()
p_max = df_runners['model_prob'].max()
p_range = p_max - p_min if p_max > p_min else 1.0
df_runners['confidence'] = ((df_runners['model_prob'] - p_min) / p_range * 70 + 15).round().astype(int)

df_sorted = df_runners.sort_values(by='gs_score', ascending=False)
print("FULL LIVE CALCULATION FOR RACE 8:")
for idx, (_, r) in enumerate(df_sorted.iterrows()):
    print(f"Rank {idx+1}: #{r['no']} {r['name']} - GS: {r.get('gs_score'):.2f}, Prob: {r.get('model_prob'):.4f}, Odds: {r.get('win_odds')}, EV: {r.get('value_diff'):.4f}")

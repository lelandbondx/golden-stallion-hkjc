import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')
import json
import scraper
import odds_tracker
import pandas as pd
from model import predict_probabilities, load_model

data = scraper.get_live_meeting_data()
meet = data['meetings'][0]
r7 = [r for r in meet['races'] if r['race_no'] == 7][0]
print(f"==================================================")
print(f"RACE 7 AUDIT: {r7.get('class_dist')} - Track: {r7.get('track')} - Going: {r7.get('going')}")
print(f"Meeting: {meet.get('venue')} | Date: {meet.get('date')}")
print(f"==================================================\n")

# Run full predictions logic on race 7
df = pd.DataFrame(r7['runners'])
probs, live_df = predict_probabilities(df, venue=meet['venue'], going=r7.get('going', 'GOOD'), race_date=meet['date'], race_class_int=3, track_type=r7.get('track', 'TURF'))
live_df['model_prob'] = probs

# Load precomputed features and trials to see exact multipliers
with open('data/precomputed_features.json', 'r', encoding='utf-8') as f:
    precomputed = json.load(f)
running_styles = precomputed.get('running_styles', {})
sectional_bursts = precomputed.get('sectional_bursts', {})

clean_name = 'MIGHTY COMMANDER'
mc = live_df[live_df['clean_name'] == clean_name]
if not mc.empty:
    mc_row = mc.iloc[0]
    print("--- MIGHTY COMMANDER DETAILED STATS ---")
    print(f"Horse:                #{mc_row.get('no')} {mc_row.get('name')} ({mc_row.get('code')})")
    print(f"Jockey / Trainer:     {mc_row.get('jockey')} / {mc_row.get('trainer')}")
    print(f"Draw (Barrier):       Gate {mc_row.get('draw')}  (Wide Draw!)")
    print(f"Weight Carried:       {mc_row.get('actual_weight')} lbs  (Heavy impost)")
    print(f"Rating:               {mc_row.get('horse_rating')} (rtg: {mc_row.get('rtg')})")
    print(f"Live Win Odds:        {mc_row.get('win_odds')}")
    print(f"Recent Avg Position:  {mc_row.get('recent_avg_pos')}")
    print(f"Recent Win Rate:      {mc_row.get('recent_win_rate')}")
    print(f"Distance Win Rate:    {mc_row.get('distance_win_rate')}")
    print(f"Sha Tin Win Rate:     {mc_row.get('ST_win_rate')}")
    print(f"HV Win Rate:          {mc_row.get('HV_win_rate')}")
    print(f"Track Pref Match:     {mc_row.get('track_pref_match')}")
    print(f"Going Pref Match:     {mc_row.get('going_pref_match')}")
    print(f"Days Since Last Run:  {mc_row.get('days_since_last_run')}")
    print(f"Class Diff:           {mc_row.get('class_diff')}")
    print(f"Rating Diff:          {mc_row.get('rating_diff')}")
    print(f"Vet Finding (Prev):   {mc_row.get('prev_run_vet_finding')}")
    print(f"Running Style (Avg1st): {running_styles.get(clean_name, 'N/A')}")
    print(f"Best Last Sectional:  {sectional_bursts.get(clean_name, 'N/A')}s")
    print(f"Raw Model Prob:       {mc_row.get('model_prob'):.4f}")

# Now let's check frozen predictions / run_predictions ranking
frozen_file = f"data/frozen_predictions_{meet.get('date').replace('-', '')}.json"
if os.path.exists(frozen_file):
    with open(frozen_file, 'r', encoding='utf-8') as f:
        f_data = json.load(f)
        r7_picks = f_data.get(f"{meet.get('venue')}_R7", [])
        if r7_picks:
            r7_picks = sorted(r7_picks, key=lambda x: x.get('gs_score', 0), reverse=True)
            print("\n--- OFFICIAL MODEL RANKINGS FOR RACE 7 ---")
            for i, p in enumerate(r7_picks):
                is_mc = " <--- [MIGHTY COMMANDER]" if p.get('name', '').upper() == clean_name else ""
                print(f"Rank {i+1:>2}: #{p.get('no'):<2} {p.get('name'):<18} | Odds: {p.get('win_odds'):>4.1f} | Conf: {p.get('confidence'):>2}% | EV: {p.get('value_diff', 0):>+6.3f} | Gate: {p.get('draw'):>2} | Wt: {p.get('actual_weight'):>3} | Jock: {p.get('jockey'):<12}{is_mc}")


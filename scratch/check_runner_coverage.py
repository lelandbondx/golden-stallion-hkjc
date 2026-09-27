import os, sys, json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd

from scraper import get_live_meeting_data

data = get_live_meeting_data()
m = data['meetings'][0]

stats_df = pd.read_csv('data/latest_horse_stats.csv')
known_names = set(stats_df['clean_name'].dropna().str.strip().str.upper())

total_runners = 0
matched_runners = 0
missing_runners = []

for r in m.get('races', []):
    for runner in r.get('runners', []):
        total_runners += 1
        name = str(runner.get('name', '')).strip().upper()
        if name in known_names:
            matched_runners += 1
        else:
            missing_runners.append((r.get('race_no'), runner.get('no'), name, runner.get('code')))

print(f"Total Declared Runners: {total_runners}")
print(f"Matched in latest_horse_stats: {matched_runners} ({matched_runners/total_runners*100:.1f}%)")
if missing_runners:
    print(f"Missing ({len(missing_runners)}):", missing_runners[:10])

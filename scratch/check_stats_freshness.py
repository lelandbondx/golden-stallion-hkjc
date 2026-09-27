import json
import pandas as pd

try:
    with open('data/last_scraped_meeting.json', 'r', encoding='utf-8') as f:
        meeting_data = json.load(f)
except Exception as e:
    print(f"Error loading meeting data: {e}")
    exit(1)

stats_df = pd.read_csv('data/latest_horse_stats.csv')
stats_dict = stats_df.set_index('clean_name').to_dict('index')

sample_runners = []
for meeting in meeting_data.get('meetings', []):
    for race in meeting.get('races', []):
        for runner in race.get('runners', []):
            name = runner.get('name', '').strip().upper()
            if name in stats_dict:
                sample_runners.append((name, stats_dict[name]))
            if len(sample_runners) >= 5:
                break
        if len(sample_runners) >= 5:
            break

print("Sample horse stats from tomorrow's runners:")
for name, stats in sample_runners:
    print(f"Horse: {name}")
    print(f"  Last Run Date: {stats.get('last_run_date')}")
    print(f"  Recent Avg Pos: {stats.get('recent_avg_pos')}")
    print(f"  ST Win Rate: {stats.get('ST_win_rate')}")
    print(f"  HV Win Rate: {stats.get('HV_win_rate')}")
    print(f"  Track Pref: {stats.get('ST_vs_HV_pref')}")
    print(f"  Vet Finding: {stats.get('prev_run_vet_finding')}")

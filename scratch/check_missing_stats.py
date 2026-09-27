import json
import pandas as pd

try:
    with open('data/last_scraped_meeting.json', 'r', encoding='utf-8') as f:
        meeting_data = json.load(f)
except Exception as e:
    print(f"Error loading meeting data: {e}")
    exit(1)

try:
    stats_df = pd.read_csv('data/latest_horse_stats.csv')
    scraped_names = set(stats_df['clean_name'].str.upper().str.strip())
except Exception as e:
    print(f"Error loading horse stats: {e}")
    scraped_names = set()

missing_horses = []
all_horses_count = 0

for meeting in meeting_data.get('meetings', []):
    for race in meeting.get('races', []):
        for runner in race.get('runners', []):
            name = runner.get('name', '').strip().upper()
            code = runner.get('code')
            all_horses_count += 1
            if name not in scraped_names:
                missing_horses.append((name, code))

print(f"Total runners in meeting: {all_horses_count}")
print(f"Total scraped horse stats: {len(scraped_names)}")
print(f"Missing horse stats count: {len(missing_horses)}")
if missing_horses:
    print("Missing horses sample (up to 20):")
    for name, code in missing_horses[:20]:
        print(f" - {name} ({code})")
else:
    print("All horses in tomorrow's meeting are present in latest_horse_stats.csv!")

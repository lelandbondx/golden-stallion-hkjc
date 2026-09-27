import json
import pandas as pd

def check_matching():
    # Load scraped meeting
    try:
        with open('data/last_scraped_meeting.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print("Failed to load scraped meeting:", e)
        return
        
    if not data.get('meetings'):
        print("No meetings in scraped data.")
        return
        
    meeting = data['meetings'][0]
    print(f"Meeting Date: {meeting.get('date')} | Venue: {meeting.get('venue')}")
    
    # Load database stats
    try:
        stats_df = pd.read_csv('data/latest_horse_stats.csv')
        stats_names = set(stats_df['clean_name'].str.upper().str.strip().tolist())
        print(f"Database contains {len(stats_names)} unique horse profiles.")
    except Exception as e:
        print("Failed to load database stats:", e)
        return
        
    total_runners = 0
    matched_runners = 0
    unmatched_runners = []
    
    for r in meeting.get('races', []):
        for runner in r.get('runners', []):
            name = runner.get('name', '').upper().strip()
            total_runners += 1
            if name in stats_names:
                matched_runners += 1
            else:
                unmatched_runners.append((r.get('race_no'), runner.get('no'), name))
                
    match_rate = (matched_runners / total_runners) * 100 if total_runners > 0 else 0
    print(f"Total runners in card: {total_runners}")
    print(f"Matched runners: {matched_runners} ({match_rate:.1f}%)")
    
    if unmatched_runners:
        print(f"Unmatched runners ({len(unmatched_runners)}):")
        for race_no, no, name in unmatched_runners[:15]:
            print(f"  Race {race_no} #{no}: {name}")
        if len(unmatched_runners) > 15:
            print(f"  ... and {len(unmatched_runners) - 15} more.")

if __name__ == "__main__":
    check_matching()

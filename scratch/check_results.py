import json

try:
    with open('data/last_scraped_meeting.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    meeting = data['meetings'][0]
    print(f"Venue: {meeting.get('venue')} | Date: {meeting.get('date')} | Going: {meeting.get('going')}")
    for race in meeting.get('races', []):
        race_no = race.get('race_no')
        print(f"\nRace {race_no}:")
        for runner in race.get('runners', []):
            pos = runner.get('final_position')
            if pos is not None and pos != 0:
                print(f"  #{runner.get('no')} {runner.get('name')} - Finished: {pos}")
except Exception as e:
    print("Error:", e)

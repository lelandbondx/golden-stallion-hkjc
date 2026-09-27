import json

try:
    with open('data/last_scraped_meeting.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    meeting = data['meetings'][0]
    
    print("Caspar Fownes (C Fownes) runners today:")
    for race in meeting.get('races', []):
        race_no = race.get('race_no')
        for runner in race.get('runners', []):
            trainer = runner.get('trainer', '')
            if 'fownes' in trainer.lower():
                pos = runner.get('final_position')
                pos_str = f"Finished {pos}" if pos else "Upcoming / Running"
                print(f"  Race {race_no}: #{runner.get('no')} {runner.get('name')} - {pos_str} | Jockey: {runner.get('jockey')}")
except Exception as e:
    print("Error:", e)

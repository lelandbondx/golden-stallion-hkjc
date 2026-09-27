import json

with open('data/last_scraped_meeting.json', 'r') as f:
    data = json.load(f)

meetings = data.get('meetings', [])
if meetings:
    meeting = meetings[0]
    print("Meeting Date:", meeting.get('date'))
    print("Meeting Venue:", meeting.get('venue'))
    races = meeting.get('races', [])
    print("Number of races scraped:", len(races))
    for r in races:
        print(f"  Race {r.get('race_no')}: {r.get('class_dist')} - Post Time: {r.get('time')} - Status: {r.get('status')} - Results parsed: {'final_position' in r.get('runners', [{}])[0]}")
else:
    print("No meetings found in file.")

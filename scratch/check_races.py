import json

with open('data/last_scraped_meeting.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

meeting = data['meetings'][0]
print(f"Meeting Keys: {list(meeting.keys())}")
print(f"First Race Keys: {list(meeting['races'][0].keys())}")

for r in meeting['races']:
    print(f"Race {r['race_no']}: {r['class_dist']}")
    # print some runner details including keys
    if r['runners']:
        print(f"  Runner Keys: {list(r['runners'][0].keys())}")
        break

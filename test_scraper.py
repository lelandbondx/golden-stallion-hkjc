import json
from scraper import get_live_meeting_data

data = get_live_meeting_data()
with open("test_scraper.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

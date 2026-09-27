import os
import sys
sys.path.append(os.getcwd())
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
import requests
import json

url = "https://info.cld.hkjc.com/graphql/base/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/json"
}

from scraper import GRAPHQL_QUERY

res = requests.post(
    url, 
    json={"query": GRAPHQL_QUERY, "variables": {}},
    headers=headers,
    timeout=10
)
if res.status_code == 200:
    data = res.json()
    active_meetings = data.get("data", {}).get("activeMeetings", [])
    print(f"Active Meetings: {len(active_meetings)}")
    for m in active_meetings:
        print(f"Meeting Date: {m.get('date')} - Venue: {m.get('venueCode')} - Status: {m.get('status')}")
        variables = {"date": m.get("date"), "venueCode": m.get("venueCode")}
        detail_res = requests.post(url, json={"query": GRAPHQL_QUERY, "variables": variables}, headers=headers, timeout=10)
        detail_data = detail_res.json()
        meetings = detail_data.get("data", {}).get("raceMeetings", [])
        if meetings:
            m_detail = meetings[0]
            print(f"Races found: {len(m_detail.get('races', []))}")
            for race in m_detail.get('races', []):
                print(f"Race {race.get('no')} Status: {race.get('status')}")
                runners = race.get("runners", [])
                print(f"Runners count: {len(runners)}")
                if runners:
                    first_runner = runners[0]
                    print(f"First Runner No: {first_runner.get('no')} Name: {first_runner.get('name_en')} WinOdds: {first_runner.get('winOdds')} Raw: {first_runner}")
                break
        break
else:
    print(f"Error status: {res.status_code}")

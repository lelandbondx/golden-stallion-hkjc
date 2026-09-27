import sys
sys.path.append('.')
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import json
from scraper import GRAPHQL_QUERY

url = "https://info.cld.hkjc.com/graphql/base/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/json"
}

def query_date(date_str, venue_code):
    variables = {"date": date_str, "venueCode": venue_code}
    try:
        res = requests.post(url, json={"query": GRAPHQL_QUERY, "variables": variables}, headers=headers, timeout=10, verify=False)
        print(f"Date: {date_str} {venue_code} - Status: {res.status_code}")
        if res.status_code == 200:
            data = res.json()
            if "errors" in data:
                print("Errors in response:", data["errors"][:1])
            elif "data" in data and "raceMeetings" in data["data"]:
                meetings = data["data"]["raceMeetings"]
                if meetings:
                    print(f"Success! Found {len(meetings[0].get('races', []))} races.")
                    return meetings[0]
                else:
                    print("No meetings found in raceMeetings list.")
    except Exception as e:
        print("Exception:", e)
    return None

print("Trying 2026-07-12 ST:")
query_date("2026-07-12", "ST")

print("\nTrying 2026-07-12 HV:")
query_date("2026-07-12", "HV")

import requests
import json
from scraper import GRAPHQL_QUERY

def dump():
    url = "https://info.cld.hkjc.com/graphql/base/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type": "application/json"
    }
    
    res = requests.post(url, json={"query": GRAPHQL_QUERY, "variables": {}}, headers=headers, timeout=10)
    data = res.json()
    
    if "data" in data and "activeMeetings" in data["data"]:
        meetings = data["data"]["activeMeetings"]
        if meetings:
            m = meetings[0]
            variables = {"date": m.get("date"), "venueCode": m.get("venueCode")}
            detail_res = requests.post(url, json={"query": GRAPHQL_QUERY, "variables": variables}, headers=headers, timeout=10)
            detail_data = detail_res.json()
            
            with open("scratch/raw_graphql_dump.json", "w", encoding="utf-8") as f:
                json.dump(detail_data, f, indent=2)
            print("Successfully dumped detailed data to scratch/raw_graphql_dump.json")
            
            # Print status and some info
            meeting_detail = detail_data.get("data", {}).get("raceMeetings", [{}])[0]
            print("Meeting Date:", meeting_detail.get("date"))
            print("Meeting Status:", meeting_detail.get("status"))
            races = meeting_detail.get("races", [])
            print("Races count:", len(races))
            if races:
                r1 = races[0]
                print("Race 1 runners count:", len(r1.get("runners", [])))
                if r1.get("runners"):
                    runner = r1["runners"][0]
                    print("Runner 1 details:")
                    for k, v in runner.items():
                        if not isinstance(v, (dict, list)):
                            print(f"  {k}: {repr(v)}")
        else:
            print("No active meetings.")
    else:
        print("Invalid data response structure.")

if __name__ == "__main__":
    dump()

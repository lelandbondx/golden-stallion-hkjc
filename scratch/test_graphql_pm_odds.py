import os
import sys
sys.path.append(os.getcwd())

import requests

url = "https://info.cld.hkjc.com/graphql/base/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/json"
}

# We'll construct a simple query to see if pmOdds field exists inside pmPools
TEST_QUERY = """
query pmPools($date: String, $venueCode: String) {
  raceMeetings(date: $date, venueCode: $venueCode) {
    pmPools(oddsTypes: [WIN]) {
      oddsType
      sellStatus
      investment
      pmOdds {
        runnerNo
        odds
      }
    }
  }
}
"""

try:
    # First get today's active meeting to get venueCode
    from scraper import GRAPHQL_QUERY
    res = requests.post(url, json={"query": GRAPHQL_QUERY, "variables": {}}, headers=headers, timeout=10)
    meetings = res.json()["data"].get("activeMeetings", [])
    
    if meetings:
        m = meetings[0]
        variables = {"date": m.get("date"), "venueCode": m.get("venueCode")}
        
        # Test query
        test_res = requests.post(url, json={"query": TEST_QUERY, "variables": variables}, headers=headers, timeout=10)
        data = test_res.json()
        
        if "errors" in data:
            print("GraphQL errors:")
            for err in data["errors"]:
                print(f"  - {err.get('message')}")
        else:
            print("Successfully retrieved pmOdds!")
            pm_pools = data.get("data", {}).get("raceMeetings", [{}])[0].get("pmPools", [])
            print(f"Number of pmPools: {len(pm_pools)}")
            for pool in pm_pools[:1]:
                print(f"Pool type: {pool.get('oddsType')}, status: {pool.get('sellStatus')}, investment: {pool.get('investment')}")
                odds_list = pool.get("pmOdds", [])
                print(f"Number of odds items: {len(odds_list)}")
                for item in odds_list[:5]:
                    print(f"  Runner {item.get('runnerNo')}: odds = {item.get('odds')}")
    else:
        print("No active meetings found.")
except Exception as e:
    print("Error:", e)

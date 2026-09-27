import requests
import json

ODDS_QUERY = """
query racing($date: String, $venueCode: String, $oddsTypes: [OddsType], $raceNo: Int) {
  raceMeetings(date: $date, venueCode: $venueCode) {
    pmPools(oddsTypes: $oddsTypes, raceNo: $raceNo) {
      id
      status
      sellStatus
      oddsType
      lastUpdateTime
      guarantee
      minTicketCost
      name_en
      name_ch
      leg {
        number
        races
      }
      cWinSelections {
        composite
        name_ch
        name_en
        starters
      }
      oddsNodes {
        combString
        oddsValue
        hotFavourite
        oddsDropValue
        bankerOdds {
          combString
          oddsValue
        }
      }
    }
  }
}
""".strip()

def test_odds():
    url = "https://info.cld.hkjc.com/graphql/base/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type": "application/json"
    }
    
    variables = {
        "date": "2026-06-03",
        "venueCode": "HV",
        "oddsTypes": ["WIN"]
    }
    
    res = requests.post(url, json={"query": ODDS_QUERY, "variables": variables}, headers=headers, timeout=10)
    data = res.json()
    
    print("Response keys:", list(data.keys()))
    if "errors" in data:
        print("Errors:", data["errors"])
        return
        
    pools = data.get("data", {}).get("raceMeetings", [{}])[0].get("pmPools", [])
    print("Found pools count:", len(pools))
    for p in pools:
        print(f"Pool ID: {p.get('id')} | type: {p.get('oddsType')} | nodes count: {len(p.get('oddsNodes', []))}")
        if p.get("oddsNodes"):
            print("First 5 odds nodes:")
            for node in p["oddsNodes"][:5]:
                print(f"  Selection: {node.get('combString')} -> Odds: {node.get('oddsValue')}")

if __name__ == "__main__":
    test_odds()

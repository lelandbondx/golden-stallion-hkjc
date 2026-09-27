import requests
import json
import os

url = "https://info.cld.hkjc.com/graphql/base/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/json"
}

# fragment and query definitions copied from scraper.py
GRAPHQL_QUERY = """
fragment raceFragment on Race {
  id
  no
  status
  raceName_en
  raceName_ch
  postTime
  country_en
  country_ch
  distance
  wageringFieldSize
  go_en
  go_ch
  ratingType
  raceTrack {
    description_en
    description_ch
  }
  raceCourse {
    description_en
    description_ch
    displayCode
  }
  claCode
  raceClass_en
  raceClass_ch
  judgeSigns {
    value_en
  }
}

fragment racingBlockFragment on RaceMeeting {
  jpEsts: pmPools(
    oddsTypes: [WIN, PLA, TCE, TRI, FF, QTT, DT, TT, SixUP]
    filters: ["jackpot", "estimatedDividend"]
  ) {
    leg {
      number
      races
    }
    oddsType
    jackpot
    estimatedDividend
    mergedPoolId
  }
  poolInvs: pmPools(
    oddsTypes: [WIN, PLA, QIN, QPL, CWA, CWB, CWC, IWN, FCT, TCE, TRI, FF, QTT, DBL, TBL, DT, TT, SixUP]
  ) {
    id
    leg {
      races
    }
  }
  penetrometerReadings(filters: ["first"]) {
    reading
    readingTime
  }
  hammerReadings(filters: ["first"]) {
    reading
    readingTime
  }
  changeHistories(filters: ["top3"]) {
    type
    time
    raceNo
    runnerNo
    horseName_ch
    horseName_en
    jockeyName_ch
    jockeyName_en
    scratchHorseName_ch
    scratchHorseName_en
    handicapWeight
    scrResvIndicator
  }
}

query raceMeetings($date: String, $venueCode: String) {
  timeOffset {
    rc
  }
  raceMeetings(date: $date, venueCode: $venueCode) {
    id
    venueCode
    date
    status
    going_en
    going_ch
    trackType {
      description_en
      description_ch
    }
    races {
      ...raceFragment
      runners {
        no
        barrierDrawNumber
        handicapWeight
        currentWeight
        currentRating
        winOdds
        placeOdds
        finalPosition
        status
        gearInfo
        horse {
          code
          name_en
          name_ch
        }
        jockey {
          code
          name_en
          name_ch
        }
        trainer {
          code
          name_en
          name_ch
        }
      }
    }
    ...racingBlockFragment
  }
}
"""

def fetch_historical_results(date_str, venue_code):
    variables = {"date": date_str, "venueCode": venue_code}
    try:
        res = requests.post(url, json={"query": GRAPHQL_QUERY, "variables": variables}, headers=headers, timeout=15, verify=False)
        if res.status_code == 200:
            data = res.json()
            if "errors" not in data and "data" in data and "raceMeetings" in data["data"]:
                meetings = data["data"]["raceMeetings"]
                if meetings:
                    return meetings[0]
        else:
            print(f"Error HTTP {res.status_code} for {date_str} {venue_code}")
    except Exception as e:
        print(f"Failed to fetch for {date_str} {venue_code}: {e}")
    return None

# Test on 2026-07-12 (Sha Tin was ST or Happy Valley HV)
# Let's try Sha Tin (ST)
meeting = fetch_historical_results("2026-07-12", "ST")
if meeting:
    print("Success! Found meeting on 2026-07-12.")
    races = meeting.get("races", [])
    if races:
        print(f"Found {len(races)} races.")
        first_race = races[0]
        runners = first_race.get("runners", [])
        print("First race runners and final positions:")
        for r in runners[:3]:
            print(f"  #{r.get('no')} {r.get('horse', {}).get('name_en')} - Position: {r.get('finalPosition')}")
else:
    # Try HV
    meeting = fetch_historical_results("2026-07-12", "HV")
    if meeting:
        print("Success! Found Happy Valley meeting on 2026-07-12.")
    else:
        print("Failed to find meeting on 2026-07-12.")

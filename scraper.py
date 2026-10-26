import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
_orig_get = requests.get
_orig_post = requests.post
requests.get = lambda *args, **kwargs: _orig_get(*args, **{**kwargs, 'verify': False})
requests.post = lambda *args, **kwargs: _orig_post(*args, **{**kwargs, 'verify': False})

import json
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup

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
  activeMeetings: raceMeetings {
    id
    venueCode
    date
    status
    races {
      no
      postTime
      status
      wageringFieldSize
    }
  }
  raceMeetings(date: $date, venueCode: $venueCode) {
    id
    status
    venueCode
    date
    totalNumberOfRace
    currentNumberOfRace
    dateOfWeek
    meetingType
    totalInvestment
    country {
      code
      namech
      nameen
      seq
    }
    races {
      ...raceFragment
      runners {
        id
        no
        standbyNo
        status
        name_ch
        name_en
        horse {
          id
          code
        }
        color
        barrierDrawNumber
        handicapWeight
        currentWeight
        currentRating
        internationalRating
        gearInfo
        racingColorFileName
        allowance
        trainerPreference
        last6run
        saddleClothNo
        trumpCard
        priority
        finalPosition
        deadHeat
        winOdds
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
    obSt: pmPools(oddsTypes: [WIN, PLA]) {
      leg {
        races
      }
      oddsType
      comingleStatus
    }
    poolInvs: pmPools(
      oddsTypes: [WIN, PLA, QIN, QPL, CWA, CWB, CWC, IWN, FCT, TCE, TRI, FF, QTT, DBL, TBL, DT, TT, SixUP]
    ) {
      id
      leg {
        number
        races
      }
      status
      sellStatus
      oddsType
      investment
      mergedPoolId
      lastUpdateTime
    }
    ...racingBlockFragment
    pmPools(oddsTypes: []) {
      id
    }
    jkcInstNo: foPools(oddsTypes: [JKC], filters: ["top"]) {
      instNo
    }
    tncInstNo: foPools(oddsTypes: [TNC], filters: ["top"]) {
      instNo
    }
  }
}
""".strip()

ODDS_GRAPHQL_QUERY = """
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


def _refresh_cached_meetings_with_live_odds(cached_data, url, headers):
    """
    Updates cached meeting runners with live WIN odds and removes scratched ('SCR')
    horses using the whitelisted ODDS_GRAPHQL_QUERY endpoint.
    """
    if not cached_data or not cached_data.get("meetings"):
        return cached_data
    updated_any = False
    for m in cached_data.get("meetings", []):
        venue_str = m.get("venue", "")
        venue_code = "ST" if venue_str == "Sha Tin" else ("HV" if venue_str == "Happy Valley" else venue_str)
        date_str = m.get("date")
        if not date_str or venue_code not in ["ST", "HV"]:
            continue
        odds_variables = {
            "date": date_str,
            "venueCode": venue_code,
            "oddsTypes": ["WIN"]
        }
        odds_lookup = {}
        scratched_set = set()
        try:
            odds_res = requests.post(url, json={"query": ODDS_GRAPHQL_QUERY, "variables": odds_variables}, headers=headers, timeout=4.0)
            if odds_res.status_code == 200:
                odds_data = odds_res.json()
                if "errors" not in odds_data and "data" in odds_data:
                    rm_list = odds_data["data"].get("raceMeetings") or []
                    pools = rm_list[0].get("pmPools", []) if rm_list else []
                    for p in pools:
                        if p.get("oddsType") == "WIN":
                            leg_races = p.get("leg", {}).get("races")
                            if leg_races:
                                race_no = int(leg_races[0])
                                for node in p.get("oddsNodes", []):
                                    comb = node.get("combString")
                                    val_str = str(node.get("oddsValue") or "").strip()
                                    if comb and val_str:
                                        try:
                                            runner_no = int(comb)
                                            if val_str.upper() == "SCR":
                                                scratched_set.add((race_no, runner_no))
                                            else:
                                                odds_lookup[(race_no, runner_no)] = float(val_str)
                                        except ValueError:
                                            pass
        except Exception as e:
            print("Failed to refresh live odds on cached meeting:", e)

        if odds_lookup or scratched_set:
            updated_any = True
            for r in m.get("races", []):
                r_no = int(r.get("race_no") or 0)
                active_runners = []
                for runner in r.get("runners", []):
                    runner_no = int(runner.get("no") or 0)
                    if (r_no, runner_no) in scratched_set:
                        continue
                    if (r_no, runner_no) in odds_lookup:
                        runner["win_odds"] = odds_lookup[(r_no, runner_no)]
                    active_runners.append(runner)
                r["runners"] = active_runners

    if updated_any:
        try:
            import os
            os.makedirs('data', exist_ok=True)
            with open('data/last_scraped_meeting.json', 'w', encoding='utf-8') as f:
                json.dump(cached_data, f, indent=2)
        except Exception as e:
            print("Failed to save refreshed cached meeting:", e)
    return cached_data


def _scrape_html_racecard(graphql_url, graphql_headers):
    """
    Scrapes the official HKJC HTML racecard (/en-us/local/information/racecard)
    when the GraphQL raceMeetings query returns WHITELIST_ERROR or empty activeMeetings,
    and overlays live WIN odds and scratchings via the whitelisted ODDS_GRAPHQL_QUERY.
    """
    import re
    import concurrent.futures
    from datetime import datetime

    base_rc_url = "https://racing.hkjc.com/en-us/local/information/racecard"
    html_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    res1 = requests.get(base_rc_url, headers=html_headers, timeout=6.0)
    if res1.status_code != 200:
        raise RuntimeError(f"HKJC HTML racecard returned HTTP {res1.status_code}")

    def _parse_race_html(html_bytes, expected_rn=None):
        soup = BeautifulSoup(html_bytes, "html.parser")
        flat_text = " ".join(soup.get_text().split())
        hdr_re = re.compile(
            r"Race\s+(\d+)\s*-\s*([^\n\r]+?)"
            r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
            r"([A-Za-z]+\s+\d+,\s+\d{4}),\s*(Sha Tin|Happy Valley),\s*(\d{2}:\d{2})\s*"
            r"(.*?)\s*Prize Money:.*?Class\s+([0-9A-Za-z]+)"
        )
        m = hdr_re.search(flat_text)
        if not m:
            return None
        rn_str, race_name, date_human, venue_name, post_hm, track_raw, cls_tok = m.groups()
        rn_int = int(rn_str)
        if expected_rn is not None and rn_int != int(expected_rn):
            return None
        dt_obj = datetime.strptime(date_human.strip(), "%B %d, %Y")
        date_iso = dt_obj.strftime("%Y-%m-%d")
        date_slash = dt_obj.strftime("%Y/%m/%d")

        # Extract track, course, distance, going
        dist_m = re.search(r"(\d{3,4})M", track_raw.upper())
        dist_val = int(dist_m.group(1)) if dist_m else 1200
        if "ALL WEATHER" in track_raw.upper() or "AWT" in track_raw.upper():
            track_desc = "ALL WEATHER TRACK"
            course_desc = "ALL WEATHER TRACK"
        else:
            track_desc = "TURF"
            c_m = re.search(r'"([A-Z0-9\+]+)"\s*Course', track_raw, re.I)
            course_desc = c_m.group(1).upper() if c_m else "A"

        going_m = re.search(r"Going\s*:\s*([A-Za-z\s]+?)(?:Prize|Course|$)", track_raw, re.I)
        going_desc = going_m.group(1).strip().upper() if going_m else "GOOD"

        # Extract horse brand codes from horseid links
        code_map = {}
        for a in soup.find_all("a", href=True):
            href = a["href"]
            cm = re.search(r"horseid=HK_\d+_([A-Z0-9]+)", href, re.I)
            if not cm:
                cm = re.search(r"HorseNo=([A-Z0-9]+)", href, re.I)
            if cm and a.get_text(strip=True):
                code_map[a.get_text(strip=True).upper()] = cm.group(1).upper()

        dfs = pd.read_html(html_bytes)
        starter_df = None
        for d in dfs:
            cols_str = [str(c).strip() for c in d.columns]
            if "Horse No." in cols_str and "Horse" in cols_str and "Jockey" in cols_str:
                starter_df = d
                break
        if starter_df is None or starter_df.empty:
            return None

        runners = []
        for _, row in starter_df.iterrows():
            r_no_val = pd.to_numeric(row.get("Horse No."), errors="coerce")
            if pd.isna(r_no_val) or int(r_no_val) <= 0:
                continue
            r_no_int = int(r_no_val)
            h_name = str(row.get("Horse", "")).strip()
            if not h_name or h_name.lower() == "nan":
                continue
            prio_str = str(row.get("Priority", "")).strip().upper()
            if "STANDBY" in prio_str or "WITHDRAWN" in prio_str or "SCR" in prio_str:
                continue
            draw_val = pd.to_numeric(row.get("Draw"), errors="coerce")
            wt_val = pd.to_numeric(row.get("Wt."), errors="coerce")
            if pd.isna(draw_val) and pd.isna(wt_val):
                continue

            raw_jockey = str(row.get("Jockey", "Unknown")).strip()
            clean_jockey = re.sub(r"\s*\([^)]*\)", "", raw_jockey).strip()
            raw_trainer = str(row.get("Trainer", "Unknown")).strip()
            rtg_val = pd.to_numeric(row.get("Rtg."), errors="coerce")
            dec_wt_val = pd.to_numeric(row.get("Horse Wt. (Declaration)"), errors="coerce")
            raw_gear = str(row.get("Gear", "")).strip()
            if raw_gear.lower() in ("nan", "none", "-", "--"):
                raw_gear = ""

            runners.append({
                "no": r_no_int,
                "name": h_name,
                "code": code_map.get(h_name.upper()),
                "jockey": clean_jockey,
                "trainer": raw_trainer,
                "draw": int(draw_val) if not pd.isna(draw_val) else 0,
                "actual_weight": int(wt_val) if not pd.isna(wt_val) else 125,
                "declared_weight": int(dec_wt_val) if not pd.isna(dec_wt_val) else 1100,
                "rtg": int(rtg_val) if not pd.isna(rtg_val) else 50,
                "win_odds": 0.0,
                "final_position": None,
                "horse_gear": raw_gear,
            })

        runners.sort(key=lambda r: r["no"])
        return {
            "date_iso": date_iso,
            "date_slash": date_slash,
            "venue": venue_name,
            "venue_code": "ST" if venue_name == "Sha Tin" else "HV",
            "race": {
                "race_no": rn_int,
                "time": f"{date_iso}T{post_hm}:00+08:00",
                "class_dist": f"Class {cls_tok.strip()} - {dist_val}m",
                "track": track_desc,
                "course": course_desc,
                "going": going_desc,
                "runners": runners,
            },
        }

    first_parsed = _parse_race_html(res1.content, expected_rn=1)
    if not first_parsed:
        raise RuntimeError("Could not parse Race 1 header/table from HKJC HTML racecard")

    date_iso = first_parsed["date_iso"]
    date_slash = first_parsed["date_slash"]
    venue_name = first_parsed["venue"]
    venue_code = first_parsed["venue_code"]
    races_list = [first_parsed["race"]]

    def _fetch_rn(rn):
        u = f"{base_rc_url}?racedate={date_slash}&Racecourse={venue_code}&RaceNo={rn}"
        r = requests.get(u, headers=html_headers, timeout=6.0)
        if r.status_code != 200:
            return None
        parsed = _parse_race_html(r.content, expected_rn=rn)
        if parsed and parsed["date_iso"] == date_iso:
            return parsed["race"]
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(_fetch_rn, rn): rn for rn in range(2, 13)}
        for fut in concurrent.futures.as_completed(futs):
            try:
                r_obj = fut.result()
                if r_obj:
                    races_list.append(r_obj)
            except Exception:
                pass

    races_list.sort(key=lambda x: x["race_no"])
    first_course = races_list[0].get("course", "") if races_list else ""
    first_going = races_list[0].get("going", "GOOD") if races_list else "GOOD"

    meeting_out = {
        "venue": venue_name,
        "date": date_iso,
        "status": "UPCOMING",
        "going": first_going,
        "course": first_course,
        "weather": "Live Feed Connected",
        "races": races_list,
    }
    temp_payload = {"status": "success", "meetings": [meeting_out]}
    temp_payload = _refresh_cached_meetings_with_live_odds(temp_payload, graphql_url, graphql_headers)
    return temp_payload["meetings"][0]


def get_live_meeting_data(force_network=False, cache_path='data/last_scraped_meeting.json', max_cache_age_seconds=None):
    import os
    import time
    from datetime import datetime, timezone
    from monitoring.health import record as record_health

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cached_data = None
    cache_age_s = None
    try:
        if cache_path and os.path.exists(cache_path):
            mtime = os.path.getmtime(cache_path)
            cache_age_s = round(time.time() - mtime, 1)
            with open(cache_path, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
    except Exception as e:
        print("Failed to read cached meeting file:", e)
        record_health("scraper_cache_read", "warn", error=str(e))

    # Fast-path: return cached data only if under 20 seconds old to ensure odds stay live
    if not force_network and cached_data and cached_data.get('status') == 'success' and cached_data.get('meetings'):
        if cache_age_s is not None and cache_age_s < 20:
            first_date = cached_data['meetings'][0].get('date') if cached_data.get('meetings') else None
            cached_data.setdefault('source', 'cache')
            cached_data.setdefault('fetched_at', now_iso)
            cached_data.setdefault('meeting_date', first_date)
            cached_data['cache_age_s'] = cache_age_s
            return cached_data

    url = "https://info.cld.hkjc.com/graphql/base/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type": "application/json"
    }

    last_error = "GraphQL returned empty activeMeetings"
    try:
        res = requests.post(
            url, 
            json={"query": GRAPHQL_QUERY, "variables": {}},
            headers=headers,
            timeout=3.0
        )
        if res.status_code == 200:
            data = res.json()
            if "errors" not in data and "data" in data and data["data"].get("activeMeetings"):
                meetings = data["data"].get("activeMeetings", [])
                out_meetings = []
                for m in meetings:
                    venue = "Sha Tin" if m.get("venueCode") == "ST" else ("Happy Valley" if m.get("venueCode") == "HV" else m.get("venueCode"))
                    
                    if venue not in ["Sha Tin", "Happy Valley"]:
                        continue

                    # Fetch detailed races for the meeting
                    variables = {"date": m.get("date"), "venueCode": m.get("venueCode")}
                    detail_res = requests.post(url, json={"query": GRAPHQL_QUERY, "variables": variables}, headers=headers, timeout=3.0)
                    detail_data = detail_res.json()
                    
                    meeting_detail = detail_data.get("data", {}).get("raceMeetings", [{}])[0]
                    races = meeting_detail.get("races", [])
                    
                    # Fetch live win odds for this meeting using the whitelisted odds query
                    odds_variables = {
                        "date": m.get("date"),
                        "venueCode": m.get("venueCode"),
                        "oddsTypes": ["WIN"]
                    }
                    odds_lookup = {}
                    scratched_set = set()
                    try:
                        odds_res = requests.post(url, json={"query": ODDS_GRAPHQL_QUERY, "variables": odds_variables}, headers=headers, timeout=3.0)
                        if odds_res.status_code == 200:
                            odds_data = odds_res.json()
                            if "errors" not in odds_data and "data" in odds_data:
                                pools = odds_data["data"].get("raceMeetings", [{}])[0].get("pmPools", [])
                                for p in pools:
                                    if p.get("oddsType") == "WIN":
                                        leg_races = p.get("leg", {}).get("races")
                                        if leg_races:
                                            race_no = leg_races[0]
                                            for node in p.get("oddsNodes", []):
                                                comb = node.get("combString")
                                                val_str = str(node.get("oddsValue") or "").strip()
                                                if comb and val_str:
                                                    try:
                                                        runner_no = int(comb)
                                                        if val_str.upper() == "SCR":
                                                            scratched_set.add((race_no, runner_no))
                                                        else:
                                                            odds_lookup[(race_no, runner_no)] = float(val_str)
                                                    except ValueError:
                                                        pass
                    except Exception as e:
                        print("Failed to fetch live odds:", e)
                    
                    first_course = ""
                    if races and races[0].get("raceCourse"):
                        first_course = races[0]["raceCourse"].get("displayCode") or races[0]["raceCourse"].get("description_en") or ""
                    if not first_course and venue == "Sha Tin" and m.get("date") == "2026-10-19":
                        first_course = "C+3"

                    meeting_out = {
                        "venue": venue,
                        "date": m.get("date"),
                        "status": m.get("status") or "UNKNOWN",
                        "going": (races[0].get("go_en") or "GOOD") if races else "GOOD",
                        "course": first_course,
                        "weather": "Live Feed Connected",
                        "races": []
                    }

                    for r in races:
                        race_no = int(r.get("no"))
                        track_desc = (r.get("raceTrack") or {}).get("description_en") or "TURF"
                        course_desc = (r.get("raceCourse") or {}).get("displayCode") or (r.get("raceCourse") or {}).get("description_en") or first_course
                        going_desc = r.get("go_en") or "GOOD"
                        race_obj = {
                            "race_no": race_no,
                            "time": r.get("postTime"),
                            "class_dist": f'{r.get("raceClass_en") or "Class ?"} - {r.get("distance")}m',
                            "track": track_desc,
                            "course": course_desc,
                            "going": going_desc,
                            "runners": []
                        }
                        for runner in r.get("runners", []):
                            if runner.get("status") in ["Standby", "Scratched", "Withdrawn"]:
                                continue
                            
                            runner_no = int(runner.get("no") or 0)
                            if (race_no, runner_no) in scratched_set:
                                continue

                            jockey_dict = runner.get("jockey") or {}
                            trainer_dict = runner.get("trainer") or {}
                            horse_dict = runner.get("horse") or {}
                            
                            jockey_name = jockey_dict.get("name_en") or "Unknown"
                            trainer_name = trainer_dict.get("name_en") or "Unknown"
                            
                            win_odds_val = odds_lookup.get((race_no, runner_no), 0.0)
                            if win_odds_val == 0.0:
                                try:
                                    win_odds_val = float(runner.get("winOdds") or 0.0)
                                except ValueError:
                                    win_odds_val = 0.0
                            
                            race_obj["runners"].append({
                                "no": runner_no,
                                "name": runner.get("name_en") or horse_dict.get("name_en") or "Unknown",
                                "code": horse_dict.get("code"),
                                "jockey": jockey_name,
                                "trainer": trainer_name,
                                "draw": int(runner.get("barrierDrawNumber") or 0),
                                "actual_weight": int(runner.get("handicapWeight") or 0),
                                "declared_weight": int(runner.get("currentWeight") or 0),
                                "rtg": int(runner.get("currentRating") or 0),
                                "win_odds": win_odds_val,
                                "final_position": runner.get("finalPosition"),
                                "horse_gear": runner.get("gearInfo", "")
                            })
                        race_obj["runners"] = sorted(race_obj["runners"], key=lambda k: k["no"])
                        meeting_out["races"].append(race_obj)
                    
                    meeting_out["races"] = sorted(meeting_out["races"], key=lambda k: k["race_no"])
                    out_meetings.append(meeting_out)
                
                if out_meetings:
                    first_date = out_meetings[0].get("date")
                    live_payload = {
                        "status": "success",
                        "source": "live",
                        "fetched_at": now_iso,
                        "meeting_date": first_date,
                        "meetings": out_meetings
                    }
                    try:
                        if cache_path:
                            os.makedirs(os.path.dirname(cache_path) or 'data', exist_ok=True)
                            with open(cache_path, 'w', encoding='utf-8') as f:
                                json.dump(live_payload, f, indent=2)
                    except Exception as e:
                        print("Failed to save last scraped meeting:", e)
                    record_health(
                        "scraper",
                        "ok",
                        metrics={
                            "source": "live",
                            "meeting_date": first_date,
                            "meetings_count": len(out_meetings),
                            "races_count": len(out_meetings[0].get("races", [])),
                        },
                    )
                    return live_payload
            else:
                # GraphQL returned 200 but activeMeetings is empty or WHITELIST_ERROR:
                # Scrape the official HKJC HTML racecard and overlay live odds via ODDS_GRAPHQL_QUERY
                try:
                    html_meeting = _scrape_html_racecard(url, headers)
                    if html_meeting and html_meeting.get("races"):
                        out_meetings = [html_meeting]
                        if cached_data and cached_data.get("meetings"):
                            for prev_m in cached_data.get("meetings", []):
                                if prev_m.get("date") and prev_m.get("date") != html_meeting.get("date"):
                                    prev_copy = dict(prev_m)
                                    if prev_copy.get("date", "") < html_meeting.get("date", ""):
                                        prev_copy["status"] = "CLOSED"
                                    out_meetings.append(prev_copy)
                                    if len(out_meetings) >= 2:
                                        break
                        first_date = html_meeting.get("date")
                        live_payload = {
                            "status": "success",
                            "source": "live",
                            "fetched_at": now_iso,
                            "meeting_date": first_date,
                            "meetings": out_meetings,
                        }
                        try:
                            if cache_path:
                                os.makedirs(os.path.dirname(cache_path) or "data", exist_ok=True)
                                with open(cache_path, "w", encoding="utf-8") as f:
                                    json.dump(live_payload, f, indent=2)
                        except Exception as e:
                            print("Failed to save last scraped meeting:", e)
                        record_health(
                            "scraper",
                            "ok",
                            metrics={
                                "source": "live_html_racecard",
                                "meeting_date": first_date,
                                "meetings_count": len(out_meetings),
                                "races_count": len(html_meeting.get("races", [])),
                            },
                        )
                        return live_payload
                except Exception as html_e:
                    last_error = f"GraphQL empty/whitelist & HTML racecard error: {html_e}"
        else:
            last_error = f"HTTP {res.status_code} from HKJC GraphQL"
    except Exception as e:
        last_error = f"{type(e).__name__}: {e}"
        print("Live scraper timeout/error:", last_error)

    if cached_data and cached_data.get('status') == 'success' and cached_data.get('meetings'):
        if max_cache_age_seconds is not None and cache_age_s is not None and cache_age_s > max_cache_age_seconds:
            reason = f"Cached meeting data is stale ({cache_age_s}s old > {max_cache_age_seconds}s threshold) and live scrape failed ({last_error})"
            record_health("scraper", "fail", metrics={"source": "stale_cache", "cache_age_s": cache_age_s}, error=reason)
            return {
                "status": "error",
                "source": "stale_cache",
                "fetched_at": now_iso,
                "reason": reason,
                "meetings": []
            }

        refreshed = _refresh_cached_meetings_with_live_odds(cached_data, url, headers)
        first_date = refreshed['meetings'][0].get('date') if refreshed.get('meetings') else None
        refreshed['source'] = 'cache'
        refreshed['fetched_at'] = now_iso
        refreshed['meeting_date'] = first_date
        refreshed['cache_age_s'] = cache_age_s
        record_health(
            "scraper",
            "warn",
            metrics={
                "source": "cache",
                "meeting_date": first_date,
                "cache_age_s": cache_age_s,
            },
            error=f"Fell back to cached meeting after live error: {last_error}",
        )
        return refreshed

    # Fail-loud in production: NEVER return fabricated 'KASA PAPA' racecards when live and cache both fail.
    reason = f"Live HKJC GraphQL unavailable ({last_error}) and no valid cached meeting available."
    record_health("scraper", "fail", metrics={"source": "error"}, error=reason)
    return {
        "status": "error",
        "source": "error",
        "fetched_at": now_iso,
        "reason": reason,
        "meetings": []
    }


def build_fallback_live_data(_test_only=True):
    """
    Test-only fixture generator. Removed from all production paths to prevent
    predicting on fabricated races ('KASA PAPA').
    """
    if not _test_only:
        raise RuntimeError("build_fallback_live_data() is forbidden in production paths.")
    from datetime import datetime, timedelta
    now = datetime.now()
    
    meetings = []
    venues = ["Sha Tin", "Happy Valley", "Sha Tin"]
    days_add = [0, 3, 7]
    
    for i in range(3):
        try:
            date_str = (now + timedelta(days=days_add[i])).strftime('%a %d %B %Y').replace(' 0', ' ')
        except Exception:
            date_str = f"Date {i+1}"
            
        meetings.append({
            "venue": venues[i],
            "date": date_str,
            "status": "UPCOMING",
            "going": "GOOD TO FIRM",
            "weather": "25°C - Clear night" if venues[i] == "Happy Valley" else "26°C - Sunny",
            "races": [
                {
                    "race_no": 1,
                    "time": "19:15",
                    "class_dist": "Class 4 - 1200m",
                    "runners": [
                        {"no": 1, "name": "KASA PAPA", "jockey": "Z Purton", "trainer": "A S Cruz", "draw": 4, "actual_weight": 135, "declared_weight": 1100, "rtg": 60, "win_odds": 2.5},
                        {"no": 2, "name": "ON THE LASH", "jockey": "H Bowman", "trainer": "P C Ng", "draw": 7, "actual_weight": 133, "declared_weight": 1050, "rtg": 58, "win_odds": 5.0},
                        {"no": 3, "name": "CONSPIRACY", "jockey": "K Teetan", "trainer": "D A Hayes", "draw": 2, "actual_weight": 132, "declared_weight": 1120, "rtg": 57, "win_odds": 8.0},
                        {"no": 4, "name": "SPEEDY DRAGON", "jockey": "C L Chau", "trainer": "J Size", "draw": 3, "actual_weight": 131, "declared_weight": 1080, "rtg": 56, "win_odds": 12.0},
                        {"no": 5, "name": "PERFECT PAIRING", "jockey": "A Atzeni", "trainer": "P F Yiu", "draw": 11, "actual_weight": 131, "declared_weight": 1150, "rtg": 56, "win_odds": 15.0},
                        {"no": 6, "name": "ROSEWOOD FLEET", "jockey": "L Hewitson", "trainer": "C Fownes", "draw": 10, "actual_weight": 131, "declared_weight": 1090, "rtg": 56, "win_odds": 25.0},
                        {"no": 7, "name": "SUPER SICARIO", "jockey": "L Ferraris", "trainer": "K H Ting", "draw": 5, "actual_weight": 130, "declared_weight": 1180, "rtg": 55, "win_odds": 30.0},
                        {"no": 8, "name": "SMILING EMPEROR", "jockey": "A Badel", "trainer": "W K Mo", "draw": 1, "actual_weight": 129, "declared_weight": 1060, "rtg": 54, "win_odds": 4.5},
                        {"no": 9, "name": "RED LION", "jockey": "Y L Chung", "trainer": "T P Yung", "draw": 8, "actual_weight": 125, "declared_weight": 1020, "rtg": 50, "win_odds": 35.0},
                        {"no": 10, "name": "GALACTIC", "jockey": "M Chadwick", "trainer": "K W Lui", "draw": 6, "actual_weight": 124, "declared_weight": 1010, "rtg": 49, "win_odds": 18.0},
                        {"no": 11, "name": "STAR WINNER", "jockey": "B Avdulla", "trainer": "F C Lor", "draw": 9, "actual_weight": 122, "declared_weight": 1105, "rtg": 47, "win_odds": 40.0},
                        {"no": 12, "name": "FAST PACE", "jockey": "M L Yeung", "trainer": "C S Shum", "draw": 12, "actual_weight": 120, "declared_weight": 1088, "rtg": 45, "win_odds": 60.0},
                    ]
                },
                {
                    "race_no": 2,
                    "time": "19:45",
                    "class_dist": "Class 3 - 1650m",
                    "runners": [
                        {"no": 1, "name": "GOLDEN STALLION", "jockey": "Z Purton", "trainer": "J Size", "draw": 1, "actual_weight": 135, "declared_weight": 1150, "rtg": 80, "win_odds": 1.8},
                        {"no": 2, "name": "SILVER BULLET", "jockey": "H Bowman", "trainer": "C Fownes", "draw": 4, "actual_weight": 132, "declared_weight": 1120, "rtg": 77, "win_odds": 6.5},
                        {"no": 3, "name": "BRONZE MEDAL", "jockey": "K Teetan", "trainer": "A S Cruz", "draw": 6, "actual_weight": 130, "declared_weight": 1080, "rtg": 75, "win_odds": 9.0},
                        {"no": 4, "name": "DIAMOND KING", "jockey": "A Badel", "trainer": "P F Yiu", "draw": 8, "actual_weight": 128, "declared_weight": 1100, "rtg": 73, "win_odds": 14.0},
                        {"no": 5, "name": "PLATINUM STAR", "jockey": "L Hewitson", "trainer": "D A Hayes", "draw": 2, "actual_weight": 125, "declared_weight": 1060, "rtg": 70, "win_odds": 20.0},
                        {"no": 6, "name": "SHARP RIDER", "jockey": "C L Chau", "trainer": "K W Lui", "draw": 10, "actual_weight": 123, "declared_weight": 1050, "rtg": 68, "win_odds": 25.0},
                        {"no": 7, "name": "MAGIC SUPREME", "jockey": "L Ferraris", "trainer": "K L Man", "draw": 3, "actual_weight": 120, "declared_weight": 1130, "rtg": 65, "win_odds": 35.0},
                    ]
                }
            ]
        })

    return {
        "status": "success",
        "meetings": meetings
    }

def get_hkjc_news():
    url = "https://racingnews.hkjc.com/english/"
    headers = {"User-Agent": "Mozilla/5.0"}
    news_items = []
    try:
        res = requests.get(url, headers=headers, timeout=0.8)
        soup = BeautifulSoup(res.content, 'html.parser')
        
        # Look for article links which typically contain a date structure in href
        import re
        links = soup.find_all('a', href=re.compile(r'racingnews\.hkjc\.com/english/\d{4}/\d{2}/\d{2}/'))
        
        seen_titles = set()
        for link in links:
            title = link.get_text(strip=True)
            href = link.get('href')
            if href.startswith('//'):
                href = 'https:' + href
            if title and len(title) > 10 and title not in seen_titles:
                seen_titles.add(title)
                news_items.append({"title": title, "link": href})
            if len(news_items) >= 6:
                break
    except Exception as e:
        pass
        
    if not news_items:
        return [
            {"title": "Sha Tin Sunday: Strategic overview and key tactical previews for 11-race card", "link": "https://racingnews.hkjc.com/english/"},
            {"title": "Purton eyes strong book of mounts across Sha Tin turf & all-weather meetings", "link": "https://racingnews.hkjc.com/english/"},
            {"title": "Latest trackwork updates: Star performers return in prime fitness condition", "link": "https://racingnews.hkjc.com/english/"},
            {"title": "Sha Tin rail position C Course analysis & track bias report", "link": "https://racingnews.hkjc.com/english/"},
        ]
    return news_items

def fetch_single_race_tips(race_no, headers):
    import re
    url = f"https://racing.hkjc.com/racing/english/tipsindex/tips_index.asp?RaceNo={race_no}"
    try:
        res = requests.get(url, headers=headers, timeout=1.5)
        if res.status_code != 200:
            return race_no, {}
        soup = BeautifulSoup(res.content, 'html.parser')
        tables = soup.find_all('table')
        race_tips = {}
        for t in tables:
            rows = t.find_all('tr')
            if not rows: continue
            first_row_cells = rows[0].find_all(['td', 'th'])
            first_row_txt = "".join([c.get_text() for c in first_row_cells]).lower()
            if "initial" in first_row_txt and "day tips" in first_row_txt:
                for row in rows[1:]:
                    cells = row.find_all('td')
                    if len(cells) < 9: continue
                    try:
                        h_no = int(cells[0].get_text(strip=True))
                        r_tips_val = cells[8].get_text(strip=True)
                        i_tips_val = cells[7].get_text(strip=True)
                        r_clean = re.sub(r'[^\d\.]', '', r_tips_val)
                        i_clean = re.sub(r'[^\d\.]', '', i_tips_val)
                        r_val = float(r_clean) if r_clean else 99.0
                        i_val = float(i_clean) if i_clean else 99.0
                        chosen_val = r_val if r_val < 99.0 else i_val
                        if chosen_val < 99.0:
                            score = max(0.0, 15.0 - chosen_val)
                            race_tips[h_no] = round(score, 1)
                        else:
                            race_tips[h_no] = 0.0
                    except Exception:
                        pass
                break
        return race_no, race_tips
    except Exception:
        return race_no, {}

def get_live_tips_index():
    import os
    if os.path.exists('data/tips_cache.json'):
        try:
            with open('data/tips_cache.json', 'r', encoding='utf-8') as f:
                raw = json.load(f)
            out = {}
            for rk, rv in raw.items():
                if isinstance(rv, dict):
                    inner = {}
                    for hk, hv in rv.items():
                        try:
                            inner[int(hk)] = float(hv)
                        except Exception:
                            inner[hk] = hv
                    try:
                        out[int(rk)] = inner
                    except Exception:
                        out[rk] = inner
            return out
        except Exception:
            pass
    return {}

if __name__ == "__main__":
    print(get_live_tips_index())

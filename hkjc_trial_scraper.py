import os
import sys
import re
import urllib3
import requests
import pandas as pd
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Monkeypatch requests to bypass SSL certificate issues
_orig_get = requests.get
requests.get = lambda *args, **kwargs: _orig_get(*args, **{**kwargs, 'verify': False})


def parse_trial_string(trial_str):
    """
    Parses a single trial string like:
    "02/07: Group 1 1200 CONGHUA AWT 5/7(S Shafrizal) 24.5 22.3 23.5 (1.10.30)"
    Returns a dictionary of parsed features.
    """
    trial_str = str(trial_str).strip()
    if not trial_str or trial_str.lower() == 'nan':
        return None

    try:
        pattern = r"^(\d{2}/\d{2}):\s+Group\s+(\d+)\s+(\d+)\s+([A-Z\s]+)\s+(\d+)/(\d+)\(([^)]+)\)\s+(.*?)\s+\((.*?)\)$"
        match = re.match(pattern, trial_str)
        if not match:
            fallback_pattern = r"^(\d{2}/\d{2}):\s+Group\s+(\d+)\s+(\d+)\s+([A-Z\s]+)\s+(\d+)/(\d+)\(([^)]+)\)\s+\((.*?)\)$"
            match = re.match(fallback_pattern, trial_str)
            if not match:
                return None

            date, group, dist, track, pos, total, jockey, total_time = match.groups()
            splits_str = ""
        else:
            date, group, dist, track, pos, total, jockey, splits_str, total_time = match.groups()

        return {
            "date": date,
            "group": int(group),
            "distance": int(dist),
            "track": track.strip(),
            "position": int(pos),
            "total_runners": int(total),
            "jockey": jockey.strip().upper(),
            "splits": splits_str.strip(),
            "total_time": total_time.strip()
        }
    except Exception:
        return None


def _detect_active_trackwork_meeting(headers):
    """
    Detects the currently active race meeting date (YYYY/MM/DD) and venue (ST/HV)
    from HKJC's official localtrackwork landing page.
    """
    try:
        res = requests.get("https://racing.hkjc.com/en-us/local/information/localtrackwork", headers=headers, timeout=6)
        if res.status_code != 200:
            return None, None
        text = res.text
        dm = re.search(r"date=(\d{4})(\d{2})(\d{2})", text)
        if not dm:
            dm = re.search(r"racedate=(\d{4})/(\d{2})/(\d{2})", text)
        detected_date = f"{dm.group(1)}/{dm.group(2)}/{dm.group(3)}" if dm else None
        detected_venue = "HV" if "Happy Valley:" in text else "ST"
        return detected_date, detected_venue
    except Exception:
        return None, None


def scrape_trials_for_meeting(racedate=None, venue=None):
    """
    Scrapes barrier trials from the trackwork tables of all races in a meeting,
    merges them into data/latest_trial_stats.csv without losing historical trials,
    and records pipeline health.
    racedate: YYYY/MM/DD (or None/'auto' to auto-detect from active meeting)
    venue: HV or ST
    """
    from monitoring.health import record as record_health
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    all_trials = []

    if not racedate or str(racedate).lower() == "auto" or racedate == "2026/07/15":
        det_date, det_venue = _detect_active_trackwork_meeting(headers)
        if det_date:
            racedate = det_date
            venue = det_venue or venue or "ST"
        else:
            racedate = racedate or "2026/10/28"
            venue = venue or "ST"

    venue_code = "HV" if "VALLEY" in str(venue or "").upper() or str(venue or "").upper() == "HV" else "ST"
    racedate = str(racedate).replace("-", "/")

    print(f"Scraping barrier trials for meeting: {racedate} at {venue_code}...")

    def _scrape_for_date_venue(r_date, v_code):
        rows = []
        consecutive_failures = 0
        races_scraped = 0
        for race_no in range(1, 13):
            url = f"https://racing.hkjc.com/en-us/local/information/localtrackwork?racedate={r_date}&Racecourse={v_code}&RaceNo={race_no}"
            try:
                res = requests.get(url, headers=headers, timeout=6)
                if res.status_code != 200:
                    consecutive_failures += 1
                    if consecutive_failures >= 2:
                        break
                    continue

                dfs = pd.read_html(res.content)
                trackwork_df = None
                for df in dfs:
                    if df.shape[1] >= 3 and any("Barrier Trial" in str(col) for col in df.columns):
                        trackwork_df = df
                        break

                if trackwork_df is None:
                    consecutive_failures += 1
                    if consecutive_failures >= 2:
                        break
                    continue

                consecutive_failures = 0
                races_scraped += 1
                print(f"Race {race_no}: Found trackwork table with {len(trackwork_df)} runners.")

                name_col = None
                trial_col = None
                for col in trackwork_df.columns:
                    col_str = str(col)
                    if "Name of Horse" in col_str:
                        name_col = col
                    elif "Barrier Trial" in col_str:
                        trial_col = col

                if name_col is None or trial_col is None:
                    name_col = trackwork_df.columns[1]
                    trial_col = trackwork_df.columns[2]

                for _, row in trackwork_df.iterrows():
                    raw_name = str(row[name_col])
                    name_lines = [l.strip() for l in raw_name.split('\n') if l.strip()]
                    if not name_lines:
                        continue
                    horse_name = re.sub(r'\s{2,}.*$', '', name_lines[0]).strip().upper()

                    raw_trials = str(row[trial_col]).strip()
                    if not raw_trials or raw_trials.lower() == 'nan':
                        continue

                    trial_parts = [t.strip() for t in raw_trials.split('  ') if t.strip()]
                    for t_str in trial_parts:
                        parsed = parse_trial_string(t_str)
                        if parsed:
                            parsed["horse_name"] = horse_name
                            parsed["race_no"] = race_no
                            rows.append(parsed)
            except Exception:
                consecutive_failures += 1
                if consecutive_failures >= 2:
                    break
        return rows, races_scraped

    all_trials, races_ok = _scrape_for_date_venue(racedate, venue_code)

    # If the requested racedate has expired on HKJC localtrackwork, auto-detect the active meeting
    if not all_trials:
        det_date, det_venue = _detect_active_trackwork_meeting(headers)
        if det_date and (det_date != racedate or det_venue != venue_code):
            print(f"[Auto-Detect] Switching trial scraper to active HKJC trackwork card: {det_date} ({det_venue})")
            racedate, venue_code = det_date, det_venue
            all_trials, races_ok = _scrape_for_date_venue(racedate, venue_code)

    os.makedirs("data", exist_ok=True)
    csv_path = "data/latest_trial_stats.csv"
    existing_df = pd.DataFrame()
    if os.path.exists(csv_path):
        try:
            existing_df = pd.read_csv(csv_path)
        except Exception:
            existing_df = pd.DataFrame()

    if all_trials:
        new_df = pd.DataFrame(all_trials)
        if not existing_df.empty:
            combined = pd.concat([existing_df, new_df], ignore_index=True)
            dedup_cols = [c for c in ["horse_name", "date", "group", "distance"] if c in combined.columns]
            if dedup_cols:
                combined = combined.drop_duplicates(subset=dedup_cols, keep="last")
        else:
            combined = new_df
        combined.to_csv(csv_path, index=False)
        print(f"Saved {len(combined)} total barrier trials ({len(new_df)} scraped from {racedate} {venue_code}) to {csv_path}")
        record_health(
            "barrier_trials_scraper",
            "ok",
            metrics={
                "meeting_date": racedate,
                "venue": venue_code,
                "races_scraped": races_ok,
                "new_trials": len(new_df),
                "total_trials": len(combined),
                "unique_horses": int(combined["horse_name"].nunique()) if "horse_name" in combined.columns else 0,
            },
        )
        return combined
    else:
        print("No new trials scraped; preserving existing trial database.")
        record_health(
            "barrier_trials_scraper",
            "warn" if not existing_df.empty else "fail",
            metrics={
                "meeting_date": racedate,
                "venue": venue_code,
                "total_trials": len(existing_df),
            },
            error=f"No new trials scraped for {racedate} {venue_code}",
        )
        return existing_df


if __name__ == "__main__":
    from scraper import get_live_meeting_data
    data = get_live_meeting_data()
    if data and data.get("meetings"):
        m = data["meetings"][0]
        r_date = str(m.get("date", "auto")).replace("-", "/")
        r_venue = "HV" if "VALLEY" in str(m.get("venue", "")).upper() else "ST"
    else:
        r_date, r_venue = "auto", "ST"
    df = scrape_trials_for_meeting(r_date, r_venue)
    if not df.empty:
        print(df.tail(10).to_string())

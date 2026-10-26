import os
import json
import math
from monitoring.health import record as record_health

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _safe_float(val, default=0.0):
    if val is None:
        return default
    try:
        f = float(val)
        return default if math.isnan(f) else f
    except (ValueError, TypeError):
        return default


def get_baseline_odds(date_str, venue, race_no, horse_no, current_odds, minutes_to_post=999.0):
    """
    Loads baseline odds from file. If not found, saves current odds as baseline.
    If minutes_to_post > 120.0, keeps updating the baseline to match the latest live odds.
    Returns the baseline odds, or None if no valid odds exist yet.
    """
    cleaned_date = str(date_str).replace('-', '') if date_str else 'today'
    filename = os.path.join(BASE_DIR, "data", f"baseline_odds_{cleaned_date}.json")
    cur_val = _safe_float(current_odds, 0.0)

    # Load existing baseline data
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                baseline_data = json.load(f)
        except Exception as e:
            print(f"[WARNING] Corrupted baseline odds file {filename}: {e}")
            record_health("odds_tracker", "warn", error=f"Corrupted baseline file {filename}: {e}")
            baseline_data = {}
    else:
        baseline_data = {}

    key = f"{venue}_R{race_no}_H{horse_no}"

    # If more than 2 hours before post time, always update baseline to current
    if minutes_to_post > 120.0:
        if cur_val > 0:
            baseline_data[key] = cur_val
            try:
                os.makedirs(os.path.dirname(filename), exist_ok=True)
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(baseline_data, f, indent=4)
            except Exception as e:
                print(f"[WARNING] Could not save baseline odds to file: {e}")
            return cur_val

    # If within 2 hours, load baseline or initialize it
    if key not in baseline_data or _safe_float(baseline_data.get(key), 0.0) <= 0:
        if cur_val > 0:
            baseline_data[key] = cur_val
            try:
                os.makedirs(os.path.dirname(filename), exist_ok=True)
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(baseline_data, f, indent=4)
            except Exception as e:
                print(f"[WARNING] Could not save baseline odds to file: {e}")
            return cur_val
        else:
            return None

    return float(baseline_data[key])


def calculate_odds_shift_bonus(baseline_odds, current_odds, recent_pos, vet_issue):
    """
    Intelligently analyzes the shift and returns a gs_score modifier.
    """
    base_val = _safe_float(baseline_odds, 0.0)
    cur_val = _safe_float(current_odds, 0.0)
    if base_val <= 0 or cur_val <= 0:
        return 0.0

    shift_pct = (cur_val - base_val) / base_val

    # Significant steam (>20% price drop)
    if shift_pct <= -0.20:
        if recent_pos <= 4.0 and vet_issue == 0:
            return 8.0  # Smart money on proven form
        elif vet_issue == 1 or recent_pos >= 8.0:
            return 2.0  # Speculative move on questionable form
        else:
            return 4.0

    # Mild steam (10% to 20% drop)
    elif shift_pct <= -0.10:
        if recent_pos <= 4.0 and vet_issue == 0:
            return 4.0
        else:
            return 2.0

    # Moderate drift (15% to 30% drift)
    elif shift_pct >= 0.15 and shift_pct < 0.30:
        return -2.0

    # Massive drift (>30% drift)
    elif shift_pct >= 0.30:
        return -5.0

    return 0.0


def cache_live_odds(date_str, venue, races):
    """
    Saves the scraped win odds of all runners if they are > 0.
    """
    cleaned_date = str(date_str).replace('-', '') if date_str else 'today'
    filename = os.path.join(BASE_DIR, "data", f"odds_cache_{cleaned_date}.json")
    cache = {}
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        except Exception as e:
            print(f"[WARNING] Failed to read odds cache {filename}: {e}")

    updated = False
    for race in races:
        race_no = race.get('race_no')
        for runner in race.get('runners', []):
            horse_no = runner.get('no')
            win_odds = _safe_float(runner.get('win_odds', 0.0), 0.0)
            if win_odds > 0:
                key = f"{venue}_R{race_no}_H{horse_no}"
                cache[key] = win_odds
                updated = True

    if updated:
        try:
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(cache, f, indent=4)
        except Exception as e:
            print(f"[WARNING] Failed to write odds cache: {e}")


def get_cached_odds(date_str, venue, race_no, horse_no, current_odds):
    """
    Returns the cached odds if current_odds is 0 or invalid, else returns current_odds.
    Returns None when neither live, cached, nor baseline odds exist.
    """
    cur_val = _safe_float(current_odds, 0.0)
    if cur_val > 0:
        return cur_val

    cleaned_date = str(date_str).replace('-', '') if date_str else 'today'
    filename = os.path.join(BASE_DIR, "data", f"odds_cache_{cleaned_date}.json")
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                key = f"{venue}_R{race_no}_H{horse_no}"
                if key in cache and _safe_float(cache[key], 0.0) > 0:
                    return float(cache[key])
        except Exception as e:
            print(f"[WARNING] Error reading odds cache {filename}: {e}")

    return get_current_odds_with_fallback(date_str, venue, race_no, horse_no, current_odds)


def get_current_odds_with_fallback(date_str, venue, race_no, horse_no, scraped_odds=None):
    """
    Returns the best available current odds from scraped_odds or baseline_odds.
    Returns None when odds are missing so callers mark `odds_missing = True`
    instead of feeding a fabricated 20.0 into implied probabilities and Kelly stakes.
    """
    scraped_val = _safe_float(scraped_odds, 0.0)
    if scraped_val > 0:
        return scraped_val

    cleaned_date = str(date_str).replace('-', '') if date_str else 'today'
    filename = os.path.join(BASE_DIR, "data", f"baseline_odds_{cleaned_date}.json")
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                baseline_data = json.load(f)
                key = f"{venue}_R{race_no}_H{horse_no}"
                if key in baseline_data and _safe_float(baseline_data[key], 0.0) > 0:
                    return float(baseline_data[key])
        except Exception as e:
            print(f"[WARNING] Error reading baseline odds {filename}: {e}")

    return None


def save_frozen_predictions(date_str, venue, race_no, runners_list):
    """
    Saves predictions (runners list) to data/frozen_predictions_{date}.json to preserve the final ratings state.
    """
    cleaned_date = str(date_str).replace('-', '') if date_str else 'today'
    filename = os.path.join(BASE_DIR, "data", f"frozen_predictions_{cleaned_date}.json")
    cache = {}
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        except Exception as e:
            print(f"[ERROR] Corrupted frozen predictions file {filename} on read: {e}")
            record_health("frozen_predictions", "warn", error=f"Corrupted frozen file {filename}: {e}")

    # Sanitize NaN values so valid JSON is always written
    clean_runners = []
    for r in runners_list:
        clean_r = {}
        for k, v in r.items():
            if isinstance(v, float) and math.isnan(v):
                clean_r[k] = None
            else:
                clean_r[k] = v
        clean_runners.append(clean_r)

    key = f"{venue}_R{race_no}"
    cache[key] = clean_runners

    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=4)
    except Exception as e:
        print(f"[ERROR] Failed to write frozen predictions {filename}: {e}")
        record_health("frozen_predictions", "fail", error=f"Write error {filename}: {e}")


def get_frozen_predictions(date_str, venue, race_no):
    """
    Returns frozen predictions if they exist, otherwise None.
    Logs an explicit error if the frozen file is corrupted.
    """
    cleaned_date = str(date_str).replace('-', '') if date_str else 'today'
    filename = os.path.join(BASE_DIR, "data", f"frozen_predictions_{cleaned_date}.json")
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                key = f"{venue}_R{race_no}"
                if key in cache:
                    return cache[key]
        except Exception as e:
            print(f"[ERROR] Corrupted frozen predictions file {filename}: {e}")
            record_health("frozen_predictions", "fail", error=f"Corrupted frozen file {filename}: {e}")
            return None
    return None


def should_defrost_predictions(frozen_runners, live_runners, frozen_going, live_going):
    """
    Checks if frozen predictions should be defrosted and recalculated.
    Triggers:
    1. Scratches: A horse in frozen predictions is missing from live runners.
    2. Track rating changed: Going changed.
    3. Jockey changes: A jockey has been substituted.
    """
    if not frozen_runners or not live_runners:
        return False

    # Check scratches
    frozen_nos = set(r.get('no') for r in frozen_runners if r.get('no') is not None)
    live_nos = set(r.get('no') for r in live_runners if r.get('no') is not None)

    if not frozen_nos.issubset(live_nos):
        scratched_nos = frozen_nos - live_nos
        print(f"[DEFROST] Triggered due to scratched runner(s): {scratched_nos}")
        return True

    # Check going change
    if frozen_going and live_going:
        if str(frozen_going).strip().upper() != str(live_going).strip().upper():
            print(f"[DEFROST] Triggered due to going change: '{frozen_going}' -> '{live_going}'")
            return True

    # Check jockey changes
    frozen_jockeys = {r.get('no'): str(r.get('jockey', '')).strip().upper() for r in frozen_runners if r.get('no') is not None}
    for live_r in live_runners:
        l_no = live_r.get('no')
        if l_no in frozen_jockeys:
            live_jockey = str(live_r.get('jockey', '')).strip().upper()
            frozen_jockey = frozen_jockeys[l_no]
            if live_jockey and frozen_jockey and live_jockey != frozen_jockey:
                print(f"[DEFROST] Triggered due to jockey change on Horse #{l_no}: '{frozen_jockey}' -> '{live_jockey}'")
                return True

    # Check if frozen predictions were generated pre-market (missing or placeholder odds) and live market odds have now opened
    frozen_all_placeholder = all(
        r.get('odds_missing', False) or (_safe_float(r.get('win_odds'), 20.0) in (0.0, 20.0))
        for r in frozen_runners
    )
    live_has_real_odds = any(
        (_safe_float(r.get('win_odds'), 0.0) > 0.0) and (_safe_float(r.get('win_odds'), 0.0) != 20.0)
        for r in live_runners
    )
    if frozen_all_placeholder and live_has_real_odds:
        print("[DEFROST] Triggered due to live market odds opening (replacing pre-market placeholders)")
        return True

    # Check if frozen predictions were generated before horse profile stats were scraped
    missing_profile_telemetry = any(
        r.get('horse_code') is None or str(r.get('horse_code', '')).strip().lower() in ['', 'nan', 'none'] or
        r.get('last_run_summary') is None or str(r.get('last_run_summary', '')).strip().lower() in ['', 'nan', 'none']
        for r in frozen_runners
    )
    if missing_profile_telemetry:
        print("[DEFROST] Triggered due to unprimed horse profile telemetry in frozen cache")
        return True

    return False

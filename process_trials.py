import os
import json
import pandas as pd
import numpy as np
from datetime import datetime


STANDARD_TIMES = {
    ("SHA TIN AWT", 1200): 70.5,
    ("SHA TIN AWT", 1050): 62.0,
    ("SHA TIN TURF", 800): 46.2,
    ("SHA TIN TURF", 1000): 58.0,
    ("SHA TIN TURF", 1200): 70.5,
    ("SHA TIN TURF", 1600): 96.0,
    ("HAPPY VALLEY TURF", 1000): 59.0,
    ("HAPPY VALLEY TURF", 1200): 72.0,
    ("HAPPY VALLEY TURF", 1700): 107.5,
    ("CONGHUA TURF", 800): 46.5,
    ("CONGHUA TURF", 1000): 58.0,
    ("CONGHUA TURF", 1200): 71.5,
    ("CONGHUA TURF", 1600): 97.0,
    ("CONGHUA AWT", 1050): 61.7,
    ("CONGHUA AWT", 1200): 70.5,
}


def time_str_to_seconds(t_str):
    """
    Converts a time string like "1.10.95" or "0.58.24" or "47.45" to float seconds.
    """
    t_str = str(t_str).strip()
    if not t_str or t_str.lower() == 'nan':
        return None
    try:
        parts = t_str.split('.')
        if len(parts) == 3:
            mins, secs, hundredths = parts
            return int(mins) * 60 + int(secs) + int(hundredths) / 100.0
        elif len(parts) == 2:
            secs, hundredths = parts
            val = float(secs) + float(hundredths) / 100.0
            return val
        else:
            return float(t_str)
    except Exception:
        return None


def process_trials(meeting_date_str=None):
    """
    Processes raw trial stats from data/latest_trial_stats.csv,
    merges engineered features into data/engineered_trial_features.json,
    and records pipeline health.
    """
    from monitoring.health import record as record_health
    trial_csv = "data/latest_trial_stats.csv"
    out_json = "data/engineered_trial_features.json"

    horse_features = {}
    if os.path.exists(out_json):
        try:
            with open(out_json, "r", encoding="utf-8") as f:
                horse_features = json.load(f)
        except Exception:
            horse_features = {}

    if not os.path.exists(trial_csv):
        print(f"Error: {trial_csv} does not exist.")
        record_health("trial_features", "fail", error=f"{trial_csv} does not exist")
        return horse_features

    df = pd.read_csv(trial_csv)
    if df.empty:
        record_health("trial_features", "warn", metrics={"horses": len(horse_features)}, error="latest_trial_stats.csv is empty")
        return horse_features

    if meeting_date_str is None:
        meeting_date = datetime.now()
    elif isinstance(meeting_date_str, str):
        try:
            meeting_date = datetime.strptime(meeting_date_str.replace("/", "-"), "%Y-%m-%d")
        except Exception:
            meeting_date = datetime.now()
    else:
        meeting_date = meeting_date_str

    updated_count = 0
    elite_trial_count = 0
    meeting_day = meeting_date.date()
    for horse_name, group in df.groupby("horse_name"):
        trials_list = []

        for _, row in group.iterrows():
            trial_date_str = str(row["date"]).strip()
            try:
                if len(trial_date_str.split("/")) == 3:
                    t_date = pd.to_datetime(trial_date_str, dayfirst=True).to_pydatetime()
                elif len(trial_date_str.split("-")) == 3:
                    t_date = pd.to_datetime(trial_date_str).to_pydatetime()
                else:
                    t_date = datetime.strptime(f"{trial_date_str}/{meeting_day.year}", "%d/%m/%Y")
                    if t_date.date() > meeting_day:
                        try:
                            t_date = datetime.strptime(f"{trial_date_str}/{meeting_day.year - 1}", "%d/%m/%Y")
                        except ValueError:
                            # Handle Feb 29 leap-day edge safely
                            t_date = t_date.replace(year=meeting_day.year - 1, day=28)
            except Exception:
                continue

            days_since = (meeting_day - t_date.date()).days
            if days_since < 0 or days_since > 90:
                continue

            pos_val = pd.to_numeric(row.get("position"), errors="coerce")
            tot_val = pd.to_numeric(row.get("total_runners"), errors="coerce")
            if pd.isna(pos_val) or pd.isna(tot_val):
                continue
            pos = float(pos_val)
            tot = float(tot_val)
            if tot <= 0:
                continue
            pos_ratio = pos / tot

            track = str(row["track"]).upper().strip()
            dist_val = pd.to_numeric(row.get("distance"), errors="coerce")
            if pd.isna(dist_val):
                continue
            dist = int(dist_val)

            # Use individual horse time column if present; otherwise HKJC total_time is
            # the batch winner's time and is valid ONLY for the winner (position == 1).
            trial_sec = None
            for indiv_col in ("trial_time_sec", "horse_time_sec", "finish_time"):
                if indiv_col in row.index and pd.notna(row.get(indiv_col)) and str(row.get(indiv_col)).strip():
                    if indiv_col.endswith("_sec"):
                        sec_num = pd.to_numeric(row.get(indiv_col), errors="coerce")
                        trial_sec = float(sec_num) if pd.notna(sec_num) else None
                    else:
                        trial_sec = time_str_to_seconds(row.get(indiv_col))
                    if trial_sec is not None:
                        break
            if trial_sec is None and int(round(pos)) == 1:
                trial_sec = time_str_to_seconds(row.get("total_time"))

            std_time = STANDARD_TIMES.get((track, dist))
            speed_diff = (std_time - trial_sec) if (std_time is not None and trial_sec is not None) else None

            jockey_name = str(row["jockey"]).strip().upper()
            top_jockeys = ['Z PURTON', 'H BOWMAN', 'J MOREIRA', 'C Y HO', 'K TEETAN', 'A ATZENI']
            is_elite_jockey_trial = any(tj in jockey_name for tj in top_jockeys)

            trials_list.append({
                "days_since": days_since,
                "pos": pos,
                "pos_ratio": pos_ratio,
                "speed_diff": speed_diff,
                "jockey": jockey_name,
                "is_elite_jockey": is_elite_jockey_trial
            })

        if not trials_list:
            continue

        trials_30d = [t for t in trials_list if t["days_since"] <= 30]
        target_pool = trials_30d if trials_30d else trials_list
        trial_count_30d = len(trials_30d)
        best_pos_ratio = min(t["pos_ratio"] for t in target_pool)
        valid_speeds = [t["speed_diff"] for t in target_pool if t["speed_diff"] is not None]
        if not valid_speeds:
            valid_speeds = [t["speed_diff"] for t in trials_list if t["speed_diff"] is not None]
        trial_jockeys = [t["jockey"] for t in target_pool]
        high_quality_trial = any(t["pos_ratio"] <= 0.35 and t["is_elite_jockey"] for t in target_pool)
        recent_top2_trials = sum(1 for t in trials_list if t["pos"] <= 2.0)
        if high_quality_trial:
            elite_trial_count += 1

        clean_horse = str(horse_name).replace("\u2019", "'").replace("\u2018", "'").strip().upper()
        feat_entry = {
            "trial_count_30d": trial_count_30d,
            "best_trial_pos_ratio": float(best_pos_ratio),
            "trial_jockeys": trial_jockeys,
            "high_quality_trial": high_quality_trial,
            "recent_top2_trials": int(recent_top2_trials),
        }
        if valid_speeds:
            feat_entry["best_trial_speed_diff"] = float(max(valid_speeds))

        horse_features[clean_horse] = feat_entry
        updated_count += 1

    os.makedirs("data", exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(horse_features, f, indent=4)

    print(f"Engineered trial features for {len(horse_features)} horses ({updated_count} updated) and saved to {out_json}")
    record_health(
        "trial_features",
        "ok",
        metrics={
            "total_horses": len(horse_features),
            "updated_horses": updated_count,
            "elite_trials_flagged": elite_trial_count,
        },
    )
    return horse_features


if __name__ == "__main__":
    from scraper import get_live_meeting_data, select_active_meeting
    data = get_live_meeting_data()
    active_m = select_active_meeting(data) if data else None
    m_date = active_m.get("date", "2026-10-28") if active_m else "2026-10-28"
    process_trials(m_date)

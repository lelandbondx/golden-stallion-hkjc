import os
import json
import pandas as pd
import numpy as np
from datetime import datetime


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

    updated_count = 0
    elite_trial_count = 0
    for horse_name, group in df.groupby("horse_name"):
        trials_list = []

        for _, row in group.iterrows():
            trial_date_str = str(row["date"]).strip()
            try:
                if len(trial_date_str.split("/")) == 3:
                    t_date = pd.to_datetime(trial_date_str, dayfirst=True).to_pydatetime()
                else:
                    t_date = datetime.strptime(f"{trial_date_str}/{meeting_date.year}", "%d/%m/%Y")
            except Exception:
                continue

            days_since = (meeting_date - t_date).days
            if abs(days_since) > 90:
                continue

            pos = float(row["position"])
            tot = float(row["total_runners"])
            pos_ratio = pos / tot if tot > 0 else 1.0

            track = str(row["track"]).upper().strip()
            dist = int(row["distance"])
            trial_sec = time_str_to_seconds(row["total_time"])

            speed_diff = 0.0
            std_time = STANDARD_TIMES.get((track, dist))
            if std_time and trial_sec:
                speed_diff = std_time - trial_sec

            jockey_name = str(row["jockey"]).strip().upper()
            top_jockeys = ['Z PURTON', 'H BOWMAN', 'J MOREIRA', 'C Y HO', 'K TEETAN', 'A ATZENI']
            is_elite_jockey_trial = any(tj in jockey_name for tj in top_jockeys)

            trials_list.append({
                "days_since": days_since,
                "pos_ratio": pos_ratio,
                "speed_diff": speed_diff,
                "jockey": jockey_name,
                "is_elite_jockey": is_elite_jockey_trial
            })

        if not trials_list:
            continue

        trials_30d = [t for t in trials_list if t["days_since"] <= 30]
        trial_count_30d = len(trials_30d)
        best_pos_ratio = min([t["pos_ratio"] for t in trials_30d]) if trials_30d else min([t["pos_ratio"] for t in trials_list])
        best_speed_diff = max([t["speed_diff"] for t in trials_30d]) if trials_30d else max([t["speed_diff"] for t in trials_list])
        trial_jockeys = [t["jockey"] for t in (trials_30d if trials_30d else trials_list)]
        high_quality_trial = any(t["pos_ratio"] <= 0.35 and t["is_elite_jockey"] for t in (trials_30d if trials_30d else trials_list))
        if high_quality_trial:
            elite_trial_count += 1

        horse_features[horse_name.strip().upper()] = {
            "trial_count_30d": trial_count_30d,
            "best_trial_pos_ratio": float(best_pos_ratio),
            "best_trial_speed_diff": float(best_speed_diff),
            "trial_jockeys": trial_jockeys,
            "high_quality_trial": high_quality_trial
        }
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
    from scraper import get_live_meeting_data
    data = get_live_meeting_data()
    m_date = data["meetings"][0].get("date", "2026-10-28") if (data and data.get("meetings")) else "2026-10-28"
    process_trials(m_date)

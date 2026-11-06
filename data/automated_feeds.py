"""
Silks.AI - Automated Standing Bot Ingestion Pipeline
Ingests authoritative inputs from:
  1. Trial Bot (Daily 06:00 HKT) -> data/trial_bot_summary.json
  2. Replay Bot (2h post-meeting) -> data/replay_bot_notes.json
  3. Steward Bot (2h post-meeting) -> data/steward_bot_clearances.json (Final Medical/Integrity Gate)

Logs file timestamps and record counts. Preserves all locked model rules.
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta
import pandas as pd

logger = logging.getLogger("automated_feeds")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")

TRIAL_BOT_CANDIDATES = [
    os.path.join(DATA_DIR, "trial_bot_summary.json"),
    os.path.join(DATA_DIR, "trial_bot_latest.json"),
    os.path.join(DATA_DIR, "engineered_trial_features.json")
]

REPLAY_BOT_CANDIDATES = [
    os.path.join(DATA_DIR, "replay_bot_notes.json"),
    os.path.join(DATA_DIR, "replay_bot_latest.json"),
    os.path.join(DATA_DIR, "grok_trip_notes_resolved.json"),
    os.path.join(DATA_DIR, "horse_incident_memory.json")
]

STEWARD_BOT_CANDIDATES = [
    os.path.join(DATA_DIR, "steward_bot_clearances.json"),
    os.path.join(DATA_DIR, "steward_bot_latest.json"),
    os.path.join(DATA_DIR, "steward_bot_notes.json"),
    os.path.join(DATA_DIR, "declared_vet_records.json")
]

TELEMETRY_FILE = os.path.join(DATA_DIR, "automated_feeds_telemetry.json")


def _get_file_metadata(filepath):
    """Returns ISO timestamps and stat info for a file."""
    if not os.path.exists(filepath):
        return None
    stat = os.stat(filepath)
    utc_mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    hkt_mtime = utc_mtime + timedelta(hours=8)
    return {
        "path": filepath,
        "filename": os.path.basename(filepath),
        "size_bytes": stat.st_size,
        "mtime_utc": utc_mtime.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mtime_hkt": hkt_mtime.strftime("%Y-%m-%d %H:%M:%S HKT"),
        "timestamp_epoch": round(stat.st_mtime, 2)
    }


def load_trial_bot_feed():
    """
    Ingests the authoritative Trial Bot summary for declared horses.
    Outputs normalized trial features mapped by clean horse name.
    """
    chosen_file = None
    for path in TRIAL_BOT_CANDIDATES:
        if os.path.exists(path) and os.path.getsize(path) > 10:
            chosen_file = path
            break

    if not chosen_file:
        logger.warning("No trial bot feed file found; returning empty dictionary.")
        return {}, {"status": "missing", "timestamp": None}

    meta = _get_file_metadata(chosen_file)
    logger.info(f"[Trial Bot Ingestion] Loading from {meta['filename']} (mtime: {meta['mtime_hkt']})")

    try:
        with open(chosen_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        logger.error(f"Error loading trial bot feed {chosen_file}: {e}")
        return {}, {"status": "error", "error": str(e), "metadata": meta}

    trial_features = {}
    if isinstance(raw, dict):
        # Already keyed by horse name (engineered_trial_features format or dictionary summary)
        for k, v in raw.items():
            c_name = str(k).strip().upper()
            trial_features[c_name] = v
    elif isinstance(raw, list):
        # Structured list of trial entries (date, track, distance, position, margin, running_comment, opposition_quality, gear)
        for item in raw:
            h_name = str(item.get("horse") or item.get("horse_name") or item.get("name") or "").strip().upper()
            if not h_name:
                continue

            pos = float(item.get("position", 5.0))
            tot = float(item.get("total_runners", item.get("runners", 8.0)))
            pos_ratio = pos / tot if tot > 0 else 0.5
            speed_diff = float(item.get("speed_diff", 0.0))
            recent_top2 = 1 if pos <= 2.0 else 0

            existing = trial_features.get(h_name, {})
            trial_features[h_name] = {
                "best_trial_pos_ratio": min(pos_ratio, existing.get("best_trial_pos_ratio", pos_ratio)),
                "best_trial_speed_diff": max(speed_diff, existing.get("best_trial_speed_diff", speed_diff)),
                "recent_top2_trials": existing.get("recent_top2_trials", 0) + recent_top2,
                "trial_comment": item.get("running_comment") or item.get("comment", ""),
                "opposition_quality": item.get("opposition_quality", "Standard"),
                "trial_gear": item.get("gear", ""),
                "last_trial_date": item.get("date", ""),
                "trial_distance": item.get("distance", 0),
                "trial_track": item.get("track", "")
            }

    meta["record_count"] = len(trial_features)
    meta["status"] = "loaded"
    return trial_features, meta


def load_replay_bot_feed():
    """
    Ingests the authoritative Replay Bot trip-notes file flagging unlucky runs,
    excuses, vet issues, pace notes, and standout performances.
    """
    chosen_file = None
    for path in REPLAY_BOT_CANDIDATES:
        if os.path.exists(path) and os.path.getsize(path) > 10:
            chosen_file = path
            break

    if not chosen_file:
        logger.warning("No replay bot feed file found; returning empty dictionary.")
        return {}, {"status": "missing", "timestamp": None}

    meta = _get_file_metadata(chosen_file)
    logger.info(f"[Replay Bot Ingestion] Loading from {meta['filename']} (mtime: {meta['mtime_hkt']})")

    try:
        with open(chosen_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        logger.error(f"Error loading replay bot feed {chosen_file}: {e}")
        return {}, {"status": "error", "error": str(e), "metadata": meta}

    replay_notes = {}
    if isinstance(raw, list):
        for entry in raw:
            h_name = str(entry.get("horse") or entry.get("horse_name") or entry.get("name") or "").strip().upper()
            if not h_name:
                continue
            replay_notes[h_name] = entry
    elif isinstance(raw, dict):
        for k, v in raw.items():
            replay_notes[str(k).strip().upper()] = v

    meta["record_count"] = len(replay_notes)
    meta["status"] = "loaded"
    return replay_notes, meta


def load_steward_bot_feed():
    """
    Ingests the authoritative Steward Bot medical/vet and integrity clearances.
    Acts as the final medical and integrity gate.
    """
    chosen_file = None
    for path in STEWARD_BOT_CANDIDATES:
        if os.path.exists(path) and os.path.getsize(path) > 10:
            chosen_file = path
            break

    if not chosen_file:
        logger.warning("No steward bot feed file found; returning empty dictionary.")
        return {}, {"status": "missing", "timestamp": None}

    meta = _get_file_metadata(chosen_file)
    logger.info(f"[Steward Bot Ingestion] Loading from {meta['filename']} (mtime: {meta['mtime_hkt']})")

    try:
        with open(chosen_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        logger.error(f"Error loading steward bot feed {chosen_file}: {e}")
        return {}, {"status": "error", "error": str(e), "metadata": meta}

    steward_clearances = {}
    if isinstance(raw, list):
        for entry in raw:
            h_name = str(entry.get("horse_name") or entry.get("horse") or entry.get("name") or "").strip().upper()
            if not h_name:
                continue
            steward_clearances[h_name] = entry
    elif isinstance(raw, dict):
        for k, v in raw.items():
            steward_clearances[str(k).strip().upper()] = v

    meta["record_count"] = len(steward_clearances)
    meta["status"] = "loaded"
    return steward_clearances, meta


def sync_and_log_automated_feeds(target_meeting="2026-11-08 Sha Tin"):
    """
    Coordinates ingestion across Trial Bot, Replay Bot, and Steward Bot.
    Writes telemetry audit log with timestamps, paths, and record counts.
    """
    trials, trial_meta = load_trial_bot_feed()
    replays, replay_meta = load_replay_bot_feed()
    stewards, steward_meta = load_steward_bot_feed()

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    telemetry = {
        "updated_at_utc": now_iso,
        "target_meeting": target_meeting,
        "first_automated_meeting": "2026-11-08 Sha Tin",
        "standing_bots": {
            "trial_bot": {
                "duty": "Daily 06:00 HKT (HKJC 48h declared barrier trials)",
                "file_used": trial_meta.get("filename"),
                "file_path": trial_meta.get("path"),
                "timestamp_hkt": trial_meta.get("mtime_hkt"),
                "timestamp_utc": trial_meta.get("mtime_utc"),
                "record_count": trial_meta.get("record_count", len(trials)),
                "status": trial_meta.get("status", "ok")
            },
            "replay_bot": {
                "duty": "2h post-meeting (Official replays + stewards trip notes & excuses)",
                "file_used": replay_meta.get("filename"),
                "file_path": replay_meta.get("path"),
                "timestamp_hkt": replay_meta.get("mtime_hkt"),
                "timestamp_utc": replay_meta.get("mtime_utc"),
                "record_count": replay_meta.get("record_count", len(replays)),
                "status": replay_meta.get("status", "ok")
            },
            "steward_bot": {
                "duty": "2h post-meeting (Cross-checks medical/vet flags & final integrity gate)",
                "file_used": steward_meta.get("filename"),
                "file_path": steward_meta.get("path"),
                "timestamp_hkt": steward_meta.get("mtime_hkt"),
                "timestamp_utc": steward_meta.get("mtime_utc"),
                "record_count": steward_meta.get("record_count", len(stewards)),
                "status": steward_meta.get("status", "ok")
            }
        }
    }

    try:
        with open(TELEMETRY_FILE, "w", encoding="utf-8") as f:
            json.dump(telemetry, f, indent=2)
        logger.info(f"[Automated Feeds Telemetry] Saved to {TELEMETRY_FILE}")
    except Exception as e:
        logger.error(f"Failed to save automated feeds telemetry: {e}")

    return trials, replays, stewards, telemetry


if __name__ == "__main__":
    t, r, s, telem = sync_and_log_automated_feeds()
    print("=== AUTOMATED FEEDS INGESTION SUMMARY ===")
    print(f"Target Meeting: {telem['target_meeting']}")
    for bot, data in telem["standing_bots"].items():
        print(f"[{bot.upper()}] File: {data['file_used']} | Timestamp: {data['timestamp_hkt']} | Records: {data['record_count']}")

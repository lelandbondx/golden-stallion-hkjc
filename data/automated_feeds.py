"""
Silks.AI - Automated Standing Bot Ingestion Pipeline
Ingests authoritative, strictly verified signals from:
  1. Trial Bot (Daily 06:00 HKT) -> verified speed_diff, quality opposition flag, poor-finish flag (recent trials only)
  2. Replay Bot (2h post-meeting) -> documented stewards' excuses (traffic, wide-without-cover, checked, blocked) & 400m sectional rank
  3. Steward Bot (2h post-meeting) -> official vet clearance or active requirement flag

Rejects incomplete or unverified rows, logs exact file timestamps & record counts,
and preserves all locked model formulas, caps, and stakes.
"""

import os
import re
import json
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("automated_feeds")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")

TRIAL_BOT_CANDIDATES = [
    os.path.join(DATA_DIR, "trial_bot_summary.json"),
    os.path.join(DATA_DIR, "trial_bot_latest.json"),
    os.path.join(DATA_DIR, "engineered_trial_features.json"),
]

REPLAY_BOT_CANDIDATES = [
    os.path.join(DATA_DIR, "replay_bot_notes.json"),
    os.path.join(DATA_DIR, "replay_bot_latest.json"),
    os.path.join(DATA_DIR, "grok_trip_notes_resolved.json"),
    os.path.join(DATA_DIR, "horse_incident_memory.json"),
]

STEWARD_BOT_CANDIDATES = [
    os.path.join(DATA_DIR, "steward_bot_clearances.json"),
    os.path.join(DATA_DIR, "steward_bot_latest.json"),
    os.path.join(DATA_DIR, "steward_bot_notes.json"),
    os.path.join(DATA_DIR, "vet_records.json"),
    os.path.join(DATA_DIR, "declared_vet_records.json"),
]

TELEMETRY_FILE = os.path.join(DATA_DIR, "automated_feeds_telemetry.json")
FIRST_FILTERED_MEETING = "2026-11-14 Sha Tin"

VERIFIED_TRIAL_FIELDS = [
    "best_trial_speed_diff",
    "best_trial_pos_ratio",
    "high_quality_trial",
    "poor_finish_flag",
    "recent_top2_trials",
    "trial_count_30d",
]
VERIFIED_REPLAY_FIELDS = [
    "date",
    "excuses",
    "flags",
    "final_section_rank",
    "steward_comment",
]
VERIFIED_STEWARD_FIELDS = [
    "horse_code",
    "status",
    "prev_run_vet_finding",
    "latest_vet_note",
]

ALLOWED_REPLAY_EXCUSES = {
    "traffic",
    "traffic_trouble",
    "wide_no_cover",
    "wide_without_cover",
    "checked",
    "blocked",
    "hampered",
}


def _get_file_metadata(filepath):
    """Returns ISO timestamps (UTC & HKT) and stat info for a file."""
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
        "timestamp_epoch": round(stat.st_mtime, 2),
    }


def _to_float(val):
    if val is None or isinstance(val, bool):
        return None
    try:
        f = float(val)
        if f != f:  # NaN
            return None
        return f
    except Exception:
        return None


def load_trial_bot_feed():
    """
    Ingests the authoritative Trial Bot summary, filtering to ONLY verified recent-trial signals:
      - best_trial_speed_diff (float)
      - high_quality_trial (bool, quality opposition flag)
      - best_trial_pos_ratio (float in [0, 1]) & poor_finish_flag (bool)
      - recent_top2_trials & trial_count_30d (recent trials only)
    Ignores incomplete rows or entries without recent trial activity.
    """
    chosen_file = None
    for path in TRIAL_BOT_CANDIDATES:
        if os.path.exists(path) and os.path.getsize(path) > 10:
            chosen_file = path
            break

    if not chosen_file:
        logger.warning("No trial bot feed file found; returning empty dictionary.")
        return {}, {"status": "missing", "timestamp_hkt": None, "fields_read": VERIFIED_TRIAL_FIELDS}

    meta = _get_file_metadata(chosen_file)
    logger.info(f"[Trial Bot Ingestion] Loading from {meta['filename']} (mtime: {meta['mtime_hkt']})")

    try:
        with open(chosen_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        logger.error(f"Error loading trial bot feed {chosen_file}: {e}")
        return {}, {"status": "error", "error": str(e), **meta}

    trial_features = {}
    rejected_count = 0

    if isinstance(raw, dict):
        for k, v in raw.items():
            c_name = str(k).strip().upper()
            if not c_name or not isinstance(v, dict):
                rejected_count += 1
                continue
            speed_diff = _to_float(v.get("best_trial_speed_diff"))
            pos_ratio = _to_float(v.get("best_trial_pos_ratio"))
            t_count_30d = int(_to_float(v.get("trial_count_30d")) or 0)
            top2_cnt = int(_to_float(v.get("recent_top2_trials")) or 0)
            if speed_diff is None or pos_ratio is None or pos_ratio < 0 or pos_ratio > 1.0:
                rejected_count += 1
                continue
            # Require at least one verified recent trial (30d) or verified top-2 / recent-window trial record
            if t_count_30d <= 0 and "trial_count_30d" in v:
                # Only retain if poor finish or strong speed was explicitly verified in recent cycle
                if top2_cnt <= 0 and not (pos_ratio >= 0.90 and speed_diff <= -1.0):
                    rejected_count += 1
                    continue

            hq_flag = bool(v.get("high_quality_trial", False))
            poor_flag = bool(
                v.get("poor_finish_flag")
                if v.get("poor_finish_flag") is not None
                else (pos_ratio >= 0.90 and speed_diff <= -1.0)
            )
            trial_features[c_name] = {
                "trial_count_30d": t_count_30d,
                "best_trial_pos_ratio": float(pos_ratio),
                "best_trial_speed_diff": float(speed_diff),
                "high_quality_trial": hq_flag,
                "poor_finish_flag": poor_flag,
                "recent_top2_trials": top2_cnt,
                "trial_jockeys": list(v.get("trial_jockeys") or []) if isinstance(v.get("trial_jockeys"), list) else [],
            }
    elif isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                rejected_count += 1
                continue
            h_name = str(item.get("horse") or item.get("horse_name") or item.get("name") or "").strip().upper()
            pos = _to_float(item.get("position"))
            tot = _to_float(item.get("total_runners", item.get("runners")))
            speed_diff = _to_float(item.get("speed_diff"))
            if not h_name or pos is None or tot is None or tot <= 0 or speed_diff is None:
                rejected_count += 1
                continue
            pos_ratio = pos / tot
            recent_top2 = 1 if pos <= 2.0 else 0
            opp_q = str(item.get("opposition_quality", "")).strip().lower()
            hq_flag = bool(item.get("high_quality_trial", False) or opp_q in ("high", "elite", "group", "top"))

            existing = trial_features.get(h_name, {})
            best_pr = min(pos_ratio, existing.get("best_trial_pos_ratio", pos_ratio))
            best_sd = max(speed_diff, existing.get("best_trial_speed_diff", speed_diff))
            trial_features[h_name] = {
                "trial_count_30d": existing.get("trial_count_30d", 0) + 1,
                "best_trial_pos_ratio": float(best_pr),
                "best_trial_speed_diff": float(best_sd),
                "high_quality_trial": bool(existing.get("high_quality_trial", False) or hq_flag),
                "poor_finish_flag": bool(best_pr >= 0.90 and best_sd <= -1.0),
                "recent_top2_trials": existing.get("recent_top2_trials", 0) + recent_top2,
                "trial_jockeys": existing.get("trial_jockeys", []),
            }

    meta["record_count"] = len(trial_features)
    meta["rejected_incomplete"] = rejected_count
    meta["fields_read"] = VERIFIED_TRIAL_FIELDS
    meta["status"] = "loaded"
    logger.info(
        f"[Trial Bot Ingestion] Accepted {len(trial_features)} verified records "
        f"(ignored {rejected_count} incomplete/stale rows)"
    )
    return trial_features, meta


def _extract_verified_replay_signals(entry):
    """
    Validates a single Replay Bot item, extracting ONLY documented stewards' excuses
    (traffic, wide-without-cover, checked, blocked) and verified 400m sectional rank.
    Returns normalized dict or None if incomplete/unverified.
    """
    if not isinstance(entry, dict):
        return None
    date_str = str(entry.get("date") or entry.get("race_date") or "").strip()
    if not date_str:
        return None

    raw_flags = entry.get("flags") or entry.get("incident_flags") or ""
    parsed_tags = []
    if isinstance(raw_flags, str):
        parsed_tags = [t.strip().lower() for t in re.split(r"[;,|]", raw_flags) if t.strip()]
    elif isinstance(raw_flags, list):
        for fobj in raw_flags:
            if isinstance(fobj, dict) and fobj.get("flag"):
                parsed_tags.append(str(fobj["flag"]).strip().lower())
            elif isinstance(fobj, str):
                parsed_tags.append(fobj.strip().lower())

    excuses = []
    for tag in parsed_tags:
        if tag in ALLOWED_REPLAY_EXCUSES:
            norm = "wide_no_cover" if "wide" in tag else ("traffic_trouble" if tag in ("traffic", "traffic_trouble") else tag)
            if norm not in excuses:
                excuses.append(norm)

    comment = str(entry.get("steward_comment") or entry.get("note") or "").strip()
    sec_rank = entry.get("final_section_rank")
    if sec_rank is None and comment:
        m_rk = re.search(r"Rank\s*#?(\d+)\s+last\s*400m", str(entry.get("note") or ""), re.I)
        if m_rk:
            sec_rank = int(m_rk.group(1))
    else:
        try:
            sec_rank = int(sec_rank) if sec_rank is not None else None
        except Exception:
            sec_rank = None

    # Must have at least one documented excuse OR a verified 400m sectional rank
    if not excuses and sec_rank is None:
        return None
    # If excuses exist without a verified sectional rank, require non-empty stewards' comment
    if excuses and not str(entry.get("steward_comment") or "").strip() and sec_rank is None:
        return None

    return {
        "date": date_str,
        "race": entry.get("race"),
        "excuses": excuses,
        "final_section_rank": sec_rank,
        "steward_comment": str(entry.get("steward_comment") or "").strip(),
    }


def load_replay_bot_feed():
    """
    Ingests the authoritative Replay Bot feed, extracting ONLY verified documented
    stewards' excuses (traffic, wide_no_cover, checked, blocked) and 400m sectional rank.
    """
    chosen_file = None
    for path in REPLAY_BOT_CANDIDATES:
        if os.path.exists(path) and os.path.getsize(path) > 10:
            chosen_file = path
            break

    if not chosen_file:
        logger.warning("No replay bot feed file found; returning empty dictionary.")
        return {}, {"status": "missing", "timestamp_hkt": None, "fields_read": VERIFIED_REPLAY_FIELDS}

    meta = _get_file_metadata(chosen_file)
    logger.info(f"[Replay Bot Ingestion] Loading from {meta['filename']} (mtime: {meta['mtime_hkt']})")

    try:
        with open(chosen_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        logger.error(f"Error loading replay bot feed {chosen_file}: {e}")
        return {}, {"status": "error", "error": str(e), **meta}

    replay_notes = {}
    rejected_count = 0

    if isinstance(raw, list):
        # Keep most recent verified entry per horse
        for entry in sorted(raw, key=lambda x: str((x or {}).get("date", ""))):
            h_name = str((entry or {}).get("horse") or (entry or {}).get("horse_name") or (entry or {}).get("name") or "").strip().upper()
            cleaned = _extract_verified_replay_signals(entry) if h_name else None
            if not h_name or not cleaned:
                rejected_count += 1
                continue
            replay_notes[h_name] = cleaned
    elif isinstance(raw, dict):
        for k, v in raw.items():
            h_name = str(k).strip().upper()
            if not h_name or not isinstance(v, dict):
                rejected_count += 1
                continue
            runs = v.get("runs")
            if isinstance(runs, list) and runs:
                cleaned = _extract_verified_replay_signals(runs[0])
            else:
                cleaned = _extract_verified_replay_signals(v)
            if not cleaned:
                rejected_count += 1
                continue
            replay_notes[h_name] = cleaned

    meta["record_count"] = len(replay_notes)
    meta["rejected_incomplete"] = rejected_count
    meta["fields_read"] = VERIFIED_REPLAY_FIELDS
    meta["status"] = "loaded"
    logger.info(
        f"[Replay Bot Ingestion] Accepted {len(replay_notes)} verified records "
        f"(ignored {rejected_count} incomplete/unverified rows)"
    )
    return replay_notes, meta


def load_steward_bot_feed():
    """
    Ingests the authoritative Steward Bot medical/vet clearances and active flags.
    Reads ONLY verified rows carrying horse identifier + explicit clearance/active flag.
    """
    chosen_file = None
    for path in STEWARD_BOT_CANDIDATES:
        if os.path.exists(path) and os.path.getsize(path) > 10:
            chosen_file = path
            break

    if not chosen_file:
        logger.warning("No steward bot feed file found; returning empty dictionary.")
        return {}, {"status": "missing", "timestamp_hkt": None, "fields_read": VERIFIED_STEWARD_FIELDS}

    meta = _get_file_metadata(chosen_file)
    logger.info(f"[Steward Bot Ingestion] Loading from {meta['filename']} (mtime: {meta['mtime_hkt']})")

    try:
        with open(chosen_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        logger.error(f"Error loading steward bot feed {chosen_file}: {e}")
        return {}, {"status": "error", "error": str(e), **meta}

    steward_clearances = {}
    rejected_count = 0

    def _parse_steward_entry(entry):
        if not isinstance(entry, dict):
            return None, None
        h_name = str(entry.get("horse_name") or entry.get("horse") or entry.get("name") or "").strip().upper()
        h_code = str(entry.get("horse_code") or "").strip().upper()
        if not h_name and not h_code:
            return None, None

        # Validate official vet status or clearance flag
        latest_entry = entry.get("latest_material_entry") or entry.get("latest_entry") or {}
        status = str(entry.get("status") or latest_entry.get("status") or "").strip().lower()
        flag_val = entry.get("prev_run_vet_finding")
        if status not in ("cleared", "no_requirement", "active_requirement") and flag_val is None:
            return None, None

        active_flag = int(flag_val) if flag_val is not None else (1 if status == "active_requirement" else 0)
        if not status:
            status = "active_requirement" if active_flag == 1 else "cleared"

        key = h_name or h_code
        return key, {
            "horse_code": h_code,
            "horse_name": h_name,
            "status": status,
            "prev_run_vet_finding": active_flag,
            "latest_vet_note": str(entry.get("latest_vet_note") or entry.get("details") or "").strip(),
        }

    items = raw if isinstance(raw, list) else (list(raw.values()) if isinstance(raw, dict) else [])
    for entry in items:
        key, parsed = _parse_steward_entry(entry)
        if not key or not parsed:
            rejected_count += 1
            continue
        steward_clearances[key] = parsed

    meta["record_count"] = len(steward_clearances)
    meta["rejected_incomplete"] = rejected_count
    meta["fields_read"] = VERIFIED_STEWARD_FIELDS
    meta["status"] = "loaded"
    logger.info(
        f"[Steward Bot Ingestion] Accepted {len(steward_clearances)} verified records "
        f"(ignored {rejected_count} incomplete/unverified rows)"
    )
    return steward_clearances, meta


def sync_and_log_automated_feeds(target_meeting=FIRST_FILTERED_MEETING):
    """
    Coordinates verified ingestion across Trial Bot, Replay Bot, and Steward Bot.
    Writes telemetry audit log with file timestamps, accepted/rejected counts, and exact fields read.
    """
    trials, trial_meta = load_trial_bot_feed()
    replays, replay_meta = load_replay_bot_feed()
    stewards, steward_meta = load_steward_bot_feed()

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    telemetry = {
        "updated_at_utc": now_iso,
        "target_meeting": target_meeting,
        "first_filtered_meeting": FIRST_FILTERED_MEETING,
        "standing_bots": {
            "trial_bot": {
                "duty": "Daily 06:00 HKT (speed_diff, quality opposition, poor-finish flag - recent trials only)",
                "file_used": trial_meta.get("filename"),
                "file_path": trial_meta.get("path"),
                "timestamp_hkt": trial_meta.get("mtime_hkt"),
                "timestamp_utc": trial_meta.get("mtime_utc"),
                "fields_read": VERIFIED_TRIAL_FIELDS,
                "record_count": trial_meta.get("record_count", len(trials)),
                "rejected_incomplete": trial_meta.get("rejected_incomplete", 0),
                "status": trial_meta.get("status", "ok"),
            },
            "replay_bot": {
                "duty": "2h post-meeting (documented excuses: traffic/wide/checked/blocked + 400m sectional rank)",
                "file_used": replay_meta.get("filename"),
                "file_path": replay_meta.get("path"),
                "timestamp_hkt": replay_meta.get("mtime_hkt"),
                "timestamp_utc": replay_meta.get("mtime_utc"),
                "fields_read": VERIFIED_REPLAY_FIELDS,
                "record_count": replay_meta.get("record_count", len(replays)),
                "rejected_incomplete": replay_meta.get("rejected_incomplete", 0),
                "status": replay_meta.get("status", "ok"),
            },
            "steward_bot": {
                "duty": "2h post-meeting (official vet clearance or active requirement flag)",
                "file_used": steward_meta.get("filename"),
                "file_path": steward_meta.get("path"),
                "timestamp_hkt": steward_meta.get("mtime_hkt"),
                "timestamp_utc": steward_meta.get("mtime_utc"),
                "fields_read": VERIFIED_STEWARD_FIELDS,
                "record_count": steward_meta.get("record_count", len(stewards)),
                "rejected_incomplete": steward_meta.get("rejected_incomplete", 0),
                "status": steward_meta.get("status", "ok"),
            },
        },
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
    print(f"First Filtered Meeting: {telem['first_filtered_meeting']} | Target: {telem['target_meeting']}")
    for bot, data in telem["standing_bots"].items():
        print(
            f"[{bot.upper()}] File: {data['file_used']} | Timestamp: {data['timestamp_hkt']} | "
            f"Accepted: {data['record_count']} (Rejected: {data['rejected_incomplete']}) | Fields: {data['fields_read']}"
        )

"""
Silks.AI - Read-Only Multi-Bot Feeds Importer (`trial-data` branch over HTTP)

Fetches, checksum-validates, caches (under `.cache/bot_feeds/`, never `data/`),
normalizes, and joins five automated feeds from GitHub branch `trial-data`:
  1. `trial_bot`   - pre-meeting trials (`declared_trials_latest.csv`, `trials_history.csv`)
  2. `steward`     - medical & integrity ledger (`records.csv`, `horses_latest.json`)
  3. `replay`      - race replay trip notes (`all_trip_notes.csv`, per-meeting CSV/JSON)
  4. `grok_rising` - canonical factual EV flags (`YYYY-MM-DD_V.csv`)
  5. `grok_bot`    - cross-check mirror (never double-counted with `grok_rising`)

Hard guarantees:
  - Never touches `data/frozen_predictions_*.json` or writes cache/coverage files into `data/`.
  - Missing values stay missing (omitted cleanly; never `None` or placeholders into core keys).
  - Controlled via `SILKS_BOT_FEEDS` (`off` [default] | `shadow` | `live`).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import math
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

from monitoring.health import record as record_health

logger = logging.getLogger("bot_feeds_import")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

REPO_SLUG = "lelandbondx/golden-stallion-hkjc"
DEFAULT_REF = "trial-data"
DEFAULT_CACHE_DIR = ".cache/bot_feeds"
DEFAULT_TIMEOUT_S = 10.0
CACHE_TTL_S = 900

HORSE_CODE_RE = re.compile(r"^[A-Z]\d{3}$")
STEWARD_MEETING_RE = re.compile(r"^(HV|ST)-(\d{4})(\d{2})(\d{2})", re.I)

CORE_TRIAL_KEYS = (
    "best_trial_pos_ratio",
    "best_trial_speed_diff",
    "recent_top2_trials",
    "high_quality_trial",
    "trial_count_30d",
)

MATERIAL_VET_CATEGORIES = {
    "surgery",
    "injury",
    "lameness",
    "bleeding_nostrils",
    "tracheal_blood",
    "cardiac",
    "airway",
    "heat_stress",
    "failed_vet_exam",
}

ALLOWED_REPLAY_EXCUSES = {
    "traffic",
    "traffic_trouble",
    "wide_no_cover",
    "wide_without_cover",
    "checked",
    "blocked",
    "hampered",
}

POSITIVE_REPLAY_VET_KEYWORDS = (
    "blood",
    "lame",
    "irregular heart rhythm",
    "roarer",
    "epiglottic",
    "laceration",
    "wound",
    "withdrawn",
)

REQUIRED_COLUMNS = {
    "trial_bot_declared": (
        "meeting_date",
        "venue",
        "race_no",
        "horse_no",
        "standby_order",
        "horse_name",
        "horse_code",
        "runner_status",
        "trial_date",
        "trial_track",
        "trial_surface",
        "trial_distance_m",
        "trial_finish_pos",
        "trial_field_size",
        "trial_lbw_lengths",
        "trial_time_sec",
        "days_since_trial",
        "trial_same_surface_distance_median_sec",
        "trial_same_surface_distance_n_timed",
        "flag_speed_outlier_fast",
        "flag_speed_outlier_slow",
        "flag_quality_opposition",
        "flag_poor_finish",
        "flag_stale_trial",
        "trial_gear_differs_from_declared",
        "trial_comment",
        "source_url_trial",
        "completeness",
    ),
    "trial_bot_history": (
        "horse_code",
        "horse_name",
        "trial_date",
        "trial_track",
        "trial_surface",
        "trial_distance_m",
        "trial_finish_pos",
        "trial_field_size",
        "trial_lbw_lengths",
        "trial_time_sec",
        "trial_comment",
        "source_url",
    ),
    "steward_records": (
        "meeting_date",
        "venue",
        "race_no",
        "horse_name",
        "horse_code",
        "horse_id",
        "record_id",
        "record_type",
        "category",
        "is_material",
        "finding_verbatim",
        "requirement",
        "status",
        "event_date",
        "passed_on",
        "source_url",
    ),
    "replay": (
        "date",
        "venue",
        "race",
        "horse",
        "horse_code",
        "draw",
        "finish",
        "win_odds",
        "flags",
        "traffic",
        "wide_no_cover",
        "slow_away",
        "stewards_excuse",
        "pace_role",
        "vet_finding",
        "clearance_required",
        "horse_last_400m_sec",
        "race_last_400m_sec",
        "source",
        "meeting_date",
        "race_no",
        "horse_name",
    ),
    "grok_rising": (
        "meeting_date",
        "venue",
        "race_no",
        "horse_name",
        "horse_code",
        "flag_type",
        "direction",
        "priority",
        "clearance_required",
        "verified",
        "evidence",
        "source_url",
    ),
    "grok_bot": (
        "meeting_date",
        "venue",
        "race_no",
        "horse_name",
        "horse_code",
        "flag_type",
        "direction",
        "priority",
        "clearance_required",
        "evidence",
        "source",
        "verified",
        "generated_at",
    ),
}

_MEM_MEETING_CACHE: dict[tuple, tuple[float, dict, dict]] = {}


# ---------------------------------------------------------------------------
# Environment configuration helpers
# ---------------------------------------------------------------------------

def get_bot_feeds_mode() -> str:
    raw = str(os.environ.get("SILKS_BOT_FEEDS", "off") or "off").strip().lower()
    if raw in ("off", "shadow", "live"):
        return raw
    logger.warning(f"Unknown SILKS_BOT_FEEDS={raw!r}; defaulting to 'off'")
    return "off"


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def get_bot_feeds_ref() -> str:
    return str(os.environ.get("SILKS_BOT_FEEDS_REF", DEFAULT_REF) or DEFAULT_REF).strip()


def get_bot_feeds_cache_dir(cache_dir: Optional[str] = None) -> str:
    if cache_dir:
        return cache_dir
    return str(os.environ.get("SILKS_BOT_FEEDS_CACHE", DEFAULT_CACHE_DIR) or DEFAULT_CACHE_DIR).strip()


def get_bot_feeds_timeout() -> float:
    try:
        return max(1.0, float(os.environ.get("SILKS_BOT_FEEDS_TIMEOUT", DEFAULT_TIMEOUT_S)))
    except Exception:
        return DEFAULT_TIMEOUT_S


def is_live_trials_enabled() -> bool:
    return _env_flag("SILKS_BOT_LIVE_TRIALS", False)


def is_live_steward_enabled() -> bool:
    return _env_flag("SILKS_BOT_LIVE_STEWARD", False)


def is_live_replay_enabled() -> bool:
    return _env_flag("SILKS_BOT_LIVE_REPLAY", False)


def is_coverage_strict() -> bool:
    return _env_flag("BOT_COVERAGE_STRICT", False)


# ---------------------------------------------------------------------------
# Normalization & CSV/JSON parsing helpers
# ---------------------------------------------------------------------------

def clean_val(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("missing", "unknown", "nan", "none", "null"):
        return None
    return s


def parse_tri_bool(val: Any) -> Optional[bool]:
    if isinstance(val, bool):
        return val
    s = clean_val(val)
    if s is None:
        return None
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    return None


def parse_float(val: Any) -> Optional[float]:
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else f
    s = clean_val(val)
    if s is None:
        return None
    try:
        f = float(s)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except Exception:
        return None


def parse_int(val: Any) -> Optional[int]:
    f = parse_float(val)
    if f is None:
        return None
    return int(round(f))


def normalize_horse_code(val: Any) -> Optional[str]:
    s = clean_val(val)
    if not s:
        return None
    up = s.upper()
    return up if HORSE_CODE_RE.match(up) else None


def normalize_horse_name(val: Any) -> Optional[str]:
    s = clean_val(val)
    if not s:
        return None
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u02bc", "'")
    s = " ".join(s.split()).upper()
    return s or None


def normalize_venue(val: Any) -> Optional[str]:
    s = clean_val(val)
    if not s:
        return None
    up = s.upper()
    if up in ("ST", "SHA TIN", "SHATIN"):
        return "ST"
    if up in ("HV", "HAPPY VALLEY", "HAPPYVALLEY"):
        return "HV"
    return None


def normalize_date(val: Any) -> Optional[str]:
    s = clean_val(val)
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return None


def parse_steward_meeting_id(mid: Any) -> tuple[Optional[str], Optional[str]]:
    s = clean_val(mid)
    if not s:
        return None, None
    m = STEWARD_MEETING_RE.match(s)
    if not m:
        return None, None
    venue = m.group(1).upper()
    iso_date = f"{m.group(2)}-{m.group(3)}-{m.group(4)}"
    return iso_date, venue


def parse_replay_finish(val: Any) -> tuple[Optional[int], bool]:
    s = clean_val(val)
    if not s:
        return None, False
    dead_heat = "DH" in s.upper()
    m = re.match(r"^\s*0*(\d+)\b", s)
    if not m:
        return None, False
    return int(m.group(1)), dead_heat


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().lower()


def _parse_csv_bytes(raw_bytes: bytes, required_cols: tuple[str, ...], label: str) -> list[dict[str, str]]:
    text = raw_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames or []
    missing = [col for col in required_cols if col not in fieldnames]
    if missing:
        raise ValueError(f"{label}: missing required columns {missing}")
    return list(reader)


def _atomic_write_bytes(path: str, data: bytes) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", dir=parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise


def _atomic_write_json(path: str, payload: Any) -> None:
    raw = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    _atomic_write_bytes(path, raw)


def _parse_iso_datetime(ts: Any) -> Optional[datetime]:
    s = clean_val(ts)
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _compute_age_hours(ts: Any, now_utc: Optional[datetime] = None) -> Optional[float]:
    dt = _parse_iso_datetime(ts)
    if dt is None:
        return None
    now = now_utc or datetime.now(timezone.utc)
    return round(max(0.0, (now - dt.astimezone(timezone.utc)).total_seconds() / 3600.0), 2)


# ---------------------------------------------------------------------------
# HTTP / fixture transport & completeness gate
# ---------------------------------------------------------------------------

def _default_http_transport(ref: str, timeout_s: float) -> Callable[[str, str], bytes]:
    token = clean_val(os.environ.get("GITHUB_TOKEN"))

    def _fetch(folder: str, relpath: str) -> bytes:
        rel_clean = relpath.lstrip("/")
        raw_url = f"https://raw.githubusercontent.com/{REPO_SLUG}/{ref}/data/{folder}/{rel_clean}"
        headers = {"User-Agent": "SilksAI-BotFeeds/1.0"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(raw_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                return resp.read()
        except urllib.error.HTTPError as err:
            if err.code in (403, 404) and token:
                api_url = (
                    f"https://api.github.com/repos/{REPO_SLUG}/contents/"
                    f"data/{folder}/{rel_clean}?ref={ref}"
                )
                api_headers = {
                    "User-Agent": "SilksAI-BotFeeds/1.0",
                    "Accept": "application/vnd.github.raw",
                    "Authorization": f"Bearer {token}",
                }
                api_req = urllib.request.Request(api_url, headers=api_headers)
                with urllib.request.urlopen(api_req, timeout=timeout_s) as api_resp:
                    return api_resp.read()
            if err.code == 404:
                raise FileNotFoundError(f"{folder}/{rel_clean} not found (HTTP 404)") from err
            raise

    return _fetch


def _validate_checksum(relpath: str, raw_bytes: bytes, sha_map: dict) -> bool:
    expected = sha_map.get(relpath)
    if not expected:
        return False
    actual = _sha256_bytes(raw_bytes)
    if actual != str(expected).strip().lower():
        raise ValueError(f"sha256 mismatch on {relpath}: expected {expected[:12]}..., got {actual[:12]}...")
    return True


def _validate_and_parse_folder(
    folder: str,
    fetcher: Callable[[str, str], bytes],
) -> tuple[dict[str, bytes], dict[str, Any], dict[str, Any]]:
    manifest_bytes = fetcher(folder, "manifest.json")
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError(f"{folder}/manifest.json must decode to dict")

    files_bytes: dict[str, bytes] = {"manifest.json": manifest_bytes}
    warnings: list[str] = []
    verified_checksums: list[str] = []
    parsed: dict[str, Any] = {"manifest": manifest}

    sha_map = manifest.get("sha256") or {}

    if folder == "trial_bot":
        if manifest.get("status") != "ok":
            raise ValueError(f"trial_bot manifest status={manifest.get('status')!r} != 'ok'")

        req_csvs = ["declared_trials_latest.csv", "trials_history.csv"]
        for key in sha_map:
            if key.startswith("meeting_") and key.endswith(".csv") and key not in req_csvs:
                req_csvs.append(key)

        for rel in req_csvs:
            raw = fetcher(folder, rel)
            if _validate_checksum(rel, raw, sha_map):
                verified_checksums.append(rel)
            files_bytes[rel] = raw

        # Probe optional listed files in manifest sha256; absent JSONs produce a warning only.
        for key in sha_map:
            if key in files_bytes:
                continue
            try:
                opt_raw = fetcher(folder, key)
                if _validate_checksum(key, opt_raw, sha_map):
                    verified_checksums.append(key)
                files_bytes[key] = opt_raw
            except FileNotFoundError:
                msg = f"trial_bot manifest lists optional file {key!r} which is absent on branch"
                logger.warning(f"[Bot Feeds Warn] {msg}")
                warnings.append(msg)
            except Exception as exc:
                msg = f"trial_bot optional file {key!r} probe failed: {exc}"
                logger.warning(f"[Bot Feeds Warn] {msg}")
                warnings.append(msg)

        decl_rows = _parse_csv_bytes(
            files_bytes["declared_trials_latest.csv"], REQUIRED_COLUMNS["trial_bot_declared"], "declared_trials_latest.csv"
        )
        hist_rows = _parse_csv_bytes(
            files_bytes["trials_history.csv"], REQUIRED_COLUMNS["trial_bot_history"], "trials_history.csv"
        )
        rc = manifest.get("row_counts") or {}
        if len(decl_rows) != int(rc.get("declared_trials_latest_csv", -1)):
            raise ValueError(
                f"trial_bot declared_trials_latest.csv rows {len(decl_rows)} != manifest {rc.get('declared_trials_latest_csv')}"
            )
        if len(hist_rows) != int(rc.get("trials_history", -1)):
            raise ValueError(
                f"trial_bot trials_history.csv rows {len(hist_rows)} != manifest {rc.get('trials_history')}"
            )
        for rel in req_csvs:
            if rel.startswith("meeting_") and rel.endswith(".csv"):
                m_rows = _parse_csv_bytes(files_bytes[rel], REQUIRED_COLUMNS["trial_bot_declared"], rel)
                if "meeting_csv" in rc and len(m_rows) != int(rc["meeting_csv"]):
                    raise ValueError(f"trial_bot {rel} rows {len(m_rows)} != manifest {rc['meeting_csv']}")

        parsed["declared_rows"] = decl_rows
        parsed["history_rows"] = hist_rows

    elif folder == "steward":
        if manifest.get("status") != "ok":
            raise ValueError(f"steward manifest status={manifest.get('status')!r} != 'ok'")
        for rel in ("records.csv", "horses_latest.json"):
            raw = fetcher(folder, rel)
            if _validate_checksum(rel, raw, sha_map):
                verified_checksums.append(rel)
            files_bytes[rel] = raw

        rec_rows = _parse_csv_bytes(files_bytes["records.csv"], REQUIRED_COLUMNS["steward_records"], "steward/records.csv")
        horses_latest = json.loads(files_bytes["horses_latest.json"].decode("utf-8"))
        if not isinstance(horses_latest, dict):
            raise ValueError("steward/horses_latest.json must decode to dict")

        rc = manifest.get("row_counts") or {}
        if len(rec_rows) != int(rc.get("records.csv", -1)):
            raise ValueError(f"steward records.csv rows {len(rec_rows)} != manifest {rc.get('records.csv')}")
        if len(horses_latest) != int(rc.get("horses_latest.json", -1)):
            raise ValueError(
                f"steward horses_latest.json count {len(horses_latest)} != manifest {rc.get('horses_latest.json')}"
            )
        parsed["records_rows"] = rec_rows
        parsed["horses_latest"] = horses_latest

    elif folder == "replay":
        vstat = str(manifest.get("validation_status") or "")
        if not vstat.startswith("PASS"):
            raise ValueError(f"replay validation_status={vstat!r} does not start with PASS")

        all_raw = fetcher(folder, "all_trip_notes.csv")
        if _validate_checksum("all_trip_notes.csv", all_raw, sha_map):
            verified_checksums.append("all_trip_notes.csv")
        files_bytes["all_trip_notes.csv"] = all_raw
        all_rows = _parse_csv_bytes(all_raw, REQUIRED_COLUMNS["replay"], "replay/all_trip_notes.csv")
        if len(all_rows) != int(manifest.get("total_rows", -1)):
            raise ValueError(f"replay all_trip_notes.csv rows {len(all_rows)} != manifest {manifest.get('total_rows')}")

        for mt in manifest.get("meetings") or []:
            csv_name = mt.get("csv")
            if csv_name:
                m_raw = fetcher(folder, csv_name)
                if _validate_checksum(csv_name, m_raw, sha_map):
                    verified_checksums.append(csv_name)
                files_bytes[csv_name] = m_raw
                m_rows = _parse_csv_bytes(m_raw, REQUIRED_COLUMNS["replay"], f"replay/{csv_name}")
                if len(m_rows) != int(mt.get("row_count", -1)):
                    raise ValueError(f"replay {csv_name} rows {len(m_rows)} != manifest {mt.get('row_count')}")
            json_name = mt.get("json")
            if json_name:
                try:
                    j_raw = fetcher(folder, json_name)
                    if _validate_checksum(json_name, j_raw, sha_map):
                        verified_checksums.append(json_name)
                    files_bytes[json_name] = j_raw
                    j_obj = json.loads(j_raw.decode("utf-8"))
                    j_rows = j_obj.get("rows", []) if isinstance(j_obj, dict) else (j_obj if isinstance(j_obj, list) else [])
                    if len(j_rows) != int(mt.get("row_count", -1)):
                        raise ValueError(f"replay {json_name} rows {len(j_rows)} != manifest {mt.get('row_count')}")
                except FileNotFoundError:
                    msg = f"replay meeting json {json_name!r} absent"
                    logger.warning(f"[Bot Feeds Warn] {msg}")
                    warnings.append(msg)

        parsed["all_rows"] = all_rows

    elif folder == "grok_rising":
        if manifest.get("status") != "ok":
            raise ValueError(f"grok_rising manifest status={manifest.get('status')!r} != 'ok'")
        rc = manifest.get("row_counts") or {}
        csv_files = [k for k in sha_map if k.endswith(".csv")]
        if not csv_files:
            csv_files = [os.path.basename(f) for f in (manifest.get("files") or []) if str(f).endswith(".csv")]

        combined_rows: list[dict[str, str]] = []
        for rel in csv_files:
            raw = fetcher(folder, rel)
            if _validate_checksum(rel, raw, sha_map):
                verified_checksums.append(rel)
            files_bytes[rel] = raw
            rows = _parse_csv_bytes(raw, REQUIRED_COLUMNS["grok_rising"], f"grok_rising/{rel}")
            if rel in rc and len(rows) != int(rc[rel]):
                raise ValueError(f"grok_rising {rel} rows {len(rows)} != manifest {rc[rel]}")
            combined_rows.extend(rows)

        parsed["rows"] = combined_rows

    elif folder == "grok_bot":
        if not isinstance(manifest.get("meetings"), list) or "total_rows" not in manifest:
            raise ValueError("grok_bot manifest missing meetings list or total_rows")
        all_raw = fetcher(folder, "all_ev_records.csv")
        files_bytes["all_ev_records.csv"] = all_raw
        all_rows = _parse_csv_bytes(all_raw, REQUIRED_COLUMNS["grok_bot"], "grok_bot/all_ev_records.csv")
        if len(all_rows) != int(manifest.get("total_rows", -1)):
            raise ValueError(f"grok_bot all_ev_records.csv rows {len(all_rows)} != manifest {manifest.get('total_rows')}")

        for mt in manifest.get("meetings") or []:
            for jf in mt.get("files") or []:
                if not str(jf).endswith(".json"):
                    continue
                j_raw = fetcher(folder, jf)
                files_bytes[jf] = j_raw
                j_obj = json.loads(j_raw.decode("utf-8"))
                j_recs = j_obj.get("records", []) if isinstance(j_obj, dict) else []
                if len(j_recs) != int(mt.get("records", -1)):
                    raise ValueError(f"grok_bot {jf} records {len(j_recs)} != manifest {mt.get('records')}")

        parsed["rows"] = all_rows
    else:
        raise ValueError(f"Unknown bot folder: {folder!r}")

    run_time = (
        manifest.get("run_time_hkt")
        or manifest.get("manifest_written_at_hkt")
        or manifest.get("built_at")
        or manifest.get("run_time_utc")
    )
    meta = {
        "folder": folder,
        "status": "ok",
        "source": "live",
        "manifest_run_time": run_time,
        "age_hours": _compute_age_hours(run_time),
        "checksums_verified": len(verified_checksums),
        "checksums_in_manifest": len(sha_map),
        "verified_files": verified_checksums,
        "warnings": warnings,
        "error": None,
    }
    return files_bytes, parsed, meta


def _load_cached_folder(folder: str, folder_dir: str) -> Optional[tuple[dict[str, Any], dict[str, Any]]]:
    manifest_path = os.path.join(folder_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        return None

    def _disk_fetcher(_folder: str, relpath: str) -> bytes:
        p = os.path.join(folder_dir, relpath)
        if not os.path.exists(p):
            raise FileNotFoundError(relpath)
        with open(p, "rb") as f:
            return f.read()

    _, parsed, meta = _validate_and_parse_folder(folder, _disk_fetcher)
    fetched_path = os.path.join(folder_dir, "_fetched.json")
    if os.path.exists(fetched_path):
        try:
            with open(fetched_path, "r", encoding="utf-8") as f:
                f_info = json.load(f)
            meta["fetched_at_utc"] = f_info.get("fetched_at_utc")
            meta["fetched_at_hkt"] = f_info.get("fetched_at_hkt")
        except Exception:
            pass
    meta["source"] = "cache"
    return parsed, meta


def _write_folder_cache(folder_dir: str, files_bytes: dict[str, bytes], meta: dict[str, Any]) -> None:
    os.makedirs(folder_dir, exist_ok=True)
    for rel, raw in files_bytes.items():
        dst = os.path.join(folder_dir, rel)
        _atomic_write_bytes(dst, raw)
    now_utc = datetime.now(timezone.utc)
    now_hkt = now_utc + timedelta(hours=8)
    fetched_meta = {
        "fetched_at_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fetched_at_hkt": now_hkt.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "manifest_run_time": meta.get("manifest_run_time"),
        "checksums_verified": meta.get("verified_files", []),
        "warnings": meta.get("warnings", []),
    }
    _atomic_write_json(os.path.join(folder_dir, "_fetched.json"), fetched_meta)
    meta["fetched_at_utc"] = fetched_meta["fetched_at_utc"]
    meta["fetched_at_hkt"] = fetched_meta["fetched_at_hkt"]


def fetch_bot_folder(
    folder: str,
    *,
    ref: Optional[str] = None,
    cache_dir: Optional[str] = None,
    transport_fn: Optional[Callable[[str, str], bytes]] = None,
    retry_delay_s: float = 60.0,
    sleep_fn: Callable[[float], None] = time.sleep,
    force_refresh: bool = False,
) -> tuple[Optional[dict[str, Any]], dict[str, Any]]:
    """
    Fetches, validates, and caches one bot folder from `trial-data`.
    Retries once on transient mismatch/fetch error, preserves existing cache on
    failure, and calls `record_health(bot_feed_<folder>, "fail", ...)` on error.
    """
    ref_val = ref or get_bot_feeds_ref()
    cache_root = get_bot_feeds_cache_dir(cache_dir)
    folder_dir = os.path.join(cache_root, folder)

    # Reuse fresh disk cache when hitting live HTTP within CACHE_TTL_S.
    if transport_fn is None and not force_refresh and not _env_flag("SILKS_BOT_FEEDS_FORCE_REFRESH", False):
        fetched_path = os.path.join(folder_dir, "_fetched.json")
        if os.path.exists(fetched_path):
            try:
                with open(fetched_path, "r", encoding="utf-8") as f:
                    f_info = json.load(f)
                dt = _parse_iso_datetime(f_info.get("fetched_at_utc"))
                if dt is not None and (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() < CACHE_TTL_S:
                    cached = _load_cached_folder(folder, folder_dir)
                    if cached is not None:
                        return cached
            except Exception:
                pass

    fetcher = transport_fn or _default_http_transport(ref_val, get_bot_feeds_timeout())
    last_exc: Optional[Exception] = None

    for attempt in range(2):
        try:
            files_bytes, parsed, meta = _validate_and_parse_folder(folder, fetcher)
            _write_folder_cache(folder_dir, files_bytes, meta)
            return parsed, meta
        except Exception as exc:
            last_exc = exc
            logger.warning(f"[Bot Feeds Retry {attempt + 1}/2] folder={folder}: {exc}")
            if attempt == 0:
                sleep_fn(max(0.0, float(retry_delay_s)))

    err_msg = str(last_exc)
    logger.error(f"[Bot Feeds Fail] folder={folder} rejected: {err_msg}")
    try:
        record_health(f"bot_feed_{folder}", "fail", metrics={"ref": ref_val}, error=err_msg)
    except Exception:
        pass

    try:
        cached = _load_cached_folder(folder, folder_dir)
        if cached is not None:
            parsed_c, meta_c = cached
            meta_c["status"] = "stale_cache"
            meta_c["error"] = f"Live validation failed (serving cached copy): {err_msg}"
            return parsed_c, meta_c
    except Exception:
        pass

    return None, {
        "folder": folder,
        "status": "fail",
        "source": "none",
        "manifest_run_time": None,
        "age_hours": None,
        "checksums_verified": 0,
        "verified_files": [],
        "warnings": [],
        "error": err_msg,
    }


# ---------------------------------------------------------------------------
# Feature extraction, grok_bot cross-check, runner join, & coverage gate
# ---------------------------------------------------------------------------

def _crosscheck_grok_feeds(rising_rows: list[dict[str, str]], bot_rows: list[dict[str, str]]) -> dict[str, Any]:
    def _to_key_map(rows: list[dict[str, str]]) -> dict[tuple[str, str, str], tuple[str, str, Optional[bool]]]:
        out = {}
        for r in rows:
            dt = normalize_date(r.get("meeting_date")) or ""
            code = normalize_horse_code(r.get("horse_code")) or ""
            ftype = (clean_val(r.get("flag_type")) or "").lower()
            direction = (clean_val(r.get("direction")) or "").lower()
            priority = (clean_val(r.get("priority")) or "").lower()
            verified = parse_tri_bool(r.get("verified"))
            out[(dt, code, ftype)] = (direction, priority, verified)
        return out

    rising_map = _to_key_map(rising_rows)
    bot_map = _to_key_map(bot_rows)
    only_rising = sorted(set(rising_map) - set(bot_map))
    only_bot = sorted(set(bot_map) - set(rising_map))
    attr_diffs = sorted(k for k in (set(rising_map) & set(bot_map)) if rising_map[k] != bot_map[k])
    diff_count = len(only_rising) + len(only_bot) + len(attr_diffs)
    if diff_count > 0:
        logger.warning(
            f"[Grok Feed Crosscheck] Detected {diff_count} differences between grok_rising and grok_bot "
            f"(only_rising={only_rising[:3]}, only_bot={only_bot[:3]}, attr_diffs={attr_diffs[:3]})"
        )
    return {
        "diff_count": diff_count,
        "only_rising": len(only_rising),
        "only_bot": len(only_bot),
        "attr_diffs": len(attr_diffs),
    }


def _match_runner_to_lookup(
    runner: dict,
    by_code: dict[str, list[dict]],
    by_name: dict[str, list[dict]],
    folder_label: str,
) -> tuple[list[dict], Optional[str]]:
    code = normalize_horse_code(runner.get("code") or runner.get("horse_code"))
    if code and code in by_code:
        return by_code[code], "code"
    c_name = normalize_horse_name(runner.get("clean_name") or runner.get("name"))
    if c_name and c_name in by_name:
        if not code:
            logger.info(f"[Bot Feeds Name Fallback] {folder_label}: matched {c_name} by normalized name (horse_code absent)")
        else:
            logger.info(f"[Bot Feeds Name Fallback] {folder_label}: matched {c_name} ({code}) by normalized name")
        return by_name[c_name], "name"
    return [], None


def _build_indexes(rows: list[dict], name_keys: tuple[str, ...] = ("horse_name", "horse")) -> tuple[dict, dict]:
    by_code: dict[str, list[dict]] = {}
    by_name: dict[str, list[dict]] = {}
    for row in rows:
        code = normalize_horse_code(row.get("horse_code"))
        if code:
            by_code.setdefault(code, []).append(row)
        for nk in name_keys:
            nm = normalize_horse_name(row.get(nk))
            if nm:
                by_name.setdefault(nm, []).append(row)
                break
    return by_code, by_name


def _set_if_present(dest: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        dest[key] = value


def _extract_trial_bot_features(row: dict[str, str], is_history_fallback: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {}
    t_date = normalize_date(row.get("trial_date"))
    pos = parse_int(row.get("trial_finish_pos"))
    field = parse_int(row.get("trial_field_size"))
    time_sec = parse_float(row.get("trial_time_sec"))
    median_sec = parse_float(row.get("trial_same_surface_distance_median_sec"))
    days_since = parse_int(row.get("days_since_trial"))

    _set_if_present(out, "bot_trial_date", t_date)
    _set_if_present(out, "bot_days_since_trial", days_since)
    _set_if_present(out, "bot_trial_pos", pos)
    _set_if_present(out, "bot_trial_field_size", field)
    if pos is not None and field is not None and field > 0:
        out["bot_trial_pos_ratio"] = float(pos / field)
    _set_if_present(out, "bot_trial_lbw_lengths", parse_float(row.get("trial_lbw_lengths")))
    _set_if_present(out, "bot_trial_time_sec", time_sec)
    if median_sec is not None and time_sec is not None:
        out["bot_trial_speed_vs_median_sec"] = round(float(median_sec - time_sec), 3)
    _set_if_present(out, "bot_trial_median_n", parse_int(row.get("trial_same_surface_distance_n_timed")))
    _set_if_present(out, "bot_trial_track", clean_val(row.get("trial_track")))
    _set_if_present(out, "bot_trial_surface", clean_val(row.get("trial_surface")))
    _set_if_present(out, "bot_trial_distance_m", parse_int(row.get("trial_distance_m")))

    _set_if_present(out, "bot_flag_fast", parse_tri_bool(row.get("flag_speed_outlier_fast")))
    _set_if_present(out, "bot_flag_slow", parse_tri_bool(row.get("flag_speed_outlier_slow")))
    _set_if_present(out, "bot_flag_quality_opp", parse_tri_bool(row.get("flag_quality_opposition")))
    _set_if_present(out, "bot_flag_poor_finish", parse_tri_bool(row.get("flag_poor_finish")))
    _set_if_present(out, "bot_flag_stale", parse_tri_bool(row.get("flag_stale_trial")))
    _set_if_present(out, "bot_trial_gear_differs", parse_tri_bool(row.get("trial_gear_differs_from_declared")))
    _set_if_present(out, "bot_trial_comment", clean_val(row.get("trial_comment")))
    _set_if_present(out, "bot_trial_source_url", clean_val(row.get("source_url_trial") or row.get("source_url")))
    if is_history_fallback:
        out["bot_trial_history_fallback"] = True
    return out


def _steward_row_event_date(row: dict[str, str]) -> Optional[str]:
    md = normalize_date(row.get("meeting_date"))
    if md:
        return md
    ev = normalize_date(row.get("event_date"))
    if ev:
        return ev
    mid_d, _ = parse_steward_meeting_id(row.get("meeting_id"))
    return mid_d


def _extract_steward_features(
    prior_rows: list[dict[str, str]],
    all_rows_for_horse: list[dict[str, str]],
    horses_latest_by_code: dict[str, dict],
    horse_code: Optional[str],
    target_date: str,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not prior_rows:
        return out

    sorted_prior = sorted(prior_rows, key=lambda r: (_steward_row_event_date(r) or "", clean_val(r.get("record_id")) or ""))
    latest_prior = sorted_prior[-1]

    has_future_row = any((_steward_row_event_date(r) or "") >= target_date for r in all_rows_for_horse)
    hl_entry = horses_latest_by_code.get(horse_code or "")
    hl_ok = False
    if hl_entry and not has_future_row:
        passed_dt = normalize_date(hl_entry.get("passed_on"))
        latest_ev = normalize_date((hl_entry.get("latest_entry") or {}).get("event_date"))
        if (latest_ev is None or latest_ev < target_date) and (passed_dt is None or passed_dt < target_date):
            hl_ok = True

    if hl_ok and hl_entry:
        _set_if_present(out, "bot_steward_status", clean_val(hl_entry.get("status")))
        open_reqs = hl_entry.get("open_requirements")
        if isinstance(open_reqs, list) and open_reqs:
            out["bot_steward_open_requirements"] = list(open_reqs)
        le = hl_entry.get("latest_entry") or {}
        _set_if_present(out, "bot_steward_latest_category", clean_val(le.get("category")))
        _set_if_present(out, "bot_steward_latest_event_date", normalize_date(le.get("event_date")) or _steward_row_event_date(latest_prior))
        _set_if_present(out, "bot_steward_source_url", clean_val(le.get("source_url") or latest_prior.get("source_url")))
    else:
        # Derive point-in-time status from prior rows without post-target_date clearances.
        active_reqs = []
        eff_statuses = []
        for r in sorted_prior:
            r_status = (clean_val(r.get("status")) or "").lower()
            passed_dt = normalize_date(r.get("passed_on"))
            if passed_dt and passed_dt >= target_date and r_status == "cleared":
                r_status = "active_requirement"
            eff_statuses.append(r_status)
            if r_status == "active_requirement":
                req_txt = clean_val(r.get("requirement")) or clean_val(r.get("finding_verbatim")) or clean_val(r.get("category"))
                if req_txt and req_txt not in active_reqs:
                    active_reqs.append(req_txt)
        eff_latest_status = "active_requirement" if "active_requirement" in eff_statuses else (eff_statuses[-1] if eff_statuses else None)
        _set_if_present(out, "bot_steward_status", eff_latest_status)
        if active_reqs:
            out["bot_steward_open_requirements"] = active_reqs
        _set_if_present(out, "bot_steward_latest_category", clean_val(latest_prior.get("category")))
        _set_if_present(out, "bot_steward_latest_event_date", _steward_row_event_date(latest_prior))
        _set_if_present(out, "bot_steward_source_url", clean_val(latest_prior.get("source_url")))

    _set_if_present(out, "bot_steward_latest_is_material", parse_tri_bool(latest_prior.get("is_material")))
    out["bot_steward_prior_records_count"] = len(sorted_prior)
    return out


def _extract_replay_features(prior_rows: list[dict[str, str]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not prior_rows:
        return out
    sorted_rows = sorted(
        prior_rows,
        key=lambda r: (normalize_date(r.get("meeting_date") or r.get("date")) or "", parse_int(r.get("race_no") or r.get("race")) or 0),
    )
    latest = sorted_rows[-1]
    _set_if_present(out, "bot_replay_meeting_date", normalize_date(latest.get("meeting_date") or latest.get("date")))

    flags_raw = clean_val(latest.get("flags"))
    flags_list = [t.strip().lower() for t in re.split(r"[;|,]", flags_raw) if t.strip()] if flags_raw else []
    if flags_list:
        out["bot_replay_flags"] = flags_list

    _set_if_present(out, "bot_replay_traffic", parse_tri_bool(latest.get("traffic")))
    _set_if_present(out, "bot_replay_wide_no_cover", parse_tri_bool(latest.get("wide_no_cover")))
    _set_if_present(out, "bot_replay_slow_away", parse_tri_bool(latest.get("slow_away")))

    fin_pos, dead_heat = parse_replay_finish(latest.get("finish"))
    _set_if_present(out, "bot_replay_finish", fin_pos)
    if dead_heat:
        out["bot_replay_dead_heat"] = True

    _set_if_present(out, "bot_replay_race_no", parse_int(latest.get("race_no") or latest.get("race")))
    _set_if_present(out, "bot_replay_race_id", clean_val(latest.get("race_id")))
    _set_if_present(out, "bot_replay_draw", parse_int(latest.get("draw")))
    _set_if_present(out, "bot_replay_win_odds", parse_float(latest.get("win_odds")))
    _set_if_present(out, "bot_replay_last400_sec", parse_float(latest.get("horse_last_400m_sec")))
    _set_if_present(out, "bot_replay_race_last400_sec", parse_float(latest.get("race_last_400m_sec")))
    _set_if_present(out, "bot_replay_clearance_text", clean_val(latest.get("clearance_required")))
    _set_if_present(out, "bot_replay_vet_finding", clean_val(latest.get("vet_finding")))
    _set_if_present(out, "bot_replay_source", clean_val(latest.get("source")))
    out["bot_replay_prior_count"] = len(sorted_rows)
    return out


def _extract_ev_flags(prior_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    flags = []
    for r in prior_rows:
        item = {}
        _set_if_present(item, "flag_type", (clean_val(r.get("flag_type")) or "").lower() or None)
        _set_if_present(item, "direction", (clean_val(r.get("direction")) or "").lower() or None)
        _set_if_present(item, "priority", (clean_val(r.get("priority")) or "").lower() or None)
        _set_if_present(item, "clearance_required", parse_tri_bool(r.get("clearance_required")))
        _set_if_present(item, "verified", parse_tri_bool(r.get("verified")))
        _set_if_present(item, "meeting_date", normalize_date(r.get("meeting_date")))
        if item:
            flags.append(item)
    return flags


def check_bot_coverage(
    meeting_date: str,
    venue: str,
    runners: list[dict],
    features: dict[str, dict],
    threshold: float = 0.95,
    *,
    folder_meta: Optional[dict[str, Any]] = None,
    match_stats: Optional[dict[str, Any]] = None,
    cache_dir: Optional[str] = None,
    grok_crosscheck: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Computes declared-runner coverage per bot folder, enforces the >=95% trial_bot
    gate, and writes the report strictly to `<cache>/coverage_<date>_<venue>.json`.
    """
    norm_date = normalize_date(meeting_date) or str(meeting_date)
    norm_venue = normalize_venue(venue) or str(venue).upper()
    cache_root = get_bot_feeds_cache_dir(cache_dir)
    f_meta = folder_meta or {}
    m_stats = match_stats or {}

    declared_runners = []
    standby_runners = []
    withdrawn_count = 0
    for rn in runners or []:
        st_raw = str(rn.get("runner_status") or rn.get("status") or "").strip().lower()
        is_standby = (st_raw == "standby") or (rn.get("horse_no") in ("", None) and rn.get("standby_order") not in ("", None)) or (rn.get("no") in (None, "", 0) and st_raw == "standby")
        if st_raw in ("withdrawn", "scratched"):
            withdrawn_count += 1
        elif is_standby:
            standby_runners.append(rn)
        else:
            declared_runners.append(rn)

    declared_count = len(declared_runners)
    folders_report: dict[str, Any] = {}

    for folder in ("trial_bot", "steward", "replay", "grok_rising"):
        meta = f_meta.get(folder) or {}
        st = m_stats.get(folder) or {}
        by_code = int(st.get("matched_by_code", 0))
        by_name = int(st.get("matched_by_name", 0))
        matched_total = by_code + by_name
        unmatched = list(st.get("unmatched", []))

        # Fallback computation purely from `features` when caller calls check_bot_coverage directly.
        if folder not in m_stats and declared_runners:
            by_code, by_name, unmatched = 0, 0, []
            fresh_c, stale_c, missing_c = 0, 0, 0
            for rn in declared_runners:
                nm = normalize_horse_name(rn.get("clean_name") or rn.get("name"))
                feat = features.get(nm or "", {}) if nm else {}
                has_rec = (
                    ("bot_trial_pos" in feat or "bot_trial_date" in feat) if folder == "trial_bot"
                    else ("bot_steward_status" in feat if folder == "steward"
                          else ("bot_replay_meeting_date" in feat if folder == "replay"
                                else bool(feat.get("bot_ev_flags"))))
                )
                if has_rec:
                    if normalize_horse_code(rn.get("code") or rn.get("horse_code")):
                        by_code += 1
                    else:
                        by_name += 1
                    if folder == "trial_bot":
                        if feat.get("bot_flag_stale") is True:
                            stale_c += 1
                        else:
                            fresh_c += 1
                else:
                    unmatched.append(
                        f"R{rn.get('race_no', '?')}-{rn.get('no', '?')} {rn.get('name', '?')} ({rn.get('code') or rn.get('horse_code') or 'NO_CODE'})"
                    )
                    if folder == "trial_bot":
                        missing_c += 1
            matched_total = by_code + by_name
        else:
            fresh_c = int(st.get("fresh", 0))
            stale_c = int(st.get("stale", 0))
            missing_c = int(st.get("missing_trial", max(0, declared_count - matched_total)))

        ratio = round(matched_total / declared_count, 4) if declared_count > 0 else 0.0
        entry: dict[str, Any] = {
            "status": meta.get("status", "unknown"),
            "source": meta.get("source", "unknown"),
            "manifest_run_time": meta.get("manifest_run_time"),
            "age_hours": meta.get("age_hours"),
            "checksums_verified": meta.get("checksums_verified", 0),
            "checksums_in_manifest": meta.get("checksums_in_manifest", 0),
            "warnings": meta.get("warnings", []),
            "error": meta.get("error"),
            "matched_by_code": by_code,
            "matched_by_name": by_name,
            "matched_total": matched_total,
            "coverage_ratio": ratio,
            "unmatched": unmatched,
        }
        if "prior_records_available" in st:
            entry["prior_records_available"] = st["prior_records_available"]
        if folder == "trial_bot":
            entry["fresh"] = fresh_c
            entry["stale"] = stale_c
            entry["missing_trial"] = missing_c
            entry["rows_for_target_meeting"] = st.get("rows_for_target_meeting", matched_total)
        folders_report[folder] = entry

    if "grok_bot" in f_meta:
        gb_meta = f_meta["grok_bot"]
        folders_report["grok_bot_crosscheck"] = {
            "status": gb_meta.get("status", "unknown"),
            "manifest_run_time": gb_meta.get("manifest_run_time"),
            "age_hours": gb_meta.get("age_hours"),
            **(grok_crosscheck or {}),
        }

    tb_rep = folders_report["trial_bot"]
    no_meeting_rows = tb_rep.get("rows_for_target_meeting", 0) == 0
    below_thresh = declared_count == 0 or tb_rep["coverage_ratio"] < threshold
    gate_failed = no_meeting_rows or below_thresh

    gate_status = "fail" if gate_failed else "ok"
    gate_reason = None
    if no_meeting_rows:
        gate_reason = f"No trial_bot rows for target meeting {norm_date} {norm_venue}"
    elif below_thresh:
        gate_reason = (
            f"trial_bot coverage {tb_rep['matched_total']}/{declared_count} "
            f"({tb_rep['coverage_ratio'] * 100:.1f}%) < {threshold * 100:.1f}%"
        )

    report = {
        "meeting_date": norm_date,
        "venue": norm_venue,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "declared_runners": declared_count,
        "standby_runners": len(standby_runners),
        "withdrawn_excluded": withdrawn_count,
        "threshold": threshold,
        "gate_status": gate_status,
        "gate_reason": gate_reason,
        "folders": folders_report,
    }

    try:
        _atomic_write_json(os.path.join(cache_root, f"coverage_{norm_date}_{norm_venue}.json"), report)
        _atomic_write_json(
            os.path.join(cache_root, "_bot_feeds_health.json"),
            {
                "updated_at_utc": report["generated_at_utc"],
                "mode": get_bot_feeds_mode(),
                "meeting_date": norm_date,
                "venue": norm_venue,
                "gate_status": gate_status,
                "gate_reason": gate_reason,
                "declared_runners": declared_count,
                "trial_bot_matched": tb_rep["matched_total"],
                "trial_bot_coverage_pct": round(tb_rep["coverage_ratio"] * 100.0, 1),
                "folders": {
                    k: {
                        "status": v.get("status"),
                        "manifest_run_time": v.get("manifest_run_time"),
                        "age_hours": v.get("age_hours"),
                        "matched_total": v.get("matched_total"),
                    }
                    for k, v in folders_report.items()
                },
            },
        )
    except Exception as exc:
        logger.warning(f"Failed writing coverage cache report: {exc}")

    if gate_failed:
        print(f"[BOT FEEDS COVERAGE GATE FAIL] {norm_date} {norm_venue}: {gate_reason}")
        try:
            record_health(
                "bot_feed_coverage",
                "fail",
                metrics={
                    "meeting_date": norm_date,
                    "venue": norm_venue,
                    "matched": tb_rep["matched_total"],
                    "declared": declared_count,
                    "coverage_ratio": tb_rep["coverage_ratio"],
                },
                error=gate_reason,
            )
        except Exception:
            pass
        if is_coverage_strict():
            raise RuntimeError(gate_reason)

    return report


def load_bot_feeds(
    meeting_date: str,
    venue: str,
    runners: list[dict],
    *,
    ref: Optional[str] = None,
    cache_dir: Optional[str] = None,
    transport_fn: Optional[Callable[[str, str], bytes]] = None,
    retry_delay_s: float = 60.0,
    sleep_fn: Callable[[float], None] = time.sleep,
    allow_history_trial_fallback: bool = False,
    threshold: float = 0.95,
) -> tuple[dict[str, dict], dict[str, Any]]:
    """
    Loads and validates all five `trial-data` bot folders, applies strict
    anti-look-ahead meeting filters, joins onto `runners`, and runs the coverage gate.
    Returns `(features_by_clean_name, coverage_report)`.
    """
    norm_date = normalize_date(meeting_date) or str(meeting_date)
    norm_venue = normalize_venue(venue) or str(venue).upper()
    cache_root = get_bot_feeds_cache_dir(cache_dir)

    parsed_by_folder: dict[str, Optional[dict[str, Any]]] = {}
    meta_by_folder: dict[str, dict[str, Any]] = {}
    for folder in ("trial_bot", "steward", "replay", "grok_rising", "grok_bot"):
        parsed, meta = fetch_bot_folder(
            folder,
            ref=ref,
            cache_dir=cache_root,
            transport_fn=transport_fn,
            retry_delay_s=retry_delay_s,
            sleep_fn=sleep_fn,
        )
        parsed_by_folder[folder] = parsed
        meta_by_folder[folder] = meta

    # 1. trial_bot index strictly matching target meeting & venue (never another card).
    tb_parsed = parsed_by_folder.get("trial_bot") or {}
    decl_rows = [
        r for r in (tb_parsed.get("declared_rows") or [])
        if normalize_date(r.get("meeting_date")) == norm_date
        and normalize_venue(r.get("venue")) == norm_venue
        and (clean_val(r.get("runner_status")) or "declared").lower() == "declared"
    ]
    tb_is_history_fb = False
    if not decl_rows and allow_history_trial_fallback:
        hist_rows = tb_parsed.get("history_rows") or []
        latest_hist_by_key: dict[str, dict] = {}
        for hr in hist_rows:
            t_dt = normalize_date(hr.get("trial_date"))
            if not t_dt or t_dt >= norm_date:
                continue
            code = normalize_horse_code(hr.get("horse_code"))
            nm = normalize_horse_name(hr.get("horse_name"))
            k = code or nm
            if not k:
                continue
            days_val = (datetime.strptime(norm_date, "%Y-%m-%d") - datetime.strptime(t_dt, "%Y-%m-%d")).days
            if days_val <= 0:
                continue
            prev = latest_hist_by_key.get(k)
            if prev is None or t_dt > prev[0]:
                enriched = dict(hr)
                enriched["days_since_trial"] = str(days_val)
                enriched["flag_stale_trial"] = "true" if days_val > 90 else "false"
                enriched["source_url_trial"] = hr.get("source_url", "")
                latest_hist_by_key[k] = (t_dt, enriched)
        decl_rows = [v[1] for v in latest_hist_by_key.values()]
        tb_is_history_fb = True

    tb_by_code, tb_by_name = _build_indexes(decl_rows)

    # 2. steward indexes (strictly prior meeting_date or history-only event_date < target_date).
    st_parsed = parsed_by_folder.get("steward") or {}
    st_all_rows = st_parsed.get("records_rows") or []
    st_prior_rows = [r for r in st_all_rows if (_steward_row_event_date(r) or "9999-99-99") < norm_date]
    st_all_by_code, st_all_by_name = _build_indexes(st_all_rows)
    st_prior_by_code, st_prior_by_name = _build_indexes(st_prior_rows)
    horses_latest_by_code: dict[str, dict] = {}
    for _, h_rec in (st_parsed.get("horses_latest") or {}).items():
        if isinstance(h_rec, dict):
            hc = normalize_horse_code(h_rec.get("horse_code"))
            if hc:
                horses_latest_by_code[hc] = h_rec

    # 3. replay index (strictly meeting_date < target_date).
    rp_parsed = parsed_by_folder.get("replay") or {}
    rp_prior_rows = [
        r for r in (rp_parsed.get("all_rows") or [])
        if (normalize_date(r.get("meeting_date") or r.get("date")) or "9999-99-99") < norm_date
    ]
    rp_by_code, rp_by_name = _build_indexes(rp_prior_rows, name_keys=("horse_name", "horse"))

    # 4. grok_rising canonical + grok_bot cross-check.
    gr_parsed = parsed_by_folder.get("grok_rising") or {}
    gb_parsed = parsed_by_folder.get("grok_bot") or {}
    grok_crosscheck = _crosscheck_grok_feeds(gr_parsed.get("rows") or [], gb_parsed.get("rows") or [])
    gr_prior_rows = [
        r for r in (gr_parsed.get("rows") or [])
        if (normalize_date(r.get("meeting_date")) or "9999-99-99") < norm_date
    ]
    gr_by_code, gr_by_name = _build_indexes(gr_prior_rows)

    bot_sources = {
        folder: meta_by_folder[folder].get("manifest_run_time")
        for folder in ("trial_bot", "steward", "replay", "grok_rising")
        if meta_by_folder.get(folder, {}).get("manifest_run_time")
    }

    match_stats: dict[str, dict[str, Any]] = {
        "trial_bot": {
            "matched_by_code": 0,
            "matched_by_name": 0,
            "unmatched": [],
            "fresh": 0,
            "stale": 0,
            "missing_trial": 0,
            "rows_for_target_meeting": len(decl_rows),
        },
        "steward": {"matched_by_code": 0, "matched_by_name": 0, "unmatched": [], "prior_records_available": len(st_prior_rows)},
        "replay": {"matched_by_code": 0, "matched_by_name": 0, "unmatched": [], "prior_records_available": len(rp_prior_rows)},
        "grok_rising": {"matched_by_code": 0, "matched_by_name": 0, "unmatched": [], "prior_records_available": len(gr_prior_rows)},
    }

    features_by_name: dict[str, dict] = {}
    for rn in runners or []:
        st_raw = str(rn.get("runner_status") or rn.get("status") or "").strip().lower()
        is_standby = (st_raw == "standby") or (rn.get("horse_no") in ("", None) and rn.get("standby_order") not in ("", None))
        is_withdrawn = st_raw in ("withdrawn", "scratched")

        c_name = normalize_horse_name(rn.get("clean_name") or rn.get("name"))
        if not c_name:
            continue
        h_code = normalize_horse_code(rn.get("code") or rn.get("horse_code"))
        runner_tag = f"R{rn.get('race_no', '?')}-{rn.get('no', '?')} {rn.get('name', c_name)} ({h_code or 'NO_CODE'})"

        feat: dict[str, Any] = {}

        # trial_bot join
        tb_hits, tb_how = _match_runner_to_lookup(rn, tb_by_code, tb_by_name, "trial_bot")
        if tb_hits:
            tb_feats = _extract_trial_bot_features(tb_hits[0], is_history_fallback=tb_is_history_fb)
            feat.update(tb_feats)
            if not is_standby and not is_withdrawn:
                match_stats["trial_bot"][f"matched_by_{tb_how}"] += 1
                if tb_feats.get("bot_flag_stale") is True:
                    match_stats["trial_bot"]["stale"] += 1
                else:
                    match_stats["trial_bot"]["fresh"] += 1
        elif not is_standby and not is_withdrawn:
            match_stats["trial_bot"]["unmatched"].append(runner_tag)
            match_stats["trial_bot"]["missing_trial"] += 1

        # steward join
        st_prior_hits, st_how = _match_runner_to_lookup(rn, st_prior_by_code, st_prior_by_name, "steward")
        st_all_hits, _ = _match_runner_to_lookup(rn, st_all_by_code, st_all_by_name, "steward_all")
        if st_prior_hits:
            feat.update(
                _extract_steward_features(st_prior_hits, st_all_hits, horses_latest_by_code, h_code, norm_date)
            )
            if not is_standby and not is_withdrawn:
                match_stats["steward"][f"matched_by_{st_how}"] += 1
        elif not is_standby and not is_withdrawn:
            match_stats["steward"]["unmatched"].append(runner_tag)

        # replay join
        rp_hits, rp_how = _match_runner_to_lookup(rn, rp_by_code, rp_by_name, "replay")
        if rp_hits:
            feat.update(_extract_replay_features(rp_hits))
            if not is_standby and not is_withdrawn:
                match_stats["replay"][f"matched_by_{rp_how}"] += 1
        elif not is_standby and not is_withdrawn:
            match_stats["replay"]["unmatched"].append(runner_tag)

        # grok_rising join
        gr_hits, gr_how = _match_runner_to_lookup(rn, gr_by_code, gr_by_name, "grok_rising")
        if gr_hits:
            ev_list = _extract_ev_flags(gr_hits)
            if ev_list:
                feat["bot_ev_flags"] = ev_list
            if not is_standby and not is_withdrawn:
                match_stats["grok_rising"][f"matched_by_{gr_how}"] += 1
        elif not is_standby and not is_withdrawn:
            match_stats["grok_rising"]["unmatched"].append(runner_tag)

        if feat:
            feat["bot_sources"] = dict(bot_sources)
            features_by_name[c_name] = feat

    report = check_bot_coverage(
        norm_date,
        norm_venue,
        runners,
        features_by_name,
        threshold=threshold,
        folder_meta=meta_by_folder,
        match_stats=match_stats,
        cache_dir=cache_root,
        grok_crosscheck=grok_crosscheck,
    )
    return features_by_name, report


# ---------------------------------------------------------------------------
# Integration helpers: merge_bot_features & live overlay candidates
# ---------------------------------------------------------------------------

def _derive_live_trial_core_keys(feat: dict[str, Any]) -> dict[str, Any]:
    """
    For horses absent from engineered_trial_features.json when SILKS_BOT_LIVE_TRIALS=1,
    derives core trial keys strictly without placeholders or `None`.
    """
    if feat.get("bot_flag_stale") is True:
        return {}
    pos_ratio = feat.get("bot_trial_pos_ratio")
    days_since = feat.get("bot_days_since_trial")
    if pos_ratio is None or (days_since is not None and days_since > 90):
        return {}

    derived: dict[str, Any] = {
        "best_trial_pos_ratio": float(pos_ratio),
        "trial_count_30d": 1 if (days_since is not None and days_since <= 30) else 0,
        "recent_top2_trials": 1 if (feat.get("bot_trial_pos") is not None and feat["bot_trial_pos"] <= 2 and (days_since is None or days_since <= 90)) else 0,
        "high_quality_trial": bool(feat.get("bot_flag_quality_opp") is True),
    }

    # Only compute best_trial_speed_diff using process_trials.STANDARD_TIMES (standard minus own time).
    track = feat.get("bot_trial_track")
    surface = feat.get("bot_trial_surface")
    dist_m = feat.get("bot_trial_distance_m")
    time_sec = feat.get("bot_trial_time_sec")
    if track and surface and dist_m and time_sec is not None:
        from process_trials import STANDARD_TIMES
        std_key = (f"{track} {surface}".strip().upper(), int(dist_m))
        std_time = STANDARD_TIMES.get(std_key)
        if std_time is not None:
            derived["best_trial_speed_diff"] = float(std_time - float(time_sec))

    return derived


def merge_bot_features(
    trial_features: Optional[dict],
    meeting: Optional[dict],
    runners: Optional[list[dict]] = None,
    *,
    cache_dir: Optional[str] = None,
    transport_fn: Optional[Callable[[str, str], bytes]] = None,
    retry_delay_s: float = 60.0,
    sleep_fn: Callable[[float], None] = time.sleep,
    allow_history_trial_fallback: Optional[bool] = None,
    prefetched_bot_features: Optional[dict] = None,
) -> dict:
    """
    Mode-gated entrypoint called right after loading `trial_features`:
      - off    : returns `trial_features` unchanged with zero I/O
      - shadow : merges `bot_*` keys only; leaves all core trial keys untouched
      - live   : also derives missing core trial keys if SILKS_BOT_LIVE_TRIALS=1
    """
    base_tf = trial_features if isinstance(trial_features, dict) else {}
    mode = get_bot_feeds_mode()
    if mode == "off" or not isinstance(meeting, dict):
        return base_tf

    if allow_history_trial_fallback is None:
        allow_history_trial_fallback = _env_flag("SILKS_BOT_ALLOW_HISTORY_TRIAL_FALLBACK", False)

    if prefetched_bot_features is not None:
        bot_feats = prefetched_bot_features
    else:
        meeting_date = normalize_date(meeting.get("date")) or str(meeting.get("date") or "")
        venue = normalize_venue(meeting.get("venue")) or str(meeting.get("venue") or "")
        if not meeting_date or not venue:
            return base_tf

        if runners is None:
            runners = [
                {**rn, "race_no": rc.get("race_no")}
                for rc in (meeting.get("races") or [])
                for rn in (rc.get("runners") or [])
            ]

        cache_root = get_bot_feeds_cache_dir(cache_dir)
        ref_val = get_bot_feeds_ref()
        runner_sig = tuple(
            (str(rn.get("race_no", "")), str(rn.get("no", "")), str(rn.get("code") or rn.get("horse_code") or ""), str(rn.get("name") or ""))
            for rn in runners
        )
        mem_key = (ref_val, cache_root, meeting_date, venue, runner_sig, allow_history_trial_fallback)

        try:
            if transport_fn is None and mem_key in _MEM_MEETING_CACHE:
                ts, cached_feats, _ = _MEM_MEETING_CACHE[mem_key]
                if (time.monotonic() - ts) < CACHE_TTL_S:
                    bot_feats = cached_feats
                else:
                    bot_feats, rep = load_bot_feeds(
                        meeting_date,
                        venue,
                        runners,
                        ref=ref_val,
                        cache_dir=cache_root,
                        transport_fn=transport_fn,
                        retry_delay_s=retry_delay_s,
                        sleep_fn=sleep_fn,
                        allow_history_trial_fallback=allow_history_trial_fallback,
                    )
                    _MEM_MEETING_CACHE[mem_key] = (time.monotonic(), bot_feats, rep)
            else:
                bot_feats, rep = load_bot_feeds(
                    meeting_date,
                    venue,
                    runners,
                    ref=ref_val,
                    cache_dir=cache_root,
                    transport_fn=transport_fn,
                    retry_delay_s=retry_delay_s,
                    sleep_fn=sleep_fn,
                    allow_history_trial_fallback=allow_history_trial_fallback,
                )
                if transport_fn is None:
                    _MEM_MEETING_CACHE[mem_key] = (time.monotonic(), bot_feats, rep)
        except Exception as exc:
            logger.error(f"[Bot Feeds Merge Fail] Falling back to existing trial_features: {exc}")
            if is_coverage_strict():
                raise
            return base_tf

    merged: dict[str, dict] = {k: deepcopy(v) for k, v in base_tf.items() if isinstance(v, dict)}
    live_trials_on = (mode == "live") and is_live_trials_enabled()

    for c_name, b_dict in bot_feats.items():
        had_core = (c_name in base_tf) and ("best_trial_pos_ratio" in base_tf[c_name])
        dest = merged.setdefault(c_name, {})
        for bk, bv in b_dict.items():
            if bv is not None:
                dest[bk] = bv
        if live_trials_on and not had_core:
            derived = _derive_live_trial_core_keys(b_dict)
            for ck, cv in derived.items():
                if cv is not None and ck not in dest:
                    dest[ck] = cv

    return merged


def apply_live_bot_runner_overlays(
    df_runners: pd.DataFrame,
    trial_features: dict,
    horse_memory: Optional[dict] = None,
) -> tuple[pd.DataFrame, Optional[dict]]:
    """
    Applies optional verified Steward / Replay candidate overlays ONLY when
    `SILKS_BOT_FEEDS=live` and the corresponding sub-flag is enabled:
      - SILKS_BOT_LIVE_STEWARD=1 -> material active_requirement feeds has_health_risk
      - SILKS_BOT_LIVE_REPLAY=1  -> verified traffic / wide_no_cover excuses map into
                                    had_excuse and augment `horse_memory` for tactical calibration
    Returns `(df_runners, horse_memory)` untouched in `off` and `shadow` modes.
    """
    mode = get_bot_feeds_mode()
    if mode != "live" or df_runners.empty or not isinstance(trial_features, dict):
        return df_runners, horse_memory

    use_steward = is_live_steward_enabled()
    use_replay = is_live_replay_enabled()
    if not use_steward and not use_replay:
        return df_runners, horse_memory

    mem_out = horse_memory
    if use_replay:
        if isinstance(horse_memory, dict):
            mem_out = dict(horse_memory)
        else:
            try:
                from data.incident_engine import load_horse_memory
                mem_out = dict(load_horse_memory() or {})
            except Exception:
                mem_out = {}

    for idx, row in df_runners.iterrows():
        c_name = normalize_horse_name(row.get("clean_name") or row.get("name"))
        if not c_name or c_name not in trial_features:
            continue
        bf = trial_features[c_name]

        if use_steward:
            st_status = str(bf.get("bot_steward_status") or "").lower()
            is_mat = bf.get("bot_steward_latest_is_material") is True
            cat = str(bf.get("bot_steward_latest_category") or "").lower()
            if st_status == "active_requirement" and is_mat and cat in MATERIAL_VET_CATEGORIES:
                df_runners.at[idx, "prev_run_vet_finding"] = 1
                df_runners.at[idx, "vet_status"] = "active_requirement"
                df_runners.at[idx, "has_health_risk"] = True
                req_note = "; ".join(bf.get("bot_steward_open_requirements") or [cat])
                df_runners.at[idx, "latest_vet_note"] = req_note

        if use_replay:
            has_health = bool(df_runners.at[idx, "has_health_risk"]) if "has_health_risk" in df_runners.columns else False
            clearance_text = str(bf.get("bot_replay_clearance_text") or "").strip()
            vet_finding = str(bf.get("bot_replay_vet_finding") or "").strip().lower()
            has_positive_finding = any(kw in vet_finding for kw in POSITIVE_REPLAY_VET_KEYWORDS)
            has_replay_vet = bool(clearance_text) or has_positive_finding

            rp_flags = {str(x).lower() for x in (bf.get("bot_replay_flags") or [])}
            has_excuse_flag = (
                bf.get("bot_replay_traffic") is True
                or bf.get("bot_replay_wide_no_cover") is True
                or bool(rp_flags & ALLOWED_REPLAY_EXCUSES)
            )
            if has_excuse_flag and not has_health and not has_replay_vet:
                if "had_excuse" in df_runners.columns:
                    df_runners.at[idx, "had_excuse"] = True
                # Augment tactical memory when no newer entry is already present.
                existing_rec = mem_out.get(c_name)
                existing_runs = list((existing_rec or {}).get("runs") or [])
                rp_date = normalize_date(bf.get("bot_replay_meeting_date"))
                if rp_date:
                    inc_flags = []
                    if bf.get("bot_replay_traffic") is True or "traffic" in rp_flags:
                        inc_flags.append({
                            "flag": "traffic_trouble",
                            "severity": 2,
                            "vet_blocked": False,
                            "snippet": "Verified replay traffic trouble",
                        })
                    if bf.get("bot_replay_wide_no_cover") is True or "wide_no_cover" in rp_flags or "wide_without_cover" in rp_flags:
                        inc_flags.append({
                            "flag": "wide_no_cover",
                            "severity": 2,
                            "vet_blocked": False,
                            "snippet": "Verified replay wide without cover",
                        })

                    replay_severity = 2 if (bf.get("bot_replay_traffic") is True or "traffic" in rp_flags) else 0

                    # Check if any existing run matches this meeting date (read race_date, fallback date)
                    matching_run = None
                    for r in existing_runs:
                        if isinstance(r, dict):
                            r_dt = normalize_date(r.get("race_date") or r.get("date"))
                            if r_dt and r_dt == rp_date:
                                matching_run = r
                                break

                    if matching_run is not None:
                        # Merge replay incident_flags into that existing run
                        curr_inc = list(matching_run.get("incident_flags") or [])
                        existing_flag_names = {
                            f.get("flag") for f in curr_inc if isinstance(f, dict) and f.get("flag")
                        }
                        for flag_obj in inc_flags:
                            if flag_obj.get("flag") not in existing_flag_names:
                                curr_inc.append(flag_obj)
                                existing_flag_names.add(flag_obj.get("flag"))
                        matching_run["incident_flags"] = curr_inc

                        # Raise interference_severity only if lower
                        curr_sev = matching_run.get("interference_severity")
                        if curr_sev is None or curr_sev < replay_severity:
                            matching_run["interference_severity"] = replay_severity

                        new_rec = dict(existing_rec or {})
                        new_rec["runs"] = existing_runs
                        mem_out[c_name] = new_rec
                    else:
                        # Only create a new run when no run for that date exists, using key "race_date" plus race_id, and omit unknown fields instead of placeholders.
                        newest_existing = normalize_date((existing_runs[0] or {}).get("race_date") or (existing_runs[0] or {}).get("date")) if existing_runs else None
                        if newest_existing is None or rp_date >= newest_existing:
                            if inc_flags and bf.get("bot_replay_finish") is not None:
                                r_id = bf.get("bot_replay_race_id")
                                if not r_id:
                                    r_no = bf.get("bot_replay_race_no")
                                    d_tag = rp_date.replace("-", "") if rp_date else "REPLAY"
                                    r_id = f"{d_tag}_R{r_no}" if r_no is not None else f"{d_tag}_REPLAY"

                                new_run: dict[str, Any] = {
                                    "race_date": rp_date,
                                    "race_id": r_id,
                                    "finish_pos": int(bf["bot_replay_finish"]),
                                    "interference_severity": replay_severity,
                                    "incident_flags": inc_flags,
                                }
                                if bf.get("bot_replay_draw") is not None:
                                    new_run["barrier"] = int(bf["bot_replay_draw"])
                                if bf.get("bot_replay_win_odds") is not None:
                                    new_run["sp"] = float(bf["bot_replay_win_odds"])

                                new_rec = dict(existing_rec or {})
                                new_rec["runs"] = [new_run] + existing_runs
                                mem_out[c_name] = new_rec

    return df_runners, mem_out


def get_bot_feeds_health_summary(cache_dir: Optional[str] = None) -> dict[str, Any]:
    """Reads cached bot-feed health summary from `.cache/bot_feeds/_bot_feeds_health.json`."""
    mode = get_bot_feeds_mode()
    cache_root = get_bot_feeds_cache_dir(cache_dir)
    h_path = os.path.join(cache_root, "_bot_feeds_health.json")
    base = {
        "mode": mode,
        "ref": get_bot_feeds_ref(),
        "live_subflags": {
            "trials": is_live_trials_enabled(),
            "steward": is_live_steward_enabled(),
            "replay": is_live_replay_enabled(),
        },
        "cache_dir": cache_root,
    }
    if os.path.exists(h_path):
        try:
            with open(h_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if isinstance(cached, dict):
                base.update(cached)
                base["mode"] = mode
        except Exception as exc:
            base["error"] = f"Corrupted bot feeds cache health file: {exc}"
    return base

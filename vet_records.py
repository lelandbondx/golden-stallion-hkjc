"""
Official HKJC Per-Horse Veterinary Records Pipeline (Silks.AI).

Scrapes full veterinary histories from:
  https://racing.hkjc.com/en-us/local/information/ovehorse?horseid=HK_YYYY_XXXX
Stores all rows per horse in `data/vet_records.json` keyed by `horse_id` (never joined on name).
Cross-checks against `https://racing.hkjc.com/en-us/local/information/overecord`.
"""

import concurrent.futures
import json
import os
import re
from datetime import datetime, timezone
from io import BytesIO
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
VET_RECORDS_PATH = os.path.join(DATA_DIR, "vet_records.json")
DECLARED_VET_RECORDS_PATH = os.path.join(DATA_DIR, "declared_vet_records.json")
LATEST_STATS_PATH = os.path.join(DATA_DIR, "latest_horse_stats.csv")

OVEHORSE_URL_TEMPLATE = "https://racing.hkjc.com/en-us/local/information/ovehorse?horseid={horse_id}"
OVERECORD_URL = "https://racing.hkjc.com/en-us/local/information/overecord"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

MATERIAL_CATEGORIES = {
    "surgery",
    "injury",
    "lameness",
    "bleeding_nostrils",
    "tracheal_blood",
    "cardiac",
    "airway",
    "failed_vet_exam",
}

CATEGORY_ICONS = {
    "surgery": "🏥 Surgery",
    "injury": "🦴 Injury",
    "lameness": "🦵 Lameness",
    "bleeding_nostrils": "🩸 Nostril Bleed",
    "tracheal_blood": "🫁 Tracheal Blood",
    "cardiac": "❤️ Cardiac",
    "airway": "🌬️ Airway",
    "failed_vet_exam": "🔬 Failed Vet Exam",
    "performance": "📋 Performance",
    "administrative": "ℹ️ Administrative",
    "other": "📋 Other",
}

CATEGORY_LABELS = {
    "surgery": "Surgery",
    "injury": "Injury",
    "lameness": "Lameness",
    "bleeding_nostrils": "Nostril Bleed",
    "tracheal_blood": "Tracheal Blood",
    "cardiac": "Cardiac",
    "airway": "Airway",
    "failed_vet_exam": "Failed Vet Exam",
    "performance": "Performance",
    "administrative": "Administrative",
    "other": "Other",
}

RADAR_TAG_MAP = {
    "surgery": "SURGERY",
    "injury": "INJURY",
    "lameness": "LAMENESS",
    "bleeding_nostrils": "NOSTRIL BLEED",
    "tracheal_blood": "TRACHEAL BLOOD",
    "cardiac": "CARDIAC",
    "airway": "AIRWAY",
    "failed_vet_exam": "FAILED VET EXAM",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_hkjc_date(date_str: Optional[str]) -> Optional[datetime]:
    """
    Explicitly parses HKJC DD/MM/YYYY (or DD/MM/YY) dates with dayfirst=True.
    Returns None for '-', '--', empty, or invalid strings.
    """
    if date_str is None or (isinstance(date_str, float) and pd.isna(date_str)):
        return None
    s = str(date_str).strip()
    if not s or s.lower() in ("-", "--", "nan", "none", "null", "n/a"):
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    dt = pd.to_datetime(s, format="%d/%m/%Y", dayfirst=True, errors="coerce")
    if pd.notnull(dt):
        return dt.to_pydatetime()
    dt2 = pd.to_datetime(s, dayfirst=True, errors="coerce")
    if pd.notnull(dt2):
        return dt2.to_pydatetime()
    return None


def _classify_clause(text: str) -> Optional[str]:
    """Classifies a single clause according to HKJC veterinary taxonomy."""
    t = text.lower().strip()
    if not t:
        return None

    # 1. Failed vet exam prefix/clause takes priority when explicitly stated
    if "failed vet exam" in t or "failed veterinary exam" in t:
        return "failed_vet_exam"

    # 2. Surgery (including tieback, hobday, tie-forward, arthroscopic, bone fragment removal)
    if any(
        kw in t
        for kw in (
            "surgery",
            "arthroscop",
            "tieback",
            "tie-back",
            "tie-forward",
            "tie forward",
            "hobday",
            "bone fragment removal",
            "prosthetic laryngoplasty",
            "ventriculocordectomy",
            "wind op",
        )
    ):
        return "surgery"

    # 3. Nostril bleeding vs Tracheal blood (strictly separate)
    if "bled from both nostrils" in t or "bled both nostrils" in t or "epistaxis" in t:
        return "bleeding_nostrils"

    if (
        "blood in trachea" in t
        or "blood on scope" in t
        or "tracheal blood" in t
        or "blood at trachea" in t
    ):
        return "tracheal_blood"

    # 4. Cardiac
    if (
        "irregular heart rhythm" in t
        or "heart irregularity" in t
        or "irregular heart" in t
        or "atrial fibrillation" in t
        or "cardiac" in t
    ):
        return "cardiac"

    # 5. Airway
    if any(
        kw in t
        for kw in (
            "roarer",
            "soft palate",
            "dorsal displacement",
            "ddsp",
            "epiglottic",
            "abnormal respiratory noise",
            "airway abnormality",
            "abnormal breathing",
        )
    ):
        return "airway"

    # 6. Structural Injury vs Lameness
    has_structural_injury = any(
        kw in t
        for kw in (
            "injury",
            "tendon",
            "ligament",
            "fracture",
            "bone",
            "laceration",
            "abrasion",
            "suspensory",
            "wound",
        )
    )
    if has_structural_injury:
        return "injury"

    if re.search(r"\blame\b", t) or "lameness" in t:
        return "lameness"

    if "fetlock" in t or "knee" in t:
        return "injury"

    # 7. Administrative
    if any(
        kw in t
        for kw in (
            "castration",
            "eight years of age",
            "years of age",
            "unraced for 12 months",
            "unraced for",
            "fractious",
            "racing manners",
            "barrier manners",
            "starting gate",
        )
    ):
        return "administrative"

    # 8. Performance
    if any(
        kw in t
        for kw in (
            "disappointing",
            "unacceptable",
            "poor trial",
            "poor performance",
            "action during racing",
            "tailed out",
        )
    ):
        return "performance"

    return None


def _extract_vet_tuple(details: str) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    """
    Returns (category, body_part, side, procedure) from full HKJC details string.
    If 'Update:' is present, takes the most specific category from the Update clause.
    """
    raw = str(details or "").strip()
    category = None

    if "update:" in raw.lower():
        parts = re.split(r"update\s*:", raw, flags=re.IGNORECASE)
        for upd_clause in reversed(parts[1:]):
            upd_cat = _classify_clause(upd_clause)
            if upd_cat and upd_cat != "other":
                category = upd_cat
                break

    if not category:
        category = _classify_clause(raw) or "other"

    t = raw.lower()

    # Side extraction
    side = None
    has_left_fore = bool(re.search(r"left\s+(?:fore|front)|\blf\b", t))
    has_right_fore = bool(re.search(r"right\s+(?:fore|front)|\brf\b", t))
    has_left_hind = bool(re.search(r"left\s+hind|\blh\b", t))
    has_right_hind = bool(re.search(r"right\s+hind|\brh\b", t))
    has_left = bool(re.search(r"\bleft\b|\blf\b|\blh\b", t))
    has_right = bool(re.search(r"\bright\b|\brf\b|\brh\b", t))
    if "both" in t or "bilateral" in t or (has_left and has_right):
        side = "both"
    elif has_left_fore:
        side = "left fore"
    elif has_right_fore:
        side = "right fore"
    elif has_left_hind:
        side = "left hind"
    elif has_right_hind:
        side = "right hind"
    elif has_left:
        side = "left"
    elif has_right:
        side = "right"

    # Body part extraction
    body_part = None
    # If 'Update:' clause exists, check update clause first for most specific body part
    search_clauses = [raw.lower()]
    if "update:" in raw.lower():
        upd_parts = [p.strip().lower() for p in re.split(r"update\s*:", raw, flags=re.IGNORECASE)[1:] if p.strip()]
        search_clauses = list(reversed(upd_parts)) + search_clauses
    body_part_patterns = [
        (r"fore\s+fetlock|front\s+fetlock|hind\s+fetlock|\bfetlock\b", "fetlock"),
        (r"\bhumerus\b|\bhumeral\b", "humerus"),
        (r"\bknees?\b|\bcarpal\b|\bcarpus\b", "knee"),
        (r"\btendons?\b", "tendon"),
        (r"\bsuspensory\b", "suspensory ligament"),
        (r"\bligaments?\b", "ligament"),
        (r"\bpelvis\b|\bpelvic\b|\bilium\b", "pelvis"),
        (r"\bstifle\b", "stifle"),
        (r"\bhock\b|\btarsal\b", "hock"),
        (r"\bhoof\b|\bfoot\b|\bsole\b", "foot"),
        (r"soft\s+palate", "soft palate"),
        (r"\bepiglottis\b|\bepiglottic\b", "epiglottis"),
        (r"\bthroat\b|\blarynx\b|\blaryngeal\b", "throat"),
        (r"\btrachea\b|\btracheal\b|\bscope\b|\bscoping\b", "trachea"),
        (r"\bnostrils?\b", "nostrils"),
        (r"\bheart\b|\bcardiac\b", "heart"),
        (r"\bairway\b|\broarer\b|\brespiratory\b", "airway"),
        (r"fore\s*leg|front\s*leg|\bfore\b|\bfront\b", "foreleg"),
        (r"hind\s*leg|\bhind\b", "hindleg"),
    ]
    for clause_txt in search_clauses:
        for pat, label in body_part_patterns:
            if re.search(pat, clause_txt):
                body_part = label
                break
        if body_part:
            break

    # Procedure extraction
    procedure = None
    if "tieback and hobday" in t or ("tieback" in t and "hobday" in t):
        procedure = "tieback and hobday"
    elif "tie-forward" in t or "tie forward" in t:
        procedure = "tie-forward"
    elif "tieback" in t or "tie-back" in t:
        procedure = "tieback"
    elif "hobday" in t:
        procedure = "hobday"
    elif "arthroscop" in t and "bone fragment removal" in t:
        procedure = "arthroscopic surgery (bone fragment removal)"
    elif "arthroscop" in t:
        procedure = "arthroscopic surgery"
    elif "bone fragment removal" in t:
        procedure = "bone fragment removal"
    elif "throat surgery" in t:
        procedure = "throat surgery"
    elif "dorsal displacement of the soft palate" in t or "ddsp" in t:
        procedure = "DDSP (soft palate displacement)"
    elif "castration" in t:
        procedure = "castration"
    elif "post-race scoping" in t or "blood on scope" in t:
        procedure = "scoping"

    return category, body_part, side, procedure


def extract_vet_attributes_dict(details: str, passed_raw: Optional[str] = None) -> Dict:
    """Returns a full structured attribute dict for details + passed_on."""
    category, body_part, side, procedure = _extract_vet_tuple(details)
    passed_dt = parse_hkjc_date(passed_raw)
    passed_ddmmyyyy = passed_dt.strftime("%d/%m/%Y") if passed_dt else None
    is_pure_admin = any(
        kw in str(details or "").lower()
        for kw in ("castration", "years of age", "unraced for 12 months", "unraced for")
    )
    if category == "administrative" and (passed_ddmmyyyy is None or is_pure_admin):
        status = "no_requirement"
    elif passed_ddmmyyyy is not None:
        status = "cleared"
    else:
        status = "active_requirement"
    return {
        "category": category,
        "body_part": body_part,
        "side": side,
        "procedure": procedure,
        "passed_on": passed_ddmmyyyy,
        "status": status,
        "is_material": category in MATERIAL_CATEGORIES,
    }


def extract_vet_attributes(details: str, passed_raw: Optional[str] = None) -> Dict:
    """Returns a full structured attribute dict for details + passed_on."""
    return extract_vet_attributes_dict(details, passed_raw)


def build_structured_entry(
    date_raw: str,
    details_raw: str,
    passed_raw: Optional[str],
    source_url: str,
    scraped_at: str,
    row_order: int = 0,
) -> Optional[ Dict ]:
    """Builds a single validated, structured veterinary record entry."""
    details = " ".join(str(details_raw or "").split()).strip()
    if not details or details.lower() in ("nan", "none", "") or "no record" in details.lower():
        return None

    dt = parse_hkjc_date(date_raw)
    if dt is None:
        return None

    date_ddmmyyyy = dt.strftime("%d/%m/%Y")
    date_iso = dt.strftime("%Y-%m-%d")

    passed_dt = parse_hkjc_date(passed_raw)
    passed_ddmmyyyy = passed_dt.strftime("%d/%m/%Y") if passed_dt else None
    passed_iso = passed_dt.strftime("%Y-%m-%d") if passed_dt else None

    category, body_part, side, procedure = _extract_vet_tuple(details)

    # Status determination:
    # - 'no_requirement' for administrative entries such as castration or age (or administrative with '-')
    # - 'cleared' if passed_on is a date
    # - 'active_requirement' if passed_on is '-' (None) and category is not administrative
    is_pure_admin = any(
        kw in details.lower()
        for kw in ("castration", "years of age", "unraced for 12 months", "unraced for")
    )
    if category == "administrative" and (passed_ddmmyyyy is None or is_pure_admin):
        status = "no_requirement"
    elif passed_ddmmyyyy is not None:
        status = "cleared"
    else:
        status = "active_requirement"

    is_material = category in MATERIAL_CATEGORIES

    return {
        "date": date_ddmmyyyy,
        "date_iso": date_iso,
        "details": details,
        "passed_on": passed_ddmmyyyy,
        "passed_on_iso": passed_iso,
        "category": category,
        "body_part": body_part,
        "side": side,
        "procedure": procedure,
        "status": status,
        "is_material": is_material,
        "source_url": source_url,
        "scraped_at": scraped_at,
        "_sort_key": (date_iso, int(row_order)),
    }


def parse_ovehorse_rows(
    raw_rows: List[Dict],
    source_url: str,
    scraped_at: Optional[str] = None,
) -> List[Dict]:
    """
    Parses a list of raw table dicts ({'Date': ..., 'Details': ..., 'Passed Date': ...})
    from HKJC ovehorse, sorts descending (newest date & latest row first), and strips internal sort keys.
    """
    scraped_at = scraped_at or utc_now_iso()
    entries = []
    for idx, r in enumerate(raw_rows):
        date_val = r.get("Date") if "Date" in r else r.get("date")
        details_val = r.get("Details") if "Details" in r else r.get("details")
        passed_val = (
            r.get("Passed Date")
            if "Passed Date" in r
            else (r.get("Passed On") if "Passed On" in r else r.get("passed_on"))
        )
        entry = build_structured_entry(
            date_raw=date_val,
            details_raw=details_val,
            passed_raw=passed_val,
            source_url=source_url,
            scraped_at=scraped_at,
            row_order=idx,
        )
        if entry is not None:
            entries.append(entry)

    # Sort descending: newest date first; if same date, later row on HKJC table is more recent
    entries.sort(key=lambda e: e["_sort_key"], reverse=True)
    for e in entries:
        e.pop("_sort_key", None)
    return entries


def compute_horse_vet_Rollup(
    entries: List[Dict],
    reference_date: Optional[datetime] = None,
) -> Dict:
    """
    Computes flags, material summaries, and 12-month bleed counts from descending-sorted entries.
    - prev_run_vet_finding = 1 ONLY when there is an active_requirement entry,
      or a material entry within 180 days that has not been passed.
    """
    ref_dt = reference_date or datetime.now()
    if isinstance(ref_dt, str):
        ref_dt = parse_hkjc_date(ref_dt) or datetime.now()
    ref_date_only = datetime(ref_dt.year, ref_dt.month, ref_dt.day)

    has_active_req = False
    has_unpassed_material_180d = False
    has_surgery_history = 0
    last_material_date = None
    days_since_material_clearance = None
    tracheal_bleed_count_12m = 0
    nostril_bleed_count_12m = 0

    latest_entry = entries[0] if entries else None
    latest_material_entry = None

    # Find the most recent official clearance date (passed_on) across all entries.
    # On HKJC ovehorse, when an earlier diagnosis (e.g. 15/11/2025 Roarer, Passed: -) is followed by
    # corrective surgery (03/07/2026 Throat surgery, Passed: 21/09/2026), HKJC records the Passed Date
    # on the newer row and leaves '-' on the older row.
    latest_clearance_dt = None
    for e in entries:
        p_dt = parse_hkjc_date(e.get("passed_on_iso") or e.get("passed_on"))
        if p_dt is not None:
            p_day = datetime(p_dt.year, p_dt.month, p_dt.day)
            if latest_clearance_dt is None or p_day > latest_clearance_dt:
                latest_clearance_dt = p_day

    for e in entries:
        cat = e.get("category")
        st = e.get("status")
        is_mat = bool(e.get("is_material"))
        e_dt = parse_hkjc_date(e.get("date_iso") or e.get("date"))
        p_dt = parse_hkjc_date(e.get("passed_on_iso") or e.get("passed_on"))
        det_low = str(e.get("details", "")).lower()
        e_day = datetime(e_dt.year, e_dt.month, e_dt.day) if e_dt is not None else None

        is_superseded_by_later_clearance = (
            p_dt is None
            and e_day is not None
            and latest_clearance_dt is not None
            and e_day <= latest_clearance_dt
        )

        if st == "active_requirement" and not is_superseded_by_later_clearance:
            has_active_req = True

        if is_mat and p_dt is None and e_day is not None and not is_superseded_by_later_clearance:
            days_old = (ref_date_only - e_day).days
            if days_old <= 180:
                has_unpassed_material_180d = True

        if cat == "surgery" or "surgery" in det_low or "arthroscop" in det_low or "tieback" in det_low or "hobday" in det_low:
            has_surgery_history = 1

        if is_mat and latest_material_entry is None:
            latest_material_entry = e
            last_material_date = e.get("date_iso") or e.get("date")
            if p_dt is not None:
                days_since_material_clearance = max(
                    0, (ref_date_only - datetime(p_dt.year, p_dt.month, p_dt.day)).days
                )

        if e_dt is not None:
            days_ago = (ref_date_only - datetime(e_dt.year, e_dt.month, e_dt.day)).days
            if 0 <= days_ago <= 365:
                if cat == "tracheal_blood" or (
                    cat == "failed_vet_exam" and ("blood on scope" in det_low or "trachea" in det_low)
                ):
                    tracheal_bleed_count_12m += 1
                elif cat == "bleeding_nostrils" or (
                    cat == "failed_vet_exam" and "nostril" in det_low
                ):
                    nostril_bleed_count_12m += 1

    prev_run_vet_finding = 1 if (has_active_req or has_unpassed_material_180d) else 0
    bleed_count_12m = tracheal_bleed_count_12m + nostril_bleed_count_12m

    # Build official latest_vet_note for latest_horse_stats.csv compatibility
    # Prefer latest material entry (or active requirement entry); if only administrative, format plainly
    display_target = latest_material_entry or (
        latest_entry if (latest_entry and latest_entry.get("status") == "active_requirement") else latest_entry
    )
    if display_target is None:
        latest_vet_note = "No Findings"
    else:
        d_str = display_target.get("date", "")
        det_str = display_target.get("details", "")
        p_str = display_target.get("passed_on")
        if p_str:
            latest_vet_note = f"{d_str}: {det_str} (Passed: {p_str})"
        else:
            latest_vet_note = f"{d_str}: {det_str} (Passed: -)"

    return {
        "latest_entry": latest_entry,
        "latest_material_entry": latest_material_entry,
        "latest_vet_note": latest_vet_note,
        "vet_display": format_vet_cell(entries),
        "prev_run_vet_finding": prev_run_vet_finding,
        "has_surgery_history": has_surgery_history,
        "last_material_date": last_material_date,
        "days_since_material_clearance": days_since_material_clearance,
        "bleed_count_12m": bleed_count_12m,
        "tracheal_bleed_count_12m": tracheal_bleed_count_12m,
        "nostril_bleed_count_12m": nostril_bleed_count_12m,
    }


def format_vet_cell(entries: List[Dict]) -> str:
    """
    Formats the Vet column display string for a runner:
    - Shows the latest material entry (or active requirement entry):
      category icon, date, body part/procedure, and Cleared/Active badge with passed date.
    - Never shows castration, age, or unraced entries as ⚠️.
    - Uses only official text/dates.
    """
    if not entries:
        return "✅ Clear Record"

    # Find latest material entry or active_requirement entry
    target = next(
        (e for e in entries if e.get("is_material") or e.get("status") == "active_requirement"),
        None,
    )
    if target is None:
        # Only administrative / cleared non-material entries exist -> do not flag with ⚠️
        return "✅ Clear Record"

    cat = target.get("category", "other")
    icon_label = CATEGORY_ICONS.get(cat, "📋 Vet Record")
    date_str = target.get("date", "")
    side = target.get("side")
    body_part = target.get("body_part")
    procedure = target.get("procedure")

    qualifiers = []
    if side and body_part:
        qualifiers.append(f"{side} {body_part}")
    elif body_part:
        qualifiers.append(body_part)
    if procedure and procedure not in qualifiers:
        qualifiers.append(procedure)

    qual_str = f" — {', '.join(qualifiers)}" if qualifiers else f" — {target.get('details', '')}"

    status = target.get("status")
    passed_on = target.get("passed_on")
    if status == "cleared" and passed_on:
        badge = f"✅ Cleared {passed_on}"
    elif status == "active_requirement":
        badge = "⚠️ Active (Passed: -)"
    else:
        badge = "ℹ️ No Requirement"

    return f"{icon_label} ({date_str}{qual_str}) [{badge}]"


def format_vet_column_display(horse_record: Dict) -> str:
    """Formats the Vet column display string from a horse_record dict."""
    if not horse_record or not isinstance(horse_record, dict):
        return "✅ Clear Record"
    return format_vet_cell(horse_record.get("entries") or [])


def build_horse_vet_record(
    horse_id: str,
    horse_code: str,
    horse_name: str,
    raw_rows: List[Dict],
    source_url: str = "",
    as_of=None,
    scraped_at: Optional[str] = None,
) -> Dict:
    """Builds a full per-horse veterinary record dict from raw table rows."""
    scraped_at = scraped_at or utc_now_iso()
    source_url = source_url or OVEHORSE_URL_TEMPLATE.format(horse_id=horse_id)
    entries = parse_ovehorse_rows(raw_rows, source_url=source_url, scraped_at=scraped_at)
    rollup = compute_horse_vet_Rollup(entries, reference_date=as_of)
    # Match last_material_date to DD/MM/YYYY format on latest_material_entry
    if rollup.get("latest_material_entry"):
        rollup["last_material_date"] = rollup["latest_material_entry"].get("date")
    return {
        "horse_id": horse_id,
        "horse_code": horse_code,
        "horse_name": horse_name,
        "source_url": source_url,
        "scraped_at": scraped_at,
        "entries": entries,
        **rollup,
    }


def format_radar_vet_item(horse_record: Dict, r_item_link: Optional[str] = None) -> Optional[Dict]:
    """
    Builds a Tactical Radar item for a horse ONLY from official vet_records.json entries.
    Never uses stewards' comments and never fabricates recovery strings.
    """
    if not horse_record or not isinstance(horse_record, dict):
        return None
    entries = horse_record.get("entries") or []
    target = next(
        (e for e in entries if e.get("is_material") or e.get("status") == "active_requirement"),
        None,
    )
    if target is None:
        return None

    cat = target.get("category", "other")
    if cat == "administrative":
        return None

    tag = RADAR_TAG_MAP.get(cat, "VET RECORD")
    date_str = target.get("date", "")
    details = target.get("details", "")
    passed_on = target.get("passed_on")
    status = target.get("status")

    if status == "cleared" and passed_on:
        status_label = f"Cleared {passed_on}"
        color = "#38bdf8"
        bg = "rgba(56, 189, 248, 0.10)"
        border = "rgba(56, 189, 248, 0.4)"
    else:
        status_label = "Active Requirement (Passed: -)"
        color = "#f97316"
        bg = "rgba(249, 115, 22, 0.10)"
        border = "rgba(249, 115, 22, 0.4)"

    link_lbl = r_item_link or horse_record.get("horse_name") or horse_record.get("horse_code") or ""
    type_str = f"🏥 {tag} — {status_label}"
    text_str = f"<b>{link_lbl}</b>: {date_str} — {details} (Passed: {passed_on or '-'})"

    return {
        "type": type_str,
        "tag": f"{tag} ({status_label})",
        "color": color,
        "bg": bg,
        "border": border,
        "text": text_str,
        "date": date_str,
        "details": details,
        "passed_on": passed_on or "-",
        "status": status,
        "source_url": target.get("source_url") or horse_record.get("source_url", ""),
    }


def resolve_horse_id(horse_code: str, existing_db: Optional[Dict] = None) -> Optional[str]:
    """Resolves a 4-char HKJC brand code (e.g. 'K308') to full horse_id ('HK_2024_K308')."""
    code = str(horse_code or "").strip().upper()
    if not code:
        return None
    if code.startswith("HK_"):
        return code

    if existing_db:
        for hid, rec in existing_db.items():
            if isinstance(rec, dict) and str(rec.get("horse_code", "")).strip().upper() == code:
                return hid

    url = f"https://racing.hkjc.com/racing/information/English/Horse/Horse.aspx?HorseNo={code}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=8, verify=False)
        m = re.search(r"horseid=(HK_\d+_[A-Z0-9]+)", res.text, re.IGNORECASE)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def scrape_horse_vet_record(
    horse_id: Optional[str] = None,
    horse_code: Optional[str] = None,
    horse_name: Optional[str] = None,
    existing_db: Optional[Dict] = None,
    reference_date: Optional[datetime] = None,
) -> Optional[Dict]:
    """
    Scrapes the complete per-horse veterinary table from:
      https://racing.hkjc.com/en-us/local/information/ovehorse?horseid=HK_YYYY_XXXX
    """
    code = str(horse_code or "").strip().upper()
    hid = str(horse_id or "").strip()
    if not hid and code:
        hid = resolve_horse_id(code, existing_db=existing_db) or ""
    if not hid:
        return None
    if not code and "_" in hid:
        code = hid.split("_")[-1].upper()

    source_url = OVEHORSE_URL_TEMPLATE.format(horse_id=hid)
    scraped_at = utc_now_iso()

    try:
        res = requests.get(source_url, headers=HEADERS, timeout=10, verify=False)
        if res.status_code != 200:
            return None

        # Extract official horse name from page if not supplied
        parsed_name = str(horse_name or "").strip().upper()
        if not parsed_name:
            m_title = re.search(r"([A-Z0-9\s'\-]+)\s*\(" + re.escape(code) + r"\)", res.text)
            if m_title:
                parsed_name = m_title.group(1).strip().upper()

        raw_rows = []
        try:
            dfs = pd.read_html(BytesIO(res.content))
        except Exception:
            dfs = []

        for df in dfs:
            if df.shape[1] == 3:
                cols = [str(c).strip() for c in df.columns]
                if "Date" in cols and "Details" in cols:
                    raw_rows = df.to_dict("records")
                    break
                if len(df) > 0:
                    row0 = [str(v).strip() for v in df.iloc[0].values]
                    if "Date" in row0 or "Details" in row0:
                        df = df.copy()
                        df.columns = row0
                        df = df.iloc[1:]
                        raw_rows = df.to_dict("records")
                        break

        entries = parse_ovehorse_rows(raw_rows, source_url=source_url, scraped_at=scraped_at)
        rollup = compute_horse_vet_Rollup(entries, reference_date=reference_date)

        return {
            "horse_id": hid,
            "horse_code": code,
            "horse_name": parsed_name,
            "source_url": source_url,
            "scraped_at": scraped_at,
            "entries": entries,
            **rollup,
        }
    except Exception as e:
        print(f"[Vet Scraper] Error scraping {hid} ({code}): {e}")
        return None


def discover_meeting_and_stewards_horses() -> Tuple[Dict[str, Dict], set]:
    """
    Discovers:
    1. Every declared runner AND standby for the next/active meeting (from live meeting data + RaceCard.aspx).
    2. Every horse in the most recent stewards' report (RaceReportFull.aspx).
    Returns (horses_by_code, declared_codes_set).
    Each value in horses_by_code is {'horse_code': code, 'horse_id': hid_or_None, 'horse_name': name, 'is_declared': bool}.
    """
    from scraper import get_live_meeting_data

    horses_by_code: Dict[str, Dict] = {}
    declared_codes = set()

    live_data = get_live_meeting_data()
    meeting_date = None
    venue_code = "HV"
    num_races = 9

    if live_data and live_data.get("meetings"):
        m0 = live_data["meetings"][0]
        meeting_date = m0.get("date")
        venue_code = "HV" if "VALLEY" in str(m0.get("venue", "")).upper() else "ST"
        races = m0.get("races") or []
        num_races = max(len(races), 9)
        for race in races:
            for runner in race.get("runners", []):
                c = str(runner.get("code") or "").strip().upper()
                n = str(runner.get("name") or "").strip().upper()
                if c:
                    declared_codes.add(c)
                    horses_by_code[c] = {
                        "horse_code": c,
                        "horse_id": None,
                        "horse_name": n,
                        "is_declared": True,
                    }

    # Scrape RaceCard.aspx for all races to get exact horse_id for all declared + standby starters
    racedate_param = meeting_date.replace("-", "/") if meeting_date else None
    for r_no in range(1, num_races + 2):
        try:
            if racedate_param:
                rc_url = f"https://racing.hkjc.com/racing/information/English/Racing/RaceCard.aspx?RaceDate={racedate_param}&Racecourse={venue_code}&RaceNo={r_no}"
            else:
                rc_url = f"https://racing.hkjc.com/racing/information/English/Racing/RaceCard.aspx?RaceNo={r_no}"
            resp = requests.get(rc_url, headers=HEADERS, timeout=8, verify=False)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.content, "html.parser")
            for a in soup.find_all("a", href=True):
                m_hid = re.search(r"horseid=(HK_\d+_([A-Z0-9]+))", a["href"], re.IGNORECASE)
                if m_hid:
                    full_hid = m_hid.group(1)
                    code = m_hid.group(2).upper()
                    name_txt = a.get_text(strip=True).upper()
                    entry = horses_by_code.get(code, {})
                    horses_by_code[code] = {
                        "horse_code": code,
                        "horse_id": full_hid,
                        "horse_name": name_txt or entry.get("horse_name", ""),
                        "is_declared": code in declared_codes,
                        "is_standby": code not in declared_codes,
                    }
        except Exception:
            continue

    # Scrape the most recent Stewards' Reports (default RaceReportFull.aspx + recent scraped_incidents dates)
    steward_urls = ["https://racing.hkjc.com/racing/information/English/Reports/RaceReportFull.aspx"]
    for recent_date in ("2026/11/08", "2026/11/04"):
        steward_urls.append(
            f"https://racing.hkjc.com/racing/information/English/Reports/RaceReportFull.aspx?RaceDate={recent_date}"
        )

    for st_url in steward_urls:
        try:
            resp = requests.get(st_url, headers=HEADERS, timeout=10, verify=False)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.content, "html.parser")
            for a in soup.find_all("a", href=True):
                m_hid = re.search(r"horseid=(HK_\d+_([A-Z0-9]+))", a["href"], re.IGNORECASE)
                if m_hid:
                    full_hid = m_hid.group(1)
                    code = m_hid.group(2).upper()
                    raw_txt = a.get_text(strip=True).upper()
                    clean_nm = re.sub(r"\s*\([A-Z0-9]+\)\s*$", "", raw_txt).strip()
                    if code not in horses_by_code:
                        horses_by_code[code] = {
                            "horse_code": code,
                            "horse_id": full_hid,
                            "horse_name": clean_nm,
                            "is_declared": False,
                            "is_standby": False,
                        }
                    elif not horses_by_code[code].get("horse_id"):
                        horses_by_code[code]["horse_id"] = full_hid
        except Exception:
            continue

    return horses_by_code, declared_codes


def scrape_overecord_crosscheck() -> List[Dict]:
    """
    Scrapes `https://racing.hkjc.com/en-us/local/information/overecord` (Declared Starters)
    handling multi-row continuation lines per horse and sorting descending per horse.
    Saves to `data/declared_vet_records.json` and returns the parsed rows.
    """
    scraped_at = utc_now_iso()
    try:
        res = requests.get(OVERECORD_URL, headers=HEADERS, timeout=10, verify=False)
        if res.status_code != 200:
            return []
        dfs = pd.read_html(BytesIO(res.content))
        if not dfs:
            return []
        df = dfs[0].copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [str(c[-1]).strip() for c in df.columns]
        else:
            df.columns = [str(c).strip() for c in df.columns]

        current_race = None
        current_name = None
        current_code = None
        raw_by_code: Dict[str, List[Dict]] = {}

        for idx, row in df.iterrows():
            first_val = str(row.iloc[0]).strip() if len(row) > 0 else ""
            if first_val.upper().startswith("RACE "):
                current_race = first_val
                current_name = None
                current_code = None
                continue

            h_name = str(row.get("Horse Name", "")).strip().upper()
            b_no = str(row.get("Brand No.", "")).strip().upper()
            date_str = str(row.get("Date", "")).strip()
            details_raw = str(row.get("Details", "")).strip()
            passed_str = str(row.get("Passed On", "")).strip()

            if h_name and h_name not in ("NAN", "NONE", "HORSE NAME") and not h_name.startswith("RACE "):
                current_name = h_name
            if b_no and b_no not in ("NAN", "NONE", "BRAND NO.") and not b_no.startswith("RACE "):
                current_code = b_no

            if not current_code or not date_str or date_str.upper() in ("NAN", "NONE", "DATE"):
                continue

            raw_by_code.setdefault(current_code, []).append(
                {
                    "race": current_race,
                    "horse_name": current_name or "",
                    "horse_code": current_code,
                    "Date": date_str,
                    "Details": details_raw,
                    "Passed On": passed_str,
                    "_order": idx,
                }
            )

        records_out = []
        for code, rows in raw_by_code.items():
            structured = parse_ovehorse_rows(rows, source_url=OVERECORD_URL, scraped_at=scraped_at)
            h_name = rows[0].get("horse_name", "")
            race_lbl = rows[0].get("race", "")
            for s in structured:
                records_out.append(
                    {
                        "race": race_lbl,
                        "horse_name": h_name,
                        "horse_code": code,
                        **s,
                    }
                )

        os.makedirs(DATA_DIR, exist_ok=True)
        with open(DECLARED_VET_RECORDS_PATH, "w", encoding="utf-8") as f:
            json.dump(records_out, f, indent=2, ensure_ascii=False)
        return records_out
    except Exception as e:
        print(f"[Vet Crosscheck] Error scraping overecord: {e}")
        return []


def load_vet_records() -> Dict[str, Dict]:
    """Loads `data/vet_records.json` keyed by `horse_id`."""
    if not os.path.exists(VET_RECORDS_PATH):
        return {}
    try:
        with open(VET_RECORDS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def build_code_index(vet_db: Dict[str, Dict]) -> Dict[str, Dict]:
    """Builds a lookup index keyed by uppercase `horse_code` (brand number) from `vet_db`."""
    idx = {}
    for hid, rec in (vet_db or {}).items():
        if isinstance(rec, dict):
            c = str(rec.get("horse_code") or "").strip().upper()
            if c:
                idx[c] = rec
    return idx


def update_latest_horse_stats_csv(store_or_db: Dict, stats_path: str = LATEST_STATS_PATH) -> int:
    """Wrapper accepting either {'horses': {...}} or top-level {horse_id: {...}}."""
    vet_db = store_or_db.get("horses") if isinstance(store_or_db, dict) and "horses" in store_or_db else store_or_db
    return sync_vet_to_latest_stats(vet_db, stats_path=stats_path)


def sync_vet_to_latest_stats(vet_db: Dict[str, Dict], stats_path: str = LATEST_STATS_PATH) -> int:
    """
    Updates `data/latest_horse_stats.csv` using `horse_code` / `horse_id` (NEVER joining on name).
    Populates:
      - horse_id
      - latest_vet_note
      - prev_run_vet_finding
      - has_surgery_history
      - last_material_date
      - days_since_material_clearance
      - bleed_count_12m
      - tracheal_bleed_count_12m
      - nostril_bleed_count_12m
    """
    if not os.path.exists(stats_path):
        return 0
    df = pd.read_csv(stats_path)
    if "horse_code" not in df.columns:
        return 0

    code_idx = build_code_index(vet_db)
    for col, default in [
        ("horse_id", ""),
        ("latest_vet_note", "No Findings"),
        ("prev_run_vet_finding", 0),
        ("has_surgery_history", 0),
        ("last_material_date", None),
        ("days_since_material_clearance", None),
        ("bleed_count_12m", 0),
        ("tracheal_bleed_count_12m", 0),
        ("nostril_bleed_count_12m", 0),
    ]:
        if col not in df.columns:
            df[col] = default

    updated = 0
    for i, row in df.iterrows():
        code = str(row.get("horse_code") or "").strip().upper()
        if not code or code not in code_idx:
            continue
        rec = code_idx[code]
        df.at[i, "horse_id"] = rec.get("horse_id", "")
        df.at[i, "latest_vet_note"] = rec.get("latest_vet_note", "No Findings")
        df.at[i, "prev_run_vet_finding"] = int(rec.get("prev_run_vet_finding", 0))
        df.at[i, "has_surgery_history"] = int(rec.get("has_surgery_history", 0))
        df.at[i, "last_material_date"] = rec.get("last_material_date")
        df.at[i, "days_since_material_clearance"] = rec.get("days_since_material_clearance")
        df.at[i, "bleed_count_12m"] = int(rec.get("bleed_count_12m", 0))
        df.at[i, "tracheal_bleed_count_12m"] = int(rec.get("tracheal_bleed_count_12m", 0))
        df.at[i, "nostril_bleed_count_12m"] = int(rec.get("nostril_bleed_count_12m", 0))
        updated += 1

    df.to_csv(stats_path, index=False)
    return updated


def refresh_all_vet_records(extra_codes: Optional[List[str]] = None) -> Dict:
    """
    Master veterinary records synchronization:
    1. Discovers all declared + standby starters for the active meeting + all horses in the latest stewards' report.
    2. Scrapes `ovehorse?horseid=HK_YYYY_XXXX` in parallel for every target horse.
    3. Saves full per-horse histories to `data/vet_records.json` keyed by `horse_id`.
    4. Cross-checks against `overecord` (declared starters) and logs any disagreements.
    5. Updates `data/latest_horse_stats.csv` keyed strictly by `horse_code`.
    6. Records coverage & cross-check metrics in `data/pipeline_health.json` (`veterinary_records`).
    """
    from monitoring.health import record as record_health

    existing_db = load_vet_records()
    targets_by_code, declared_codes = discover_meeting_and_stewards_horses()

    # Include key audit horses and any extra requested brand codes
    audit_codes = ["H321", "K415", "L305", "J534", "K358", "L142", "K308", "K239", "J360", "L187", "L077", "L260"]
    for c in audit_codes + (extra_codes or []):
        cu = str(c).strip().upper()
        if cu and cu not in targets_by_code:
            targets_by_code[cu] = {
                "horse_code": cu,
                "horse_id": None,
                "horse_name": "",
                "is_declared": cu in declared_codes,
            }

    print(
        f"[Vet Pipeline] Scraping official HKJC ovehorse records for {len(targets_by_code)} horses "
        f"({len(declared_codes)} declared runners)..."
    )

    scraped_records: Dict[str, Dict] = dict(existing_db)
    scraped_declared_codes = set()

    def _worker(item: Dict) -> Optional[Dict]:
        return scrape_horse_vet_record(
            horse_id=item.get("horse_id"),
            horse_code=item.get("horse_code"),
            horse_name=item.get("horse_name"),
            existing_db=existing_db,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        future_map = {executor.submit(_worker, item): code for code, item in targets_by_code.items()}
        for fut in concurrent.futures.as_completed(future_map):
            code = future_map[fut]
            try:
                rec = fut.result()
                if rec and rec.get("horse_id"):
                    scraped_records[rec["horse_id"]] = rec
                    if code in declared_codes:
                        scraped_declared_codes.add(code)
            except Exception as e:
                print(f"[Vet Pipeline] Worker error for {code}: {e}")

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(VET_RECORDS_PATH, "w", encoding="utf-8") as f:
        json.dump(scraped_records, f, indent=2, ensure_ascii=False)

    # Cross-check against overecord (declared starters)
    overecord_rows = scrape_overecord_crosscheck()
    overecord_latest_by_code: Dict[str, Dict] = {}
    for row in overecord_rows:
        c = str(row.get("horse_code") or "").strip().upper()
        if c and c not in overecord_latest_by_code:
            overecord_latest_by_code[c] = row

    code_idx = build_code_index(scraped_records)
    disagreements = []
    for c, ov_latest in overecord_latest_by_code.items():
        per_horse = code_idx.get(c)
        if not per_horse or not per_horse.get("entries"):
            disagreements.append(
                {
                    "horse_code": c,
                    "reason": "Missing from per-horse ovehorse records",
                    "overecord_date": ov_latest.get("date"),
                }
            )
            continue
        ph_latest = per_horse["entries"][0]
        if ph_latest.get("date") != ov_latest.get("date") or ph_latest.get("passed_on") != ov_latest.get("passed_on"):
            disagreements.append(
                {
                    "horse_code": c,
                    "ovehorse_latest": {"date": ph_latest.get("date"), "passed_on": ph_latest.get("passed_on")},
                    "overecord_latest": {"date": ov_latest.get("date"), "passed_on": ov_latest.get("passed_on")},
                }
            )

    updated_stats_count = sync_vet_to_latest_stats(scraped_records)

    declared_total = len(declared_codes)
    declared_scraped = len(scraped_declared_codes)
    coverage_pct = round((declared_scraped / declared_total) * 100.0, 2) if declared_total > 0 else 100.0
    status = "ok" if (coverage_pct >= 100.0 and len(disagreements) == 0) else "warn"
    now_iso = utc_now_iso()

    metrics = {
        "horses_scraped": len(scraped_records),
        "target_horses_this_run": len(targets_by_code),
        "horses_declared": declared_total,
        "declared_horses_scraped": declared_scraped,
        "declared_coverage_pct": coverage_pct,
        "overecord_disagreements_count": len(disagreements),
        "overecord_disagreements": disagreements[:10],
        "latest_stats_rows_updated": updated_stats_count,
        "last_successful_commit_at": now_iso,
        "source_url": "https://racing.hkjc.com/en-us/local/information/ovehorse",
    }
    warn_msg = None
    if coverage_pct < 100.0:
        warn_msg = f"Declared runner coverage {coverage_pct}% ({declared_scraped}/{declared_total})"
    elif disagreements:
        warn_msg = f"{len(disagreements)} disagreement(s) between ovehorse and overecord"

    record_health("veterinary_records", status, metrics=metrics, error=warn_msg)
    print(
        f"[Vet Pipeline] Complete: {len(scraped_records)} horses stored in data/vet_records.json, "
        f"declared coverage {declared_scraped}/{declared_total} ({coverage_pct}%), "
        f"disagreements={len(disagreements)}."
    )
    return metrics


if __name__ == "__main__":
    refresh_all_vet_records()

"""
Golden Stallion HKJC - Tactical Incident Engine & Memory Architecture
Automated Stewards' Report NLP Parser, Tactical Memory Bank & Outlier Radar
"""

import os
import re
import sys
import json
import glob
import logging
import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# -------------------------------------------------------------------------
# Regex & NLP Dictionaries (Negation-aware & Word-boundary enclosed)
# -------------------------------------------------------------------------

NEGATION_PATTERNS = [
    r'\bnot\s+held\s+up\b',
    r'\bno\s+interference\b',
    r'\bnot\s+checked\b',
    r'\bnot\s+crowded\b',
    r'\bwithout\s+interruption\b',
    r'\bclear\s+run\b',
    r'\bunimpeded\b'
]

TRAFFIC_TROUBLE_KEYWORDS = [
    r'\bheld\s+up\s+for\s+clear\s+running\b',
    r'\bdifficulty\s+obtaining\s+clear\s+running\b',
    r'\bheld\s+up\b',
    r'\bpocketed\b',
    r'\bseverely\s+checked\b',
    r'\bbadly\s+checked\b',
    r'\bchecked\b',
    r'\bseverely\s+crowded\b',
    r'\bcrowded\b',
    r'\bhampered\b',
    r'\bdisappointed\s+for\s+a\s+run\b',
    r'\bno\s+clear\s+run\b',
    r'受困',
    r'沒有足夠空隙',
    r'勒避'
]

WIDE_NO_COVER_KEYWORDS = [
    r'\braced\s+wide\b',
    r'\bthree\s+wide\b',
    r'\b3-wide\b',
    r'\bfour\s+wide\b',
    r'\b4-wide\b',
    r'\bwithout\s+cover\b',
    r'\bforced\s+wide\b',
    r'三疊無遮'
]

SLOW_START_KEYWORDS = [
    r'\bslow\s+to\s+begin\b',
    r'\bjumped\s+only\s+fairly\b',
    r'\bjumped\s+awkwardly\b',
    r'\blost\s+ground\s+at\s+the\s+start\b',
    r'\bcrowded\s+at\s+the\s+start\b',
    r'出閘緩慢'
]

SAVED_GROUND_KEYWORDS = [
    r'\bon\s+the\s+rail\b',
    r'\bsaved\s+ground\b',
    r'\bhugged\s+the\s+rail\b',
    r'\balong\s+the\s+fence\b',
    r'\bon\s+the\s+paint\b',
    r'\bthe\s+inside\s+rail\b'
]

GATE_SPEED_KEYWORDS = [
    r'\bjumped\s+well\b',
    r'\bbegan\s+speedily\b',
    r'\bled\s+early\b',
    r'\braced\s+prominently\b',
    r'\bquick\s+to\s+begin\b',
    r'\bshowed\s+good\s+early\s+speed\b'
]

VET_OR_MERIT_KEYWORDS = [
    r'\blame\b',
    r'\brespiratory\b',
    r'\bblood\s+in\s+trachea\b',
    r'\btrachea\b',
    r'\bsore\b',
    r'\bfinished\s+only\s+fairly\b',
    r'\bno\s+excuse\b',
    r'\bdisappointing\b',
    r'\birregular\s+heart\s+rhythm\b',
    r'\bbled\b',
    r'\bveterinary\s+examination\b'
]

MARKER_PATTERNS = {
    'final_200m': [r'\b200m\b', r'\b150m\b', r'\b100m\b', r'\bfinal\s+100m\b', r'\bconcluding\s+stages\b'],
    'final_400m': [r'\b400m\b', r'\b350m\b', r'\b300m\b', r'\b250m\b', r'\bentering\s+the\s+home\s+straight\b', r'\bstraight\b'],
    'final_600m': [r'\b600m\b', r'\b500m\b', r'\bhome\s+turn\b', r'\brounding\s+the\s+turn\b', r'\bturn\b'],
    'mid': [r'\b800m\b', r'\b1000m\b', r'\b1200m\b', r'\bbackstretch\b', r'\bmiddle\s+stages\b'],
    'start': [r'\bstart\b', r'\bjumpe?d?\b', r'\bgates?\b', r'\bshortly\s+after\s+the\s+start\b', r'\bbeginning\b']
}


def parse_incident(text, target_horse_name=None):
    """
    Parses an individual incident snippet.
    Returns: list of dicts: {flag, severity (0-3), marker, snippet, vet_blocked, is_victim}
    """
    if not text or not isinstance(text, str):
        return []

    text_lower = text.lower().strip()
    if not text_lower:
        return []

    # Check for global negation / clear run
    for neg in NEGATION_PATTERNS:
        if re.search(neg, text_lower):
            # If explicit "no excuse" or "finished only fairly", flag as vet_or_merit
            if "no excuse" in text_lower or "finished only fairly" in text_lower:
                return [{
                    'flag': 'vet_or_merit',
                    'severity': 1,
                    'marker': 'final_400m',
                    'snippet': text[:120],
                    'vet_blocked': True,
                    'is_victim': False
                }]
            return []

    # Careless Riding Victim vs Offender Disambiguation:
    is_offender = False
    if target_horse_name and ("careless riding" in text_lower or "reprimanded" in text_lower or "suspended" in text_lower):
        offender_match = re.search(r'([a-z\s]+)\s*\(([^)]+)\)\s*(?:pleaded guilty|was reprimanded|was suspended|was found guilty)', text_lower)
        if offender_match:
            offender_horse = offender_match.group(2).strip()
            if target_horse_name.lower() in offender_horse or offender_horse in target_horse_name.lower():
                is_offender = True

    # Identify Location Marker
    detected_marker = 'mid'
    for marker, patterns in MARKER_PATTERNS.items():
        if any(re.search(p, text_lower) for p in patterns):
            detected_marker = marker
            break

    flags = []

    # 1. Vet or Merit Block
    for kw in VET_OR_MERIT_KEYWORDS:
        if re.search(kw, text_lower):
            flags.append({
                'flag': 'vet_or_merit',
                'severity': 2,
                'marker': detected_marker,
                'snippet': text[:120],
                'vet_blocked': True,
                'is_victim': False
            })
            break

    # If vet blocked, do not grant positive forgiveness
    has_vet = any(f['flag'] == 'vet_or_merit' for f in flags)

    # 2. Traffic Trouble
    for kw in TRAFFIC_TROUBLE_KEYWORDS:
        if re.search(kw, text_lower):
            if is_offender:
                # Offender does not receive victim traffic trouble flag
                continue
            
            # Determine severity
            if detected_marker in ['final_200m', 'final_400m', 'final_600m']:
                if 'severely' in text_lower or 'badly' in text_lower or 'disappointed' in text_lower or 'held up' in text_lower:
                    sev = 3
                else:
                    sev = 2
            elif detected_marker == 'mid':
                sev = 2
            else: # start bump
                sev = 1

            flags.append({
                'flag': 'traffic_trouble',
                'severity': sev,
                'marker': detected_marker,
                'snippet': text[:120],
                'vet_blocked': has_vet,
                'is_victim': not is_offender
            })
            break

    # 3. Wide Without Cover
    for kw in WIDE_NO_COVER_KEYWORDS:
        if re.search(kw, text_lower):
            sev = 3 if ('four wide' in text_lower or '4-wide' in text_lower or 'without cover' in text_lower) else 2
            flags.append({
                'flag': 'wide_no_cover',
                'severity': sev,
                'marker': detected_marker,
                'snippet': text[:120],
                'vet_blocked': has_vet,
                'is_victim': True
            })
            break

    # 4. Slow Start
    for kw in SLOW_START_KEYWORDS:
        if re.search(kw, text_lower):
            flags.append({
                'flag': 'slow_start',
                'severity': 2 if ('lost ground' in text_lower or 'awkwardly' in text_lower) else 1,
                'marker': 'start',
                'snippet': text[:120],
                'vet_blocked': has_vet,
                'is_victim': True
            })
            break

    # 5. Saved Ground
    for kw in SAVED_GROUND_KEYWORDS:
        if re.search(kw, text_lower):
            flags.append({
                'flag': 'saved_ground',
                'severity': 2,
                'marker': detected_marker,
                'snippet': text[:120],
                'vet_blocked': False,
                'is_victim': False
            })
            break

    # 6. Gate Speed (From race text only)
    for kw in GATE_SPEED_KEYWORDS:
        if re.search(kw, text_lower):
            flags.append({
                'flag': 'gate_speed',
                'severity': 2,
                'marker': 'start',
                'snippet': text[:120],
                'vet_blocked': False,
                'is_victim': False
            })
            break

    return flags


# -------------------------------------------------------------------------
# Web Scraper for Official HKJC Incident Reports
# -------------------------------------------------------------------------

def _clean_horse_name(raw_text: str) -> str:
    """Strips brand codes like (J123) and normalizes horse name to uppercase."""
    if not raw_text:
        return ""
    cleaned = re.sub(r"\s*\([A-Z0-9]+\)", "", str(raw_text)).strip().upper()
    return cleaned


def parse_hkjc_racereport_html(html_text: str, expect_date: str = None) -> dict:
    """
    Parses HKJC `racereportfull` HTML content into {clean_horse_name: incident_text}.
    Asserts the page's 'Race Meeting: DD/MM/YYYY' header matches `expect_date` (via hkjc_guard)
    and identifies the Horse and Incident columns properly instead of reading Placing (tds[0]).
    """
    from monitoring.hkjc_guard import validate_hkjc_html

    validate_hkjc_html(html_text, expect_date=expect_date)
    soup = BeautifulSoup(html_text, "html.parser")
    meeting_incidents = {}

    for table in soup.find_all("table"):
        # Detect column indices from header row if present
        horse_col_idx = None
        incident_col_idx = None

        rows = table.find_all("tr")
        for tr in rows:
            header_cells = tr.find_all(["th", "td"])
            header_texts = [c.get_text(strip=True).upper() for c in header_cells]
            if any("INCIDENT" in h for h in header_texts) and any("HORSE" in h for h in header_texts):
                for idx, h in enumerate(header_texts):
                    if h in ("HORSE", "HORSE NAME") or ("HORSE" in h and "NO" not in h):
                        horse_col_idx = idx
                    elif "INCIDENT" in h or "REPORT" in h:
                        incident_col_idx = idx
                continue

            tds = tr.find_all("td")
            if len(tds) < 2:
                continue

            if horse_col_idx is not None and incident_col_idx is not None and len(tds) > max(horse_col_idx, incident_col_idx):
                h_raw = tds[horse_col_idx].get_text(strip=True)
                inc_text = tds[incident_col_idx].get_text(strip=True)
            elif len(tds) >= 5:
                # Standard HKJC 5-column layout: [Pla., Horse No., Horse, Jockey, Incident]
                h_raw = tds[2].get_text(strip=True)
                inc_text = tds[-1].get_text(strip=True)
            elif len(tds) == 4:
                # 4-column layout: [Pla./No., Horse, Jockey, Incident]
                h_raw = tds[1].get_text(strip=True) if tds[0].get_text(strip=True).isdigit() else tds[2].get_text(strip=True)
                inc_text = tds[-1].get_text(strip=True)
            elif len(tds) == 3:
                # 3-column layout: [Horse No., Horse, Incident]
                h_raw = tds[1].get_text(strip=True)
                inc_text = tds[2].get_text(strip=True)
            else:
                # 2-column layout: [Horse, Incident]
                h_raw = tds[0].get_text(strip=True)
                inc_text = tds[1].get_text(strip=True)

            h_clean = _clean_horse_name(h_raw)
            if (
                h_clean
                and not h_clean.isdigit()
                and h_clean not in ("HORSE", "PLA.", "PLACING", "HORSE NO.", "NO.")
                and len(inc_text) > 3
            ):
                meeting_incidents[h_clean] = inc_text

    return meeting_incidents


def scrape_meeting_incidents(date_str, html_content=None):
    """
    Scrapes official HKJC full race incident reports.
    date_str format: 'YYYY/MM/DD' or 'YYYY-MM-DD' or 'YYYYMMDD'
    Returns: dict of clean_horse_name -> incident report string
    Raises HKJCDateMismatch if HKJC returns a report for a different meeting date.
    """
    from monitoring.health import record as record_health
    from monitoring.hkjc_guard import HKJCDateMismatch, HKJCFetchError

    clean_date = date_str.replace('-', '').replace('/', '')
    if len(clean_date) == 8:
        formatted_date = f"{clean_date[:4]}/{clean_date[4:6]}/{clean_date[6:]}"
    else:
        formatted_date = date_str

    url = f"https://racing.hkjc.com/en-us/local/information/racereportfull?Date={formatted_date}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }

    try:
        if html_content is None:
            logging.info(f"Fetching HKJC Incident Report from {url}...")
            resp = requests.get(url, headers=headers, timeout=12)
            if resp.status_code != 200:
                msg = f"Failed to fetch HKJC Incident Report (Status {resp.status_code}) for {date_str}"
                logging.warning(msg)
                record_health("incident_engine", "fail", metrics={"date": date_str, "url": url}, error=msg)
                return {}
            html_text = resp.text
        else:
            html_text = html_content

        meeting_incidents = parse_hkjc_racereport_html(html_text, expect_date=date_str)
        logging.info(f"Parsed {len(meeting_incidents)} incident records from HKJC report for {date_str}.")
        status = "ok" if len(meeting_incidents) > 0 else "warn"
        record_health(
            "incident_engine",
            status,
            metrics={"date": date_str, "rows": len(meeting_incidents), "source_url": url},
        )
        return meeting_incidents
    except (HKJCDateMismatch, HKJCFetchError) as guard_err:
        record_health("incident_engine", "fail", metrics={"date": date_str, "source_url": url}, error=str(guard_err))
        raise
    except Exception as e:
        logging.warning(f"Error scraping HKJC incident report for {date_str}: {e}")
        record_health("incident_engine", "fail", metrics={"date": date_str, "source_url": url}, error=str(e))
        return {}


# -------------------------------------------------------------------------
# Tactical Memory Bank Builder & Ingestion
# -------------------------------------------------------------------------

MEMORY_FILE = 'data/horse_incident_memory.json'
CONFIG_FILE = 'data/tactical_overlay_config.json'

def load_tactical_config():
    """Loads tactical overlay configuration."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"Failed to read {CONFIG_FILE}: {e}")
    return {
        "seeds": {"forgiven_run": 2.5, "trip_regression": -2.0, "sectional_eye_catcher": 2.0},
        "total_clip": 3.5,
        "relative_clip": 0.15,
        "apply_tactical_overlay": False,
        "live_coefficients": {"forgiven_run": 0.0, "trip_regression": 0.0, "sectional_eye_catcher": 0.0}
    }


def load_horse_memory():
    """Loads horse incident memory."""
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"Error reading memory file: {e}")
    return {}


def save_horse_memory(mem_dict):
    """Saves horse incident memory."""
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(mem_dict, f, indent=2, ensure_ascii=False)


def build_horse_incident_memory(force_rebuild=False):
    """
    Builds the complete incident and trip memory across all available race data, comments, and stats.
    """
    from monitoring.health import record as record_health

    logging.info("Building / Updating Tactical Incident Memory Bank...")
    memory = load_horse_memory() if not force_rebuild else {}

    # 1. Load precomputed last_comments (keyed by clean horse name)
    comments_dict = {}
    precomp_data = {}
    if os.path.exists('data/precomputed_features.json'):
        try:
            with open('data/precomputed_features.json', 'r', encoding='utf-8') as f:
                precomp_data = json.load(f)
                for h_name, c_text in (precomp_data.get('last_comments') or {}).items():
                    if h_name and c_text:
                        comments_dict[str(h_name).strip().upper()] = str(c_text)
        except Exception as e:
            logging.warning(f"Error loading precomputed_features.json comments: {e}")

    # 1b. Automatically scrape & ingest official HKJC Stewards' Reports for recent meetings
    #     plus any replay_incident_notes_*.json files so the AI logs every meeting automatically.
    from datetime import datetime, timezone, timedelta
    today_hkt_tag = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d")

    recent_dates = set()
    for fp in sorted(glob.glob('data/frozen_predictions_202610*.json'))[-5:]:
        m = re.search(r'(\d{8})', fp)
        if m and m.group(1) <= today_hkt_tag:
            recent_dates.add(m.group(1))
    for ma in sorted(glob.glob('data/meeting_audit_2026*.json'))[-5:]:
        m = re.search(r'(\d{8})', ma)
        if m and m.group(1) <= today_hkt_tag:
            recent_dates.add(m.group(1))

    total_ingested_incidents = 0
    for d_tag in sorted(recent_dates):
        inc_cache_path = f"data/scraped_incidents_{d_tag}.json"
        inc_map = {}
        if os.path.exists(inc_cache_path):
            try:
                with open(inc_cache_path, 'r', encoding='utf-8') as f:
                    inc_map = json.load(f)
            except Exception as e:
                logging.warning(f"Error reading {inc_cache_path}: {e}")
        else:
            try:
                inc_map = scrape_meeting_incidents(d_tag)
                if inc_map:
                    with open(inc_cache_path, 'w', encoding='utf-8') as f:
                        json.dump(inc_map, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logging.warning(f"Stewards report scrape skipped/failed for {d_tag}: {e}")

        for h_name, inc_txt in (inc_map or {}).items():
            c_h = _clean_horse_name(h_name)
            if c_h and inc_txt:
                comments_dict[c_h] = str(inc_txt)
                total_ingested_incidents += 1

    # Ingest replay_incident_notes_*.json (e.g. Oct 25 Sha Tin replay & stewards intelligence)
    replay_notes_by_date = {}
    for rn_file in sorted(glob.glob('data/replay_incident_notes_*.json')):
        try:
            with open(rn_file, 'r', encoding='utf-8') as f:
                rn_payload = json.load(f)
                m_date = str(rn_payload.get('meeting_date', '2026-10-25'))
                m_venue = str(rn_payload.get('venue', 'Sha Tin'))
                inc_dict = rn_payload.get('incidents') or {}
                replay_notes_by_date[m_date] = (m_venue, inc_dict)
                for h_name, inc_txt in inc_dict.items():
                    c_h = _clean_horse_name(h_name)
                    if c_h and inc_txt:
                        comments_dict[c_h] = str(inc_txt)
        except Exception as e:
            logging.warning(f"Error loading {rn_file}: {e}")

    # Persist updated last_comments back to data/precomputed_features.json so all prediction scripts use them
    if precomp_data and comments_dict:
        try:
            precomp_data['last_comments'] = comments_dict
            with open('data/precomputed_features.json', 'w', encoding='utf-8') as f:
                json.dump(precomp_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.warning(f"Error updating precomputed_features.json: {e}")

    # 2. Initialize from latest_horse_stats.csv and harvest last_run_summary / latest_vet_note
    if os.path.exists('data/latest_horse_stats.csv'):
        lhs = pd.read_csv('data/latest_horse_stats.csv')
        for _, r in lhs.iterrows():
            cname = str(r.get('clean_name', '')).strip().upper()
            hcode = str(r.get('horse_code', '')).strip().upper()
            if cname and cname != 'NAN':
                if cname not in memory:
                    memory[cname] = {
                        'horse_name': cname,
                        'horse_code': hcode if hcode and hcode != 'NAN' else '',
                        'runs': [],
                        'trial_note': None
                    }
                if hcode and hcode != 'NAN' and hcode not in memory:
                    memory[hcode] = memory[cname]

                summary_txt = str(r.get('last_run_summary', '')).strip()
                vet_txt = str(r.get('latest_vet_note', '')).strip()
                combined_note = " ".join(
                    [t for t in (comments_dict.get(cname, ''), summary_txt, vet_txt) if t and t.lower() not in ('nan', 'none', 'no findings')]
                ).strip()
                if combined_note:
                    comments_dict[cname] = combined_note
                    flags = parse_incident(combined_note, target_horse_name=cname)
                    lrd = str(r.get('last_run_date', '')).strip()
                    if flags and not memory[cname]['runs']:
                        max_interf = max([f['severity'] for f in flags if f['flag'] == 'traffic_trouble'], default=0)
                        saved_g_flag = any(f['flag'] == 'saved_ground' for f in flags)
                        raw_cls = pd.to_numeric(r.get('last_race_class_int'), errors='coerce')
                        cls_val = 4 if pd.isna(raw_cls) else int(raw_cls)
                        raw_pos = pd.to_numeric(r.get('recent_avg_pos'), errors='coerce')
                        pos_val = 6 if pd.isna(raw_pos) else int(raw_pos)
                        raw_ep = pd.to_numeric(r.get('avg_first_pos'), errors='coerce')
                        ep_val = 6.0 if pd.isna(raw_ep) else float(raw_ep)
                        memory[cname]['runs'].append({
                            'race_date': lrd if lrd and lrd.lower() != 'nan' else '2026-10-25',
                            'race_id': f"{lrd or 'profile'}_LAST",
                            'venue': str(r.get('ST_vs_HV_pref', 'Sha Tin')),
                            'course_rail': 'A',
                            'surface': str(r.get('AWT_vs_Turf_pref', 'TURF')).upper(),
                            'going': str(r.get('last_form_going', 'GOOD')),
                            'distance': 1200,
                            'class': f"Class {cls_val}",
                            'barrier': 6,
                            'finish_pos': pos_val,
                            'beaten_lengths': 2.0,
                            'sp': 8.0,
                            'weight_carried': 125.0,
                            'early_pos': ep_val,
                            'final_section_time': 22.8,
                            'final_section_rank': 4,
                            'field_size': 12,
                            'incident_flags': flags,
                            'ground_saved_score': 1.0 if saved_g_flag else 0.5,
                            'interference_severity': max_interf,
                            'gate_speed_proven': any(f['flag'] == 'gate_speed' for f in flags),
                            'steward_comment': combined_note
                        })

    # 3. Ingest scraped results files (e.g. 20261001, etc.) and last_scraped_meeting.json
    for res_file in sorted(glob.glob('data/scraped_results_*.json')):
        date_match = re.search(r'(\d{8})', res_file)
        r_date = date_match.group(1) if date_match else "20261001"
        formatted_date = f"{r_date[:4]}-{r_date[4:6]}-{r_date[6:]}"
        try:
            with open(res_file, 'r', encoding='utf-8') as f:
                res_data = json.load(f)
                for r_num, runners in res_data.items():
                    if isinstance(runners, dict):
                        runners = runners.get('runners') or runners.get('top4') or []
                    if not isinstance(runners, list):
                        continue
                    for r in runners:
                        if not isinstance(r, dict):
                            continue
                        raw_name = r.get('horse_name', '')
                        clean_name = re.sub(r'\s*\([A-Z0-9]+\)', '', raw_name).strip().upper()
                        code_match = re.search(r'\(([A-Z0-9]+)\)', raw_name)
                        hcode = code_match.group(1).upper() if code_match else ''
                        
                        key = clean_name
                        if key not in memory:
                            memory[key] = {
                                'horse_name': clean_name,
                                'horse_code': hcode,
                                'runs': [],
                                'trial_note': None
                            }
                        if hcode and hcode not in memory:
                            memory[hcode] = memory[key]
                        
                        fin_pos = r.get('place', 99)
                        lbw_str = str(r.get('lbw', '0')).strip()
                        if lbw_str in ['---', '', 'SH', 'HD', 'NOSE']:
                            lbw = 0.0 if lbw_str in ['---', ''] else (0.1 if lbw_str == 'NOSE' else (0.2 if lbw_str == 'HD' else 0.15))
                        else:
                            try:
                                if '-' in lbw_str:
                                    parts = lbw_str.split('-')
                                    whole = float(parts[0])
                                    frac = parts[1].split('/')
                                    lbw = whole + (float(frac[0]) / float(frac[1]))
                                elif '/' in lbw_str:
                                    frac = lbw_str.split('/')
                                    lbw = float(frac[0]) / float(frac[1])
                                else:
                                    lbw = float(lbw_str)
                            except ValueError:
                                lbw = 2.0

                        comm = comments_dict.get(clean_name, '')
                        incident_flags = parse_incident(comm, target_horse_name=clean_name)
                        max_interf = max([f['severity'] for f in incident_flags if f['flag'] == 'traffic_trouble'], default=0)
                        saved_g_flag = any(f['flag'] == 'saved_ground' for f in incident_flags)

                        run_rec = {
                            'race_date': formatted_date,
                            'race_id': f"{r_date}_R{r_num}",
                            'venue': 'Sha Tin',
                            'course_rail': 'A',
                            'surface': 'TURF',
                            'going': 'GOOD TO FIRM' if '1001' in r_date else 'GOOD',
                            'distance': 1200,
                            'class': 'Class 4',
                            'barrier': 5,
                            'finish_pos': fin_pos,
                            'beaten_lengths': lbw,
                            'sp': float(r.get('win_odds', 10.0)),
                            'weight_carried': 125.0,
                            'early_pos': 6.0,
                            'final_section_time': 22.8,
                            'final_section_rank': 4,
                            'field_size': len(runners),
                            'incident_flags': incident_flags,
                            'ground_saved_score': 1.0 if saved_g_flag else 0.5,
                            'interference_severity': max_interf,
                            'gate_speed_proven': any(f['flag'] == 'gate_speed' for f in incident_flags)
                        }

                        runs_list = memory[key]['runs']
                        if not any(x.get('race_id') == run_rec['race_id'] for x in runs_list):
                            runs_list.insert(0, run_rec)
                        else:
                            for existing_r in runs_list:
                                if existing_r.get('race_id') == run_rec['race_id'] and incident_flags:
                                    existing_r['incident_flags'] = incident_flags
                                    existing_r['interference_severity'] = max_interf
                        memory[key]['runs'] = runs_list[:6]
        except Exception as e:
            logging.warning(f"Error parsing {res_file}: {e}")

    # Also ingest latest completed meeting from last_scraped_meeting.json if present
    if os.path.exists('data/last_scraped_meeting.json'):
        try:
            with open('data/last_scraped_meeting.json', 'r', encoding='utf-8') as f:
                lsm = json.load(f)
                for m in (lsm.get('meetings') or []):
                    m_date = str(m.get('date', '2026-10-21'))
                    m_venue = str(m.get('venue', 'Happy Valley'))
                    for race in (m.get('races') or []):
                        r_no = race.get('race_no', 1)
                        for runner in (race.get('runners') or []):
                            fin = runner.get('final_position')
                            if fin is None:
                                continue
                            cname = _clean_horse_name(runner.get('name', ''))
                            if not cname:
                                continue
                            if cname not in memory:
                                memory[cname] = {
                                    'horse_name': cname,
                                    'horse_code': str(runner.get('code') or ''),
                                    'runs': [],
                                    'trial_note': None
                                }
                            comm = comments_dict.get(cname, '')
                            flags = parse_incident(comm, target_horse_name=cname)
                            max_interf = max([fl['severity'] for fl in flags if fl['flag'] == 'traffic_trouble'], default=0)
                            race_id = f"{m_date.replace('-', '')}_R{r_no}"
                            run_rec = {
                                'race_date': m_date,
                                'race_id': race_id,
                                'venue': m_venue,
                                'course_rail': str(race.get('course', 'C')),
                                'surface': 'TURF',
                                'going': str(m.get('going', 'GOOD')),
                                'distance': int(race.get('distance', 1200) or 1200),
                                'class': str(race.get('class_dist', 'Class 4')),
                                'barrier': int(runner.get('draw', 6) or 6),
                                'finish_pos': int(fin),
                                'beaten_lengths': 0.0 if int(fin) == 1 else 2.0,
                                'sp': float(runner.get('win_odds', 10.0) or 10.0),
                                'weight_carried': float(runner.get('actual_weight', 125.0) or 125.0),
                                'early_pos': 5.0,
                                'final_section_time': 22.8,
                                'final_section_rank': 4,
                                'field_size': len(race.get('runners') or []),
                                'incident_flags': flags,
                                'ground_saved_score': 0.5,
                                'interference_severity': max_interf,
                                'gate_speed_proven': any(fl['flag'] == 'gate_speed' for fl in flags)
                            }
                            runs_list = memory[cname]['runs']
                            if not any(x.get('race_id') == race_id for x in runs_list):
                                runs_list.insert(0, run_rec)
                                memory[cname]['runs'] = runs_list[:6]
        except Exception as e:
            logging.warning(f"Error ingesting last_scraped_meeting.json into incident memory: {e}")

    # Also ingest replay_incident_notes_*.json and meeting_audit_*.json so every recent runner is logged
    # Cross-reference with frozen_predictions_<YYYYMMDD>.json and last_scraped_meeting.json for real draw, odds, distance, weight, and finish
    for m_date, (m_venue, inc_dict) in replay_notes_by_date.items():
        r_date_tag = m_date.replace('-', '')
        runner_meta_by_name = {}

        # Load runner metadata (race_no, draw, weight, sp, avg_first_pos, field_size) from frozen_predictions_<YYYYMMDD>.json
        fp_path = f"data/frozen_predictions_{r_date_tag}.json"
        if os.path.exists(fp_path):
            try:
                with open(fp_path, 'r', encoding='utf-8') as f:
                    fp_data = json.load(f)
                for r_key, r_list in (fp_data or {}).items():
                    if not isinstance(r_list, list):
                        continue
                    r_no_m = re.search(r'_R(\d+)', str(r_key))
                    r_no_val = int(r_no_m.group(1)) if r_no_m else 1
                    f_size = len(r_list)
                    for r_item in r_list:
                        if not isinstance(r_item, dict):
                            continue
                        rn_clean = _clean_horse_name(r_item.get('clean_name') or r_item.get('name') or '')
                        if rn_clean:
                            runner_meta_by_name[rn_clean] = {
                                'race_no': r_no_val,
                                'horse_no': int(r_item.get('no', 0) or 0),
                                'horse_code': str(r_item.get('code') or r_item.get('horse_code') or ''),
                                'barrier': int(r_item.get('draw', 6) or 6),
                                'weight_carried': float(r_item.get('actual_weight', 125.0) or 125.0),
                                'sp': float(r_item.get('scraped_win_odds') or r_item.get('win_odds') or 6.0),
                                'early_pos': float(r_item.get('avg_first_pos', 6.0) or 6.0),
                                'best_last_sec': float(r_item.get('best_last_sec', 22.8) or 22.8),
                                'going': str(r_item.get('current_going', 'GOOD') or 'GOOD'),
                                'field_size': f_size,
                            }
            except Exception as e:
                logging.warning(f"Error reading {fp_path} for replay metadata: {e}")

        # Supplement distance, class, course, surface from last_scraped_meeting.json if matching date exists
        race_info_by_no = {}
        if os.path.exists('data/last_scraped_meeting.json'):
            try:
                with open('data/last_scraped_meeting.json', 'r', encoding='utf-8') as f:
                    lsm_data = json.load(f)
                for m_obj in (lsm_data.get('meetings') or []):
                    if str(m_obj.get('date', '')).replace('/', '-') == m_date:
                        for rc in (m_obj.get('races') or []):
                            rc_no = int(rc.get('race_no', 0) or 0)
                            c_dist_str = str(rc.get('class_dist', 'Class 4 - 1200m'))
                            d_m = re.search(r'(\d{4})m', c_dist_str)
                            dist_val = int(d_m.group(1)) if d_m else 1200
                            cls_label = c_dist_str.split('-')[0].strip() if '-' in c_dist_str else c_dist_str
                            race_info_by_no[rc_no] = {
                                'distance': dist_val,
                                'class': cls_label,
                                'course_rail': str(rc.get('course', 'A') or 'A'),
                                'surface': str(rc.get('track', 'TURF') or 'TURF').upper(),
                                'going': str(rc.get('going', m_obj.get('going', 'GOOD')) or 'GOOD'),
                            }
            except Exception as e:
                logging.warning(f"Error reading race info from last_scraped_meeting.json: {e}")

        for h_raw, inc_txt in inc_dict.items():
            cname = _clean_horse_name(h_raw)
            if not cname:
                continue
            meta = runner_meta_by_name.get(cname, {})
            h_code = meta.get('horse_code', '')
            if cname not in memory:
                memory[cname] = {
                    'horse_name': cname,
                    'horse_code': h_code,
                    'runs': [],
                    'trial_note': None
                }
            elif h_code and not memory[cname].get('horse_code'):
                memory[cname]['horse_code'] = h_code

            flags = parse_incident(inc_txt, target_horse_name=cname)
            max_interf = max([fl['severity'] for fl in flags if fl['flag'] == 'traffic_trouble'], default=0)
            saved_g = any(fl['flag'] == 'saved_ground' for fl in flags)

            rc_no = meta.get('race_no')
            rc_info = race_info_by_no.get(rc_no, {}) if rc_no else {}
            race_id = f"{r_date_tag}_R{rc_no}" if rc_no else f"{r_date_tag}_REPLAY"

            inc_lower = inc_txt.lower()
            # Parse true finish_pos and beaten_lengths from replay/stewards text
            if re.search(r'\b(to win|won impressively|win unextended|sustained run to win)\b', inc_lower):
                fin_pos = 1
                lbw_val = 0.0
            elif re.search(r'\bfinish(?:ed)?\s+2nd\b|\btiring in the final 50m\b', inc_lower):
                fin_pos = 2
                lbw_val = 0.5
            elif re.search(r'\bfinish(?:ed)?\s+3rd\b', inc_lower):
                fin_pos = 3
                lbw_val = 1.2
            elif re.search(r'\bfaded\b|\bdisappointing\b|\blost ground abruptly\b|\bmissed the start\b|\blost three lengths\b', inc_lower):
                fin_pos = 8
                lbw_val = 5.5
            elif max_interf >= 2:
                fin_pos = 4
                lbw_val = 1.5
            else:
                fin_pos = 4
                lbw_val = 2.0

            # Parse true early running position
            if re.search(r'\bled early\b|\bsetting the early pace\b|\bwent hard in front\b|\bled by\b', inc_lower):
                early_pos_val = 1.2
            elif re.search(r'\bsettled (?:at the )?(?:rear|back)\b|\bfrom well back\b|\bfrom the rear\b|\bsettled rearward\b|\bsettled back\b', inc_lower):
                early_pos_val = 10.0
            else:
                early_pos_val = float(meta.get('early_pos', 6.0))

            is_fast_closer_note = any(
                phrase in inc_lower
                for phrase in ('closed strongly', 'flew home', 'swept past', 'sprinted clear', 'made up significant late ground')
            )
            run_rec = {
                'race_date': m_date,
                'race_id': race_id,
                'venue': m_venue,
                'course_rail': rc_info.get('course_rail', 'A'),
                'surface': rc_info.get('surface', 'TURF'),
                'going': rc_info.get('going', meta.get('going', 'GOOD')),
                'distance': int(rc_info.get('distance', 1200)),
                'class': rc_info.get('class', 'Class 4'),
                'barrier': int(meta.get('barrier', 6)),
                'finish_pos': fin_pos,
                'beaten_lengths': lbw_val,
                'sp': round(float(meta.get('sp', 6.0)), 1),
                'weight_carried': float(meta.get('weight_carried', 125.0)),
                'early_pos': round(early_pos_val, 1),
                'final_section_time': 22.35 if is_fast_closer_note else float(meta.get('best_last_sec', 22.8)),
                'final_section_rank': 1 if is_fast_closer_note else 4,
                'field_size': int(meta.get('field_size', 14)),
                'incident_flags': flags,
                'ground_saved_score': 1.0 if saved_g else 0.5,
                'interference_severity': max_interf,
                'gate_speed_proven': any(fl['flag'] == 'gate_speed' for fl in flags),
                'steward_comment': inc_txt
            }
            runs_list = memory[cname]['runs']
            runs_list = [x for x in runs_list if x.get('race_id') not in (race_id, f"{r_date_tag}_REPLAY") and x.get('race_date') != m_date]
            runs_list.insert(0, run_rec)
            memory[cname]['runs'] = runs_list[:6]

    # 4. Attach secondary trial note (Trials cannot outrank races)
    if os.path.exists('data/engineered_trial_features.json'):
        try:
            with open('data/engineered_trial_features.json', 'r', encoding='utf-8') as f:
                trials = json.load(f)
                for tname, tdata in trials.items():
                    c_tname = tname.strip().upper()
                    if c_tname in memory:
                        memory[c_tname]['trial_note'] = {
                            'best_trial_pos_ratio': tdata.get('best_trial_pos_ratio', 1.0),
                            'best_trial_speed_diff': tdata.get('best_trial_speed_diff', 0.0),
                            'jockeys': tdata.get('trial_jockeys', [])
                        }
        except Exception as e:
            logging.warning(f"Error loading trial notes: {e}")

    save_horse_memory(memory)
    flagged_count = sum(
        1 for v in memory.values()
        if isinstance(v, dict) and any(r.get('incident_flags') for r in (v.get('runs') or []))
    )
    record_health(
        "incident_engine",
        "ok" if flagged_count > 0 else "warn",
        metrics={"ingested_incidents": total_ingested_incidents, "flagged_horses": flagged_count},
    )
    record_health(
        "incident_memory",
        "ok" if flagged_count > 0 else "warn",
        metrics={"horses": len(memory), "flagged_horses": flagged_count},
    )
    logging.info(f"Memory Bank successfully built with {len(memory)} active horse keys ({flagged_count} with incident flags).")
    return memory


# -------------------------------------------------------------------------
# Tactical Scoring & Badge Evaluation (Prior Starts Only: R -> R+1)
# -------------------------------------------------------------------------

def evaluate_tactical_scores(horse_key, today_context, memory_dict=None):
    """
    Evaluates tactical scores and badges for a runner using strictly prior starts (R -> R+1).
    today_context = {
        'barrier': int,
        'venue': str,
        'surface': str,
        'going': str,
        'distance': int,
        'sp': float,
        'winner_weight': float,
        'weight_carried': float
    }
    """
    if memory_dict is None:
        memory_dict = load_horse_memory()

    config = load_tactical_config()
    seeds = config.get('seeds', {})
    live_coeffs = config.get('live_coefficients', {})
    apply_overlay = config.get('apply_tactical_overlay', False)

    clean_key = str(horse_key).strip().upper()
    record = memory_dict.get(clean_key)
    if not record or not record.get('runs'):
        return {
            'forgiven_run': 0.0,
            'trip_regression': 0.0,
            'sectional_eye_catcher': 0.0,
            'weight_merit': 0.0,
            'badges': [],
            'net_score_seed': 0.0,
            'live_adjustment': 0.0
        }

    past_runs = record['runs']
    last_run = past_runs[0]
    today_barrier = today_context.get('barrier', 8)
    today_venue = today_context.get('venue', 'Sha Tin')

    badges = []
    scores = {
        'forgiven_run': 0.0,
        'trip_regression': 0.0,
        'sectional_eye_catcher': 0.0,
        'weight_merit': 0.0
    }

    # 1. FORGIVEN RUN (Traffic Trouble or Wide-Without-Cover Merit)
    last_interf = last_run.get('interference_severity', 0)
    last_sp = last_run.get('sp', 99.0)
    last_lbw = last_run.get('beaten_lengths', 99.0)
    last_finish = last_run.get('finish_pos', 99)
    inc_flags = last_run.get('incident_flags', [])
    has_vet = any(f.get('vet_blocked', False) for f in inc_flags)
    wide_flags = [f for f in inc_flags if f.get('flag') == 'wide_no_cover']
    wide_sev = max((f.get('severity', 0) for f in wide_flags), default=0)

    if last_interf >= 2 and (last_sp <= 12.0) and (last_lbw <= 2.5 or last_finish <= 4) and not has_vet:
        scores['forgiven_run'] = seeds.get('forgiven_run', 2.5)
        snippet = next((f['snippet'] for f in inc_flags if f['flag'] == 'traffic_trouble'), "Held up late")
        badges.append({
            'type': 'credit',
            'badge': '🎯 UNLUCKY RUNNER',
            'text': f"Blocked in straight ({snippet[:40]}); beaten only {last_lbw}L"
        })
    elif wide_sev >= 2 and (last_finish <= 4 or last_lbw <= 2.5) and not has_vet:
        scores['forgiven_run'] = seeds.get('wide_merit', 2.0)
        snippet = next((f['snippet'] for f in wide_flags), "Raced wide without cover")
        badges.append({
            'type': 'credit',
            'badge': '🔥 WIDE-TRIP MERIT',
            'text': f"Tough wide trip ({snippet[:40]}); finished #{last_finish}"
        })
    elif last_interf >= 2 and last_lbw <= 3.5 and not has_vet:
        scores['forgiven_run'] = 1.5
        badges.append({
            'type': 'credit',
            'badge': '🎯 PLACE LEAN',
            'text': f"Suffered interference; finished within {last_lbw}L"
        })

    # 2. TRIP REGRESSION
    last_saved_ground = last_run.get('ground_saved_score', 0.0) >= 0.8
    last_draw = last_run.get('barrier', 8)

    if last_finish in [1, 2] and last_saved_ground:
        if today_barrier >= 8 and (today_barrier - last_draw >= 4):
            scores['trip_regression'] = seeds.get('trip_regression', -2.0)
            badges.append({
                'type': 'warning',
                'badge': '⚠️ TRIP REGRESSION RISK',
                'text': f"Won via soft rail run (Gate {last_draw}); facing tough Gate {today_barrier} today"
            })

    # 3. SECTIONAL EYE-CATCHER
    last_sec_rank = last_run.get('final_section_rank', 99)
    last_sec_time = last_run.get('final_section_time', 99.0)
    last_early = last_run.get('early_pos', 6.0)

    if (last_sec_rank <= 3 or last_sec_time <= 22.6) and (last_early >= 7.0 or last_draw >= 10):
        if today_barrier <= 6 or (last_draw - today_barrier >= 4):
            scores['sectional_eye_catcher'] = seeds.get('sectional_eye_catcher', 2.0)
            badges.append({
                'type': 'credit',
                'badge': '⚡ SECTIONAL FLYER',
                'text': f"Clocked top split ({last_sec_time}s) from Gate {last_draw}; major barrier relief (Gate {today_barrier})"
            })

    # 4. WEIGHT MERIT RESIDUAL
    winner_wt = today_context.get('winner_weight', 125.0)
    today_wt = today_context.get('weight_carried', 125.0)
    scores['weight_merit'] = round(last_lbw - (today_wt - winner_wt) * 0.15, 2)

    # Net seed calculation with clips
    net_seed = sum([scores['forgiven_run'], scores['trip_regression'], scores['sectional_eye_catcher']])
    total_clip = config.get('total_clip', 3.5)
    net_seed_clipped = max(min(net_seed, total_clip), -total_clip)

    # Live adjustment (in percentage points, clipped to [-total_clip, +total_clip])
    if apply_overlay:
        live_adj = sum([
            (scores['forgiven_run'] / seeds.get('forgiven_run', 2.5)) * live_coeffs.get('forgiven_run', 2.5) if seeds.get('forgiven_run') else 0.0,
            (scores['trip_regression'] / seeds.get('trip_regression', -2.0)) * live_coeffs.get('trip_regression', -2.0) if seeds.get('trip_regression') else 0.0,
            (scores['sectional_eye_catcher'] / seeds.get('sectional_eye_catcher', 2.0)) * live_coeffs.get('sectional_eye_catcher', 2.0) if seeds.get('sectional_eye_catcher') else 0.0
        ])
        live_adj = max(min(live_adj, total_clip), -total_clip)
    else:
        live_adj = 0.0

    return {
        'forgiven_run': scores['forgiven_run'],
        'trip_regression': scores['trip_regression'],
        'sectional_eye_catcher': scores['sectional_eye_catcher'],
        'weight_merit': scores['weight_merit'],
        'badges': badges[:2],
        'net_score_seed': net_seed_clipped,
        'live_adjustment': live_adj
    }


if __name__ == '__main__':
    build_horse_incident_memory(force_rebuild=True)

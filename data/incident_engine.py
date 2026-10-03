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

def scrape_meeting_incidents(date_str):
    """
    Scrapes official HKJC full race incident reports.
    date_str format: 'YYYY/MM/DD' or 'YYYY-MM-DD' or 'YYYYMMDD'
    Returns: dict of race -> runners incident reports
    """
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
        logging.info(f"Fetching HKJC Incident Report from {url}...")
        resp = requests.get(url, headers=headers, timeout=12)
        if resp.status_code != 200:
            logging.warning(f"Failed to fetch HKJC Incident Report (Status {resp.status_code}) for {date_str}")
            return {}

        soup = BeautifulSoup(resp.content, "html.parser")
        meeting_incidents = {}
        
        # Look for incident report tables / paragraphs
        for table in soup.find_all("table"):
            for tr in table.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) >= 2:
                    h_text = tds[0].get_text(strip=True)
                    inc_text = tds[1].get_text(strip=True)
                    if len(inc_text) > 10 and h_text:
                        meeting_incidents[h_text] = inc_text
            
        logging.info(f"Parsed {len(meeting_incidents)} incident records from HKJC report.")
        return meeting_incidents
    except Exception as e:
        logging.warning(f"Error scraping HKJC incident report for {date_str}: {e}")
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
        except Exception:
            pass
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
    logging.info("Building / Updating Tactical Incident Memory Bank...")
    memory = load_horse_memory() if not force_rebuild else {}

    # 1. Initialize from latest_horse_stats.csv
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

    # 2. Ingest comments from comments.csv
    comments_dict = {}
    if os.path.exists('data/comments.csv'):
        try:
            cdf = pd.read_csv('data/comments.csv')
            for _, r in cdf.iterrows():
                h_name = str(r.get('horse_name', '')).strip().upper()
                c_text = str(r.get('comment', ''))
                if h_name:
                    comments_dict[h_name] = c_text
        except Exception as e:
            logging.warning(f"Error loading comments.csv: {e}")

    # 3. Ingest scraped results files (e.g. 20261001)
    for res_file in sorted(glob.glob('data/scraped_results_*.json')):
        date_match = re.search(r'(\d{8})', res_file)
        r_date = date_match.group(1) if date_match else "20261001"
        formatted_date = f"{r_date[:4]}-{r_date[4:6]}-{r_date[6:]}"
        try:
            with open(res_file, 'r', encoding='utf-8') as f:
                res_data = json.load(f)
                for r_num, runners in res_data.items():
                    for r in runners:
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
                            except:
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
                            memory[key]['runs'] = runs_list[:6]
        except Exception as e:
            logging.warning(f"Error parsing {res_file}: {e}")

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
    logging.info(f"Memory Bank successfully built with {len(memory)} active horse keys.")
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

    # 1. FORGIVEN RUN
    last_interf = last_run.get('interference_severity', 0)
    last_sp = last_run.get('sp', 99.0)
    last_lbw = last_run.get('beaten_lengths', 99.0)
    has_vet = any(f.get('vet_blocked', False) for f in last_run.get('incident_flags', []))

    if last_interf >= 2 and (last_sp < 8.0 or last_sp <= 10.0) and last_lbw <= 1.5 and not has_vet:
        scores['forgiven_run'] = seeds.get('forgiven_run', 2.5)
        snippet = next((f['snippet'] for f in last_run.get('incident_flags', []) if f['flag'] == 'traffic_trouble'), "Held up late")
        badges.append({
            'type': 'credit',
            'badge': '🎯 UNLUCKY RUNNER',
            'text': f"Blocked in straight ({snippet[:40]}); beaten only {last_lbw}L"
        })
    elif last_interf >= 2 and last_lbw <= 3.0 and not has_vet:
        badges.append({
            'type': 'credit',
            'badge': '🎯 PLACE LEAN',
            'text': f"Suffered interference; finished within {last_lbw}L"
        })

    # 2. TRIP REGRESSION
    last_finish = last_run.get('finish_pos', 99)
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

    # Live adjustment (Defaults to 0.0 unless apply_tactical_overlay is True)
    if apply_overlay:
        live_adj = sum([
            (scores['forgiven_run'] / seeds.get('forgiven_run', 2.5)) * live_coeffs.get('forgiven_run', 0.0) if seeds.get('forgiven_run') else 0.0,
            (scores['trip_regression'] / seeds.get('trip_regression', -2.0)) * live_coeffs.get('trip_regression', 0.0) if seeds.get('trip_regression') else 0.0,
            (scores['sectional_eye_catcher'] / seeds.get('sectional_eye_catcher', 2.0)) * live_coeffs.get('sectional_eye_catcher', 0.0) if seeds.get('sectional_eye_catcher') else 0.0
        ])
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

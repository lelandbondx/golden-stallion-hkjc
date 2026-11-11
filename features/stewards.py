"""
Silks.AI Stewards and Veterinary Intelligence Module.
Strict separation between Tactical Trip Excuses (unlucky trips) and Medical Health Risks.
"""

import re
import pandas as pd

# Phrases that indicate an unimpeded, clean run
CLEAN_PHRASES = [
    'without interruption', 'no interference', 'not checked', 
    'no incident', 'clear run throughout', 'without impediment',
    'clear run'
]

# Genuine tactical/racing excuses where the horse was an unlucky victim
TACTICAL_EXCUSE_KEYWORDS = [
    'badly checked', 'severely checked', 'checked', 'check ', 'crowded', 'hampered',
    'held up', 'no clear run', 'denied a clear run', 'pocketed', 'clipped heels', 'clip heels',
    'lost ground at start', 'slow to begin', 'stumbled', 'stumble', 'lost shoe', 'lost plate',
    'lost a plate', 'saddle slipped', 'forced wide', 'no room', 'blocked',
    'without cover', 'no cover', 'three wide', 'four wide', 'raced wide', 'wide without cover',
    'raced keenly', 'over-raced', 'unbalanced', 'stood awkwardly'
]

# Severe medical, physical, or respiratory unsoundness flags
HEALTH_RISK_KEYWORDS = [
    'blood in trachea', 'trachea', 'bleeder', 'bled', 'irregular heart', 'heart irregularity',
    'lame', 'lameness', 'mucus', 'substantial blood', 'roarer', 'epistaxis',
    'distress', 'substantial mucus', 'unacceptable', 'tailed out', 'abnormal'
]


def check_stewards_excuse(comment):
    """
    Returns True ONLY if the runner suffered legitimate tactical interference or racing bad luck.
    DOES NOT forgive medical, veterinary, or lameness issues!
    """
    if not comment or pd.isna(comment):
        return False
    c = str(comment).lower()

    # If explicit clean run phrase, no excuse
    if any(cp in c for cp in CLEAN_PHRASES):
        return False

    # Medical red flags override and invalidate tactical forgiveness
    if any(hr in c for hr in HEALTH_RISK_KEYWORDS):
        return False

    return any(kw in c for kw in TACTICAL_EXCUSE_KEYWORDS)


def _is_note_cleared_or_admin(latest_vet_note: str) -> bool:
    """Return True if a vet note has an explicit Passed date (DD/MM/YYYY) or is an administrative note."""
    if not latest_vet_note or pd.isna(latest_vet_note):
        return False
    txt = str(latest_vet_note).strip()
    if not txt or txt.lower() in ('no findings', 'none', 'nan', '✅ clear record'):
        return True
    try:
        from vet_records import extract_vet_attributes
        m_pass = re.search(r'\(Passed:\s*([^)]+)\)', txt, re.I)
        passed_val = m_pass.group(1).strip() if m_pass else '-'
        attrs = extract_vet_attributes(txt, passed_val)
        if attrs.get('status') in ('cleared', 'no_requirement'):
            return True
    except Exception:
        if re.search(r'Passed:\s*\d{1,2}/\d{1,2}/\d{2,4}', txt, re.I):
            return True
    return False


def check_health_risk(comment='', vet_status=0, latest_vet_note='', horse_name=None, steward_clearances=None):
    """
    Returns True if an active or recent medical unsoundness flag is detected.
    Includes bleeders, respiratory issues, lameness, heart irregularities, and roarers.
    Steward Bot acts as the final medical and integrity clearance gate.
    """
    # Final medical/integrity gate via Steward Bot
    if horse_name and steward_clearances and isinstance(steward_clearances, dict):
        c_name = str(horse_name).strip().upper()
        if c_name in steward_clearances:
            gate = steward_clearances[c_name]
            if isinstance(gate, dict):
                status = str(gate.get('status', '')).upper()
                cleared = gate.get('cleared')
                if cleared is False or status in ('BARRED', 'FAILED', 'UNFIT', 'NOT_CLEARED'):
                    return True
                if cleared is True or status in ('CLEARED', 'PASSED', 'FIT'):
                    return False

    if vet_status and vet_status != 0 and str(vet_status).lower() not in ('0', 'false', 'none', 'nan'):
        return True

    # If the vet note is explicitly cleared (Passed: DD/MM/YYYY) or administrative, only inspect stewards comment
    effective_vet_note = '' if _is_note_cleared_or_admin(latest_vet_note) else (latest_vet_note or '')
    combined = f"{comment or ''} {effective_vet_note}".lower()
    return any(hr in combined for hr in HEALTH_RISK_KEYWORDS)


def get_health_risk_severity(comment='', vet_status=0, latest_vet_note='', category=None, status=None):
    """
    Returns severity score (0 to 3) for medical risks using structured categories:
    3: bleeding_nostrils (bled from both nostrils / bled both nostrils), cardiac (irregular heart), airway (roarer / DDSP)
    2: tracheal_blood (blood/mucus in trachea), lameness, surgery, injury, failed_vet_exam, performance (unacceptable)
    1: Minor soreness / other active vet flag
    0: Clean / Cleared / Administrative (castration, age, unraced)
    """
    if status in ('cleared', 'no_requirement') and not comment:
        return 0

    note_str = str(latest_vet_note or '').strip()
    inferred_cat = category
    inferred_status = status
    if not inferred_cat and note_str and note_str.lower() not in ('no findings', 'none', 'nan', ''):
        try:
            from vet_records import extract_vet_attributes
            m_pass = re.search(r'\(Passed:\s*([^)]+)\)', note_str, re.I)
            passed_val = m_pass.group(1).strip() if m_pass else '-'
            attrs = extract_vet_attributes(note_str, passed_val)
            inferred_cat = attrs.get('category')
            if not inferred_status:
                inferred_status = attrs.get('status')
        except Exception:
            pass

    if inferred_status in ('cleared', 'no_requirement') and not (vet_status and str(vet_status) not in ('0', 'false', 'False', 'None', 'nan')):
        note_for_matching = ''
    else:
        note_for_matching = note_str

    combined = f"{comment or ''} {note_for_matching}".lower()

    if inferred_status not in ('cleared', 'no_requirement'):
        if inferred_cat in ('bleeding_nostrils', 'cardiac', 'airway'):
            return 3
        if inferred_cat in ('tracheal_blood', 'lameness', 'surgery', 'injury', 'failed_vet_exam', 'performance'):
            return 2
        if inferred_cat == 'administrative' and not comment:
            return 0

    if (
        'bled from both nostrils' in combined
        or 'bled both nostrils' in combined
        or 'irregular heart' in combined
        or 'heart irregularity' in combined
        or 'roarer' in combined
        or 'dorsal displacement' in combined
    ):
        return 3
    if (
        'blood in trachea' in combined
        or 'substantial blood' in combined
        or 'lame' in combined
        or 'arthroscop' in combined
        or 'surgery' in combined
        or 'unacceptable' in combined
    ):
        return 2
    if any(hr in combined for hr in HEALTH_RISK_KEYWORDS) or (vet_status and str(vet_status) not in ('0', 'false', 'False', 'None', 'nan')):
        return 1
    return 0

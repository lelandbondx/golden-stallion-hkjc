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


def check_health_risk(comment='', vet_status=0, latest_vet_note=''):
    """
    Returns True if an active or recent medical unsoundness flag is detected.
    Includes bleeders, respiratory issues, lameness, heart irregularities, and roarers.
    """
    if vet_status and vet_status != 0 and str(vet_status).lower() not in ('0', 'false', 'none', 'nan'):
        return True

    combined = f"{comment or ''} {latest_vet_note or ''}".lower()
    return any(hr in combined for hr in HEALTH_RISK_KEYWORDS)


def get_health_risk_severity(comment='', vet_status=0, latest_vet_note=''):
    """
    Returns severity score (0 to 3) for medical risks:
    3: Bleeder (both nostrils), heart irregularity, severe lameness, roarer
    2: Blood/mucus in trachea, moderate lameness, unacceptable performance
    1: Minor soreness / vet exam required
    0: Clean / No active health risk
    """
    combined = f"{comment or ''} {latest_vet_note or ''}".lower()
    if 'bled both nostrils' in combined or 'irregular heart' in combined or 'roarer' in combined:
        return 3
    if 'blood in trachea' in combined or 'lame' in combined or 'unacceptable' in combined:
        return 2
    if any(hr in combined for hr in HEALTH_RISK_KEYWORDS) or (vet_status and str(vet_status) != '0'):
        return 1
    return 0

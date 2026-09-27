import json
import os
import sys

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import pandas as pd
from scraper import get_live_meeting_data
from model import load_model

def main():
    data = get_live_meeting_data()
    if data.get('status') != 'success' or not data.get('meetings'):
        print("Failed to get live meeting data.")
        return
        
    meeting = data['meetings'][0]
    print(f"Checking meeting: {meeting['venue']} on {meeting['date']}")
    
    jockeys = set()
    trainers = set()
    for race in meeting.get('races', []):
        for runner in race.get('runners', []):
            if runner.get('jockey'):
                jockeys.add(runner.get('jockey').upper().strip())
            if runner.get('trainer'):
                trainers.add(runner.get('trainer').upper().strip())
                
    print(f"\nFound {len(jockeys)} unique jockeys today:")
    print(sorted(list(jockeys)))
    
    print(f"\nFound {len(trainers)} unique trainers today:")
    print(sorted(list(trainers)))

    # Check fallbacks in model.py
    FALLBACK_JOCKEY_RATES = {
        'Z PURTON': 0.25, 'H BOWMAN': 0.18, 'K TEETAN': 0.12, 'C Y HO': 0.11,
        'A BADEL': 0.10, 'L HEWITSON': 0.09, 'A ATZENI': 0.09, 'L FERRARIS': 0.08,
        'B AVDULLA': 0.08, 'E C W WONG': 0.09, 'M CHADWICK': 0.07, 'Y L CHUNG': 0.07,
        'C L CHAU': 0.07, 'H BENTLEY': 0.08, 'K C LEUNG': 0.07, 'M F POON': 0.06,
        'H T MO': 0.04, 'A HAMELIN': 0.06, 'M L YEUNG': 0.04, 'K DE MELO': 0.08,
        'J ORMAN': 0.10, 'E BROWN': 0.10, 'P N WONG': 0.05
    }
    
    FALLBACK_TRAINER_RATES = {
        'J SIZE': 0.15, 'P C NG': 0.13, 'F C LOR': 0.13, 'K W LUI': 0.12,
        'C S SHUM': 0.11, 'C FOWNES': 0.11, 'A S CRUZ': 0.10, 'P F YIU': 0.10,
        'D A HAYES': 0.10, 'M NEWNHAM': 0.10, 'D J WHYTE': 0.09, 'J RICHARDS': 0.08,
        'T P YUNG': 0.07, 'K L MAN': 0.08, 'W Y SO': 0.07, 'Y S TSUI': 0.05,
        'C W CHANG': 0.05, 'K H TING': 0.04, 'W K MO': 0.06, 'M NEWMAN': 0.10,
        'D EUSTACE': 0.11, 'B CRAWFORD': 0.08
    }

    # Load from csv if available
    db_jockeys = {}
    if os.path.exists('data/jockey_win_rates.csv'):
        df = pd.read_csv('data/jockey_win_rates.csv')
        df['jockey_clean'] = df['jockey'].str.upper().str.strip()
        db_jockeys = df.set_index('jockey_clean')['jockey_win_rate'].to_dict()
        
    db_trainers = {}
    if os.path.exists('data/trainer_win_rates.csv'):
        df = pd.read_csv('data/trainer_win_rates.csv')
        df['trainer_clean'] = df['trainer'].str.upper().str.strip()
        db_trainers = df.set_index('trainer_clean')['trainer_win_rate'].to_dict()

    print("\nJockeys not in CSV and not in fallback dict:")
    missing_jockeys = []
    for j in jockeys:
        if j not in db_jockeys and j not in FALLBACK_JOCKEY_RATES:
            print(f"  - {j} (using default 0.08)")
            missing_jockeys.append(j)
            
    print("\nTrainers not in CSV and not in fallback dict:")
    missing_trainers = []
    for t in trainers:
        if t not in db_trainers and t not in FALLBACK_TRAINER_RATES:
            print(f"  - {t} (using default 0.08)")
            missing_trainers.append(t)

if __name__ == '__main__':
    main()

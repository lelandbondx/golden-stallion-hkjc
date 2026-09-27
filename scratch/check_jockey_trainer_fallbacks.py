import json
import pandas as pd
import os

with open('data/last_scraped_meeting.json', 'r', encoding='utf-8') as f:
    meeting_data = json.load(f)

# Load jockey rates from CSV
if os.path.exists('data/jockey_win_rates.csv'):
    jockey_df = pd.read_csv('data/jockey_win_rates.csv')
    jockey_rates = dict(zip(jockey_df['jockey'].str.upper().str.strip(), jockey_df['jockey_win_rate']))
else:
    jockey_rates = {}

# Load trainer rates from CSV
if os.path.exists('data/trainer_win_rates.csv'):
    trainer_df = pd.read_csv('data/trainer_win_rates.csv')
    trainer_rates = dict(zip(trainer_df['trainer'].str.upper().str.strip(), trainer_df['trainer_win_rate']))
else:
    trainer_rates = {}

# Fallbacks from model.py
FALLBACK_JOCKEY_RATES = {
    'Z PURTON': 0.25, 'H BOWMAN': 0.18, 'K TEETAN': 0.12, 'C Y HO': 0.11,
    'A BADEL': 0.10, 'L HEWITSON': 0.09, 'A ATZENI': 0.09, 'L FERRARIS': 0.08,
    'B AVDULLA': 0.08, 'E C W WONG': 0.09, 'M CHADWICK': 0.07, 'Y L CHUNG': 0.07,
    'C L CHAU': 0.07, 'H BENTLEY': 0.08, 'K C LEUNG': 0.07, 'M F POON': 0.06,
    'H T MO': 0.04, 'A HAMELIN': 0.06, 'M L YEUNG': 0.04, 'K DE MELO': 0.08
}

FALLBACK_TRAINER_RATES = {
    'J SIZE': 0.15, 'P C NG': 0.13, 'F C LOR': 0.13, 'K W LUI': 0.12,
    'C S SHUM': 0.11, 'C FOWNES': 0.11, 'A S CRUZ': 0.10, 'P F YIU': 0.10,
    'D A HAYES': 0.10, 'M NEWNHAM': 0.10, 'D J WHYTE': 0.09, 'J RICHARDS': 0.08,
    'T P YUNG': 0.07, 'K L MAN': 0.08, 'W Y SO': 0.07, 'Y S TSUI': 0.05,
    'C W CHANG': 0.05, 'K H TING': 0.04, 'W K MO': 0.06, 'M NEWMAN': 0.10
}

jockey_infos = {}
trainer_infos = {}

for meeting in meeting_data.get('meetings', []):
    for race in meeting.get('races', []):
        for runner in race.get('runners', []):
            jockey = runner.get('jockey', '').upper().strip()
            trainer = runner.get('trainer', '').upper().strip()
            
            # Resolve jockey rate
            j_rate = jockey_rates.get(jockey)
            j_source = "CSV"
            if j_rate is None:
                j_rate = FALLBACK_JOCKEY_RATES.get(jockey)
                j_source = "Fallback Dict"
                if j_rate is None:
                    j_rate = 0.08
                    j_source = "Global Default (8%)"
            
            # Resolve trainer rate
            t_rate = trainer_rates.get(trainer)
            t_source = "CSV"
            if t_rate is None:
                t_rate = FALLBACK_TRAINER_RATES.get(trainer)
                t_source = "Fallback Dict"
                if t_rate is None:
                    t_rate = 0.08
                    t_source = "Global Default (8%)"
            
            jockey_infos[jockey] = (j_rate, j_source)
            trainer_infos[trainer] = (t_rate, t_source)

print("=== JOCKEY RESOLUTIONS ===")
for j, info in sorted(jockey_infos.items()):
    print(f"Jockey: {j:<25} Rate: {info[0]:.2f} (Source: {info[1]})")

print("\n=== TRAINER RESOLUTIONS ===")
for t, info in sorted(trainer_infos.items()):
    print(f"Trainer: {t:<25} Rate: {info[0]:.2f} (Source: {info[1]})")

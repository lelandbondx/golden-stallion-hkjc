import json
import pandas as pd
import numpy as np
import os
import sys

# Configure stdout to support UTF-8 emojis on Windows
if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

def generate():
    meeting_file = 'data/last_scraped_meeting.json'
    if not os.path.exists(meeting_file):
        print("Missing meeting data file.")
        return
        
    with open(meeting_file, 'r', encoding='utf-8') as f:
        meeting_data = json.load(f)
        
    meeting = meeting_data['meetings'][0]
    date_str = meeting.get('date', '2026-07-15')
    venue = meeting.get('venue', 'Happy Valley')
    going = meeting.get('going', 'GOOD')
    
    frozen_file = f"data/frozen_predictions_{date_str.replace('-', '')}.json"
    if not os.path.exists(frozen_file):
        print(f"Missing frozen predictions file: {frozen_file}")
        return
        
    with open(frozen_file, 'r', encoding='utf-8') as f:
        frozen_data = json.load(f)
    
    # Format Date
    try:
        dt = pd.to_datetime(date_str)
        formatted_date = dt.strftime('%B %d, %Y').upper()
    except:
        formatted_date = date_str.upper()
        
    report = f"*GOLDEN STALLION AI — {venue.upper()} ({formatted_date})*\n"
    report += f"Venue: {venue} | Track Going: {going}\n\n"
    
    races = meeting.get('races', [])
    for race in races:
        race_no = race.get('race_no')
        class_dist = race.get('class_dist', f'Race {race_no}')
        runners = race.get('runners', [])
        if not runners:
            continue
            
        # Get runner positions
        runner_pos = {}
        for r in runners:
            no = r.get('no')
            pos = r.get('final_position')
            if pos is not None:
                try:
                    runner_pos[no] = int(pos)
                except:
                    runner_pos[no] = 99
                    
        # Get frozen predictions
        key = f"{venue}_R{race_no}"
        predictions = frozen_data.get(key, [])
        if not predictions:
            key_alt = f"Sha Tin_R{race_no}"
            predictions = frozen_data.get(key_alt, [])
            
        if not predictions:
            continue
            
        df_pred = pd.DataFrame(predictions).sort_values(by='gs_score', ascending=False).reset_index(drop=True)
        
        report += f"*RACE {race_no} ({class_dist})*\n"
        
        emojis = {1: "🥇 1st Pick", 2: "🥈 2st Pick", 3: "🥉 3st Pick", 4: "🔹 4st Pick", 5: "🔹 5st Pick"}
        
        for idx in range(min(5, len(df_pred))):
            row = df_pred.iloc[idx]
            no = int(row['no'])
            name = row['name']
            odds = float(row['scraped_win_odds']) if 'scraped_win_odds' in row else float(row['win_odds'])
            conf = int(row['confidence']) if 'confidence' in row else 85
            jockey = row['jockey']
            
            pos = runner_pos.get(no, 99)
            
            outcome_str = ""
            if pos == 1:
                outcome_str = " 🏆 *[WINNER]*"
            elif pos == 2:
                outcome_str = " 🥈 *[2nd]*"
            elif pos == 3:
                outcome_str = " 🥉 *[3rd]*"
            elif pos < 99:
                outcome_str = f" *(Finished {pos})*"
            else:
                outcome_str = " *(Finished NP)*"
                
            prefix = emojis.get(idx + 1, "🔹")
            report += f"{prefix}: #{no} {name} (Odds: {odds:.1f}) - Conf: {conf}% - Jockey: {jockey}{outcome_str}\n"
            
        report += "\n"
        
    print(report)
    
    # Save report
    with open('whatsapp_report.txt', 'w', encoding='utf-8') as f:
        f.write(report)
    print("Report saved to whatsapp_report.txt")

if __name__ == '__main__':
    generate()

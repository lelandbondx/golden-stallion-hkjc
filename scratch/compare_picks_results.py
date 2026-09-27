import os
import json

def main():
    filename = 'data/frozen_predictions_20260621.json'
    if not os.path.exists(filename):
        print(f"File {filename} does not exist. No frozen predictions recorded locally.")
        # Check if there is another file
        files = [f for f in os.listdir('data') if 'frozen' in f]
        print("Available frozen files:", files)
        return

    with open(filename, 'r', encoding='utf-8') as f:
        frozen = json.load(f)

    print("Frozen predictions keys (Races):", list(frozen.keys()))
    
    # Load last scraped meeting to compare results
    with open('data/last_scraped_meeting.json', 'r', encoding='utf-8') as f:
        meeting_data = json.load(f)
    
    meeting = meeting_data['meetings'][0]
    races_dict = {r.get('race_no'): r for r in meeting.get('races', [])}
    
    for r_key, runners in frozen.items():
        # r_key is like "Sha Tin_R1"
        parts = r_key.split('_R')
        if len(parts) < 2:
            continue
        race_no = int(parts[1])
        
        # Sort frozen runners by gs_score descending
        runners_sorted = sorted(runners, key=lambda x: x.get('gs_score', 0), reverse=True)
        print(f"\n--- Race {race_no} (Frozen Selections) ---")
        
        # Get actual results for this race
        actual_race = races_dict.get(race_no, {})
        actual_runners = {r.get('no'): r for r in actual_race.get('runners', [])}
        
        for i in range(min(5, len(runners_sorted))):
            runner = runners_sorted[i]
            no = runner.get('no')
            name = runner.get('name')
            odds = runner.get('win_odds')
            conf = runner.get('confidence')
            ev = runner.get('value_diff')
            jockey = runner.get('jockey')
            
            # Actual final position
            actual_pos = actual_runners.get(no, {}).get('final_position', 'Unknown')
            actual_odds = actual_runners.get(no, {}).get('win_odds', odds)
            
            print(f"  {i+1}st Pick: #{no} {name} (Odds: {odds:.1f} -> Actual: {actual_odds:.1f}) - Conf: {conf}% - EV: {ev:.3f} - Jockey: {jockey} - Actual Position: {actual_pos}")

if __name__ == '__main__':
    main()

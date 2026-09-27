import json
import os
import pandas as pd

# Configure stdout to support UTF-8 emojis on Windows
import sys
if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

files = [f for f in os.listdir('data') if f.startswith('frozen_predictions_') and f.endswith('.json')]

for fn in sorted(files):
    date_part = fn.replace("frozen_predictions_", "").replace(".json", "")
    date_str = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
    
    with open(os.path.join('data', fn), 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    print(f"\n==========================================")
    print(f"MEETING: {date_str}")
    print(f"==========================================")
    
    for r_key, runners in data.items():
        if not runners:
            continue
            
        df = pd.DataFrame(runners).sort_values(by='gs_score', ascending=False).reset_index(drop=True)
        if 1 not in df['final_position'].values:
            continue
            
        race_no = r_key.split("_R")[1]
        
        # Get winner
        winner_row = df[df['final_position'] == 1].iloc[0]
        winner_name = winner_row.get('name')
        winner_no = winner_row.get('no')
        winner_odds = winner_row.get('win_odds')
        
        # Get our picks rank of the winner
        winner_rank = df[df['final_position'] == 1].index[0] + 1
        
        # Check if we hit the Quinella (1st and 2nd in our top 5)
        top5 = df.iloc[:5]
        q_hit = (1 in top5['final_position'].values) and (2 in top5['final_position'].values)
        q_str = " | 🎯 QUINELLA HIT!" if q_hit else ""
        
        if winner_rank <= 5:
            print(f"  Race {race_no}: Hitted Winner! #{winner_no} {winner_name} (Odds: {winner_odds}) - Rank: {winner_rank}{q_str}")
        else:
            print(f"  Race {race_no}: Missed Winner. #{winner_no} {winner_name} (Odds: {winner_odds}) - Rank: {winner_rank}{q_str}")

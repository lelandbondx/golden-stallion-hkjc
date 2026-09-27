import subprocess
import json
import pandas as pd

try:
    content = subprocess.check_output(
        ["git", "show", "origin/main:data/frozen_predictions_20260715.json"],
        cwd="c:\\Users\\lelan\\Desktop\\golden-stallion-hkjc"
    ).decode('utf-8')
    
    data = json.loads(content)
    
    for r_key in sorted(data.keys()):
        print(f"\n--- {r_key} (Remote origin/main) ---")
        df = pd.DataFrame(data[r_key])
        if 'gs_score' in df.columns:
            df = df.sort_values(by='gs_score', ascending=False)
            for idx in range(min(5, len(df))):
                row = df.iloc[idx]
                print(f"  {idx+1}. #{row.get('no')} {row.get('name')} (Odds: {row.get('win_odds')}) - GS Score: {row.get('gs_score')}")
        else:
            print("No gs_score column!")
except Exception as e:
    print("Error:", e)

import json
import pandas as pd

try:
    with open('data/frozen_predictions_20260715.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    r8_runners = data.get("Happy Valley_R8", [])
    df = pd.DataFrame(r8_runners)
    
    for idx, row in df.iterrows():
        if row.get('name') in ['BOTTOMUPTOGETHER', 'CRIMSON FLASH']:
            print(f"\nHorse: {row.get('name')}")
            print(f"  model_prob: {row.get('model_prob'):.4f}")
            print(f"  baseline_odds: {row.get('baseline_odds')}")
            print(f"  win_odds: {row.get('win_odds')}")
            print(f"  shift_bonus: {row.get('shift_bonus')}")
            print(f"  gs_score: {row.get('gs_score'):.4f}")
except Exception as e:
    print("Error:", e)

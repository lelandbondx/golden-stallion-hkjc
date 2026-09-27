import json
import pandas as pd

try:
    with open('data/frozen_predictions_20260715.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    r6_runners = data.get("Happy Valley_R6", [])
    df = pd.DataFrame(r6_runners)
    df = df.sort_values(by='gs_score', ascending=False)
    
    print("Race 6 Runners Ranked by GS Score:")
    for idx, row in df.iterrows():
        print(f"  #{row.get('no')} {row.get('name')} | Jockey: {row.get('jockey')} | Trainer: {row.get('trainer')} | Odds: {row.get('win_odds')} | Model Prob: {row.get('model_prob'):.4f} | Consensus: {row.get('consensus_score')} | GS Score: {row.get('gs_score'):.4f}")
except Exception as e:
    print("Error:", e)

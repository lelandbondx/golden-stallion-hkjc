import json

with open('data/frozen_predictions_20260927.json', 'r', encoding='utf-8') as f:
    preds = json.load(f)

print(f"Frozen predictions races count: {len(preds)}")
for r_key, runners in preds.items():
    sorted_runners = sorted(runners, key=lambda x: x.get('model_prob', 0), reverse=True)
    top = sorted_runners[0]
    print(f"{r_key}: {len(runners)} runners. Top Pick: #{top.get('no')} {top.get('name')} (J: {top.get('jockey')}, T: {top.get('trainer')}) | Conf: {top.get('confidence')}% | Odds: {top.get('win_odds')}")

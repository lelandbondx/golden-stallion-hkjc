import json

with open('data/frozen_predictions_20260927.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

r1 = d['Sha Tin_R1']
print("Keys in runner:", list(r1[0].keys()))
for r in r1:
    print(f"#{r.get('no')} {r.get('name')} | model_prob: {r.get('model_prob')} | win_prob: {r.get('win_prob')} | rank: {r.get('rank')} | conf: {r.get('confidence')}% | EV: {r.get('ev')}")

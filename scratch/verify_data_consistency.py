import json

with open('data/detailed_picks.json', 'r', encoding='utf-8') as f:
    picks = json.load(f)

print(f"Detailed picks count: {len(picks)}")
for p in picks:
    print(f"R{p.get('race_no')} #{p.get('no')} {p.get('name')} | Jockey: {p.get('jockey')} | Odds: {p.get('win_odds')} | Conf: {p.get('confidence')}% | EV: {p.get('value_diff'):.3f}")

with open('data/frozen_predictions_20260927.json', 'r', encoding='utf-8') as f:
    preds = json.load(f)

print(f"\nFrozen predictions races: {len(preds)}")
for r_key, runners in preds.items():
    print(f"{r_key}: {len(runners)} runners loaded.")

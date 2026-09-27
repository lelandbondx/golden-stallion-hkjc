import json

with open('data/frozen_predictions_20260927.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

for r_key, runners in d.items():
    # Sort runners by model_prob descending
    sorted_runners = sorted(runners, key=lambda x: x.get('model_prob', 0), reverse=True)
    print(f"\n==================== {r_key} ====================")
    for rank, r in enumerate(sorted_runners[:4], 1):
        odds = r.get('win_odds', 0)
        prob = r.get('model_prob', 0)
        ev = (prob * odds) - 1 if odds else 0
        print(f"Rank {rank}: #{r.get('no')} {r.get('name')} (Jockey: {r.get('jockey')}, Draw: {r.get('draw')}, Wgt: {r.get('actual_weight')} lbs, Rtg: {r.get('horse_rating')}) | Prob: {prob*100:.1f}% | Odds: {odds} | Conf: {r.get('confidence')}% | EV: {ev:+.3f}")

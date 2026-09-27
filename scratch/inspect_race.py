import json

with open('data/frozen_predictions_20260624.json', 'r', encoding='utf-8') as f:
    preds = json.load(f)

r2_preds = preds.get('Happy Valley_R2', [])
if isinstance(r2_preds, list):
    # Sort by model_prob descending
    by_prob = sorted(r2_preds, key=lambda x: x.get('model_prob', 0), reverse=True)
    print("=== RACE 2 SORTED BY MODEL PROBABILITY ===")
    for idx, p in enumerate(by_prob):
        name = p.get('name', 'Unknown')
        num = p.get('no', 'Unknown')
        prob = p.get('model_prob', 0)
        odds = p.get('win_odds', 0)
        ev = p.get('value_diff', 0)
        conf = p.get('confidence', 0)
        print(f"{idx+1}. #{num} {name} - Prob: {prob:.4f}, Odds: {odds}, EV: {ev:.3f}, Conf: {conf}%")

    # Sort by value_diff descending
    by_ev = sorted(r2_preds, key=lambda x: x.get('value_diff', -99), reverse=True)
    print("\n=== RACE 2 SORTED BY EXPECTED VALUE (value_diff) ===")
    for idx, p in enumerate(by_ev):
        name = p.get('name', 'Unknown')
        num = p.get('no', 'Unknown')
        prob = p.get('model_prob', 0)
        odds = p.get('win_odds', 0)
        ev = p.get('value_diff', 0)
        conf = p.get('confidence', 0)
        print(f"{idx+1}. #{num} {name} - EV: {ev:.3f}, Prob: {prob:.4f}, Odds: {odds}, Conf: {conf}%")

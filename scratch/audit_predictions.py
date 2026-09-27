import os, sys, json

pred_file = "data/frozen_predictions_20260927.json"
if not os.path.exists(pred_file):
    print("No predictions file found.")
    sys.exit(0)

with open(pred_file, "r", encoding="utf-8") as f:
    races_dict = json.load(f)

print(f"=== FULL AUDIT OF SHA TIN 2026-09-27 PREDICTIONS ({len(races_dict)} RACES) ===")
for r_key, runners in races_dict.items():
    top1 = runners[0] if len(runners) > 0 else {}
    top2 = runners[1] if len(runners) > 1 else {}
    top3 = runners[2] if len(runners) > 2 else {}
    
    print(f"\n--- {r_key} ---")
    print(f"  [1] Rank 1: #{top1.get('no')} {top1.get('name')} (Jockey: {top1.get('jockey')}, Draw: {top1.get('draw')}, Weight: {top1.get('actual_weight')} lbs, Rating: {top1.get('horse_rating')}) | Prob: {top1.get('win_prob', 0)*100:.1f}%, Conf: {top1.get('confidence')}%, Odds: {top1.get('win_odds')}")
    print(f"  [2] Rank 2: #{top2.get('no')} {top2.get('name')} (Jockey: {top2.get('jockey')}, Draw: {top2.get('draw')}, Weight: {top2.get('actual_weight')} lbs, Rating: {top2.get('horse_rating')}) | Prob: {top2.get('win_prob', 0)*100:.1f}%, Conf: {top2.get('confidence')}%, Odds: {top2.get('win_odds')}")
    print(f"  [3] Rank 3: #{top3.get('no')} {top3.get('name')} (Jockey: {top3.get('jockey')}, Draw: {top3.get('draw')}, Weight: {top3.get('actual_weight')} lbs, Rating: {top3.get('horse_rating')}) | Prob: {top3.get('win_prob', 0)*100:.1f}%, Conf: {top3.get('confidence')}%, Odds: {top3.get('win_odds')}")

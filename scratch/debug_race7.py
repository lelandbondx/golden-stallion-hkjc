import json

with open('data/frozen_predictions_20260610.json', 'r') as f:
    data = json.load(f)

print("Keys in frozen_predictions:", list(data.keys()))
for race_key in sorted(data.keys()):
    r_list = data.get(race_key, [])
    print(f"\n{race_key} runners (sorted by gs_score):")
    sorted_runners = sorted(r_list, key=lambda x: x.get('gs_score', 0), reverse=True)
    for i, r in enumerate(sorted_runners):
        print(f"  Rank {i+1}: #{r['no']} {r['name']} - GS: {r.get('gs_score'):.2f}, Odds: {r.get('win_odds')}, EV: {r.get('value_diff'):.4f}, Final Pos: {r.get('final_position')}")

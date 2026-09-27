import json
import os

files = [f for f in os.listdir('data') if f.startswith('frozen_predictions_') and f.endswith('.json')]
for fn in sorted(files):
    with open(os.path.join('data', fn), 'r', encoding='utf-8') as f:
        data = json.load(f)
    first_race = list(data.keys())[0]
    runners = data[first_race]
    positions = [r.get('final_position') for r in runners if r.get('final_position') is not None]
    print(f"{fn}: {len(runners)} runners, positions found: {positions}")

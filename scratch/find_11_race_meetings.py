import os
import json

# Find baseline odds files
files = [f for f in os.listdir('data') if f.startswith('baseline_odds_') and f.endswith('.json')]

print("Baseline odds files and their race counts:")
for fn in sorted(files):
    filepath = os.path.join('data', fn)
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    # Keys format is "Happy Valley_R1_H1" or "Sha Tin_R1_H1"
    # Let's extract distinct races
    races = set()
    for k in data.keys():
        try:
            parts = k.split("_")
            race_part = parts[1] # "R1"
            races.add(race_part)
        except:
            pass
            
    print(f"  {fn}: {len(races)} races ({sorted(list(races))})")

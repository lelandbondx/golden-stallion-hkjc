import os
import glob
import json

print("Checking all prediction/picks files...")
files = glob.glob("*.txt") + glob.glob("*.json") + glob.glob("data/*.txt") + glob.glob("data/*.json")
for f in files:
    if "predictions" in f.lower() or "picks" in f.lower() or "preds" in f.lower():
        print(f"File: {f}, size: {os.path.getsize(f)} bytes")
        # Let's inspect content briefly if text, or check JSON keys
        if f.endswith('.json'):
            try:
                with open(f, 'r', encoding='utf-8') as jsf:
                    data = json.load(jsf)
                    if isinstance(data, dict):
                        print(f"  Keys: {list(data.keys())[:5]}")
                        # Check if 'Happy Valley_R2' or 'HV_R2' exists
                        for k in data.keys():
                            if 'R2' in k:
                                print(f"  Found R2 key: {k}")
            except Exception as e:
                print(f"  Error reading json {f}: {e}")
        else:
            # print first 3 lines
            try:
                with open(f, 'r', encoding='utf-8', errors='ignore') as txtf:
                    lines = [txtf.readline().strip() for _ in range(5)]
                    print(f"  First lines: {lines}")
            except Exception as e:
                print(f"  Error reading txt {f}: {e}")

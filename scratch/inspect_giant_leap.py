import json
import pandas as pd

try:
    with open('data/frozen_predictions_20260715.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    r6_runners = data.get("Happy Valley_R6", [])
    df = pd.DataFrame(r6_runners)
    
    # Find GIANT LEAP
    gl = df[df['name'].str.upper().str.strip() == 'GIANT LEAP']
    if not gl.empty:
        gl_row = gl.iloc[0].to_dict()
        print("GIANT LEAP properties:")
        for k, v in gl_row.items():
            if v not in [None, '', '-'] and not isinstance(v, list):
                print(f"  {k}: {v}")
    else:
        print("GIANT LEAP not found in Race 6!")
except Exception as e:
    print("Error:", e)

import subprocess
import json

try:
    # Run git show to get the file contents from origin/main
    content = subprocess.check_output(
        ["git", "show", "origin/main:data/frozen_predictions_20260715.json"],
        cwd="c:\\Users\\lelan\\Desktop\\golden-stallion-hkjc"
    ).decode('utf-8')
    
    data = json.loads(content)
    # Print keys
    print("Races in origin/main predictions:")
    for k in sorted(data.keys()):
        print(f"  {k}: {len(data[k])} runners")
        
    # Check SOMELOVEFROMABOVE in Race 7
    r7_runners = data.get("Happy Valley_R7", [])
    for r in r7_runners:
        if r.get("name") == "SOMELOVEFROMABOVE":
            print("\nSOMELOVEFROMABOVE details on remote (origin/main):")
            print(f"  win_odds: {r.get('win_odds')}")
            print(f"  scraped_win_odds: {r.get('scraped_win_odds')}")
            print(f"  gs_score: {r.get('gs_score')}")
            
    # Check SETANTA in Race 1
    r1_runners = data.get("Happy Valley_R1", [])
    for r in r1_runners:
        if r.get("name") == "SETANTA":
            print("\nSETANTA details on remote (origin/main):")
            print(f"  win_odds: {r.get('win_odds')}")
            print(f"  scraped_win_odds: {r.get('scraped_win_odds')}")
            print(f"  gs_score: {r.get('gs_score')}")
except Exception as e:
    print("Error:", e)

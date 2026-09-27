import requests
import re

url = "https://racing.hkjc.com/racing/english/tipsindex/tips_index.asp?RaceNo=1"
headers = {"User-Agent": "Mozilla/5.0"}

try:
    res = requests.get(url, headers=headers, timeout=10)
    html = res.text
    
    # Find EVER WEALTH or SPICE BAG
    match = re.search(r'SPICE BAG', html)
    if match:
        start = max(0, match.start() - 500)
        end = min(len(html), match.end() + 1500)
        print("HTML snippet around 'SPICE BAG':")
        print(html[start:end])
    else:
        print("Could not find SPICE BAG in the raw HTML. Printing first 2000 chars of body...")
        body_start = html.find('<body')
        if body_start != -1:
            print(html[body_start:body_start+2000])
        else:
            print(html[:2000])
            
except Exception as e:
    print("Error:", e)

import requests
import re

url = "https://racing.hkjc.com/racing/english/tipsindex/tips_index.asp?RaceNo=1"
headers = {"User-Agent": "Mozilla/5.0"}

try:
    res = requests.get(url, headers=headers, timeout=10)
    html = res.text
    
    match = re.search(r'SPICE BAG', html)
    if match:
        start = max(0, match.start() - 1500)
        end = min(len(html), match.end() + 200)
        print("HTML snippet before 'SPICE BAG':")
        print(html[start:end])
            
except Exception as e:
    print("Error:", e)

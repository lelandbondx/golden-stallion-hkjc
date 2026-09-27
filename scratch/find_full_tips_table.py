import requests
from bs4 import BeautifulSoup
import re

url = "https://racing.hkjc.com/racing/english/tipsindex/tips_index.asp?RaceNo=1"
headers = {"User-Agent": "Mozilla/5.0"}

try:
    res = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(res.content, 'html.parser')
    
    tables = soup.find_all('table')
    print("Found total tables:", len(tables))
    
    for idx, t in enumerate(tables):
        text = t.get_text().lower()
        if "tips index" in text or "tips_index" in text:
            print(f"\n--- Found potential table (Index: {idx}) containing 'tips index' ---")
            rows = t.find_all('tr')
            print(f"Table has {len(rows)} rows.")
            
            # Print the first 5 rows to inspect
            for r_idx, row in enumerate(rows[:10]):
                cells = row.find_all(['td', 'th'])
                cell_texts = [c.get_text(strip=True) for c in cells]
                # Only print if we have elements and it's not super long
                if cell_texts and len(str(cell_texts)) < 500:
                    print(f"Row {r_idx}: {cell_texts}")
                elif cell_texts:
                    print(f"Row {r_idx} is too long ({len(str(cell_texts))} chars)")
                
except Exception as e:
    print("Error:", e)

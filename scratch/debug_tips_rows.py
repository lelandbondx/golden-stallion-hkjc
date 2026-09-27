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
    
    count = 0
    for idx, t in enumerate(tables):
        rows = t.find_all('tr')
        for r_idx, row in enumerate(rows):
            cells = row.find_all('td')
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True)
                val = cells[1].get_text(strip=True)
                label_norm = re.sub(r'\s+', ' ', label).lower()
                val_norm = re.sub(r'\s+', ' ', val).lower()
                if 'horse' in label_norm or 'tips' in label_norm:
                    print(f"Table {idx} Row {r_idx}: Label={repr(label_norm)} | Val={repr(val_norm)}")
                    count += 1
                    if count >= 30:
                        break
        if count >= 30:
            break
            
except Exception as e:
    print("Error:", e)

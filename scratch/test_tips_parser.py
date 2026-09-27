import requests
from bs4 import BeautifulSoup
import re

def parse_tips_for_race(race_no):
    url = f"https://racing.hkjc.com/racing/english/tipsindex/tips_index.asp?RaceNo={race_no}"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.content, 'html.parser')
        
        race_tips = {}
        tables = soup.find_all('table')
        
        for t in tables:
            rows = t.find_all('tr')
            horse_no = None
            tips_idx = None
            
            for row in rows:
                cells = row.find_all('td')
                if len(cells) < 2:
                    continue
                
                label = cells[0].get_text(strip=True)
                val = cells[1].get_text(strip=True)
                
                # Strip all spaces for robust matching
                label_norm = re.sub(r'\s+', '', label).lower()
                
                if 'horsenumber' in label_norm:
                    m = re.search(r'\d+', val)
                    if m:
                        horse_no = int(m.group(0))
                elif 'tipsindex' in label_norm:
                    val_clean = re.sub(r'[^\d\.]', '', val)
                    try:
                        tips_idx = float(val_clean)
                    except ValueError:
                        pass
                        
            if horse_no is not None and tips_idx is not None:
                race_tips[horse_no] = tips_idx
                
        return race_tips
    except Exception as e:
        print(f"Error parsing race {race_no}:", e)
        return {}

def test():
    for r in range(1, 4):
        tips = parse_tips_for_race(r)
        print(f"Race {r} Tips Index mapping:")
        print(tips)

if __name__ == "__main__":
    test()

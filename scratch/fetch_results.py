import requests
from bs4 import BeautifulSoup
import re
import urllib3
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# The correct HKJC results URL uses DD/MM/YYYY format for RaceDate
date_str = "24/06/2026"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

results = {}

for r_no in range(1, 10):
    url = f"https://racing.hkjc.com/racing/information/English/Racing/LocalResults.aspx?RaceDate={date_str}&RaceNo={r_no}"
    try:
        print(f"Fetching Race {r_no} from: {url}")
        res = requests.get(url, headers=headers, verify=False, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.content, 'html.parser')
            
            # The performance table contains results
            table = soup.find('table', class_='performance')
            if not table:
                # Sometimes class name might be different or multiple tables, let's find any table with a header containing 'Plc' or 'Horse'
                for t in soup.find_all('table'):
                    txt = t.get_text().lower()
                    if 'plc' in txt and 'horse' in txt and 'jockey' in txt:
                        table = t
                        break
            
            if table:
                rows = table.find_all('tr')
                finishers = []
                for row in rows[1:]: # skip header
                    cells = [c.get_text(strip=True) for c in row.find_all('td')]
                    if len(cells) >= 3:
                        plc = cells[0]
                        horse_no = cells[1]
                        horse_name = cells[2]
                        # Remove jockey, trainer weight etc if we want, or keep first few
                        finishers.append({
                            "plc": plc,
                            "horse_no": horse_no,
                            "horse_name": horse_name
                        })
                results[r_no] = finishers
                print(f"  Successfully parsed Race {r_no}. Winner: #{finishers[0]['horse_no']} {finishers[0]['horse_name']}")
            else:
                print(f"  Could not find results table for Race {r_no}")
        else:
            print(f"  HTTP error {res.status_code} for Race {r_no}")
    except Exception as e:
        print(f"  Error for Race {r_no}: {e}")

# Save the parsed results
with open('scratch/scraped_results_20260624.json', 'w') as f:
    json.dump(results, f, indent=4)
print("Saved all results to scratch/scraped_results_20260624.json")

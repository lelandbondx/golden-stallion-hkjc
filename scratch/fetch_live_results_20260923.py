import requests
from bs4 import BeautifulSoup
import re
import urllib3
import json
import sys

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

date_str = "2026/09/23"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

results = {}

for r_no in range(1, 10):
    url = f"https://racing.hkjc.com/racing/information/English/Racing/LocalResults.aspx?RaceDate={date_str}&RaceNo={r_no}"
    try:
        res = requests.get(url, headers=headers, verify=False, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.content, 'html.parser')
            
            # Find the performance table containing results
            table = soup.find('table', class_='performance')
            if not table:
                for t in soup.find_all('table'):
                    txt = t.get_text().lower()
                    if 'plc' in txt and 'horse' in txt and 'jockey' in txt:
                        table = t
                        break
            
            if table:
                rows = table.find_all('tr')
                finishers = []
                for row in rows[1:]:
                    cells = [c.get_text(strip=True) for c in row.find_all('td')]
                    if len(cells) >= 3:
                        plc = cells[0]
                        horse_no = cells[1]
                        horse_name = cells[2]
                        jockey = cells[3] if len(cells) > 3 else ""
                        trainer = cells[4] if len(cells) > 4 else ""
                        act_wt = cells[5] if len(cells) > 5 else ""
                        dec_wt = cells[6] if len(cells) > 6 else ""
                        draw = cells[7] if len(cells) > 7 else ""
                        finish_time = cells[10] if len(cells) > 10 else ""
                        win_odds = cells[11] if len(cells) > 11 else ""
                        finishers.append({
                            "plc": plc,
                            "horse_no": horse_no,
                            "horse_name": horse_name,
                            "jockey": jockey,
                            "trainer": trainer,
                            "act_wt": act_wt,
                            "draw": draw,
                            "finish_time": finish_time,
                            "win_odds": win_odds
                        })
                
                # Also parse dividends if present
                div_table = soup.find('table', class_='dividend') or soup.find('table', attrs={'summary': re.compile(r'dividend', re.I)})
                dividends = {}
                if div_table:
                    for drow in div_table.find_all('tr'):
                        dcells = [dc.get_text(strip=True) for dc in drow.find_all('td')]
                        if len(dcells) >= 3:
                            pool = dcells[0]
                            comb = dcells[1]
                            div = dcells[2]
                            dividends[pool] = dividends.get(pool, []) + [{"combination": comb, "dividend": div}]

                results[str(r_no)] = {
                    "finishers": finishers,
                    "dividends": dividends
                }
                if finishers:
                    print(f"✅ Race {r_no} parsed: 1st #{finishers[0]['horse_no']} {finishers[0]['horse_name']} (Odds: {finishers[0]['win_odds']}), 2nd #{finishers[1]['horse_no'] if len(finishers)>1 else 'N/A'}, 3rd #{finishers[2]['horse_no'] if len(finishers)>2 else 'N/A'}, 4th #{finishers[3]['horse_no'] if len(finishers)>3 else 'N/A'}")
            else:
                print(f"⏳ Race {r_no}: Results table not yet available (race not yet run or finalized).")
        else:
            print(f"⚠️ Race {r_no}: HTTP {res.status_code}")
    except Exception as e:
        print(f"❌ Error for Race {r_no}: {e}")

with open('data/scraped_results_20260923.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=4)
print("\nSaved scraped results to data/scraped_results_20260923.json")

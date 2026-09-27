import os
import json
import requests
from bs4 import BeautifulSoup
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import time

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def scrape_meeting_results_from_html(date_str):
    hkjc_date = date_str.replace("-", "/")
    print(f"\nScraping results for {date_str}...")
    
    results = {}
    
    for race_no in range(1, 13):
        url = f"https://racing.hkjc.com/racing/information/English/Racing/LocalResults.aspx?RaceDate={hkjc_date}&RaceNo={race_no}"
        
        # Retry up to 3 times
        success = False
        for attempt in range(1, 4):
            try:
                res = requests.get(url, headers=headers, timeout=12, verify=False)
                if res.status_code == 404:
                    # Normal end of card
                    break
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, 'html.parser')
                    table = soup.find('table', class_='draggable')
                    if not table:
                        # Page exists but no results table (e.g. cancelled race or no more races)
                        break
                        
                    race_results = {}
                    rows = table.find_all('tr')
                    for row in rows[1:]:
                        cells = row.find_all('td')
                        if len(cells) >= 2:
                            pla = cells[0].text.strip()
                            horse_no = cells[1].text.strip()
                            try:
                                pla_clean = "".join([c for c in pla if c.isdigit()])
                                if pla_clean:
                                    race_results[int(horse_no)] = int(pla_clean)
                                else:
                                    race_results[int(horse_no)] = 0
                            except:
                                pass
                    
                    if race_results:
                        results[race_no] = race_results
                        print(f"  Race {race_no}: Found {len(race_results)} placements on attempt {attempt}.")
                        success = True
                        break
            except Exception as e:
                print(f"  Attempt {attempt} failed for race {race_no}: {e}")
                time.sleep(2)
        
        # If we hit a 404 or empty page on the first attempt, it's the end of the card
        if not success:
            # Check if it was because of 404/empty table
            # If so, we stop querying higher race numbers
            try:
                res = requests.get(url, headers=headers, timeout=12, verify=False)
                if res.status_code == 404 or not BeautifulSoup(res.text, 'html.parser').find('table', class_='draggable'):
                    print(f"  End of meeting card reached at Race {race_no}.")
                    break
            except:
                pass
            print(f"  Skipping race {race_no} and continuing to next race.")
            
        time.sleep(0.5)
            
    return results

def main():
    files = [f for f in os.listdir('data') if f.startswith('frozen_predictions_') and f.endswith('.json')]
    
    for fn in sorted(files):
        date_part = fn.replace("frozen_predictions_", "").replace(".json", "")
        date_str = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
        
        filepath = os.path.join('data', fn)
        
        # Scrape results
        meeting_results = scrape_meeting_results_from_html(date_str)
        if not meeting_results:
            print(f"No results found for {date_str} via HTML.")
            continue
            
        with open(filepath, 'r', encoding='utf-8') as f:
            frozen_data = json.load(f)
            
        updated_count = 0
        for r_key, runners in frozen_data.items():
            try:
                race_no = int(r_key.split("_R")[1])
            except:
                continue
                
            race_results = meeting_results.get(race_no, {})
            for r in runners:
                try:
                    h_no = int(r.get("no", 0))
                except:
                    continue
                    
                pos = race_results.get(h_no)
                if pos is not None:
                    r["final_position"] = pos
                    updated_count += 1
                else:
                    r["final_position"] = 0
                    
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(frozen_data, f, indent=4)
            
        print(f"Updated {fn}: {updated_count} runners filled.")

if __name__ == '__main__':
    main()

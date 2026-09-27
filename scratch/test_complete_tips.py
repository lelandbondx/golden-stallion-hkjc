import requests
from bs4 import BeautifulSoup
import re

def parse_all_tips():
    # We will loop over 11 races (standard HKJC meeting size)
    all_tips = {}
    headers = {"User-Agent": "Mozilla/5.0"}
    
    for race_no in range(1, 12):
        url = f"https://racing.hkjc.com/racing/english/tipsindex/tips_index.asp?RaceNo={race_no}"
        try:
            res = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(res.content, 'html.parser')
            
            tables = soup.find_all('table')
            race_tips = {}
            
            for t in tables:
                rows = t.find_all('tr')
                # We are looking for the table with header row containing "Initial" and "Day Tips"
                if not rows:
                    continue
                    
                first_row_cells = rows[0].find_all(['td', 'th'])
                first_row_txt = "".join([c.get_text() for c in first_row_cells]).lower()
                
                if "initial" in first_row_txt and "day tips" in first_row_txt:
                    # This is the correct table!
                    for row in rows[1:]: # Skip header
                        cells = row.find_all('td')
                        if len(cells) < 9:
                            continue
                        
                        try:
                            h_no = int(cells[0].get_text(strip=True))
                            
                            # We can check either initial or race day tips index. 
                            # Let's check race day tips index (index 8). If it's 99, fallback to initial (index 7).
                            r_tips_val = cells[8].get_text(strip=True)
                            i_tips_val = cells[7].get_text(strip=True)
                            
                            r_val = float(re.sub(r'[^\d\.]', '', r_tips_val))
                            i_val = float(re.sub(r'[^\d\.]', '', i_tips_val))
                            
                            # Determine chosen index
                            chosen_val = r_val if r_val < 99.0 else i_val
                            
                            if chosen_val < 99.0:
                                # Convert: lower index is better. Map to a positive score (e.g. 15.0 - index)
                                score = max(0.0, 15.0 - chosen_val)
                                race_tips[h_no] = round(score, 1)
                            else:
                                race_tips[h_no] = 0.0
                        except Exception as ex:
                            pass
                    break # Found the correct table, no need to check other tables in this race
            
            if race_tips:
                all_tips[race_no] = race_tips
                print(f"Race {race_no} Parsed Tips: {race_tips}")
            else:
                print(f"Race {race_no}: No tips table parsed.")
        except Exception as e:
            print(f"Error race {race_no}:", e)
            
    return all_tips

if __name__ == "__main__":
    parse_all_tips()

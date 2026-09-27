import requests
from bs4 import BeautifulSoup
import re
import urllib3
import json
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

date_str = "24/06/2026"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# Fetch results if they aren't already parsed, or parse them from HKJC live
scraped_results = {}
for r_no in range(1, 10):
    url = f"https://racing.hkjc.com/racing/information/English/Racing/LocalResults.aspx?RaceDate={date_str}&RaceNo={r_no}"
    try:
        res = requests.get(url, headers=headers, verify=False, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.content, 'html.parser')
            # Look for Table 2 (class f_tac, table_bd, draggable)
            table = None
            for t in soup.find_all('table'):
                classes = t.get('class')
                if classes and 'table_bd' in classes and 'f_tac' in classes:
                    table = t
                    break
            
            if table:
                rows = table.find_all('tr')
                finishers = []
                for row in rows[1:]: # skip header
                    cells = [c.get_text(strip=True) for c in row.find_all(['td', 'th'])]
                    if len(cells) >= 3:
                        plc = cells[0]
                        horse_no = cells[1]
                        horse_name = cells[2]
                        finishers.append({
                            "plc": plc,
                            "horse_no": horse_no,
                            "horse_name": horse_name
                        })
                scraped_results[r_no] = finishers
            else:
                print(f"Could not find table for Race {r_no}")
        else:
            print(f"HTTP error {res.status_code} for Race {r_no}")
    except Exception as e:
        print(f"Error parsing race {r_no}: {e}")

# Load predictions
with open('data/frozen_predictions_20260624.json', 'r', encoding='utf-8') as f:
    preds = json.load(f)

print(f"\n==================================================")
print(f"HAPPY VALLEY MEETING results & PREDICTIONS COMPARISON (2026-06-24)")
print(f"==================================================")

correct_top_picks = 0
correct_ev_picks = 0

for r_no in range(1, 10):
    pred_key = f"Happy Valley_R{r_no}"
    race_preds = preds.get(pred_key, [])
    actual = scraped_results.get(r_no, [])
    
    if not race_preds or not actual:
        print(f"\nRace {r_no}: Missing predictions or results.")
        continue
    
    # Sort predictions by gs_score descending
    by_gs = sorted(race_preds, key=lambda x: x.get('gs_score', 0), reverse=True)
    # Sort predictions by model_prob descending
    by_prob = sorted(race_preds, key=lambda x: x.get('model_prob', 0), reverse=True)
    # Sort predictions by value_diff descending
    by_ev = sorted(race_preds, key=lambda x: x.get('value_diff', -99), reverse=True)
    
    actual_winner = actual[0]
    # The actual winner's horse number (as string or int)
    winner_no = str(actual_winner['horse_no']).strip()
    winner_name = actual_winner['horse_name'].split('(')[0].strip()
    
    # 1st pick by gs_score (bot's published 1st pick)
    top_pick_gs = by_gs[0]
    top_pick_gs_no = str(top_pick_gs.get('no', '')).strip()
    top_pick_gs_name = top_pick_gs.get('name', '').strip()
    top_pick_gs_odds = top_pick_gs.get('win_odds', 0.0)
    
    # 1st pick by model_prob
    top_pick_prob = by_prob[0]
    top_pick_prob_no = str(top_pick_prob.get('no', '')).strip()
    top_pick_prob_name = top_pick_prob.get('name', '').strip()
    top_pick_prob_odds = top_pick_prob.get('win_odds', 0.0)
    
    # 1st pick by EV (value_diff)
    top_pick_ev = by_ev[0]
    top_pick_ev_no = str(top_pick_ev.get('no', '')).strip()
    top_pick_ev_name = top_pick_ev.get('name', '').strip()
    top_pick_ev_odds = top_pick_ev.get('win_odds', 0.0)
    
    is_gs_hit = (top_pick_gs_no == winner_no)
    is_prob_hit = (top_pick_prob_no == winner_no)
    is_ev_hit = (top_pick_ev_no == winner_no)
    
    if is_gs_hit:
        correct_top_picks += 1
    
    print(f"\n--- RACE {r_no} ---")
    print(f"Actual Winner: #{winner_no} {winner_name}")
    print(f"Bot 1st Pick (gs_score): #{top_pick_gs_no} {top_pick_gs_name} (Odds: {top_pick_gs_odds}) -> {'HIT! [WIN]' if is_gs_hit else 'Missed'}")
    print(f"Bot 1st Pick (model_prob): #{top_pick_prob_no} {top_pick_prob_name} (Odds: {top_pick_prob_odds}) -> {'HIT! [WIN]' if is_prob_hit else 'Missed'}")
    print(f"Bot 1st Pick (value_diff): #{top_pick_ev_no} {top_pick_ev_name} (Odds: {top_pick_ev_odds}) -> {'HIT! [WIN]' if is_ev_hit else 'Missed'}")
    
    # Print where the actual winner was ranked by the bot
    for rank, p in enumerate(by_gs):
        if str(p.get('no', '')).strip() == winner_no:
            print(f"Actual winner ranked #{rank+1} by gs_score (Prob: {p.get('model_prob', 0):.4f}, EV: {p.get('value_diff', 0):.3f})")
            break

print(f"\n==================================================")
print(f"Total Hits on 1st Pick (gs_score): {correct_top_picks} out of 9 races")
print(f"==================================================")

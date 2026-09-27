import requests
from bs4 import BeautifulSoup
import re
import urllib3
import json
import sys
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

date_str = "2026/09/23"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Load frozen predictions
frozen_path = "data/frozen_predictions_20260923.json"
predictions = {}
if os.path.exists(frozen_path):
    with open(frozen_path, "r", encoding="utf-8") as f:
        predictions = json.load(f)

results = {}

print("=================================================================")
print("🏆 GOLDEN STALLION AI — LIVE RACEDAY PERFORMANCE AUDIT")
print(f"Meeting Date: {date_str} | Track: Happy Valley (Turf 'C' Course)")
print("=================================================================\n")

total_races_completed = 0
top1_win_hits = 0
top2_win_hits = 0
top3_place_hits = 0
top2_place_hits = 0
best_bet_wins = 0
best_bet_count = 0
quinella_hits = 0
trio_hits = 0

for r_no in range(1, 10):
    url = f"https://racing.hkjc.com/racing/information/English/Racing/LocalResults.aspx?RaceDate={date_str}&RaceNo={r_no}"
    try:
        res = requests.get(url, headers=headers, verify=False, timeout=15)
        if res.status_code != 200:
            print(f"Race {r_no}: HTTP {res.status_code}")
            continue

        soup = BeautifulSoup(res.content, 'html.parser')
        
        # 1. Find the performance / results table
        perf_table = soup.find('table', class_=lambda c: c and 'table_bd' in c and 'draggable' in c)
        if not perf_table:
            # Fallback search for table with 'Pla.' in header
            for t in soup.find_all('table'):
                txt = t.get_text()
                if 'Pla.' in txt and 'Horse No.' in txt:
                    perf_table = t
                    break

        if not perf_table:
            print(f"⏳ Race {r_no}: Not yet run or results pending...")
            continue

        finishers = []
        rows = perf_table.find_all('tr')
        for row in rows[1:]: # skip header
            cells = [c.get_text(strip=True) for c in row.find_all(['td', 'th'])]
            if len(cells) >= 5:
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
                
                # Clean horse name
                clean_name = re.sub(r'\(.*?\)', '', horse_name).strip()
                finishers.append({
                    "plc": plc,
                    "horse_no": int(horse_no) if horse_no.isdigit() else horse_no,
                    "horse_name": clean_name,
                    "raw_name": horse_name,
                    "jockey": jockey,
                    "trainer": trainer,
                    "act_wt": act_wt,
                    "draw": draw,
                    "finish_time": finish_time,
                    "win_odds": win_odds
                })

        # 2. Find dividends table
        div_table = soup.find('table', class_=lambda c: c and 'f_fl' in c and 'table_bd' in c)
        dividends = {}
        if div_table:
            for drow in div_table.find_all('tr'):
                dcells = [dc.get_text(strip=True) for dc in drow.find_all('td')]
                if len(dcells) >= 3:
                    pool = dcells[0]
                    comb = dcells[1]
                    div = dcells[2]
                    dividends[pool] = dividends.get(pool, []) + [{"combination": comb, "dividend": div}]

        if finishers:
            total_races_completed += 1
            results[str(r_no)] = {
                "finishers": finishers,
                "dividends": dividends
            }

            # Compare with Golden Stallion predictions
            race_key = f"Happy Valley_R{r_no}"
            pred_runners = predictions.get(race_key, [])
            # Sort predicted runners by gs_score descending
            pred_runners_sorted = sorted(pred_runners, key=lambda x: -float(x.get("gs_score", 0) or 0))

            top5_preds = pred_runners_sorted[:5]
            top5_nos = [int(p.get("no")) for p in top5_preds if p.get("no") is not None]

            # Actual top 3
            winner = finishers[0] if len(finishers) > 0 else None
            second = finishers[1] if len(finishers) > 1 else None
            third = finishers[2] if len(finishers) > 2 else None

            win_no = winner.get("horse_no") if winner else None
            sec_no = second.get("horse_no") if second else None
            thd_no = third.get("horse_no") if third else None

            # Check if winner was in Top 1, Top 2, Top 3, Top 5
            win_pred_rank = None
            for idx, p in enumerate(pred_runners_sorted):
                if p.get("no") == win_no:
                    win_pred_rank = idx + 1
                    break

            is_top1_hit = (win_pred_rank == 1)
            is_top2_hit = (win_pred_rank in [1, 2])
            is_top3_hit = (win_pred_rank in [1, 2, 3])
            is_top5_hit = (win_pred_rank in [1, 2, 3, 4, 5])

            if is_top1_hit: top1_win_hits += 1
            if is_top2_hit: top2_win_hits += 1

            # Check if Anchor (Rank 1) placed in Top 2 / Top 3
            rank1_horse_no = top5_nos[0] if top5_nos else None
            rank1_finish = None
            for f in finishers:
                if f.get("horse_no") == rank1_horse_no:
                    rank1_finish = f.get("plc")
                    break

            if rank1_finish in ["1", "2"]: top2_place_hits += 1
            if rank1_finish in ["1", "2", "3"]: top3_place_hits += 1

            # Check exotics
            top3_actual_nos = [win_no, sec_no, thd_no]
            qin_hit = (win_no in top5_nos[:2] and sec_no in top5_nos[:2]) or (win_no in top5_nos and sec_no in top5_nos)
            trio_hit = all(n in top5_nos for n in top3_actual_nos if n is not None)
            if qin_hit: quinella_hits += 1
            if trio_hit: trio_hits += 1

            print(f"-----------------------------------------------------------------")
            print(f"🏇 RACE {r_no} OFFICIAL RESULTS")
            print(f"-----------------------------------------------------------------")
            print(f"  🥇 1st: #{winner['horse_no']} {winner['horse_name']} (Odds: {winner['win_odds']}) | Jockey: {winner['jockey']}")
            print(f"  🥈 2nd: #{second['horse_no']} {second['horse_name']} (Odds: {second['win_odds']}) | Jockey: {second['jockey']}")
            print(f"  🥉 3rd: #{third['horse_no']} {third['horse_name']} (Odds: {third['win_odds']}) | Jockey: {third['jockey']}")
            print(f"  \n  🤖 Golden Stallion Predicted Top 5:")
            for idx, p in enumerate(top5_preds):
                hit_badge = ""
                if p.get("no") == win_no: hit_badge = "🏆 [WINNER!]"
                elif p.get("no") == sec_no: hit_badge = "🥈 [2ND]"
                elif p.get("no") == thd_no: hit_badge = "🥉 [3RD]"
                print(f"    Rank {idx+1}: #{p.get('no'):>2} {p.get('name'):<18} (Odds: {p.get('win_odds'):>4.1f}) {hit_badge}")
            
            # Print dividends
            if dividends:
                div_summary = []
                for p_name in ['WIN', 'PLA', 'QIN', 'QPL', 'TCE', 'TRI']:
                    if p_name in dividends:
                        for item in dividends[p_name]:
                            div_summary.append(f"{p_name} ({item['combination']}): ${item['dividend']}")
                print(f"  \n  💰 Dividends: {' | '.join(div_summary[:4])}")
            print(f"  🎯 Evaluation: Winner Rank #{win_pred_rank} | Anchor #{rank1_horse_no} Finished: {rank1_finish}\n")

    except Exception as e:
        print(f"❌ Error scraping Race {r_no}: {e}")

print("=================================================================")
print(f"📊 INTERIM PERFORMANCE SUMMARY ({total_races_completed} Races Run)")
print("=================================================================")
if total_races_completed > 0:
    print(f"• Top-1 Win Strike Rate: {top1_win_hits}/{total_races_completed} ({(top1_win_hits/total_races_completed)*100:.1f}%)")
    print(f"• Top-2 Win Strike Rate: {top2_win_hits}/{total_races_completed} ({(top2_win_hits/total_races_completed)*100:.1f}%)")
    print(f"• Anchor Top-2 Place Rate: {top2_place_hits}/{total_races_completed} ({(top2_place_hits/total_races_completed)*100:.1f}%)")
    print(f"• Anchor Top-3 Place Rate: {top3_place_hits}/{total_races_completed} ({(top3_place_hits/total_races_completed)*100:.1f}%)")
    print(f"• Top 5 Boxed Trio Hits: {trio_hits}/{total_races_completed} ({(trio_hits/total_races_completed)*100:.1f}%)")
print("=================================================================")

# Save scraped results
with open('data/scraped_results_20260923.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=4)

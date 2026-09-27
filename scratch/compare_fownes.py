import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import scraper

# Official finishes for 2026-09-06
# R1: 1st: 13, 2nd: 7, 3rd: 2, 4th: 10
# R2: 1st: 1, 2nd: 8, 3rd: 11, 4th: 2
# R3: 1st: 1, 2nd: 2, 3rd: 6, 4th: 4
# R4: 1st: 10, 2nd: 1, 3rd: 7, 4th: 9
# R5: 1st: 7, 2nd: 5, 3rd: 12, 4th: 13
# R6: 1st: 1, 2nd: 3, 3rd: 8, 4th: 14
# R7: 1st: 6, 2nd: 7, 3rd: 9, 4th: 5
# R8: 1st: 1, 2nd: 2, 3rd: 8, 4th: 6
# R9: 1st: 5, 2nd: 8, 3rd: 7, 4th: 4
# R10: 1st: 2, 2nd: 1, 3rd: 10, 4th: 7

fownes_picks = {
    1: [4, 2, 7, 6, 3],
    2: [1, 9, 2, 6, 7],
    3: [1, 3, 5],
    4: [1, 10, 3, 7, 9],
    5: [1, 5, 7, 3, 8],
    6: [2, 12, 3, 1, 7],
    7: [3, 4, 2, 5, 1],
    8: [1, 4, 2, 6, 13],
    9: [5, 6, 4, 1, 2],
    10: [1, 12, 6, 8, 10]
}

# Load Golden Stallion AI picks
with open('data/frozen_predictions_20260906.json', 'r') as f:
    gs_data = json.load(f)

# Load scraped results
meet = scraper.get_live_meeting_data()['meetings'][0]

print("=== HEAD-TO-HEAD AUDIT: GOLDEN STALLION AI vs FOWNES TIPSHEET ===")

gs_top1_wins = 0
fownes_top1_wins = 0

gs_top3_wins = 0
fownes_top3_wins = 0

gs_top5_wins = 0
fownes_top5_wins = 0

gs_quinellas = 0
fownes_quinellas = 0

gs_trifectas = 0
fownes_trifectas = 0

for r in meet.get('races', []):
    r_no = r.get('race_no')
    runners = r.get('runners', [])
    finished = sorted([h for h in runners if h.get('final_position', 0) > 0], key=lambda x: x.get('final_position', 99))
    
    f1 = finished[0].get('no') if len(finished) > 0 else 0
    f2 = finished[1].get('no') if len(finished) > 1 else 0
    f3 = finished[2].get('no') if len(finished) > 2 else 0
    f4 = finished[3].get('no') if len(finished) > 3 else 0
    
    # GS picks
    gs_r = sorted(gs_data.get(f"Sha Tin_R{r_no}", []), key=lambda x: x.get('gs_score', 0), reverse=True)
    gs_nos = [p.get('no') for p in gs_r[:5]]
    
    # Fownes picks
    f_nos = fownes_picks.get(r_no, [])
    
    # Top 1 Win
    if len(gs_nos) > 0 and gs_nos[0] == f1: gs_top1_wins += 1
    if len(f_nos) > 0 and f_nos[0] == f1: fownes_top1_wins += 1
    
    # Top 3 Win
    if f1 in gs_nos[:3]: gs_top3_wins += 1
    if f1 in f_nos[:3]: fownes_top3_wins += 1
    
    # Top 5 Win
    if f1 in gs_nos[:5]: gs_top5_wins += 1
    if f1 in f_nos[:5]: fownes_top5_wins += 1
    
    # Quinella (1st & 2nd in top 5)
    if f1 in gs_nos[:5] and f2 in gs_nos[:5]: gs_quinellas += 1
    if f1 in f_nos[:5] and f2 in f_nos[:5]: fownes_quinellas += 1
    
    # Trifecta (1st, 2nd, 3rd in top 5)
    if f1 in gs_nos[:5] and f2 in gs_nos[:5] and f3 in gs_nos[:5]: gs_trifectas += 1
    if f1 in f_nos[:5] and f2 in f_nos[:5] and f3 in f_nos[:5]: fownes_trifectas += 1
    
    print(f"\nRACE {r_no}: Official 1st: #{f1}, 2nd: #{f2}, 3rd: #{f3}, 4th: #{f4}")
    print(f"  Golden Stallion AI: {gs_nos}")
    print(f"  Fownes Tipsheet:    {f_nos}")
    
    # Compare
    gs_hit = "WIN (Rank 1)" if len(gs_nos)>0 and gs_nos[0]==f1 else ("WIN (Top 3)" if f1 in gs_nos[:3] else ("WIN (Top 5)" if f1 in gs_nos[:5] else "MISS"))
    f_hit = "WIN (Rank 1)" if len(f_nos)>0 and f_nos[0]==f1 else ("WIN (Top 3)" if f1 in f_nos[:3] else ("WIN (Top 5)" if f1 in f_nos[:5] else "MISS"))
    
    gs_q = "QUINELLA YES" if (f1 in gs_nos[:5] and f2 in gs_nos[:5]) else "NO Q"
    f_q = "QUINELLA YES" if (f1 in f_nos[:5] and f2 in f_nos[:5]) else "NO Q"
    
    print(f"  -> GS AI: {gs_hit} | {gs_q}")
    print(f"  -> Fownes: {f_hit} | {f_q}")

print("\n==========================================")
print(f"FINAL SCORECARD:")
print(f"Metric                    | GS AI   | Fownes")
print(f"--------------------------|---------|-------")
print(f"Primary (Rank 1) Wins     | {gs_top1_wins}/10   | {fownes_top1_wins}/10")
print(f"Top 3 Selections Wins     | {gs_top3_wins}/10   | {fownes_top3_wins}/10")
print(f"Total Winners Found (Top 5)| {gs_top5_wins}/10   | {fownes_top5_wins}/10")
print(f"Quinellas (1st & 2nd)     | {gs_quinellas}/10   | {fownes_quinellas}/10")
print(f"Trifectas (1-2-3 Sweep)   | {gs_trifectas}/10   | {fownes_trifectas}/10")
print("==========================================")

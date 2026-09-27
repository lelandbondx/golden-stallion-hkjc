import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')
import json
import scraper
import pandas as pd

meeting_data = scraper.get_live_meeting_data()
if meeting_data.get('status') != 'success' or not meeting_data.get('meetings'):
    print("Failed to get meeting data")
    exit()

meet = meeting_data['meetings'][0]
date = meet.get('date')
venue = meet.get('venue')

print(f"==========================================================================")
print(f"   GOLDEN STALLION AI — RACE DAY MASTER PERFORMANCE REPORT")
print(f"   Meeting: {venue} | Date: {date} | Track Going: {meet.get('going')}")
print(f"==========================================================================\n")

# Load frozen predictions
frozen_file = f"data/frozen_predictions_{date.replace('-', '')}.json"
frozen_data = {}
try:
    with open(frozen_file, 'r', encoding='utf-8') as f:
        frozen_data = json.load(f)
except Exception as e:
    print(f"Error loading frozen predictions: {e}")

total_races = len(meet.get('races', []))
top1_wins = 0
top1_podiums = 0
top3_wins = 0
top5_wins = 0
top5_quinellas = 0
top3_quinellas = 0
top5_tierces = 0

races_detail = []

for r in meet.get('races', []):
    r_no = r.get('race_no')
    c_dist = r.get('class_dist')
    runners = r.get('runners', [])
    
    # Official finish
    finished = [h for h in runners if h.get('final_position', 0) > 0]
    finished.sort(key=lambda x: x.get('final_position', 99))
    
    # Model picks
    r_key = f"{venue}_R{r_no}"
    picks = frozen_data.get(r_key, [])
    if picks:
        picks = sorted(picks, key=lambda x: x.get('gs_score', 0), reverse=True)
    
    p1 = picks[0] if len(picks) > 0 else {}
    p2 = picks[1] if len(picks) > 1 else {}
    p3 = picks[2] if len(picks) > 2 else {}
    p4 = picks[3] if len(picks) > 3 else {}
    p5 = picks[4] if len(picks) > 4 else {}
    
    top5_nos = [p.get('no') for p in picks[:5]]
    top3_nos = [p.get('no') for p in picks[:3]]
    top2_nos = [p.get('no') for p in picks[:2]]
    
    f1 = finished[0] if len(finished) > 0 else {}
    f2 = finished[1] if len(finished) > 1 else {}
    f3 = finished[2] if len(finished) > 2 else {}
    f4 = finished[3] if len(finished) > 3 else {}
    
    winner_no = f1.get('no')
    second_no = f2.get('no')
    third_no = f3.get('no')
    
    is_top1_win = (winner_no == p1.get('no'))
    is_top3_win = (winner_no in top3_nos)
    is_top5_win = (winner_no in top5_nos)
    is_top1_podium = any(f.get('no') == p1.get('no') for f in finished[:3])
    
    is_top5_q = (winner_no in top5_nos and second_no in top5_nos)
    is_top3_q = (winner_no in top3_nos and second_no in top3_nos)
    is_top5_tierce = (winner_no in top5_nos and second_no in top5_nos and third_no in top5_nos)
    
    if is_top1_win: top1_wins += 1
    if is_top1_podium: top1_podiums += 1
    if is_top3_win: top3_wins += 1
    if is_top5_win: top5_wins += 1
    if is_top5_q: top5_quinellas += 1
    if is_top3_q: top3_quinellas += 1
    if is_top5_tierce: top5_tierces += 1
    
    print(f"--------------------------------------------------------------------------")
    print(f"RACE {r_no}: {c_dist}")
    print(f"--------------------------------------------------------------------------")
    print(f"🏁 Official Finish:")
    for f in finished[:4]:
        pos = f.get('final_position')
        no = f.get('no')
        name = f.get('name')
        odds = f.get('win_odds')
        jock = f.get('jockey')
        rank_str = f"★ [AI Rank {top5_nos.index(no)+1}]" if no in top5_nos else ""
        print(f"  {pos}st/nd/rd: #{no} {name:<18} (Odds: {odds:>5.1f}) [{jock}] {rank_str}")
        
    print(f"\n🧠 Golden Stallion AI Top 5 Selections:")
    for i, p in enumerate(picks[:5]):
        p_no = p.get('no')
        p_name = p.get('name')
        p_odds = p.get('win_odds')
        p_conf = p.get('confidence')
        p_ev = p.get('value_diff', 0)
        p_jock = p.get('jockey')
        # Find actual finish
        act_f = next((f for f in finished if f.get('no') == p_no), None)
        act_pos = act_f.get('final_position', 0) if act_f else 0
        if act_pos == 1:
            res_str = "🏆 WINNER (1st)"
        elif act_pos == 2:
            res_str = "🥈 2nd (Placed)"
        elif act_pos == 3:
            res_str = "🥉 3rd (Placed)"
        elif act_pos == 4:
            res_str = "4th"
        else:
            res_str = "Unplaced"
            
        print(f"  Rank {i+1}: #{p_no:<2} {p_name:<18} | Odds: {p_odds:>4.1f} | Conf: {p_conf:>2}% | EV: {p_ev:>+6.3f} | {p_jock:<12} -> {res_str}")
        
    print()

print(f"==========================================================================")
print(f"🏆 MASTER METRICS & SUMMARY STATS:")
print(f"==========================================================================")
print(f"• Total Races:                     {total_races}")
print(f"• Top Pick (Rank 1) Straight Wins: {top1_wins} / {total_races} ({top1_wins/total_races*100:.1f}%)")
print(f"• Top Pick (Rank 1) Podium (1-2-3):{top1_podiums} / {total_races} ({top1_podiums/total_races*100:.1f}%)")
print(f"• Top 3 Selections Winners Hit:    {top3_wins} / {total_races} ({top3_wins/total_races*100:.1f}%)")
print(f"• Top 5 Selections Winners Hit:    {top5_wins} / {total_races} ({top5_wins/total_races*100:.1f}%)")
print(f"• Quinella (1st & 2nd in Top 5):   {top5_quinellas} / {total_races} ({top5_quinellas/total_races*100:.1f}%)")
print(f"• Exacta / Top 3 Quinella:         {top3_quinellas} / {total_races} ({top3_quinellas/total_races*100:.1f}%)")
print(f"• Tierce / Trifecta (1-2-3 Top 5): {top5_tierces} / {total_races} ({top5_tierces/total_races*100:.1f}%)")
print(f"==========================================================================")

import sys
import json
import os
import pandas as pd
import numpy as np

# Configure stdout to support UTF-8 emojis on Windows
if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

files = [f for f in os.listdir('data') if f.startswith('frozen_predictions_') and f.endswith('.json')]

total_races = 0
top_pick_wins = 0
top_pick_places = 0 # Top 3
top_pick_top4 = 0

top5_wins = 0
exotic_exacta_hits = 0 # 1st and 2nd place both in Top 5
swinger_hits = 0 # At least two of the Top 3 are in our Top 5

anchor_wins = 0 # Rank 1 wins
sleeper_wins = 0 # Rank 5 wins
dual_staking_hits = 0 # Either Rank 1 or Rank 5 wins
dual_staking_places = 0 # Either Rank 1 or Rank 5 places (Top 3)

meeting_summaries = []

for fn in sorted(files):
    date_part = fn.replace("frozen_predictions_", "").replace(".json", "")
    date_str = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
    
    with open(os.path.join('data', fn), 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    m_races = 0
    m_top_wins = 0
    m_top_places = 0
    m_top5_wins = 0
    m_exacta_hits = 0
    
    for r_key, runners in data.items():
        if not runners:
            continue
            
        positions = [r.get('final_position') for r in runners if r.get('final_position') is not None and r.get('final_position') != 0]
        if not positions:
            continue
            
        df = pd.DataFrame(runners).sort_values(by='gs_score', ascending=False).reset_index(drop=True)
        
        # Verify if results are valid (must have at least one horse with position 1)
        if 1 not in df['final_position'].values:
            continue
            
        total_races += 1
        m_races += 1
        
        # Top Pick
        top_pick = df.iloc[0]
        top_pos = top_pick.get('final_position')
        
        if top_pos == 1:
            top_pick_wins += 1
            m_top_wins += 1
            top_pick_places += 1
            top_pick_top4 += 1
        elif top_pos in [2, 3]:
            top_pick_places += 1
            m_top_places += 1
            top_pick_top4 += 1
        elif top_pos == 4:
            top_pick_top4 += 1
            
        # Top 5 picks
        top5_df = df.iloc[:5]
        top5_pos = top5_df['final_position'].tolist()
        
        if 1 in top5_pos:
            top5_wins += 1
            m_top5_wins += 1
            
        # Exotics
        # Exacta / Quinella: 1 and 2 are both in the Top 5
        if 1 in top5_pos and 2 in top5_pos:
            exotic_exacta_hits += 1
            m_exacta_hits += 1
            
        # Swinger: At least two of the Top 3 are in the Top 5
        top3_in_top5 = sum(1 for p in top5_pos if p in [1, 2, 3])
        if top3_in_top5 >= 2:
            swinger_hits += 1
            
        # Dual-Staking (Rank 1 Anchor + Rank 5 Sleeper)
        if len(df) >= 5:
            r1_pos = df.iloc[0].get('final_position')
            r5_pos = df.iloc[4].get('final_position')
            
            if r1_pos == 1:
                anchor_wins += 1
            if r5_pos == 1:
                sleeper_wins += 1
            if r1_pos == 1 or r5_pos == 1:
                dual_staking_hits += 1
            if r1_pos in [1, 2, 3] or r5_pos in [1, 2, 3]:
                dual_staking_places += 1
                
    if m_races > 0:
        meeting_summaries.append({
            "date": date_str,
            "races": m_races,
            "top_wins": m_top_wins,
            "top_places": m_top_places,
            "top5_wins": m_top5_wins,
            "exactas": m_exacta_hits
        })

print("\n==================================================")
print("🏆 GOLDEN STALLION AI - SEASON-LONG PERFORMANCE REPORT 🏆")
print("==================================================")
print(f"Total Evaluated Meetings: {len(meeting_summaries)}")
print(f"Total Evaluated Races: {total_races}")
print("--------------------------------------------------")
print(f"🥇 Top Pick (Rank 1) Outright Winner Rate: {top_pick_wins}/{total_races} ({top_pick_wins/total_races:.1%})")
print(f"🥈 Top Pick (Rank 1) Place Rate (Top 3): {top_pick_places}/{total_races} ({top_pick_places/total_races:.1%})")
print(f"🥉 Top Pick (Rank 1) Top-4 Rate: {top_pick_top4}/{total_races} ({top_pick_top4/total_races:.1%})")
print("--------------------------------------------------")
print(f"🏇 Top-5 Hit Rate (Hit winner in top 5): {top5_wins}/{total_races} ({top5_wins/total_races:.1%})")
print(f"🎯 Quinella / Exacta Box Hit Rate: {exotic_exacta_hits}/{total_races} ({exotic_exacta_hits/total_races:.1%})")
print(f"💎 Swinger / Quinella Place Hit Rate: {swinger_hits}/{total_races} ({swinger_hits/total_races:.1%})")
print("--------------------------------------------------")
print(f"🛡️ Dual-Staking Wagers (Rank 1 Anchor + Rank 5 Sleeper):")
print(f"  - Anchor Win Rate: {anchor_wins}/{total_races} ({anchor_wins/total_races:.1%})")
print(f"  - Sleeper Win Rate: {sleeper_wins}/{total_races} ({sleeper_wins/total_races:.1%})")
print(f"  - Combined Win Rate (At least one wins): {dual_staking_hits}/{total_races} ({dual_staking_hits/total_races:.1%})")
print(f"  - Combined Place Rate (At least one in Top 3): {dual_staking_places}/{total_races} ({dual_staking_places/total_races:.1%})")
print("--------------------------------------------------")
print("\nMeeting Breakdown:")
for m in meeting_summaries:
    print(f"  📅 {m['date']}: {m['races']} Races | Top Pick Wins: {m['top_wins']} | Top Pick Places: {m['top_places']} | Top 5 Winners: {m['top5_wins']} | Exactas: {m['exactas']}")
print("==================================================")

import os
import sys
import json
import pandas as pd
import numpy as np

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

files = sorted([f for f in os.listdir('data') if f.startswith('frozen_predictions_') and f.endswith('.json')])

all_race_highlights = []
meeting_stats = []

for fn in files:
    date_part = fn.replace("frozen_predictions_", "").replace(".json", "")
    date_str = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
    
    with open(os.path.join('data', fn), 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    m_races = 0
    m_top1_wins = 0
    m_top3_places = 0
    m_top5_wins = 0
    m_exactas = 0
    m_trios = 0
    
    for r_key, runners in data.items():
        if not runners:
            continue
            
        df = pd.DataFrame(runners)
        if 'final_position' not in df.columns:
            continue
            
        # Filter valid finishers
        valid_df = df[df['final_position'].notna() & (df['final_position'] != 0)].copy()
        if valid_df.empty or 1 not in valid_df['final_position'].values:
            continue
            
        m_races += 1
        
        # Sort by gs_score descending
        ranked = valid_df.sort_values(by='gs_score', ascending=False).reset_index(drop=True)
        ranked['model_rank'] = range(1, len(ranked) + 1)
        
        winner = ranked[ranked['final_position'] == 1].iloc[0]
        second = ranked[ranked['final_position'] == 2].iloc[0] if 2 in ranked['final_position'].values else None
        third = ranked[ranked['final_position'] == 3].iloc[0] if 3 in ranked['final_position'].values else None
        
        winner_rank = winner['model_rank']
        winner_name = winner.get('name', winner.get('horse', 'Unknown'))
        winner_no = winner.get('no', winner.get('horseno', '?'))
        winner_odds = float(winner.get('win_odds', winner.get('odds', 0)))
        
        top1_horse = ranked.iloc[0]
        top1_pos = top1_horse.get('final_position')
        top1_name = top1_horse.get('name', top1_horse.get('horse', 'Unknown'))
        top1_odds = float(top1_horse.get('win_odds', top1_horse.get('odds', 0)))
        
        if top1_pos == 1:
            m_top1_wins += 1
        if top1_pos in [1, 2, 3]:
            m_top3_places += 1
            
        top5 = ranked.head(5)
        top5_pos = top5['final_position'].tolist()
        
        if 1 in top5_pos:
            m_top5_wins += 1
            
        exacta = (1 in top5_pos) and (2 in top5_pos)
        if exacta:
            m_exactas += 1
            
        trio = (1 in top5_pos) and (2 in top5_pos) and (3 in top5_pos)
        if trio:
            m_trios += 1
            
        top3_picks = ranked.head(3)['final_position'].tolist()
        super_trio = set([1, 2, 3]).issubset(set(top3_picks))
        top4_trio = set([1, 2, 3]).issubset(set(ranked.head(4)['final_position'].tolist()))
        
        highlight_reasons = []
        
        if winner_odds >= 10.0 and winner_rank <= 5:
            highlight_reasons.append(f"LONGSHOT WINNER: {winner_name} @ {winner_odds:.1f} (Ranked #{winner_rank} by AI)")
        elif winner_odds >= 6.0 and winner_rank == 1:
            highlight_reasons.append(f"VALUE TOP PICK WINNER: {winner_name} @ {winner_odds:.1f} (AI Top Pick)")
            
        if super_trio:
            highlight_reasons.append("PERFECT TRIO/TRIFECTA: Top 3 AI picks finished 1st, 2nd, 3rd!")
        elif top4_trio:
            highlight_reasons.append("TOP-4 TRIO SWEEP: Top 3 finishers all in AI Top-4 picks")
        elif trio:
            highlight_reasons.append("TOP-5 TRIO BOX: 1st, 2nd, and 3rd all captured in AI Top 5")
            
        if exacta and not trio and winner_odds >= 8.0:
            highlight_reasons.append(f"EXACTA BOX WINNER: {winner_name} @ {winner_odds:.1f}")

        if winner_rank == 5 and winner_odds >= 8.0:
            highlight_reasons.append(f"SLEEPER STRIKE (Rank 5): {winner_name} @ {winner_odds:.1f}")

        if highlight_reasons:
            all_race_highlights.append({
                "date": date_str,
                "race_no": r_key,
                "winner_name": winner_name,
                "winner_odds": winner_odds,
                "winner_rank": int(winner_rank),
                "top1_name": top1_name,
                "top1_pos": int(top1_pos) if pd.notna(top1_pos) else None,
                "top1_odds": top1_odds,
                "second_name": second.get('name', second.get('horse', '')) if second is not None else '',
                "second_odds": float(second.get('win_odds', 0)) if second is not None else 0,
                "second_rank": int(second['model_rank']) if second is not None else 0,
                "third_name": third.get('name', third.get('horse', '')) if third is not None else '',
                "third_odds": float(third.get('win_odds', 0)) if third is not None else 0,
                "third_rank": int(third['model_rank']) if third is not None else 0,
                "reasons": highlight_reasons
            })

    meeting_stats.append({
        "date": date_str,
        "races": m_races,
        "top1_wins": m_top1_wins,
        "top3_places": m_top3_places,
        "top5_wins": m_top5_wins,
        "exactas": m_exactas,
        "trios": m_trios
    })

print("=== MEETING SUMMARY ===")
print(pd.DataFrame(meeting_stats).to_string())

print("\n=== ALL EXCEPTIONAL RACES ===")
for r in all_race_highlights:
    print(f"\n📅 Date: {r['date']} | Race {r['race_no']}")
    print(f"   Winner: {r['winner_name']} (@ {r['winner_odds']:.1f} - AI Rank #{r['winner_rank']})")
    print(f"   2nd: {r['second_name']} (@ {r['second_odds']:.1f} - AI Rank #{r['second_rank']})")
    print(f"   3rd: {r['third_name']} (@ {r['third_odds']:.1f} - AI Rank #{r['third_rank']})")
    print(f"   Top Pick: {r['top1_name']} (@ {r['top1_odds']:.1f} - Finished #{r['top1_pos']})")
    print("   Highlights:")
    for h in r['reasons']:
        print(f"     - {h}")

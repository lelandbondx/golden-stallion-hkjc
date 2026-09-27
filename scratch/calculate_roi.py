import sys
import os
import json
import pandas as pd

# Configure stdout to support UTF-8 emojis on Windows
if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

files = [f for f in os.listdir('data') if f.startswith('frozen_predictions_') and f.endswith('.json')]

total_races = 0

s1_stake = 0
s1_payout = 0

s2_stake = 0
s2_payout = 0

s3_stake = 0
s3_payout = 0

s4_stake = 0
s4_payout = 0

for fn in sorted(files):
    with open(os.path.join('data', fn), 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    for r_key, runners in data.items():
        if not runners:
            continue
            
        positions = [r.get('final_position') for r in runners if r.get('final_position') is not None and r.get('final_position') != 0]
        if not positions or 1 not in positions:
            continue
            
        df = pd.DataFrame(runners).sort_values(by='gs_score', ascending=False).reset_index(drop=True)
        
        df['win_odds'] = pd.to_numeric(df['win_odds'], errors='coerce').fillna(1.0)
        
        total_races += 1
        
        # --- Strategy 1: Rank 1 Win ---
        s1_stake += 1
        r1_row = df.iloc[0]
        if r1_row.get('final_position') == 1:
            s1_payout += r1_row.get('win_odds')
            
        # --- Strategy 2: Dual Staking (Rank 1 + Rank 5) ---
        if len(df) >= 5:
            s2_stake += 2
            r1 = df.iloc[0]
            r5 = df.iloc[4]
            if r1.get('final_position') == 1:
                s2_payout += r1.get('win_odds')
            if r5.get('final_position') == 1:
                s2_payout += r5.get('win_odds')
                
        # --- Strategy 3: Flat Top 5 ---
        s3_stake += 5
        for idx in range(min(5, len(df))):
            horse = df.iloc[idx]
            if horse.get('final_position') == 1:
                s3_payout += horse.get('win_odds')
                
        # --- Strategy 4: Value Bet (Rank 1 with EV > 0) ---
        if 'ev' in df.columns:
            r1_ev = pd.to_numeric(df.iloc[0].get('ev'), errors='coerce')
            if r1_ev > 0:
                s4_stake += 1
                if df.iloc[0].get('final_position') == 1:
                    s4_payout += df.iloc[0].get('win_odds')

print("==========================================")
print("💵 GOLDEN STALLION AI - ROI PERFORMANCE SUMMARY 💵")
print("==========================================")
print(f"Total Evaluated Races: {total_races}")
print("------------------------------------------")

s1_profit = s1_payout - s1_stake
s1_roi = (s1_profit / s1_stake) * 100 if s1_stake > 0 else 0
print(f"Strategy 1: Flat Bet on Rank 1 (Top Pick) to Win")
print(f"  - Total Stake:  {s1_stake} units")
print(f"  - Total Return: {s1_payout:.2f} units")
print(f"  - Net Profit:   {s1_profit:.2f} units")
print(f"  - ROI:          {s1_roi:+.1f}%")
print("------------------------------------------")

s2_profit = s2_payout - s2_stake
s2_roi = (s2_profit / s2_stake) * 100 if s2_stake > 0 else 0
print(f"Strategy 2: Recommended Dual-Staking (Rank 1 Anchor + Rank 5 Sleeper)")
print(f"  - Total Stake:  {s2_stake} units")
print(f"  - Total Return: {s2_payout:.2f} units")
print(f"  - Net Profit:   {s2_profit:.2f} units")
print(f"  - ROI:          {s2_roi:+.1f}%")
print("------------------------------------------")

s3_profit = s3_payout - s3_stake
s3_roi = (s3_profit / s3_stake) * 100 if s3_stake > 0 else 0
print(f"Strategy 3: Flat Bet on all Top 5 Picks to Win")
print(f"  - Total Stake:  {s3_stake} units")
print(f"  - Total Return: {s3_payout:.2f} units")
print(f"  - Net Profit:   {s3_profit:.2f} units")
print(f"  - ROI:          {s3_roi:+.1f}%")
print("------------------------------------------")

if s4_stake > 0:
    s4_profit = s4_payout - s4_stake
    s4_roi = (s4_profit / s4_stake) * 100
    print(f"Strategy 4: Value Betting (Rank 1 ONLY when EV > 0)")
    print(f"  - Total Stake:  {s4_stake} units")
    print(f"  - Total Return: {s4_payout:.2f} units")
    print(f"  - Net Profit:   {s4_profit:.2f} units")
    print(f"  - ROI:          {s4_roi:+.1f}%")
    print("==========================================")

import os
import sys

# Add parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import joblib
from model import prepare_features, ALL_FEATURES

def evaluate():
    if not os.path.exists('data/train_horse_features.csv'):
        print("Historical feature dataset not found.")
        return
        
    print("Loading historical features...")
    df = pd.read_csv('data/train_horse_features.csv')
    print(f"Loaded {len(df)} runner rows.")
    
    if 'race_id' not in df.columns or 'won' not in df.columns:
        print("Missing race_id or won columns.")
        return
        
    # Drop rows without labels or essential columns
    essential_cols = [c for c in ALL_FEATURES if c in df.columns] + ['won', 'race_id']
    df = df.dropna(subset=essential_cols)
    print(f"Rows after dropping NaNs: {len(df)}")
    
    # Load model
    if not os.path.exists('model.joblib'):
        print("Model file model.joblib not found.")
        return
    model = joblib.load('model.joblib')
    
    # Prepare features (adds rank columns etc.)
    df = prepare_features(df, is_live=False)
    
    # Predict probabilities
    X = df[ALL_FEATURES]
    probs = model.predict_proba(X)[:, 1]
    df['model_prob'] = probs
    
    # Load runs.csv to get the actual results (position)
    has_result = False
    if os.path.exists('data/runs.csv'):
        try:
            print("Loading runs.csv for actual positions...")
            runs_df = pd.read_csv('data/runs.csv', usecols=['race_id', 'horse_id', 'result'])
            
            def parse_pos(x):
                try:
                    val = str(x).strip()
                    if 'DH' in val:
                        val = val.replace('DH', '').strip()
                    return float(val)
                except:
                    return 7.0
                    
            runs_df['result_num'] = runs_df['result'].apply(parse_pos)
            
            # Merge on race_id and horse_id
            # Ensure types match
            df['race_id'] = df['race_id'].astype(str)
            df['horse_id'] = df['horse_id'].astype(str)
            runs_df['race_id'] = runs_df['race_id'].astype(str)
            runs_df['horse_id'] = runs_df['horse_id'].astype(str)
            
            df = pd.merge(df, runs_df[['race_id', 'horse_id', 'result_num']], on=['race_id', 'horse_id'], how='left')
            print("Successfully merged finish positions from runs.csv.")
            has_result = True
        except Exception as e:
            print("Failed to merge result from runs.csv:", e)
            
    # Let's group by race_id and evaluate
    races = df.groupby('race_id')
    total_races = 0
    top1_wins = 0
    top1_places = 0
    top2_places = 0
    top3_places = 0
    
    for race_id, group in races:
        if len(group) < 3:
            continue
        total_races += 1
        
        # Sort by predicted probability
        sorted_group = group.sort_values(by='model_prob', ascending=False)
        
        # Check Top 1 pick
        top1 = sorted_group.iloc[0]
        if top1['won'] == 1:
            top1_wins += 1
            
        if has_result:
            if 'result_num' in top1 and pd.notna(top1['result_num']) and top1['result_num'] <= 3:
                top1_places += 1
            # Top 2 pick
            if len(sorted_group) > 1:
                top2 = sorted_group.iloc[1]
                if 'result_num' in top2 and pd.notna(top2['result_num']) and top2['result_num'] <= 3:
                    top2_places += 1
            # Top 3 pick
            if len(sorted_group) > 2:
                top3 = sorted_group.iloc[2]
                if 'result_num' in top3 and pd.notna(top3['result_num']) and top3['result_num'] <= 3:
                    top3_places += 1
                
    print(f"\nEvaluation Results over {total_races} races:")
    print(f"Top-1 Win Rate (Accuracy of picking winner): {top1_wins / total_races * 100:.2f}%")
    if has_result:
        print(f"Top-1 Place Rate (Top 3 finish): {top1_places / total_races * 100:.2f}%")
        print(f"Top-2 Place Rate (Top 3 finish): {top2_places / total_races * 100:.2f}%")
        print(f"Top-3 Place Rate (Top 3 finish): {top3_places / total_races * 100:.2f}%")
        # Let's check how often at least one of the top 3 picks wins
        top3_win = 0
        for race_id, group in races:
            if len(group) < 3:
                continue
            sorted_group = group.sort_values(by='model_prob', ascending=False)
            has_win = False
            for i in range(min(3, len(sorted_group))):
                if sorted_group.iloc[i]['won'] == 1:
                    has_win = True
                    break
            if has_win:
                top3_win += 1
        print(f"Any of Top-3 Picks Wins: {top3_win / total_races * 100:.2f}%")

if __name__ == '__main__':
    evaluate()

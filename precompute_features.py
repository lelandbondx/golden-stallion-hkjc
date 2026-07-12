import os
import json
import pandas as pd
import numpy as np
import re

def precompute():
    print("Loading results.csv and comments.csv for comments and gears...")
    results_path = 'data/results.csv'
    comments_path = 'data/comments.csv'
    
    if not os.path.exists(results_path) or not os.path.exists(comments_path):
        print(f"[ERROR] Required database files results.csv or comments.csv not found.")
        return
        
    results = pd.read_csv(results_path, usecols=['date', 'raceno', 'horseno', 'horse', 'runningpos'])
    comments = pd.read_csv(comments_path, usecols=['date', 'raceno', 'horseno', 'comment', 'plc', 'gear'])
    
    # helper for clean_name
    def get_clean_name(df_col):
        # Extract name before parenthesis if exists, else return full name
        extracted = df_col.astype(str).str.extract(r'^(.*?)\(')[0]
        return extracted.fillna(df_col).str.strip().str.upper()

    # 1. Winning Gears
    print("Computing winning gears...")
    parse_won = lambda x: 1 if str(x).strip() in ['1', '1.0', '1 DH'] or '1 DH' in str(x) else 0
    comments['won_calc'] = comments['plc'].apply(parse_won)
    wins_comments = comments[comments['won_calc'] == 1]
    wins_df = pd.merge(wins_comments, results, on=['date', 'raceno', 'horseno'], how='inner')
    
    wins_df['clean_name'] = get_clean_name(wins_df['horse'])
    wins_df['clean_gear'] = wins_df['gear'].fillna('').astype(str).str.strip().str.upper()
    wins_df.loc[wins_df['clean_gear'] == '-', 'clean_gear'] = ''
    
    winning_gears = {}
    for name, group in wins_df.groupby('clean_name'):
        winning_gears[name] = sorted(list(group['clean_gear'].unique()))
        
    # 2. Running Styles
    print("Computing running styles...")
    results['clean_name'] = get_clean_name(results['horse'])
    
    def parse_first_pos(x):
        if not isinstance(x, str): return np.nan
        parts = x.strip().split()
        if not parts: return np.nan
        try:
            return float(parts[0])
        except:
            return np.nan
            
    results['first_pos'] = results['runningpos'].apply(parse_first_pos)
    running_styles = results.groupby('clean_name')['first_pos'].mean().dropna().to_dict()
    
    # 3. Last Comments
    print("Computing last comments...")
    df_comm = pd.merge(comments, results, on=['date', 'raceno', 'horseno'], how='inner')
    df_comm['clean_name'] = get_clean_name(df_comm['horse'])
    df_comm = df_comm.sort_values(by='date', ascending=False)
    last_comments = df_comm.drop_duplicates(subset=['clean_name'], keep='first').set_index('clean_name')['comment'].dropna().to_dict()
    
    # 4. Sectional Bursts
    print("Computing sectional bursts...")
    sectional_bursts = {}
    runs_path = 'data/runs.csv'
    horse_info_path = 'data/horse_info.csv'
    
    if os.path.exists(runs_path) and os.path.exists(horse_info_path):
        runs = pd.read_csv(runs_path, usecols=['horse_id', 'time1', 'time2', 'time3', 'time4', 'time5', 'time6'])
        horse_info = pd.read_csv(horse_info_path, usecols=['Unnamed: 0', 'horse'])
        horse_info['clean_name'] = get_clean_name(horse_info['horse'])
        horse_map = horse_info[['Unnamed: 0', 'clean_name']].rename(columns={'Unnamed: 0': 'horse_id'}).drop_duplicates()
        df_runs = pd.merge(runs, horse_map, on='horse_id', how='inner')
        
        def parse_last_sec(row):
            for col in ['time6', 'time5', 'time4', 'time3', 'time2']:
                val = pd.to_numeric(row[col], errors='coerce')
                if not pd.isna(val) and val > 0:
                    return val
            return pd.to_numeric(row['time1'], errors='coerce')
            
        df_runs['last_sec_val'] = df_runs.apply(parse_last_sec, axis=1)
        df_runs = df_runs[df_runs['last_sec_val'] > 10.0]
        sectional_bursts = df_runs.groupby('clean_name')['last_sec_val'].min().dropna().to_dict()
    else:
        print("[WARNING] runs.csv or horse_info.csv not found. Skipping sectional bursts calculation.")
        
    print("Saving precomputed features to data/precomputed_features.json...")
    precomputed = {
        "winning_gears": winning_gears,
        "running_styles": running_styles,
        "last_comments": last_comments,
        "sectional_bursts": sectional_bursts
    }
    
    os.makedirs('data', exist_ok=True)
    with open('data/precomputed_features.json', 'w', encoding='utf-8') as f:
        json.dump(precomputed, f, indent=4)
        
    print("Saving runs.csv and races.csv slices...")
    if os.path.exists('data/runs.csv'):
        df_runs_full = pd.read_csv('data/runs.csv', nrows=1000)
        df_runs_full.to_csv('data/runs_slice.csv', index=False)
    if os.path.exists('data/races.csv'):
        df_races_full = pd.read_csv('data/races.csv', nrows=250)
        df_races_full.to_csv('data/races_slice.csv', index=False)
        
    print("Precomputation complete!")

if __name__ == '__main__':
    precompute()

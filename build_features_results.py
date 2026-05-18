import pandas as pd
import numpy as np
import os

def build_features_from_results():
    print("Loading datasets...")
    df = pd.read_csv('data/results.csv')
    comments = pd.read_csv('data/comments.csv')

    # Ensure date is datetime
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    comments['date'] = pd.to_datetime(comments['date'], errors='coerce')

    # Clean horse name
    df['clean_name'] = df['horse'].str.extract(r'^(.*?)\(')[0].str.strip().str.upper()
    df['horse_id'] = df['horse'].str.extract(r'\((.*?)\)')[0].str.strip()
    
    df['race_id'] = df['date'].dt.strftime('%Y%m%d') + "_" + df['raceno'].astype(str)
    
    # Parse won
    df['plc'] = df['plc'].astype(str)
    df['won'] = df['plc'].apply(lambda x: 1 if x.strip() == '1' else 0)
    
    # Parse position
    def parse_pos(x):
        try:
            val = x.strip()
            if 'DH' in val:
                val = val.replace('DH', '').strip()
            return float(val)
        except:
            return 7.0
    df['result_num'] = df['plc'].apply(parse_pos)
    
    df['draw'] = pd.to_numeric(df['draw'], errors='coerce').fillna(5)
    df['actual_weight'] = pd.to_numeric(df['actualwt'], errors='coerce').fillna(120)
    df['declared_weight'] = pd.to_numeric(df['declarwt'], errors='coerce').fillna(1050)
    df['horse_rating'] = 40.0 # Missing in results.csv
    
    df['class_int'] = df['class'].astype(str).str.extract(r'(\d+)')[0]
    df['class_int'] = pd.to_numeric(df['class_int'], errors='coerce').fillna(4)

    df = df.sort_values(by=['date', 'race_id'])
    df = df.sort_values(by=['horse_id', 'date'])

    # Time shifts
    df['prev_date'] = df.groupby('horse_id')['date'].shift(1)
    df['days_since_last_run'] = (df['date'] - df['prev_date']).dt.days.fillna(30).clip(0, 365)
    
    df['prev_class'] = df.groupby('horse_id')['class_int'].shift(1).fillna(df['class_int'])
    df['class_diff'] = df['class_int'] - df['prev_class']
    df['rating_diff'] = 0.0 # No ratings
    
    df['gear_changed'] = 0
    df['gear_win_rate'] = 0.0

    # Recent Form
    df['shifted_result'] = df.groupby('horse_id')['result_num'].shift(1)
    df['recent_avg_pos'] = df.groupby('horse_id')['shifted_result'].rolling(window=4, min_periods=1).mean().reset_index(level=0, drop=True).fillna(7.0)
    
    df['shifted_won'] = df.groupby('horse_id')['won'].shift(1)
    df['recent_win_rate'] = df.groupby('horse_id')['shifted_won'].rolling(window=4, min_periods=1).mean().reset_index(level=0, drop=True).fillna(0.0)
    
    # Distance win rate
    df['is_this_dist'] = 1
    df['cum_dist_runs'] = df.groupby(['horse_id', 'distance'])['is_this_dist'].cumsum() - 1
    df['cum_dist_wins'] = df.groupby(['horse_id', 'distance'])['won'].cumsum() - df['won']
    df['distance_win_rate'] = np.where(df['cum_dist_runs'] > 0, df['cum_dist_wins'] / df['cum_dist_runs'], 0.0)

    # Vet finding
    comments = comments.rename(columns={'raceno': 'race_no', 'horseno': 'horse_no'})
    df['race_no'] = df['raceno']
    df['horse_no'] = df['horseno']
    df = pd.merge(df, comments[['date', 'race_no', 'horse_no', 'comment']], on=['date', 'race_no', 'horse_no'], how='left')
    
    vet_keywords = ['lame', 'blood', 'trachea', 'heart']
    df['vet_finding'] = df['comment'].fillna('').str.lower().apply(lambda x: 1 if any(k in x for k in vet_keywords) else 0)
    
    df = df.sort_values(by=['horse_id', 'date'])
    df['prev_run_vet_finding'] = df.groupby('horse_id')['vet_finding'].shift(1).fillna(0)

    # Venue & going
    df['is_ST'] = (df['venue'].isin(['Sha Tin', 'ST'])).astype(int)
    df['is_HV'] = (df['venue'].isin(['Happy Valley', 'HV'])).astype(int)
    df['won_ST'] = ((df['venue'].isin(['Sha Tin', 'ST'])) & (df['won'] == 1)).astype(int)
    df['won_HV'] = ((df['venue'].isin(['Happy Valley', 'HV'])) & (df['won'] == 1)).astype(int)

    df['cum_ST_runs'] = df.groupby('horse_id')['is_ST'].cumsum().shift(1).fillna(0)
    df['cum_HV_runs'] = df.groupby('horse_id')['is_HV'].cumsum().shift(1).fillna(0)
    df['cum_ST_wins'] = df.groupby('horse_id')['won_ST'].cumsum().shift(1).fillna(0)
    df['cum_HV_wins'] = df.groupby('horse_id')['won_HV'].cumsum().shift(1).fillna(0)
    
    df['ST_win_rate'] = np.where(df['cum_ST_runs'] > 0, df['cum_ST_wins'] / df['cum_ST_runs'], 0)
    df['HV_win_rate'] = np.where(df['cum_HV_runs'] > 0, df['cum_HV_wins'] / df['cum_HV_runs'], 0)
    df['ST_vs_HV_pref'] = np.where(df['ST_win_rate'] > df['HV_win_rate'], 'Sha Tin', np.where(df['HV_win_rate'] > df['ST_win_rate'], 'Happy Valley', 'Neutral'))
    
    df['placed'] = (df['result_num'] <= 3).astype(int)
    df['temp_form_going'] = np.where(df['placed'] == 1, df['going'], np.nan)
    df['last_form_going'] = df.groupby('horse_id')['temp_form_going'].ffill().shift(1).fillna('Unknown')
    
    df['last_win_rating'] = 40.0
    df['config'] = df.get('course', 'Unknown')
    
    # Jockey and Trainer
    df['is_jockey_run'] = 1
    df['cum_jockey_runs'] = df.groupby('jockey')['is_jockey_run'].cumsum().shift(1).fillna(0)
    df['cum_jockey_wins'] = df.groupby('jockey')['won'].cumsum().shift(1).fillna(0)
    df['jockey_win_rate'] = np.where(df['cum_jockey_runs'] > 0, df['cum_jockey_wins'] / df['cum_jockey_runs'], 0.08)
    
    df['is_trainer_run'] = 1
    df['cum_trainer_runs'] = df.groupby('trainer')['is_trainer_run'].cumsum().shift(1).fillna(0)
    df['cum_trainer_wins'] = df.groupby('trainer')['won'].cumsum().shift(1).fillna(0)
    df['trainer_win_rate'] = np.where(df['cum_trainer_runs'] > 0, df['cum_trainer_wins'] / df['cum_trainer_runs'], 0.08)
    
    df['win_odds'] = pd.to_numeric(df['winodds'], errors='coerce').fillna(20.0).replace(0, 20.0)
    df['implied_prob'] = 1.0 / df['win_odds']
    df['norm_implied_prob'] = df['implied_prob'] / df.groupby('race_id')['implied_prob'].transform('sum')

    features_to_keep = ['race_id', 'horse_id', 'clean_name', 'won', 'draw', 'actual_weight', 'declared_weight', 'horse_rating', 
                        'last_win_rating', 'ST_win_rate', 'HV_win_rate', 'last_form_going', 'ST_vs_HV_pref',
                        'days_since_last_run', 'class_diff', 'rating_diff', 'gear_changed', 'recent_avg_pos', 'recent_win_rate',
                        'distance_win_rate', 'gear_win_rate', 'jockey_win_rate', 'trainer_win_rate', 'venue', 'going', 'config', 'norm_implied_prob', 'prev_run_vet_finding']
    
    # Check for missing cols
    for col in features_to_keep:
        if col not in df.columns:
            print("Missing col:", col)
            df[col] = 0

    df_out = df[features_to_keep]
    print(f"Generated {len(df_out)} rows with {df_out['prev_run_vet_finding'].sum()} vet findings.")
    
    existing = pd.read_csv('data/train_horse_features.csv')
    # Filter out any exact duplicates by race_id and horse_id if present
    existing_keys = set(zip(existing['race_id'], existing['horse_id']))
    df_out = df_out[~df_out.apply(lambda row: (row['race_id'], row['horse_id']) in existing_keys, axis=1)]
    
    combined = pd.concat([existing, df_out], ignore_index=True)
    combined.to_csv('data/train_horse_features.csv', index=False)
    print(f"Appended {len(df_out)} successfully! Total rows now {len(combined)}.")

if __name__ == '__main__':
    build_features_from_results()

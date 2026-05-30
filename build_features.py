import pandas as pd
import numpy as np

def build_features():
    print("Loading datasets...")
    races = pd.read_csv('data/races.csv')
    runs = pd.read_csv('data/runs.csv')
    horse_info = pd.read_csv('data/horse_info.csv')
    
    comments = pd.read_csv('data/comments.csv')
    
    # Map horse_id to clean_name
    horse_info['horse_id'] = horse_info['Unnamed: 0']
    horse_info['clean_name'] = horse_info['horse'].str.extract(r'^(.*?)\(')[0].str.strip().str.upper()
    horse_map = horse_info[['horse_id', 'clean_name']].drop_duplicates()
    
    print("Merging data...")
    df = pd.merge(runs, races[['race_id', 'date', 'venue', 'config', 'surface', 'going', 'distance', 'race_class', 'race_no']], on='race_id', how='inner')
    df = pd.merge(df, horse_map, on='horse_id', how='left')
    
    # Ensure date is datetime and sort
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values(by=['date', 'race_id'])
    
    print("Calculating historical features...")
    
    # Parse race_class
    def parse_class(c):
        c = str(c)
        if '1' in c: return 1
        if '2' in c: return 2
        if '3' in c: return 3
        if '4' in c: return 4
        if '5' in c: return 5
        if 'Group' in c or 'G' in c: return 0
        return 4 # Default
    df['class_int'] = df['race_class'].apply(parse_class)
    
    # Sort by horse and date
    df = df.sort_values(by=['horse_id', 'date'])
    
    # Grouped shifts for previous race info
    df['prev_date'] = df.groupby('horse_id')['date'].shift(1)
    df['days_since_last_run'] = (df['date'] - df['prev_date']).dt.days.fillna(30) # Default to 30 days
    df['days_since_last_run'] = np.clip(df['days_since_last_run'], 0, 365) # Cap at 1 year
    
    # Parse comments for vet findings
    comments['date'] = pd.to_datetime(comments['date'])
    comments = comments.rename(columns={'raceno': 'race_no', 'horseno': 'horse_no'})
    df = pd.merge(df, comments[['date', 'race_no', 'horse_no', 'comment']], on=['date', 'race_no', 'horse_no'], how='left')
    
    vet_keywords = ['lame', 'blood', 'trachea', 'heart']
    df['vet_finding'] = df['comment'].fillna('').str.lower().apply(lambda x: 1 if any(k in x for k in vet_keywords) else 0)
    
    # Needs to be sorted again just in case merge messed it up
    df = df.sort_values(by=['horse_id', 'date'])
    df['prev_run_vet_finding'] = df.groupby('horse_id')['vet_finding'].shift(1).fillna(0)
    
    df['prev_class'] = df.groupby('horse_id')['class_int'].shift(1).fillna(df['class_int'])
    df['class_diff'] = df['class_int'] - df['prev_class'] # Drop in class (e.g. from 3 to 4) = +1
    
    df['prev_rating'] = df.groupby('horse_id')['horse_rating'].shift(1).fillna(df['horse_rating'])
    df['rating_diff'] = df['horse_rating'] - df['prev_rating']
    
    # Normalize gear
    def norm_gear(g):
        if not isinstance(g, str) or g.strip() in ['', '--', 'nan']: return '--'
        return '/'.join(sorted([x.strip() for x in g.split('/') if x.strip()]))
    
    df['horse_gear'] = df['horse_gear'].apply(norm_gear)
    
    df['prev_gear'] = df.groupby('horse_id')['horse_gear'].shift(1).fillna('--')
    df['gear_changed'] = (df['horse_gear'] != df['prev_gear']).astype(int)
    
    # Recent Form (last 4 runs)
    df['result_num'] = pd.to_numeric(df['result'], errors='coerce').fillna(7) # default to mid-pack
    
    # Rolling averages excluding the current row by shifting first
    df['shifted_result'] = df.groupby('horse_id')['result_num'].shift(1)
    df['recent_avg_pos'] = df.groupby('horse_id')['shifted_result'].rolling(window=4, min_periods=1).mean().reset_index(level=0, drop=True)
    df['recent_avg_pos'] = df['recent_avg_pos'].fillna(7.0)
    
    df['shifted_won'] = df.groupby('horse_id')['won'].shift(1)
    df['recent_win_rate'] = df.groupby('horse_id')['shifted_won'].rolling(window=4, min_periods=1).mean().reset_index(level=0, drop=True)
    df['recent_win_rate'] = df['recent_win_rate'].fillna(0.0)
    
    # Track & Distance Prefs
    df['is_ST'] = (df['venue'].isin(['Sha Tin', 'ST'])).astype(int)
    df['is_HV'] = (df['venue'].isin(['Happy Valley', 'HV'])).astype(int)
    df['won_ST'] = ((df['venue'].isin(['Sha Tin', 'ST'])) & (df['won'] == 1)).astype(int)
    df['won_HV'] = ((df['venue'].isin(['Happy Valley', 'HV'])) & (df['won'] == 1)).astype(int)
    df['placed'] = (df['result_num'] <= 3).astype(int)
    
    df['cum_ST_runs'] = df.groupby('horse_id')['is_ST'].cumsum().shift(1).fillna(0)
    df['cum_HV_runs'] = df.groupby('horse_id')['is_HV'].cumsum().shift(1).fillna(0)
    df['cum_ST_wins'] = df.groupby('horse_id')['won_ST'].cumsum().shift(1).fillna(0)
    df['cum_HV_wins'] = df.groupby('horse_id')['won_HV'].cumsum().shift(1).fillna(0)
    
    # Reset cum counts to 0 where horse_id changes due to shift
    df['prev_horse_id'] = df['horse_id'].shift(1)
    mask = (df['horse_id'] != df['prev_horse_id'])
    df.loc[mask, ['cum_ST_runs', 'cum_HV_runs', 'cum_ST_wins', 'cum_HV_wins']] = 0
    
    df['ST_win_rate'] = np.where(df['cum_ST_runs'] > 0, df['cum_ST_wins'] / df['cum_ST_runs'], 0)
    df['HV_win_rate'] = np.where(df['cum_HV_runs'] > 0, df['cum_HV_wins'] / df['cum_HV_runs'], 0)
    
    df['ST_vs_HV_pref'] = np.where(
        df['ST_win_rate'] > df['HV_win_rate'], 'Sha Tin',
        np.where(df['HV_win_rate'] > df['ST_win_rate'], 'Happy Valley', 'Neutral')
    )
    
    # Distance win rate
    df['is_this_dist'] = 1
    df['cum_dist_runs'] = df.groupby(['horse_id', 'distance'])['is_this_dist'].cumsum() - 1
    df['cum_dist_wins'] = df.groupby(['horse_id', 'distance'])['won'].cumsum() - df['won']
    df['distance_win_rate'] = np.where(df['cum_dist_runs'] > 0, df['cum_dist_wins'] / df['cum_dist_runs'], 0)
    
    # Gear win rate
    df['is_this_gear'] = 1
    df['cum_gear_runs'] = df.groupby(['horse_id', 'horse_gear'])['is_this_gear'].cumsum() - 1
    df['cum_gear_wins'] = df.groupby(['horse_id', 'horse_gear'])['won'].cumsum() - df['won']
    df['gear_win_rate'] = np.where(df['cum_gear_runs'] > 0, df['cum_gear_wins'] / df['cum_gear_runs'], 0)
    
    # Last Win Rating
    df['temp_win_rtg'] = np.where(df['won'] == 1, df['horse_rating'], np.nan)
    df['last_win_rating'] = df.groupby('horse_id')['temp_win_rtg'].ffill().shift(1)
    df.loc[mask, 'last_win_rating'] = np.nan
    
    # Last form going
    df['temp_form_going'] = np.where(df['placed'] == 1, df['going'], np.nan)
    df['last_form_going'] = df.groupby('horse_id')['temp_form_going'].ffill().shift(1)
    df.loc[mask, 'last_form_going'] = 'Unknown'
    df['last_form_going'] = df['last_form_going'].fillna('Unknown')
    
    # Jockey and Trainer Win Rates (from runs.csv)
    df['is_jockey_run'] = 1
    df['cum_jockey_runs'] = df.groupby('jockey_id')['is_jockey_run'].cumsum().shift(1).fillna(0)
    df['cum_jockey_wins'] = df.groupby('jockey_id')['won'].cumsum().shift(1).fillna(0)
    df['jockey_win_rate'] = np.where(df['cum_jockey_runs'] > 0, df['cum_jockey_wins'] / df['cum_jockey_runs'], 0.08) # 8% default
    
    df['is_trainer_run'] = 1
    df['cum_trainer_runs'] = df.groupby('trainer_id')['is_trainer_run'].cumsum().shift(1).fillna(0)
    df['cum_trainer_wins'] = df.groupby('trainer_id')['won'].cumsum().shift(1).fillna(0)
    df['trainer_win_rate'] = np.where(df['cum_trainer_runs'] > 0, df['cum_trainer_wins'] / df['cum_trainer_runs'], 0.08)
    
    train_df = df.copy()
    
    latest = df.groupby('horse_id').tail(1).copy()
    
    latest['cum_ST_runs'] += latest['is_ST']
    latest['cum_HV_runs'] += latest['is_HV']
    latest['cum_ST_wins'] += latest['won_ST']
    latest['cum_HV_wins'] += latest['won_HV']
    
    latest['ST_win_rate'] = np.where(latest['cum_ST_runs'] > 0, latest['cum_ST_wins'] / latest['cum_ST_runs'], 0)
    latest['HV_win_rate'] = np.where(latest['cum_HV_runs'] > 0, latest['cum_HV_wins'] / latest['cum_HV_runs'], 0)
    latest['ST_vs_HV_pref'] = np.where(
        latest['ST_win_rate'] > latest['HV_win_rate'], 'Sha Tin',
        np.where(latest['HV_win_rate'] > latest['ST_win_rate'], 'Happy Valley', 'Neutral')
    )
    
    latest['last_win_rating'] = np.where(latest['won'] == 1, latest['horse_rating'], latest['last_win_rating'])
    latest['last_form_going'] = np.where(latest['placed'] == 1, latest['going'], latest['last_form_going'])
    
    # We will compute recent_avg_pos, days_since_last_run natively in model.py during inference, or store them here.
    # It's better to store the latest values needed for inference.
    # Actually, days_since_last_run needs the last run date. 
    latest['last_run_date'] = latest['date']
    latest['last_race_class_int'] = latest['class_int']
    latest['last_horse_rating'] = latest['horse_rating']
    latest['last_gear'] = latest['horse_gear']
    
    live_stats = latest[['clean_name', 'last_win_rating', 'ST_win_rate', 'HV_win_rate', 'ST_vs_HV_pref', 'last_form_going', 
                         'recent_avg_pos', 'recent_win_rate', 'last_run_date', 'last_race_class_int', 'last_horse_rating', 'last_gear', 'distance_win_rate', 'prev_run_vet_finding']]
    live_stats = live_stats.dropna(subset=['clean_name'])
    
    live_stats.to_csv('data/latest_horse_stats.csv', index=False)
    print("Saved data/latest_horse_stats.csv")
    
    gear_stats = df.groupby(['clean_name', 'horse_gear']).tail(1)[['clean_name', 'horse_gear', 'gear_win_rate']]
    gear_stats = gear_stats.dropna(subset=['clean_name'])
    gear_stats.to_csv('data/gear_win_rates.csv', index=False)
    print("Saved data/gear_win_rates.csv")
    
    try:
        results = pd.read_csv('data/results.csv')
        def parse_won(x):
            x_str = str(x).strip()
            if x_str in ['1', '1.0', '1 DH'] or '1 DH' in x_str:
                return 1
            return 0
        results['won_calc'] = results['plc'].apply(parse_won)
        
        j_runs = results.groupby('jockey').size().reset_index(name='runs')
        j_wins = results.groupby('jockey')['won_calc'].sum().reset_index(name='wins')
        j_stats = pd.merge(j_runs, j_wins, on='jockey')
        j_stats['jockey_win_rate'] = np.where(j_stats['runs'] > 0, j_stats['wins'] / j_stats['runs'], 0.08)
        j_stats['jockey'] = j_stats['jockey'].str.strip().str.upper()
        j_stats[['jockey', 'jockey_win_rate']].to_csv('data/jockey_win_rates.csv', index=False)
        print("Saved data/jockey_win_rates.csv")
        
        t_runs = results.groupby('trainer').size().reset_index(name='runs')
        t_wins = results.groupby('trainer')['won_calc'].sum().reset_index(name='wins')
        t_stats = pd.merge(t_runs, t_wins, on='trainer')
        t_stats['trainer_win_rate'] = np.where(t_stats['runs'] > 0, t_stats['wins'] / t_stats['runs'], 0.08)
        t_stats['trainer'] = t_stats['trainer'].str.strip().str.upper()
        t_stats[['trainer', 'trainer_win_rate']].to_csv('data/trainer_win_rates.csv', index=False)
        print("Saved data/trainer_win_rates.csv")
    except Exception as e:
        print(f"Error computing jockey/trainer stats: {e}")
    
    # Clean up train_df and save
    df['win_odds'] = pd.to_numeric(df['win_odds'], errors='coerce').fillna(20.0).replace(0, 20.0)
    df['implied_prob'] = 1.0 / df['win_odds']
    df['norm_implied_prob'] = df['implied_prob'] / df.groupby('race_id')['implied_prob'].transform('sum')

    train_df = df.copy()

    features_to_keep = ['race_id', 'horse_id', 'clean_name', 'won', 'draw', 'actual_weight', 'declared_weight', 'horse_rating', 
                        'last_win_rating', 'ST_win_rate', 'HV_win_rate', 'last_form_going', 'ST_vs_HV_pref',
                        'days_since_last_run', 'class_diff', 'rating_diff', 'gear_changed', 'recent_avg_pos', 'recent_win_rate',
                        'distance_win_rate', 'gear_win_rate', 'jockey_win_rate', 'trainer_win_rate', 'venue', 'going', 'config', 'norm_implied_prob', 'prev_run_vet_finding']
    
    train_df = train_df[features_to_keep]
    train_df.to_csv('data/train_horse_features.csv', index=False)
    print("Saved data/train_horse_features.csv")

if __name__ == '__main__':
    build_features()

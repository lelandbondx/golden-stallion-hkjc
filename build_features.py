import pandas as pd
import numpy as np

def build_features():
    print("Loading datasets...")
    races = pd.read_csv('data/races.csv')
    runs = pd.read_csv('data/runs.csv')
    horse_info = pd.read_csv('data/horse_info.csv')
    
    # Map horse_id to clean_name
    horse_info['horse_id'] = horse_info['Unnamed: 0']
    horse_info['clean_name'] = horse_info['horse'].str.extract(r'^(.*?)\(')[0].str.strip().str.upper()
    horse_map = horse_info[['horse_id', 'clean_name']].drop_duplicates()
    
    print("Merging data...")
    df = pd.merge(runs, races[['race_id', 'date', 'venue', 'surface', 'going', 'distance', 'race_class']], on='race_id', how='inner')
    df = pd.merge(df, horse_map, on='horse_id', how='left')
    
    # Ensure date is datetime and sort
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values(by=['date', 'race_id'])
    
    # We will build features for each horse based on past performance
    print("Calculating historical features...")
    
    # Create empty columns
    df['last_win_rating'] = np.nan
    df['fav_venue'] = 'Unknown'
    df['fav_going'] = 'Unknown'
    df['ST_win_rate'] = 0.0
    df['HV_win_rate'] = 0.0
    
    # To avoid looping over DataFrame rows which is slow, we can use rolling/expanding grouped operations
    # 1. Last Win Rating
    win_ratings = df[df['won'] == 1][['horse_id', 'date', 'horse_rating']].rename(columns={'horse_rating': 'win_rating_val'})
    
    # Merge back as 'last_win_rating' using merge_asof or just by grouping
    # Since we only want PAST info, shift is needed
    
    df['is_ST'] = (df['venue'] == 'Sha Tin').astype(int)
    df['is_HV'] = (df['venue'] == 'Happy Valley').astype(int)
    df['won_ST'] = ((df['venue'] == 'Sha Tin') & (df['won'] == 1)).astype(int)
    df['won_HV'] = ((df['venue'] == 'Happy Valley') & (df['won'] == 1)).astype(int)
    df['placed'] = (df['result'] <= 3).astype(int)
    
    # Sort by horse_id and date
    df = df.sort_values(by=['horse_id', 'date'])
    
    # Shifted cumulative counts (so it only includes PAST races)
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
    
    # Last Win Rating
    # Create a temporary series of win rating, then forward fill
    df['temp_win_rtg'] = np.where(df['won'] == 1, df['horse_rating'], np.nan)
    df['last_win_rating'] = df.groupby('horse_id')['temp_win_rtg'].ffill().shift(1)
    df.loc[mask, 'last_win_rating'] = np.nan
    
    # Last form going
    df['temp_form_going'] = np.where(df['placed'] == 1, df['going'], np.nan)
    df['last_form_going'] = df.groupby('horse_id')['temp_form_going'].ffill().shift(1)
    df.loc[mask, 'last_form_going'] = 'Unknown'
    df['last_form_going'] = df['last_form_going'].fillna('Unknown')
    
    # Now we save the enhanced dataset for training
    features_to_keep = ['race_id', 'horse_id', 'clean_name', 'won', 'last_win_rating', 
                        'ST_win_rate', 'HV_win_rate', 'last_form_going']
    
    train_df = df.copy()
    
    # Save the LATEST stats for each horse for live predictions
    # We want the stats after their LAST race. 
    # To get this, we take the last row of each horse, but we must update the cumulative stats 
    # to include that last race!
    # Because for the NEXT live race, the last race is in the past.
    
    latest = df.groupby('horse_id').tail(1).copy()
    
    # Add the last race into the cumulative
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
    
    # Select only what we need for live predictions
    live_stats = latest[['clean_name', 'last_win_rating', 'ST_win_rate', 'HV_win_rate', 'ST_vs_HV_pref', 'last_form_going']]
    live_stats = live_stats.dropna(subset=['clean_name'])
    
    # Due to naming inconsistencies, let's keep it clean
    live_stats.to_csv('data/latest_horse_stats.csv', index=False)
    print("Saved data/latest_horse_stats.csv")
    
    # Save the training features
    train_df.to_csv('data/train_horse_features.csv', index=False)
    print("Saved data/train_horse_features.csv")

if __name__ == '__main__':
    build_features()

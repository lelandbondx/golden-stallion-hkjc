import os
import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
from datetime import datetime

MODEL_PATH = 'model.joblib'

# The complete list of features for XGBoost
ALL_FEATURES = [
    'draw', 'actual_weight', 'declared_weight', 'horse_rating', 'weight_rank', 'rating_rank', 
    'last_win_rating', 'ST_win_rate', 'HV_win_rate', 'track_pref_match', 'going_pref_match', 
    'consensus_score', 'days_since_last_run', 'class_diff', 'rating_diff', 'gear_changed', 
    'recent_avg_pos', 'recent_win_rate', 'distance_win_rate'
]

def prepare_features(df, is_live=False, venue=None, going=None, race_date=None, race_class_int=None):
    """
    Computes advanced relative features.
    If is_live is True, we assume df contains runners for a single race.
    """
    df = df.copy()
    
    for col, default_val in [('draw', 5), ('actual_weight', 120), ('declared_weight', 1050), ('horse_rating', 40), ('rtg', 40), ('win_odds', 20.0)]:
        if col not in df.columns:
            df[col] = default_val
            
    # Allow fallback for horse_rating if rtg is present
    if 'rtg' in df.columns and 'horse_rating' in df.columns:
        df['horse_rating'] = df['horse_rating'].fillna(df['rtg'])
        
    df['draw'] = pd.to_numeric(df['draw'], errors='coerce').fillna(5)
    df['actual_weight'] = pd.to_numeric(df['actual_weight'], errors='coerce').fillna(120)
    df['declared_weight'] = pd.to_numeric(df['declared_weight'], errors='coerce').fillna(1050)
    df['horse_rating'] = pd.to_numeric(df['horse_rating'], errors='coerce').fillna(40)
    df['win_odds'] = pd.to_numeric(df['win_odds'], errors='coerce').fillna(20.0)
    
    df['win_odds'] = df['win_odds'].replace(0, 20.0)
    df['implied_prob'] = 1.0 / df['win_odds']

    if is_live:
        total_implied = df['implied_prob'].sum()
        df['norm_implied_prob'] = df['implied_prob'] / total_implied if total_implied > 0 else df['implied_prob']
        
        df['weight_rank'] = df['actual_weight'].rank(ascending=False, method='min')
        df['rating_rank'] = df['horse_rating'].rank(ascending=False, method='min')
        
        df['current_venue'] = venue
        df['current_going'] = going
        
        # Calculate dynamic features
        # days_since_last_run
        if 'last_run_date' in df.columns and race_date:
            rd = pd.to_datetime(race_date)
            lrd = pd.to_datetime(df['last_run_date'], errors='coerce')
            df['days_since_last_run'] = (rd - lrd).dt.days.fillna(30).clip(0, 365)
        else:
            df['days_since_last_run'] = df.get('days_since_last_run', 30)
            
        # class_diff
        if 'last_race_class_int' in df.columns and race_class_int:
            df['class_diff'] = race_class_int - pd.to_numeric(df['last_race_class_int'], errors='coerce').fillna(race_class_int)
        else:
            df['class_diff'] = df.get('class_diff', 0)
            
        # rating_diff
        if 'last_horse_rating' in df.columns:
            df['rating_diff'] = df['horse_rating'] - pd.to_numeric(df['last_horse_rating'], errors='coerce').fillna(df['horse_rating'])
        else:
            df['rating_diff'] = df.get('rating_diff', 0)
            
        # gear_changed
        if 'last_gear' in df.columns and 'horse_gear' in df.columns:
            df['gear_changed'] = (df['horse_gear'] != df['last_gear']).astype(int)
        else:
            df['gear_changed'] = df.get('gear_changed', 0)
            
    else:
        # Historical data grouping
        if 'race_id' in df.columns:
            total_implied = df.groupby('race_id')['implied_prob'].transform('sum')
            df['norm_implied_prob'] = df['implied_prob'] / total_implied
            df['weight_rank'] = df.groupby('race_id')['actual_weight'].rank(ascending=False, method='min')
            df['rating_rank'] = df.groupby('race_id')['horse_rating'].rank(ascending=False, method='min')
        else:
            df['norm_implied_prob'] = df['implied_prob']
            df['weight_rank'] = 1
            df['rating_rank'] = 1
            
        df['current_venue'] = df.get('venue', 'Unknown')
        df['current_going'] = df.get('going', 'Unknown')

    df['ST_vs_HV_pref'] = df.get('ST_vs_HV_pref', 'Neutral').fillna('Neutral')
    df['last_form_going'] = df.get('last_form_going', 'Unknown').fillna('Unknown')
    
    df['track_pref_match'] = np.where(
        ((df['current_venue'].str.contains('Sha Tin', case=False, na=False)) & (df['ST_vs_HV_pref'] == 'Sha Tin')) |
        ((df['current_venue'].str.contains('Happy Valley', case=False, na=False)) & (df['ST_vs_HV_pref'] == 'Happy Valley')),
        1, 0
    )
    
    df['going_pref_match'] = np.where(
        (df['last_form_going'] != 'Unknown') & (df['current_going'].str.upper() == df['last_form_going'].str.upper()),
        1, 0
    )
    
    if 'consensus_score' not in df.columns:
        df['consensus_score'] = 0.0
    df['consensus_score'] = pd.to_numeric(df['consensus_score'], errors='coerce').fillna(0)

    # Fill any missing new features with safe defaults
    for f in ALL_FEATURES:
        if f not in df.columns:
            df[f] = 0.0
            
    return df

def train_and_save_model():
    print("Loading data for training...")
    try:
        if os.path.exists('data/train_horse_features.csv'):
            runs = pd.read_csv('data/train_horse_features.csv')
            
            runs['last_win_rating'] = runs['last_win_rating'].fillna(runs['horse_rating'])
            runs['ST_win_rate'] = runs['ST_win_rate'].fillna(0)
            runs['HV_win_rate'] = runs['HV_win_rate'].fillna(0)
            runs['ST_vs_HV_pref'] = runs['ST_vs_HV_pref'].fillna('Neutral')
            runs['last_form_going'] = runs['last_form_going'].fillna('Unknown')
            
            runs['days_since_last_run'] = runs['days_since_last_run'].fillna(30)
            runs['class_diff'] = runs['class_diff'].fillna(0)
            runs['rating_diff'] = runs['rating_diff'].fillna(0)
            runs['gear_changed'] = runs['gear_changed'].fillna(0)
            runs['recent_avg_pos'] = runs['recent_avg_pos'].fillna(7)
            runs['recent_win_rate'] = runs['recent_win_rate'].fillna(0)
            runs['distance_win_rate'] = runs['distance_win_rate'].fillna(0)
            runs['venue'] = runs['venue'].fillna('Unknown')
            runs['going'] = runs['going'].fillna('Unknown')
        else:
            return None
    except Exception as e:
        print(f"Error loading data: {e}. Model will not be trained.")
        return None

    if 'won' not in runs.columns:
        if 'result' in runs.columns:
            runs['won'] = (runs['result'] == 1).astype(int)
        else:
            return None

    # Feature Engineering
    runs = prepare_features(runs, is_live=False)
    
    train_data = runs.dropna(subset=ALL_FEATURES + ['won'])
    
    X = train_data[ALL_FEATURES]
    y = train_data['won']
    
    scale_pos_weight = (len(y) - sum(y)) / sum(y) if sum(y) > 0 else 1.0

    print("Training Enhanced XGBoost model with new factors...")
    model = xgb.XGBClassifier(
        n_estimators=500, 
        max_depth=6, 
        learning_rate=0.05, 
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale_pos_weight,
        eval_metric='logloss',
        use_label_encoder=False
    )
    model.fit(X, y)
    
    joblib.dump(model, MODEL_PATH)
    print("Model saved to", MODEL_PATH)
    return model

_loaded_model = None

def load_model():
    global _loaded_model
    if _loaded_model is not None:
        return _loaded_model
        
    if os.path.exists(MODEL_PATH):
        _loaded_model = joblib.load(MODEL_PATH)
        return _loaded_model
    else:
        _loaded_model = train_and_save_model()
        return _loaded_model

def predict_probabilities(df, venue=None, going=None, race_date=None, race_class_int=None):
    """
    Given a dataframe with current race cards, predict win probabilities.
    df must be a single race's runners.
    """
    model = load_model()
    if not model:
        return np.ones(len(df)) / len(df)
    
    live_df = df.copy()
    if os.path.exists('data/latest_horse_stats.csv'):
        stats_df = pd.read_csv('data/latest_horse_stats.csv')
        live_df['clean_name'] = live_df['name'].str.upper().str.strip()
        stats_df['clean_name'] = stats_df['clean_name'].str.upper().str.strip()
        cols_to_use = stats_df.columns.difference(live_df.columns).tolist() + ['clean_name']
        live_df = pd.merge(live_df, stats_df[cols_to_use], on='clean_name', how='left')
        
        # Fill NAs
        rating_col = live_df['horse_rating'] if 'horse_rating' in live_df.columns else live_df.get('rtg', 40)
        live_df['last_win_rating'] = live_df['last_win_rating'].fillna(rating_col)
        live_df['ST_win_rate'] = live_df['ST_win_rate'].fillna(0)
        live_df['HV_win_rate'] = live_df['HV_win_rate'].fillna(0)
        live_df['ST_vs_HV_pref'] = live_df['ST_vs_HV_pref'].fillna('Neutral')
        live_df['last_form_going'] = live_df['last_form_going'].fillna('Unknown')
        live_df['recent_avg_pos'] = live_df['recent_avg_pos'].fillna(7)
        live_df['recent_win_rate'] = live_df['recent_win_rate'].fillna(0)
        live_df['distance_win_rate'] = live_df['distance_win_rate'].fillna(0)
    else:
        for col in ['last_win_rating', 'ST_win_rate', 'HV_win_rate', 'recent_avg_pos', 'recent_win_rate', 'distance_win_rate']:
            live_df[col] = 0.0
        rating_col = live_df['horse_rating'] if 'horse_rating' in live_df.columns else live_df.get('rtg', 40)
        live_df['last_win_rating'] = rating_col
        live_df['ST_vs_HV_pref'] = 'Neutral'
        live_df['last_form_going'] = 'Unknown'
        
    if os.path.exists('data/gear_win_rates.csv') and 'horse_gear' in live_df.columns:
        gear_df = pd.read_csv('data/gear_win_rates.csv')
        gear_df['clean_name'] = gear_df['clean_name'].str.upper().str.strip()
        if 'gear_win_rate' in live_df.columns:
            live_df = live_df.drop(columns=['gear_win_rate'])
        live_df = pd.merge(live_df, gear_df, on=['clean_name', 'horse_gear'], how='left')
        live_df['gear_win_rate'] = live_df['gear_win_rate'].fillna(0)
    else:
        if 'gear_win_rate' not in live_df.columns:
            live_df['gear_win_rate'] = 0.0

    live_df = prepare_features(live_df, is_live=True, venue=venue, going=going, race_date=race_date, race_class_int=race_class_int)
    
    for f in ALL_FEATURES:
        if f not in live_df.columns:
            live_df[f] = 0.0
            
    X_live = live_df[ALL_FEATURES]
    probs = model.predict_proba(X_live)[:, 1]
    
    total_prob = probs.sum()
    if total_prob > 0:
        probs = probs / total_prob
        
    return probs, live_df

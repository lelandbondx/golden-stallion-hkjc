import os
import pandas as pd
import numpy as np
import xgboost as xgb
import joblib

MODEL_PATH = 'model.joblib'

def prepare_features(df, is_live=False, venue=None, going=None):
    """
    Computes advanced relative features.
    If is_live is True, we assume df contains runners for a single race.
    If is_live is False, df contains historical runs and must be grouped by race_id.
    """
    df = df.copy()
    
    # 1. Base cleanups
    df['draw'] = pd.to_numeric(df.get('draw', 5), errors='coerce').fillna(5)
    df['actual_weight'] = pd.to_numeric(df.get('actual_weight', 120), errors='coerce').fillna(120)
    df['declared_weight'] = pd.to_numeric(df.get('declared_weight', 1050), errors='coerce').fillna(1050)
    df['horse_rating'] = pd.to_numeric(df.get('horse_rating', df.get('rtg', 40)), errors='coerce').fillna(40)
    df['win_odds'] = pd.to_numeric(df.get('win_odds', 20.0), errors='coerce').fillna(20.0)
    
    # Prevent divide by zero
    df['win_odds'] = df['win_odds'].replace(0, 20.0)
    df['implied_prob'] = 1.0 / df['win_odds']

    if is_live:
        # Compute relative features for a single live race
        total_implied = df['implied_prob'].sum()
        df['norm_implied_prob'] = df['implied_prob'] / total_implied if total_implied > 0 else df['implied_prob']
        
        df['weight_rank'] = df['actual_weight'].rank(ascending=False, method='min')
        df['rating_rank'] = df['horse_rating'].rank(ascending=False, method='min')
        
        df['current_venue'] = venue
        df['current_going'] = going
    else:
        # Group by race_id for historical data
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

    # Track match and going match
    df['ST_vs_HV_pref'] = df.get('ST_vs_HV_pref', 'Neutral').fillna('Neutral')
    df['last_form_going'] = df.get('last_form_going', 'Unknown').fillna('Unknown')
    
    # Clean string matching
    df['track_pref_match'] = np.where(
        ((df['current_venue'].str.contains('Sha Tin', case=False, na=False)) & (df['ST_vs_HV_pref'] == 'Sha Tin')) |
        ((df['current_venue'].str.contains('Happy Valley', case=False, na=False)) & (df['ST_vs_HV_pref'] == 'Happy Valley')),
        1, 0
    )
    
    df['going_pref_match'] = np.where(
        (df['last_form_going'] != 'Unknown') & (df['current_going'].str.upper() == df['last_form_going'].str.upper()),
        1, 0
    )
    
    # Tips Index consensus score
    if 'consensus_score' not in df.columns:
        df['consensus_score'] = 0.0
    df['consensus_score'] = pd.to_numeric(df['consensus_score'], errors='coerce').fillna(0)

    return df

def train_and_save_model():
    print("Loading data for training...")
    try:
        runs = pd.read_csv('data/runs.csv')
        # Load enhanced features
        if os.path.exists('data/train_horse_features.csv'):
            enhanced = pd.read_csv('data/train_horse_features.csv')[['race_id', 'horse_id', 'last_win_rating', 'ST_win_rate', 'HV_win_rate', 'ST_vs_HV_pref', 'last_form_going', 'venue', 'going']]
            # Note: venue and going are already in runs.csv, but if we need them, we can use runs' own
            runs = pd.merge(runs, enhanced[['race_id', 'horse_id', 'last_win_rating', 'ST_win_rate', 'HV_win_rate', 'ST_vs_HV_pref', 'last_form_going']], on=['race_id', 'horse_id'], how='left')
            runs['last_win_rating'] = runs['last_win_rating'].fillna(runs['horse_rating'])
            runs['ST_win_rate'] = runs['ST_win_rate'].fillna(0)
            runs['HV_win_rate'] = runs['HV_win_rate'].fillna(0)
            runs['ST_vs_HV_pref'] = runs['ST_vs_HV_pref'].fillna('Neutral')
            runs['last_form_going'] = runs['last_form_going'].fillna('Unknown')
        else:
            runs['last_win_rating'] = runs['horse_rating']
            runs['ST_win_rate'] = 0.0
            runs['HV_win_rate'] = 0.0
            runs['ST_vs_HV_pref'] = 'Neutral'
            runs['last_form_going'] = 'Unknown'
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
    
    # Features to use for training
    features = ['draw', 'actual_weight', 'declared_weight', 'horse_rating', 'weight_rank', 'rating_rank', 'last_win_rating', 'ST_win_rate', 'HV_win_rate', 'track_pref_match', 'going_pref_match', 'consensus_score']
    
    # Drop rows with NaN in features or target
    train_data = runs.dropna(subset=features + ['won'])
    
    X = train_data[features]
    y = train_data['won']
    
    # Handle class imbalance (winners are minority)
    scale_pos_weight = (len(y) - sum(y)) / sum(y) if sum(y) > 0 else 1.0

    print("Training Enhanced XGBoost model...")
    model = xgb.XGBClassifier(
        n_estimators=400, 
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

def load_model():
    if os.path.exists(MODEL_PATH):
        return joblib.load(MODEL_PATH)
    else:
        return train_and_save_model()

def predict_probabilities(df, venue=None, going=None):
    """
    Given a dataframe with current race cards, predict win probabilities.
    df must be a single race's runners.
    """
    model = load_model()
    if not model:
        return np.ones(len(df)) / len(df) # Uniform probability fallback
    
    # Merge live runners with latest historical stats FIRST so prepare_features can use them
    live_df = df.copy()
    if os.path.exists('data/latest_horse_stats.csv'):
        stats_df = pd.read_csv('data/latest_horse_stats.csv')
        live_df['clean_name'] = live_df['name'].str.upper().str.strip()
        stats_df['clean_name'] = stats_df['clean_name'].str.upper().str.strip()
        live_df = pd.merge(live_df, stats_df, on='clean_name', how='left')
        live_df['last_win_rating'] = live_df['last_win_rating'].fillna(live_df['horse_rating'])
        live_df['ST_win_rate'] = live_df['ST_win_rate'].fillna(0)
        live_df['HV_win_rate'] = live_df['HV_win_rate'].fillna(0)
        live_df['ST_vs_HV_pref'] = live_df['ST_vs_HV_pref'].fillna('Neutral')
        live_df['last_form_going'] = live_df['last_form_going'].fillna('Unknown')
    else:
        live_df['last_win_rating'] = live_df['horse_rating']
        live_df['ST_win_rate'] = 0.0
        live_df['HV_win_rate'] = 0.0
        live_df['ST_vs_HV_pref'] = 'Neutral'
        live_df['last_form_going'] = 'Unknown'

    # Prepare features identically to training phase
    live_df = prepare_features(live_df, is_live=True, venue=venue, going=going)
    
    features = ['draw', 'actual_weight', 'declared_weight', 'horse_rating', 'weight_rank', 'rating_rank', 'last_win_rating', 'ST_win_rate', 'HV_win_rate', 'track_pref_match', 'going_pref_match', 'consensus_score']
    
    # Ensure all features exist in the dataframe
    for f in features:
        if f not in live_df.columns:
            live_df[f] = 0.0
            
    X_live = live_df[features]
    probs = model.predict_proba(X_live)[:, 1] # Probability of winning
    
    # Normalize probabilities per race so they sum to 1
    total_prob = probs.sum()
    if total_prob > 0:
        probs = probs / total_prob
        
    return probs

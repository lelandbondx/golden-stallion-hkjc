import os
import pandas as pd
import numpy as np
import xgboost as xgb
import joblib

MODEL_PATH = 'model.joblib'

def prepare_features(df, is_live=False):
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

    return df

def train_and_save_model():
    print("Loading data for training...")
    try:
        runs = pd.read_csv('data/runs.csv')
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
    features = ['draw', 'actual_weight', 'declared_weight', 'horse_rating', 'weight_rank', 'rating_rank']
    
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

def predict_probabilities(df):
    """
    Given a dataframe with current race cards, predict win probabilities.
    df must be a single race's runners.
    """
    model = load_model()
    if not model:
        return np.ones(len(df)) / len(df) # Uniform probability fallback
    
    # Prepare features identically to training phase
    live_df = prepare_features(df, is_live=True)
    
    features = ['draw', 'actual_weight', 'declared_weight', 'horse_rating', 'weight_rank', 'rating_rank']
    
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

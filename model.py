import os
import pandas as pd
import numpy as np
import xgboost as xgb
import joblib

MODEL_PATH = 'model.joblib'

def calculate_win_rates(df, col_name, new_col_name):
    win_rates = df.groupby(col_name)['won'].mean().reset_index()
    win_rates.rename(columns={'won': new_col_name}, inplace=True)
    return win_rates

def train_and_save_model():
    print("Loading data for training...")
    try:
        runs = pd.read_csv('data/runs.csv')
        races = pd.read_csv('data/races.csv')
    except Exception as e:
        print(f"Error loading data: {e}. Model will not be trained.")
        return None

    # We need a 'won' column. It's usually present, or we derive it from 'result'
    if 'won' not in runs.columns:
        if 'result' in runs.columns:
            runs['won'] = (runs['result'] == 1).astype(int)
        else:
            return None

    # Select basic features
    # Ensure they exist or fillna
    features = ['draw', 'actual_weight', 'declared_weight', 'horse_rating', 'win_odds']
    for f in features:
        if f not in runs.columns:
            runs[f] = 0
            
    # Clean up NaN inputs for new statistical parameters
    runs['horse_rating'] = pd.to_numeric(runs['horse_rating'], errors='coerce').fillna(40)
    runs['win_odds'] = pd.to_numeric(runs['win_odds'], errors='coerce').fillna(20.0)
            
    # Jockey and Trainer win rates
    if 'jockey_id' in runs.columns:
        jockey_rates = calculate_win_rates(runs, 'jockey_id', 'jockey_win_rate')
        runs = runs.merge(jockey_rates, on='jockey_id', how='left')
    else:
        runs['jockey_win_rate'] = 0.08
        
    if 'trainer_id' in runs.columns:
        trainer_rates = calculate_win_rates(runs, 'trainer_id', 'trainer_win_rate')
        runs = runs.merge(trainer_rates, on='trainer_id', how='left')
    else:
        runs['trainer_win_rate'] = 0.08

    model_features = features + ['jockey_win_rate', 'trainer_win_rate']
    
    # Drop rows with NaN in features or target
    train_data = runs.dropna(subset=model_features + ['won'])
    
    X = train_data[model_features]
    y = train_data['won']
    
    print("Training Enhanced XGBoost model...")
    model = xgb.XGBClassifier(
        n_estimators=300, 
        max_depth=5, 
        learning_rate=0.03, 
        subsample=0.8,
        colsample_bytree=0.8,
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
    df must have 'draw', 'actual_weight', 'declared_weight', 'jockey', 'trainer'
    We map jockey and trainer to basic win rates (Zac Purton gets a boost)
    """
    model = load_model()
    if not model:
        return np.ones(len(df)) / len(df) # Uniform probability fallback
    
    features = []
    for _, row in df.iterrows():
        # Heuristic mapping for live data
        jockey_str = str(row.get('jockey', ''))
        if 'Purton' in jockey_str:
            j_rate = 0.18
        elif any(j in jockey_str for j in ['Bowman', 'Teetan', 'Ho', 'Avdulla']):
            j_rate = 0.12
        else:
            j_rate = 0.06
            
        trainer_str = str(row.get('trainer', ''))
        if any(t in trainer_str for t in ['Size', 'Lui', 'Cruz']):
            t_rate = 0.13
        elif any(t in trainer_str for t in ['Richards', 'Fownes', 'Hayes']):
            t_rate = 0.10
        else:
            t_rate = 0.06
        
        draw = pd.to_numeric(row.get('draw', 5), errors='coerce')
        if pd.isna(draw): draw = 5
        
        actual_weight = pd.to_numeric(row.get('actual_weight', 120), errors='coerce')
        if pd.isna(actual_weight): actual_weight = 120
            
        declared_weight = pd.to_numeric(row.get('declared_weight', 1050), errors='coerce')
        if pd.isna(declared_weight): declared_weight = 1050
            
        rtg = pd.to_numeric(row.get('rtg', 40), errors='coerce')
        if pd.isna(rtg): rtg = 40
            
        win_odds = pd.to_numeric(row.get('win_odds', 20.0), errors='coerce')
        if pd.isna(win_odds): win_odds = 20.0
            
        features.append({
            'draw': draw,
            'actual_weight': actual_weight,
            'declared_weight': declared_weight,
            'horse_rating': rtg,
            'win_odds': win_odds,
            'jockey_win_rate': j_rate,
            'trainer_win_rate': t_rate
        })
        
    X_live = pd.DataFrame(features)
    probs = model.predict_proba(X_live)[:, 1] # Probability of winning
    
    # Normalize probabilities per race so they sum to 1
    # Assuming df is passed per race
    total_prob = probs.sum()
    if total_prob > 0:
        probs = probs / total_prob
        
    return probs

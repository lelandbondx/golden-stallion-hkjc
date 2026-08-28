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
    'last_win_rating', 'ST_win_rate', 'HV_win_rate', 'AWT_win_rate', 'Turf_win_rate', 'track_pref_match', 'going_pref_match', 'surface_pref_match',
    'days_since_last_run', 'class_diff', 'rating_diff', 'gear_changed', 
    'recent_avg_pos', 'recent_win_rate', 'distance_win_rate', 'gear_win_rate', 'jockey_win_rate', 'trainer_win_rate',
    'norm_implied_prob', 'prev_run_vet_finding'
]

def prepare_features(df, is_live=False, venue=None, going=None, race_date=None, race_class_int=None, track_type=None):
    """
    Computes advanced relative features.
    If is_live is True, we assume df contains runners for a single race.
    """
    df = df.copy()
    
    if 'rtg' in df.columns:
        if 'horse_rating' not in df.columns:
            df['horse_rating'] = df['rtg']
        else:
            df['horse_rating'] = df['horse_rating'].fillna(df['rtg'])
            
    for col, default_val in [('draw', 5), ('actual_weight', 120), ('declared_weight', 1050), ('horse_rating', 40), ('rtg', 40), ('win_odds', 20.0)]:
        if col not in df.columns:
            df[col] = default_val
        
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
        
        # Track surface extraction (0: Turf, 1: AWT)
        track_str = str(track_type or 'TURF').upper()
        df['current_surface'] = 1 if ('ALL WEATHER' in track_str or 'AWT' in track_str) else 0
        
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
        df['current_surface'] = df.get('surface', 0)

    df['ST_vs_HV_pref'] = df.get('ST_vs_HV_pref', 'Neutral').fillna('Neutral')
    df['last_form_going'] = df.get('last_form_going', 'Unknown').fillna('Unknown')
    
    df['track_pref_match'] = np.where(
        ((df['current_venue'].str.contains('Sha Tin', case=False, na=False)) & (df['ST_vs_HV_pref'] == 'Sha Tin')) |
        ((df['current_venue'].str.contains('Happy Valley', case=False, na=False)) & (df['ST_vs_HV_pref'] == 'Happy Valley')),
        1, 0
    )
    
    def normalize_going(g):
        if not isinstance(g, str): return "UNKNOWN"
        g = g.upper()
        if "FIRM" in g: return "FIRM"
        if "YIELD" in g or "SOFT" in g or "HEAVY" in g: return "SOFT"
        if "GOOD" in g: return "GOOD"
        if "WET" in g: return "WET"
        return "UNKNOWN"

    df['norm_current_going'] = df['current_going'].apply(normalize_going)
    df['norm_last_going'] = df['last_form_going'].apply(normalize_going)
    
    df['going_pref_match'] = np.where(
        (df['last_form_going'] != 'Unknown') & (df['norm_current_going'] == df['norm_last_going']) & (df['norm_current_going'] != 'UNKNOWN'),
        1, 0
    )
    
    df['AWT_vs_Turf_pref'] = df.get('AWT_vs_Turf_pref', 'Neutral').fillna('Neutral')
    df['AWT_win_rate'] = pd.to_numeric(df.get('AWT_win_rate', 0.0), errors='coerce').fillna(0.0)
    df['Turf_win_rate'] = pd.to_numeric(df.get('Turf_win_rate', 0.0), errors='coerce').fillna(0.0)
    
    df['surface_pref_match'] = np.where(
        ((df['current_surface'] == 1) & (df['AWT_vs_Turf_pref'] == 'AWT')) |
        ((df['current_surface'] == 0) & (df['AWT_vs_Turf_pref'] == 'Turf')),
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
            runs['AWT_win_rate'] = runs['AWT_win_rate'].fillna(0)
            runs['Turf_win_rate'] = runs['Turf_win_rate'].fillna(0)
            runs['ST_vs_HV_pref'] = runs['ST_vs_HV_pref'].fillna('Neutral')
            runs['AWT_vs_Turf_pref'] = runs['AWT_vs_Turf_pref'].fillna('Neutral')
            runs['last_form_going'] = runs['last_form_going'].fillna('Unknown')
            
            runs['days_since_last_run'] = runs['days_since_last_run'].fillna(30)
            runs['class_diff'] = runs['class_diff'].fillna(0)
            runs['rating_diff'] = runs['rating_diff'].fillna(0)
            runs['gear_changed'] = runs['gear_changed'].fillna(0)
            runs['recent_avg_pos'] = runs['recent_avg_pos'].fillna(7)
            runs['recent_win_rate'] = runs['recent_win_rate'].fillna(0)
            runs['distance_win_rate'] = runs['distance_win_rate'].fillna(0)
            runs['gear_win_rate'] = runs.get('gear_win_rate', 0).fillna(0)
            runs['prev_run_vet_finding'] = runs.get('prev_run_vet_finding', 0).fillna(0)
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
        random_state=42
    )
    model.fit(X, y)
    
    joblib.dump(model, MODEL_PATH)
    print("Model saved to", MODEL_PATH)
    return model

_loaded_model = None
_model_mtime = None

def load_model():
    global _loaded_model, _model_mtime
    
    if os.path.exists(MODEL_PATH):
        current_mtime = os.path.getmtime(MODEL_PATH)
        if _loaded_model is None or _model_mtime != current_mtime:
            _loaded_model = joblib.load(MODEL_PATH)
            _model_mtime = current_mtime
        return _loaded_model
    else:
        _loaded_model = train_and_save_model()
        if os.path.exists(MODEL_PATH):
            _model_mtime = os.path.getmtime(MODEL_PATH)
        return _loaded_model

def predict_probabilities(df, venue=None, going=None, race_date=None, race_class_int=None, track_type=None):
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
        live_df['AWT_win_rate'] = live_df['AWT_win_rate'].fillna(0)
        live_df['Turf_win_rate'] = live_df['Turf_win_rate'].fillna(0)
        live_df['ST_vs_HV_pref'] = live_df['ST_vs_HV_pref'].fillna('Neutral')
        live_df['AWT_vs_Turf_pref'] = live_df['AWT_vs_Turf_pref'].fillna('Neutral')
        live_df['last_form_going'] = live_df['last_form_going'].fillna('Unknown')
        live_df['recent_avg_pos'] = live_df['recent_avg_pos'].fillna(7)
        live_df['recent_win_rate'] = live_df['recent_win_rate'].fillna(0)
        live_df['distance_win_rate'] = live_df['distance_win_rate'].fillna(0)
        live_df['prev_run_vet_finding'] = live_df.get('prev_run_vet_finding', 0).fillna(0)
        live_df['has_overseas_form'] = live_df.get('has_overseas_form', 0).fillna(0)
    else:
        for col in ['last_win_rating', 'ST_win_rate', 'HV_win_rate', 'AWT_win_rate', 'Turf_win_rate', 'recent_avg_pos', 'recent_win_rate', 'distance_win_rate', 'prev_run_vet_finding', 'has_overseas_form']:
            live_df[col] = 0.0
        rating_col = live_df['horse_rating'] if 'horse_rating' in live_df.columns else live_df.get('rtg', 40)
        live_df['last_win_rating'] = rating_col
        live_df['ST_vs_HV_pref'] = 'Neutral'
        live_df['AWT_vs_Turf_pref'] = 'Neutral'
        live_df['last_form_going'] = 'Unknown'
        
    if os.path.exists('data/gear_win_rates.csv') and 'horse_gear' in live_df.columns:
        def norm_gear(g):
            if not isinstance(g, str) or g.strip() in ['', '--', 'nan']: return '--'
            return '/'.join(sorted([x.strip() for x in str(g).split('/') if x.strip()]))
            
        live_df['horse_gear'] = live_df['horse_gear'].apply(norm_gear)
        
        gear_df = pd.read_csv('data/gear_win_rates.csv')
        gear_df['clean_name'] = gear_df['clean_name'].str.upper().str.strip()
        if 'gear_win_rate' in live_df.columns:
            live_df = live_df.drop(columns=['gear_win_rate'])
        live_df = pd.merge(live_df, gear_df, on=['clean_name', 'horse_gear'], how='left')
        live_df['gear_win_rate'] = live_df['gear_win_rate'].fillna(0)
    else:
        if 'gear_win_rate' not in live_df.columns:
            live_df['gear_win_rate'] = 0.0

    # Fallback dictionaries for modern jockeys/trainers not present in historical results.csv (post-2017)
    FALLBACK_JOCKEY_RATES = {
        'Z PURTON': 0.207, 'H BOWMAN': 0.109, 'K TEETAN': 0.08, 'C Y HO': 0.087,
        'A BADEL': 0.075, 'L HEWITSON': 0.06, 'A ATZENI': 0.105, 'L FERRARIS': 0.079,
        'B AVDULLA': 0.05, 'E C W WONG': 0.07, 'M CHADWICK': 0.07, 'Y L CHUNG': 0.06,
        'C L CHAU': 0.093, 'H BENTLEY': 0.077, 'K C LEUNG': 0.074, 'M F POON': 0.06,
        'H T MO': 0.04, 'A HAMELIN': 0.06, 'M L YEUNG': 0.04, 'K DE MELO': 0.08,
        'J ORMAN': 0.068, 'E BROWN': 0.10, 'P N WONG': 0.05, 'J MOREIRA': 0.17,
        'R KINGSCOTE': 0.03
    }
    
    FALLBACK_TRAINER_RATES = {
        'J SIZE': 0.0897, 'P C NG': 0.08, 'F C LOR': 0.09, 'K W LUI': 0.1051,
        'C S SHUM': 0.1214, 'C FOWNES': 0.1228, 'A S CRUZ': 0.0754, 'P F YIU': 0.0952,
        'D A HAYES': 0.0819, 'M NEWNHAM': 0.1085, 'D J WHYTE': 0.06, 'J RICHARDS': 0.07,
        'T P YUNG': 0.07, 'K L MAN': 0.0877, 'W Y SO': 0.06, 'Y S TSUI': 0.06,
        'C W CHANG': 0.04, 'K H TING': 0.06, 'W K MO': 0.0895, 'M NEWMAN': 0.11,
        'D EUSTACE': 0.07, 'B CRAWFORD': 0.08
    }

    if 'jockey' not in live_df.columns:
        live_df['jockey'] = ''
    if 'trainer' not in live_df.columns:
        live_df['trainer'] = ''

    if os.path.exists('data/jockey_win_rates.csv'):
        jockey_df = pd.read_csv('data/jockey_win_rates.csv')
        jockey_df['jockey_clean'] = jockey_df['jockey'].astype(str).str.upper().str.strip()
        live_df['jockey_clean'] = live_df['jockey'].astype(str).str.upper().str.strip()
        live_df = pd.merge(live_df, jockey_df[['jockey_clean', 'jockey_win_rate']], on='jockey_clean', how='left')
        live_df['jockey_win_rate'] = live_df['jockey_win_rate'].fillna(live_df['jockey_clean'].map(FALLBACK_JOCKEY_RATES)).fillna(0.08)
    else:
        live_df['jockey_clean'] = live_df['jockey'].astype(str).str.upper().str.strip()
        live_df['jockey_win_rate'] = live_df['jockey_clean'].map(FALLBACK_JOCKEY_RATES).fillna(0.08)
        
    if os.path.exists('data/trainer_win_rates.csv'):
        trainer_df = pd.read_csv('data/trainer_win_rates.csv')
        trainer_df['trainer_clean'] = trainer_df['trainer'].astype(str).str.upper().str.strip()
        live_df['trainer_clean'] = live_df['trainer'].astype(str).str.upper().str.strip()
        live_df = pd.merge(live_df, trainer_df[['trainer_clean', 'trainer_win_rate']], on='trainer_clean', how='left')
        live_df['trainer_win_rate'] = live_df['trainer_win_rate'].fillna(live_df['trainer_clean'].map(FALLBACK_TRAINER_RATES)).fillna(0.08)
    else:
        live_df['trainer_clean'] = live_df['trainer'].astype(str).str.upper().str.strip()
        live_df['trainer_win_rate'] = live_df['trainer_clean'].map(FALLBACK_TRAINER_RATES).fillna(0.08)

    live_df = prepare_features(live_df, is_live=True, venue=venue, going=going, race_date=race_date, race_class_int=race_class_int, track_type=track_type)
    
    for f in ALL_FEATURES:
        if f not in live_df.columns:
            live_df[f] = 0.0
            
    X_live = live_df[ALL_FEATURES]
    probs = model.predict_proba(X_live)[:, 1]
    
    total_prob = probs.sum()
    if total_prob > 0:
        probs = probs / total_prob
        
    return probs, live_df

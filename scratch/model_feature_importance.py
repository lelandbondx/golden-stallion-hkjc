import os
import sys
sys.path.append(os.getcwd())
import joblib
import pandas as pd
from model import ALL_FEATURES, MODEL_PATH

try:
    model = joblib.load(MODEL_PATH)
    importances = model.feature_importances_
    feat_imp = pd.Series(importances, index=ALL_FEATURES).sort_values(ascending=False)
    print("XGBoost Model Feature Importances:")
    print(feat_imp)
except Exception as e:
    print(f"Error loading model or getting feature importances: {e}")

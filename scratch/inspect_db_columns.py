import pandas as pd
import os

try:
    if os.path.exists('data/results.csv'):
        df = pd.read_csv('data/results.csv', nrows=5)
        print("results.csv columns:", df.columns.tolist())
    if os.path.exists('data/runs.csv'):
        df_runs = pd.read_csv('data/runs.csv', nrows=5)
        print("runs.csv columns:", df_runs.columns.tolist())
except Exception as e:
    print("Error:", e)

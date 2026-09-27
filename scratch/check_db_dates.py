import pandas as pd

for filepath in ['data/races.csv', 'data/runs.csv', 'data/results.csv', 'data/train_horse_features.csv']:
    try:
        df = pd.read_csv(filepath)
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            latest_date = df['date'].max()
            print(f"{filepath}: Latest Date = {latest_date.strftime('%Y-%m-%d')} (Shape = {df.shape})")
        else:
            print(f"{filepath}: No 'date' column. Shape = {df.shape}")
    except Exception as e:
        print(f"Error reading {filepath}: {e}")

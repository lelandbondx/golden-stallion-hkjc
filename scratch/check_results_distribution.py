import pandas as pd

df = pd.read_csv('data/results.csv')
print("Value counts of plc:")
print(df['plc'].value_counts().head(20))
print(f"Total rows: {len(df)}")

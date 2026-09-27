import pandas as pd

df = pd.read_csv('data/results.csv')
purton_runs = df[df['jockey'].str.upper().str.strip() == 'Z PURTON']
print(f"Z Purton runs in results.csv: {len(purton_runs)}")
purton_wins = purton_runs[purton_runs['plc'].astype(str).str.strip() == '1']
print(f"Z Purton wins in results.csv: {len(purton_wins)}")
print(f"Calculated win rate: {len(purton_wins) / len(purton_runs) if len(purton_runs) > 0 else 0}")

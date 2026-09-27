import pandas as pd
import numpy as np

results = pd.read_csv('data/results.csv')

# Old buggy logic
results['won_calc_old'] = results['plc'].astype(str).str.startswith('1').astype(int)

# Correct logic
def parse_won(x):
    x_str = str(x).strip()
    if x_str in ['1', '1.0', '1 DH'] or '1 DH' in x_str:
        return 1
    return 0

results['won_calc_new'] = results['plc'].apply(parse_won)

print("Old wins count:", results['won_calc_old'].sum())
print("New wins count:", results['won_calc_new'].sum())

# Let's compare jockeys win rates
j_runs = results.groupby('jockey').size().reset_index(name='runs')
j_wins_old = results.groupby('jockey')['won_calc_old'].sum().reset_index(name='wins_old')
j_wins_new = results.groupby('jockey')['won_calc_new'].sum().reset_index(name='wins_new')

j_stats = pd.merge(j_runs, j_wins_old, on='jockey')
j_stats = pd.merge(j_stats, j_wins_new, on='jockey')

j_stats['rate_old'] = j_stats['wins_old'] / j_stats['runs']
j_stats['rate_new'] = j_stats['wins_new'] / j_stats['runs']

print("\nJockey Win Rates Comparison (Top 10 by runs):")
print(j_stats.sort_values(by='runs', ascending=False).head(10).to_string(index=False))

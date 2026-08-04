import pandas as pd
import numpy as np

def calculate_jvoe():
    print("Loading data/results.csv...")
    try:
        results = pd.read_csv('data/results.csv')
    except Exception as e:
        print(f"Error loading results.csv: {e}")
        return

    # Filter out records without win odds or jockey
    results = results.dropna(subset=['jockey', 'winodds'])
    results['winodds'] = pd.to_numeric(results['winodds'], errors='coerce')
    results = results[results['winodds'] > 0]
    
    # Calculate implied probability
    results['implied_prob'] = 1.0 / results['winodds']
    
    # Calculate won status
    def parse_won(x):
        x_str = str(x).strip()
        if x_str in ['1', '1.0', '1 DH'] or '1 DH' in x_str:
            return 1
        return 0
    results['won'] = results['plc'].apply(parse_won)
    
    # Calculate JVOE for each ride
    results['jvoe_raw'] = results['won'] - results['implied_prob']
    
    # Group by jockey
    j_stats = results.groupby('jockey').agg(
        runs=('jvoe_raw', 'count'),
        sum_jvoe=('jvoe_raw', 'sum'),
        wins=('won', 'sum')
    ).reset_index()
    
    # Apply Bayesian smoothing to shrink towards 0.0 (prior_weight = 20)
    prior_weight = 20
    j_stats['jockey_jvoe'] = j_stats['sum_jvoe'] / (j_stats['runs'] + prior_weight)
    
    # Format jockey names to match live runs (uppercase, stripped)
    j_stats['jockey'] = j_stats['jockey'].str.strip().str.upper()
    
    # Save to CSV
    output_file = 'data/jockey_jvoe.csv'
    j_stats[['jockey', 'jockey_jvoe', 'runs', 'wins']].to_csv(output_file, index=False)
    print(f"Saved {len(j_stats)} jockeys' JVOE values to {output_file}")
    
    # Print top 15 and bottom 5 for verification
    print("\n--- TOP 15 JOCKEYS BY JVOE (Smoothed) ---")
    print(j_stats.sort_values(by='jockey_jvoe', ascending=False).head(15)[['jockey', 'runs', 'wins', 'jockey_jvoe']].to_string(index=False))
    
    print("\n--- BOTTOM 5 JOCKEYS BY JVOE (Smoothed) ---")
    print(j_stats.sort_values(by='jockey_jvoe', ascending=True).head(5)[['jockey', 'runs', 'wins', 'jockey_jvoe']].to_string(index=False))

if __name__ == '__main__':
    calculate_jvoe()

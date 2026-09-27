import pandas as pd
import numpy as np

def test():
    print("Reading results...")
    df = pd.read_csv('data/results.csv', usecols=['horse', 'runningpos'])
    
    # Extract clean name
    df['clean_name'] = df['horse'].str.extract(r'^(.*?)\(')[0].str.strip().str.upper()
    
    # Parse first running position
    def parse_first_pos(x):
        if not isinstance(x, str):
            return np.nan
        parts = x.strip().split()
        if not parts:
            return np.nan
        try:
            return float(parts[0])
        except:
            return np.nan
            
    df['first_pos'] = df['runningpos'].apply(parse_first_pos)
    
    # Group by horse and get average first position
    horse_style = df.groupby('clean_name')['first_pos'].mean().reset_index()
    horse_style = horse_style.dropna()
    
    print("\nTop 20 horses that run closest to the lead (front-runners/on-speed):")
    print(horse_style.sort_values(by='first_pos').head(20))
    
    print("\nTop 20 horses that run in the back (closers/back-runners):")
    print(horse_style.sort_values(by='first_pos', ascending=False).head(20))

if __name__ == '__main__':
    test()

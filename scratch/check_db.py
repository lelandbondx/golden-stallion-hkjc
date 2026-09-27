import pandas as pd
import os

print("Checking if database files exist:")
print("data/results.csv exists:", os.path.exists('data/results.csv'))
print("data/comments.csv exists:", os.path.exists('data/comments.csv'))

try:
    if os.path.exists('data/results.csv'):
        results_df = pd.read_csv('data/results.csv', nrows=5)
        print("\nresults.csv columns:", list(results_df.columns))
    if os.path.exists('data/comments.csv'):
        comments_df = pd.read_csv('data/comments.csv', nrows=5)
        print("\ncomments.csv columns:", list(comments_df.columns))
except Exception as e:
    print("Error reading sample rows:", e)

# Test fetch_historical_comments
try:
    results = pd.read_csv('data/results.csv', usecols=['date', 'raceno', 'horseno', 'horse'])
    comments = pd.read_csv('data/comments.csv', usecols=['date', 'raceno', 'horseno', 'comment'])
    print("\nRead successful. merging...")
    df = pd.merge(comments, results, on=['date', 'raceno', 'horseno'], how='inner')
    print("Merge successful. Rows:", len(df))
    if not df.empty:
        df['clean_name'] = df['horse'].str.extract(r'^(.*?)\(')[0].str.strip().str.upper()
        print("Sample clean names:", df['clean_name'].head().tolist())
except Exception as e:
    print("Error in merge logic:", e)

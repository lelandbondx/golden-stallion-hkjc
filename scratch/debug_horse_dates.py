import requests
import pandas as pd
from bs4 import BeautifulSoup

horse_code = "L152"
url = f"https://racing.hkjc.com/racing/information/English/Horse/Horse.aspx?HorseNo={horse_code}"
headers = {"User-Agent": "Mozilla/5.0"}

res = requests.get(url, headers=headers, timeout=10)
dfs = pd.read_html(res.content)

# Find the table with race history
race_df = None
for df in dfs:
    if df.shape[1] == 19 and ("Race Index" in str(df.columns) or "Race Index" in str(df.iloc[0].values)):
        race_df = df
        break

if race_df is not None:
    print("Columns:", race_df.iloc[0].values)
    print("First 3 rows:")
    print(race_df.iloc[1:4].to_dict('records'))
else:
    print("Could not find race history table.")

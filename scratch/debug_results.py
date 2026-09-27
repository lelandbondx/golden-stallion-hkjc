import requests
import urllib3
import re

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

url = "https://racing.hkjc.com/racing/information/English/Racing/LocalResults.aspx?RaceDate=24/06/2026&RaceNo=2"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

res = requests.get(url, headers=headers, verify=False)
print("Status code:", res.status_code)
print("Content length:", len(res.content))

# Save html to scratch
with open("scratch/race2.html", "wb") as f:
    f.write(res.content)

# Let's search the HTML for keywords
html_text = res.text.lower()
print("Contains 'performance' table class:", 'performance' in html_text)
print("Contains 'matsu victor':", 'matsu victor' in html_text)
print("Contains 'all are mine':", 'all are mine' in html_text)

# Find all table elements class names
from bs4 import BeautifulSoup
soup = BeautifulSoup(res.content, 'html.parser')
tables = soup.find_all('table')
print("Total tables found:", len(tables))
for i, t in enumerate(tables):
    classes = t.get('class')
    print(f"Table {i}: class={classes}, id={t.get('id')}")

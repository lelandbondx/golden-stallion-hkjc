import requests
from bs4 import BeautifulSoup
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

url = "https://racing.hkjc.com/racing/information/English/Racing/LocalResults.aspx?RaceDate=2026/06/27&RaceNo=1"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

res = requests.get(url, headers=headers, timeout=10, verify=False)
soup = BeautifulSoup(res.text, 'html.parser')
table = soup.find('table', class_='draggable')
if table:
    print("Found draggable table!")
    rows = table.find_all('tr')
    # Print the header row
    headers = [th.text.strip() for th in rows[0].find_all(['td', 'th'])]
    print("Headers:", headers)
    # Print first 3 runner rows
    for r in rows[1:4]:
        cells = [td.text.strip() for td in r.find_all('td')]
        print("Row:", cells[:6])
else:
    print("Draggable table not found.")

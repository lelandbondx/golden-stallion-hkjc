import requests
from bs4 import BeautifulSoup
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

url = "https://racing.hkjc.com/racing/information/English/Racing/LocalResults.aspx?RaceDate=2026/06/27&RaceNo=1"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

try:
    res = requests.get(url, headers=headers, timeout=10, verify=False)
    print("Status:", res.status_code)
    print("Content length:", len(res.text))
    if res.status_code == 200:
        soup = BeautifulSoup(res.text, 'html.parser')
        # Find performance table
        table = soup.find('table', class_='performance')
        if table:
            print("Found performance table!")
            rows = table.find_all('tr')
            for r in rows[:3]:
                print(r.text.strip().replace('\n', ' '))
        else:
            print("Performance table not found. Table classes:")
            for t in soup.find_all('table'):
                classes = t.get('class')
                if classes:
                    print(classes)
except Exception as e:
    print("Error:", e)

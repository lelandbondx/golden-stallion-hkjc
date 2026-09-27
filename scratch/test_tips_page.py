import requests
from bs4 import BeautifulSoup

url = "https://racing.hkjc.com/racing/english/tipsindex/tips_index.asp"
headers = {"User-Agent": "Mozilla/5.0"}

try:
    res = requests.get(url, headers=headers, timeout=10)
    print("Status code:", res.status_code)
    soup = BeautifulSoup(res.content, 'html.parser')
    
    tables = soup.find_all('table')
    print("Found tables:", len(tables))
    
    text = soup.get_text()
    print("Page text snippet (first 1000 chars):")
    print(text[:1000])
    
    # Check if we see race tips mentions
    print("\nContains 'Race 1':", "Race 1" in text or "Race  1" in text)
    print("Contains 'Apple Daily':", "Apple Daily" in text)
    print("Contains 'Media':", "Media" in text)
    
except Exception as e:
    print("Error:", e)

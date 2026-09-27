import requests
from bs4 import BeautifulSoup
import urllib.parse

url = "https://racing.hkjc.com/racing/english/tipsindex/tips_index.asp"
headers = {"User-Agent": "Mozilla/5.0"}

try:
    res = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(res.content, 'html.parser')
    
    links = soup.find_all('a')
    print(f"Found {len(links)} links on the page.")
    
    tips_links = []
    for link in links:
        href = link.get('href', '')
        if 'tips_index.asp' in href or 'tips_index' in href.lower():
            tips_links.append((link.get_text(strip=True), href))
            
    print("\nLinks containing 'tips_index':")
    for text, href in tips_links:
        print(f"Text: {repr(text)} | Href: {href}")
        
except Exception as e:
    print("Error:", e)

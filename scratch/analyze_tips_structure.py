import requests
from bs4 import BeautifulSoup
import re

url = "https://racing.hkjc.com/racing/english/tipsindex/tips_index.asp"
headers = {"User-Agent": "Mozilla/5.0"}

try:
    res = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(res.content, 'html.parser')
    
    # Let's search for cells containing "Horse number:" or similar
    cells = soup.find_all(text=re.compile(r'Horse\s*number:', re.I))
    print(f"Found {len(cells)} cells with 'Horse number:'")
    
    for i, cell in enumerate(cells[:5]):
        print(f"\n--- Instance {i+1} ---")
        parent = cell.parent
        print("Cell parent tag:", parent.name)
        print("Cell parent text:", repr(parent.get_text(strip=True)))
        
        # Let's climb up to find sibling/parent structures
        grandparent = parent.parent
        print("Grandparent tag:", grandparent.name)
        print("Grandparent text content snippet:")
        print(repr(grandparent.get_text(strip=True)[:300]))
        
        # Let's find Tips Index within the grandparent or sibling
        tips_index_matches = grandparent.find_all(text=re.compile(r'Tips\s*Index:', re.I))
        for match in tips_index_matches:
            print("  Found Tips Index sibling text:", repr(match.parent.get_text(strip=True)))
            
except Exception as e:
    print("Error:", e)

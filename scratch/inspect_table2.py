from bs4 import BeautifulSoup

with open("scratch/race2.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')
tables = soup.find_all('table')

# Table 2 has classes f_tac, table_bd, draggable
t = tables[2]
print("Table 2 class:", t.get('class'))
rows = t.find_all('tr')
print("Number of rows:", len(rows))
for i, row in enumerate(rows[:15]):
    cells = [c.get_text(strip=True) for c in row.find_all(['td', 'th'])]
    print(f"Row {i}: {cells[:6]}")

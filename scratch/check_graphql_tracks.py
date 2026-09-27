import requests

GRAPHQL_QUERY = """
query {
  activeMeetings: raceMeetings {
    id
    venueCode
    date
    status
  }
}
"""

url = "https://info.cld.hkjc.com/graphql/base/"
headers = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json"
}

res = requests.post(url, json={"query": GRAPHQL_QUERY}, headers=headers, timeout=10)
print(res.status_code)
print(res.text[:1000])

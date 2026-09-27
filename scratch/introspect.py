import requests
import json

INTROSPICT_QUERY = """
query Introspect($name: String!) {
  __type(name: $name) {
    name
    fields {
      name
      type {
        name
        kind
        ofType {
          name
          kind
        }
      }
    }
  }
}
"""

def introspect():
    url = "https://info.cld.hkjc.com/graphql/base/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type": "application/json"
    }
    
    # Introspect PmPool
    res = requests.post(url, json={"query": INTROSPICT_QUERY, "variables": {"name": "PmPool"}}, headers=headers, timeout=10)
    data = res.json()
    print("=== PmPool fields ===")
    print(json.dumps(data, indent=2))
    
    # Introspect OddsNode if exists
    res = requests.post(url, json={"query": INTROSPICT_QUERY, "variables": {"name": "OddsNode"}}, headers=headers, timeout=10)
    data = res.json()
    print("=== OddsNode fields ===")
    print(json.dumps(data, indent=2))

if __name__ == "__main__":
    introspect()

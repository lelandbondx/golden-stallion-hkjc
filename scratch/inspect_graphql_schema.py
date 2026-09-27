import requests
import json

url = "https://info.cld.hkjc.com/graphql/base/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/json"
}

INTROSPECTION_QUERY = """
query {
  __type(name: "PmPool") {
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

try:
    res = requests.post(url, json={"query": INTROSPECTION_QUERY}, headers=headers, timeout=10)
    data = res.json()
    if "errors" in data:
        print("Errors:")
        print(data["errors"])
    else:
        fields = data.get("data", {}).get("__type", {}).get("fields", [])
        print("Fields in PmPool type:")
        for f in fields:
            ftype = f.get("type", {})
            type_name = ftype.get("name") or (ftype.get("ofType") or {}).get("name")
            print(f"  - {f.get('name')}: {type_name}")
except Exception as e:
    print("Error:", e)

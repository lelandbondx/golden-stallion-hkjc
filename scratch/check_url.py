import requests

url = "https://hkjcbotlee.streamlit.app/"
print(f"Pinging {url}...")
try:
    res = requests.get(url, timeout=15)
    print(f"Status Code: {res.status_code}")
    print("Headers:")
    for k, v in res.headers.items():
        print(f"  {k}: {v}")
except Exception as e:
    print(f"Error pinging {url}: {e}")

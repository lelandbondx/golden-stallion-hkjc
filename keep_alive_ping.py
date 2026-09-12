import time
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

url = "https://hkjcbotlee.streamlit.app/"
print(f"Starting Golden Stallion AI keep-alive ping service for: {url}")

while True:
    try:
        # We disable verification in case the host machine still has certificate trust issues
        res = requests.get(url, timeout=15, verify=False)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Ping status: {res.status_code}")
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Ping failed: {e}")
    
    # Sleep for 5 minutes (300 seconds) to prevent the container from sleeping
    time.sleep(300)

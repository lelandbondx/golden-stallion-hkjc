import time
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

urls = [
    "https://silks-ai.onrender.com/",
    "https://hkjcbotlee.streamlit.app/"
]
print(f"Starting Golden Stallion / SILKS.AI keep-alive ping service for: {urls}")

while True:
    for target_url in urls:
        try:
            res = requests.get(target_url, timeout=15, verify=False)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Ping {target_url} status: {res.status_code}", flush=True)
        except Exception as e:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Ping {target_url} failed: {e}", flush=True)
    
    # Sleep for 60 seconds to ensure Render and Streamlit containers never spin down
    time.sleep(60)

import requests

url = "https://hkjcbotlee.streamlit.app/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

try:
    print(f"Sending request to {url}...")
    res = requests.get(url, headers=headers, timeout=15)
    print(f"Status Code: {res.status_code}")
    print(f"Final URL after redirects: {res.url}")
    
    # Check if the page is a sleep/wake page or if it contains Streamlit indicators
    text = res.text.lower()
    print("\nAnalyzing page content:")
    if "sleep" in text or "wake" in text:
        print("  - Page mentions sleep/wake. Streamlit App might be waking up.")
    if "streamlit" in text:
        print("  - Streamlit signature found in the HTML.")
    
    # Snippet of the page
    print("\nPage text snippet (first 1000 characters):")
    print(res.text[:1000])
    
except Exception as e:
    print("Error checking remote app:", e)

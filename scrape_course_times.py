import pandas as pd
from playwright.sync_api import sync_playwright
import os

def scrape_times():
    print("Launching browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print("Navigating to HKJC Course Time page...")
        page.goto('https://racing.hkjc.com/en-us/local/page/racing-course-time', timeout=60000)
        
        print("Waiting for tables to load...")
        page.wait_for_selector('table')
        
        print("Extracting HTML...")
        html = page.content()
        dfs = pd.read_html(html)
        
        print(f"Found {len(dfs)} tables.")
        
        os.makedirs('data', exist_ok=True)
        
        for i, df in enumerate(dfs):
            output_path = f'data/scraped_table_{i}.csv'
            df.to_csv(output_path, index=False)
            print(f"Saved {output_path} with shape {df.shape}")
        
        browser.close()

if __name__ == '__main__':
    scrape_times()

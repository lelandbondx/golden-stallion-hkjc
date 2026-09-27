import os
import sys
import requests
import pandas as pd
import numpy as np
from bs4 import BeautifulSoup
import concurrent.futures

# Add parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper import get_live_meeting_data

def get_horse_id_from_profile(horse_code):
    url = f"https://racing.hkjc.com/racing/information/English/Horse/Horse.aspx?HorseNo={horse_code}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content, 'html.parser')
        # Search for links containing ovehorse
        for a in soup.find_all('a', href=True):
            if 'ovehorse' in a['href']:
                # Extract horseid from href
                href = a['href']
                if 'horseid=' in href:
                    horse_id = href.split('horseid=')[-1].split('&')[0]
                    return horse_id
    except Exception as e:
        print(f"Error finding horseid for {horse_code}: {e}")
    return None

def get_horse_vet_history(horse_id):
    if not horse_id:
        return []
    url = f"https://racing.hkjc.com/racing/information/English/Horse/ovehorse.aspx?horseid={horse_id}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return []
        dfs = pd.read_html(r.content)
        # Look for the veterinary table. It has columns 'Date', 'Details', 'Passed Date'
        for df in dfs:
            if df.shape[1] == 3 and 'Date' in df.columns and 'Details' in df.columns:
                return df.to_dict('records')
            # Sometimes headers are in row 0
            if df.shape[1] == 3 and 'Date' in df.iloc[0].values or 'Details' in df.iloc[0].values:
                df.columns = df.iloc[0]
                df = df.drop(0)
                return df.to_dict('records')
    except Exception as e:
        print(f"Error fetching vet history for {horse_id}: {e}")
    return []

def scrape_all_vets():
    print("Scraping live meeting data to get tomorrow's runners...")
    data = get_live_meeting_data()
    if not data or 'meetings' not in data:
        print("No live meeting data found.")
        return
        
    runners = []
    for meeting in data['meetings']:
        for race in meeting.get('races', []):
            for r in race.get('runners', []):
                code = r.get('code')
                name = r.get('name', '').strip().upper()
                if code:
                    runners.append({'code': code, 'name': name, 'race_no': race['race_no']})
                    
    print(f"Found {len(runners)} declared runners.")
    
    # Concurrent scraping of horse IDs and vet histories
    vet_findings_dict = {}
    
    def process_runner(runner):
        code = runner['code']
        name = runner['name']
        # Find horseid
        horse_id = get_horse_id_from_profile(code)
        if not horse_id:
            # Fallback format: HK_Year_code, but Year varies. We try to guess or skip
            # Usually the scraper finds it
            return None
            
        history = get_horse_vet_history(horse_id)
        return name, history

    print("Fetching veterinary records from HKJC...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(process_runner, runners))
        
    # Analyze vet history
    # Keywords indicating critical vet findings
    vet_keywords = ['lame', 'blood', 'trachea', 'heart', 'irregularity', 'mucus', 'surgery', 'abnormal', 'infection', 'fever']
    
    vet_updates = {}
    
    for res in results:
        if not res:
            continue
        name, history = res
        if not history:
            vet_updates[name] = 0
            continue
            
        # Check if the most recent vet finding is within, say, the last 180 days or has unresolved status
        # Let's inspect all findings. We'll mark prev_run_vet_finding = 1 if there's any vet finding in their last run
        # (usually the first row in the table is the most recent)
        recent_finding = history[0]
        date_str = str(recent_finding.get('Date', '')).strip()
        details = str(recent_finding.get('Details', '')).strip().lower()
        passed_date = str(recent_finding.get('Passed Date', '')).strip()
        
        has_issue = 0
        if any(k in details for k in vet_keywords):
            # If there's an issue and it has not been passed, or if it was very recent (e.g. in 2026 or 2025)
            # Let's parse date
            try:
                date = pd.to_datetime(date_str, format="%d/%m/%y")
                # If date is within last 180 days (let's assume relative to today 2026-05-26)
                today = pd.to_datetime("2026-05-26")
                days_diff = (today - date).days
                if days_diff <= 180:
                    has_issue = 1
                    print(f"CRITICAL VET ALERT: {name} had '{details}' on {date_str} ({days_diff} days ago). Passed date: {passed_date}")
            except Exception:
                # Fallback to string checks or older dates
                if '2026' in date_str or '2025' in date_str:
                    has_issue = 1
                    print(f"VET ALERT (year check): {name} had '{details}' on {date_str}. Passed date: {passed_date}")
                    
        vet_updates[name] = has_issue
        
    # Update latest_horse_stats.csv
    if os.path.exists('data/latest_horse_stats.csv'):
        stats_df = pd.read_csv('data/latest_horse_stats.csv')
        stats_df['clean_name'] = stats_df['clean_name'].str.strip().str.upper()
        
        # Merge or map the scraped veterinary findings
        def get_vet_val(name):
            name_upper = str(name).strip().upper()
            return vet_updates.get(name_upper, 0)
            
        # If prev_run_vet_finding exists, update it. If not, create it.
        stats_df['prev_run_vet_finding'] = stats_df['clean_name'].apply(get_vet_val)
        stats_df.to_csv('data/latest_horse_stats.csv', index=False)
        print("Updated data/latest_horse_stats.csv with live veterinary findings.")
    else:
        print("latest_horse_stats.csv not found, cannot update.")

if __name__ == '__main__':
    scrape_all_vets()

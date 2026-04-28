import requests
import pandas as pd
import json
import time

def get_horse_profile_stats(horse_code):
    if not horse_code:
        return None
        
    url = f"https://racing.hkjc.com/racing/information/English/Horse/Horse.aspx?HorseNo={horse_code}"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        dfs = pd.read_html(res.content)
        
        # Find the table with race history
        race_df = None
        for df in dfs:
            if df.shape[1] == 19 and "Race Index" in str(df.columns) or "Race Index" in str(df.iloc[0].values):
                race_df = df
                break
                
        if race_df is None:
            return None
            
        # The first row is usually headers, let's clean it up
        race_df.columns = race_df.iloc[0]
        race_df = race_df.drop(0)
        
        # Filter out season headers
        race_df = race_df[~race_df['Race Index'].str.contains('Season', na=False)]
        
        # Clean up data
        race_df['Pla.'] = race_df['Pla.'].astype(str)
        race_df['is_win'] = race_df['Pla.'].apply(lambda x: 1 if x.strip() == '1' or '1 DH' in x else 0)
        race_df['is_place'] = race_df['Pla.'].apply(lambda x: 1 if x.strip() in ['1', '2', '3'] or 'DH' in x and any(n in x for n in ['1', '2', '3']) else 0)
        
        # Track
        race_df['Track'] = race_df['RC/Track/ Course'].astype(str).apply(lambda x: 'Sha Tin' if 'ST' in x else ('Happy Valley' if 'HV' in x else 'Unknown'))
        
        # Rating
        race_df['Rtg.'] = pd.to_numeric(race_df['Rtg.'], errors='coerce')
        
        last_win_rating = None
        wins = race_df[race_df['is_win'] == 1]
        if not wins.empty:
            last_win_rating = wins.iloc[0]['Rtg.'] # 0th is the most recent because HKJC lists newest first!
            
        ST_runs = len(race_df[race_df['Track'] == 'Sha Tin'])
        ST_wins = len(wins[wins['Track'] == 'Sha Tin'])
        HV_runs = len(race_df[race_df['Track'] == 'Happy Valley'])
        HV_wins = len(wins[wins['Track'] == 'Happy Valley'])
        
        ST_win_rate = ST_wins / ST_runs if ST_runs > 0 else 0
        HV_win_rate = HV_wins / HV_runs if HV_runs > 0 else 0
        
        if ST_win_rate > HV_win_rate:
            ST_vs_HV_pref = 'Sha Tin'
        elif HV_win_rate > ST_win_rate:
            ST_vs_HV_pref = 'Happy Valley'
        else:
            ST_vs_HV_pref = 'Neutral'
            
        # Fav going
        places = race_df[race_df['is_place'] == 1]
        last_form_going = 'Unknown'
        if not places.empty:
            last_form_going = places.iloc[0]['G']
            
        return {
            "last_win_rating": last_win_rating,
            "ST_win_rate": ST_win_rate,
            "HV_win_rate": HV_win_rate,
            "ST_vs_HV_pref": ST_vs_HV_pref,
            "last_form_going": last_form_going
        }
        
    except Exception as e:
        print(f"Error scraping {horse_code}: {e}")
        return None

def update_latest_stats():
    # Load live data to get all tomorrow's horses
    from scraper import get_live_meeting_data
    data = get_live_meeting_data()
    
    horses_to_update = {}
    
    if data and 'meetings' in data:
        for meeting in data['meetings']:
            for race in meeting.get('races', []):
                for runner in race.get('runners', []):
                    code = runner.get('code')
                    name = runner.get('name', '').strip().upper()
                    if code and name:
                        horses_to_update[code] = name
                        
    print(f"Found {len(horses_to_update)} horses to update.")
    
    # Load existing stats
    try:
        stats_df = pd.read_csv('data/latest_horse_stats.csv')
    except Exception:
        stats_df = pd.DataFrame(columns=['clean_name', 'last_win_rating', 'ST_win_rate', 'HV_win_rate', 'ST_vs_HV_pref', 'last_form_going'])
        
    stats_dict = stats_df.to_dict('records')
    existing_names = {row['clean_name'] for row in stats_dict}
    
    new_rows = []
    
    import concurrent.futures
    
    def fetch_horse(code, name):
        print(f"Fetching {name} ({code})...")
        stats = get_horse_profile_stats(code)
        if stats:
            stats['clean_name'] = name
            return stats
        return None
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for code, name in horses_to_update.items():
            if name not in existing_names:
                futures.append(executor.submit(fetch_horse, code, name))
                
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                new_rows.append(res)
                
    if new_rows:
        new_df = pd.DataFrame(new_rows)
        combined = pd.concat([stats_df, new_df], ignore_index=True)
        combined.to_csv('data/latest_horse_stats.csv', index=False)
        print(f"Added {len(new_rows)} new horse stats and saved.")
    else:
        print("No new horses to add.")

if __name__ == '__main__':
    update_latest_stats()

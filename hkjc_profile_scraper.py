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
        
        # Enforce "Current Form" constraint: Only look at the horse's last 12 runs (approx 1 to 1.5 seasons)
        # This prevents the AI from being confused by track or gear wins from 5-8 years ago.
        race_df = race_df.head(12)
        
        # Clean up data
        race_df['Pla.'] = race_df['Pla.'].astype(str)
        
        def check_win(x):
            x_clean = str(x).strip().upper()
            if x_clean.lstrip('0') == '1' or '1 DH' in x_clean: return 1
            return 0
            
        def check_place(x):
            x_clean = str(x).strip().upper()
            val = x_clean.lstrip('0')
            if val in ['1', '2', '3'] or ('DH' in x_clean and any(n in x_clean for n in ['1', '2', '3'])): return 1
            return 0
            
        race_df['is_win'] = race_df['Pla.'].apply(check_win)
        race_df['is_place'] = race_df['Pla.'].apply(check_place)
        
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
        
        going_map = {
            'GF': 'GOOD TO FIRM',
            'G': 'GOOD',
            'GD': 'GOOD',
            'GY': 'GOOD TO YIELDING',
            'Y': 'YIELDING',
            'YS': 'YIELDING TO SOFT',
            'S': 'SOFT',
            'H': 'HEAVY',
            'WS': 'WET SLOW',
            'F': 'FIRM',
            'WF': 'WET FAST'
        }
        
        if not places.empty:
            raw_going = str(places.iloc[0]['G']).strip().upper()
            last_form_going = going_map.get(raw_going, 'Unknown')
            
        # Date
        last_run_date = None
        if not race_df.empty:
            last_run_date = pd.to_datetime(race_df.iloc[0]['Date'], format="%d/%m/%y", errors='coerce')
            
        # Class
        last_race_class_int = 4
        if not race_df.empty:
            cls_str = str(race_df.iloc[0].get('Cls', '4'))
            if '1' in cls_str: last_race_class_int = 1
            elif '2' in cls_str: last_race_class_int = 2
            elif '3' in cls_str: last_race_class_int = 3
            elif '4' in cls_str: last_race_class_int = 4
            elif '5' in cls_str: last_race_class_int = 5
            elif 'G' in cls_str.upper(): last_race_class_int = 0
            
        # Last rating
        last_horse_rating = None
        if not race_df.empty:
            last_horse_rating = pd.to_numeric(race_df.iloc[0].get('Rtg.'), errors='coerce')
            
        # Last gear
        last_gear = None
        if not race_df.empty:
            last_gear = str(race_df.iloc[0].get('Gear', ''))
            
        # Gear Win Rate (win rate with the exact same gear as last time)
        gear_win_rate = 0.0
        if last_gear and last_gear.strip() not in ['-', '']:
            gear_runs = race_df[race_df['Gear'] == last_gear]
            gear_wins = gear_runs[gear_runs['is_win'] == 1]
            gear_win_rate = len(gear_wins) / len(gear_runs) if len(gear_runs) > 0 else 0.0
            
        # Distance Win Rate (using last distance as proxy)
        distance_win_rate = 0.0
        if not race_df.empty:
            last_dist = str(race_df.iloc[0].get('Dist.', ''))
            if last_dist and last_dist.strip() not in ['-', '']:
                dist_runs = race_df[race_df['Dist.'] == last_dist]
                dist_wins = dist_runs[dist_runs['is_win'] == 1]
                distance_win_rate = len(dist_wins) / len(dist_runs) if len(dist_runs) > 0 else 0.0

        # Recent Form
        recent_avg_pos = 7.0
        recent_win_rate = 0.0
        if not race_df.empty:
            recent_runs = race_df.head(4).copy()
            recent_runs['pos_num'] = pd.to_numeric(recent_runs['Pla.'].astype(str).str.lstrip('0'), errors='coerce').fillna(7)
            recent_avg_pos = recent_runs['pos_num'].mean()
            recent_win_rate = recent_runs['is_win'].mean()
            
        return {
            "last_win_rating": last_win_rating,
            "ST_win_rate": ST_win_rate,
            "HV_win_rate": HV_win_rate,
            "ST_vs_HV_pref": ST_vs_HV_pref,
            "last_form_going": last_form_going,
            "recent_avg_pos": recent_avg_pos,
            "recent_win_rate": recent_win_rate,
            "last_run_date": last_run_date.strftime('%Y-%m-%d') if pd.notnull(last_run_date) else None,
            "last_race_class_int": last_race_class_int,
            "last_horse_rating": last_horse_rating,
            "last_gear": last_gear,
            "gear_win_rate": gear_win_rate,
            "distance_win_rate": distance_win_rate
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
            # Force update for all horses running in the upcoming meeting
            futures.append(executor.submit(fetch_horse, code, name))
                
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                new_rows.append(res)
                
    if new_rows:
        new_df = pd.DataFrame(new_rows)
        combined = pd.concat([stats_df, new_df], ignore_index=True)
        # Drop duplicates, keeping the most recently appended row
        combined = combined.drop_duplicates(subset=['clean_name'], keep='last')
        combined.to_csv('data/latest_horse_stats.csv', index=False)
        print(f"Added {len(new_rows)} new horse stats and saved.")
    else:
        print("No new horses to add.")

if __name__ == '__main__':
    update_latest_stats()

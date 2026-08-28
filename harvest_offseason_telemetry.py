import os
import sys
import re
import urllib3
import requests
import pandas as pd
from datetime import datetime
import concurrent.futures

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
_orig_get = requests.get
_orig_post = requests.post
requests.get = lambda *args, **kwargs: _orig_get(*args, **{**kwargs, 'verify': False})
requests.post = lambda *args, **kwargs: _orig_post(*args, **{**kwargs, 'verify': False})

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def get_active_horses(limit=100):
    horses = {}
    if os.path.exists('data/horse_info.csv'):
        h_df = pd.read_csv('data/horse_info.csv')
        for _, r in h_df.iterrows():
            raw_h = str(r.get('horse', ''))
            m = re.search(r'^(.*?)\(([A-Z0-9]+)\)', raw_h)
            if m:
                name = m.group(1).strip().upper()
                code = m.group(2).strip().upper()
                if code and code[0] in ['G', 'H', 'J', 'K', 'L']:
                    horses[code] = name
                    
    active_list = list(horses.items())
    return active_list[:limit] if limit else active_list

def harvest_single_horse(code, name):
    data = {
        "clean_name": name,
        "horse_code": code,
        "gallops_30d": 0,
        "trots_30d": 0,
        "swims_30d": 0,
        "last_workout_date": None,
        "last_workout_type": None,
        "last_workout_detail": None,
        "is_in_conghua": 0,
        "latest_body_weight": None,
        "prev_run_vet_finding": 0,
        "has_overseas_form": 0
    }
    
    try:
        url = f"https://racing.hkjc.com/racing/information/English/Horse/Horse.aspx?HorseNo={code}"
        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code != 200:
            return data
            
        horse_id = None
        m = re.search(r'horseid=([A-Z0-9_]+)', res.text)
        if m:
            horse_id = m.group(1)
            
        data["has_overseas_form"] = 1 if 'pre-import formrecords' in res.text.lower() or 'fse_' in res.text.lower() else 0
        
        if not horse_id:
            return data
            
        try:
            tw_url = f"https://racing.hkjc.com/racing/information/English/Horse/TrackworkResult.aspx?HorseId={horse_id}"
            r_tw = requests.get(tw_url, headers=HEADERS, timeout=8)
            if r_tw.status_code == 200:
                dfs = pd.read_html(r_tw.content)
                for df in dfs:
                    if df.shape[1] == 5 and 'Date' in df.columns:
                        df['dt'] = pd.to_datetime(df['Date'], format='%d/%m/%Y', errors='coerce')
                        now = pd.to_datetime(datetime.now().date())
                        recent = df[(now - df['dt']).dt.days <= 30]
                        data["gallops_30d"] = int(len(recent[recent['Type'] == 'Gallop']))
                        data["trots_30d"] = int(len(recent[recent['Type'] == 'Trotting']))
                        data["swims_30d"] = int(len(recent[recent['Type'] == 'Swimming']))
                        if not recent.empty:
                            data["last_workout_date"] = str(recent.iloc[0]['Date'])
                            data["last_workout_type"] = str(recent.iloc[0]['Type'])
                            data["last_workout_detail"] = str(recent.iloc[0]['Workouts'])
                        break
        except Exception:
            pass
            
        try:
            mov_url = f"https://racing.hkjc.com/racing/information/English/Horse/MovementRecords.aspx?HorseId={horse_id}"
            r_mov = requests.get(mov_url, headers=HEADERS, timeout=8)
            if r_mov.status_code == 200:
                dfs_mov = pd.read_html(r_mov.content)
                for df in dfs_mov:
                    if 'Destination' in df.columns and not df.empty:
                        dest = str(df.iloc[0]['Destination']).upper()
                        data["is_in_conghua"] = 1 if 'CONGHUA' in dest or 'CTC' in dest else 0
                        break
        except Exception:
            pass
            
        try:
            rw_url = f"https://racing.hkjc.com/racing/information/English/Horse/RatingResultWeight.aspx?HorseId={horse_id}"
            r_rw = requests.get(rw_url, headers=HEADERS, timeout=8)
            if r_rw.status_code == 200:
                dfs_rw = pd.read_html(r_rw.content)
                for df in dfs_rw:
                    if 'Body Weight' in df.columns and not df.empty:
                        bw = pd.to_numeric(df.iloc[0]['Body Weight'], errors='coerce')
                        if pd.notnull(bw):
                            data["latest_body_weight"] = float(bw)
                        break
        except Exception:
            pass
            
        try:
            vet_url = f"https://racing.hkjc.com/racing/information/English/Horse/ovehorse.aspx?horseid={horse_id}"
            r_vet = requests.get(vet_url, headers=HEADERS, timeout=8)
            if r_vet.status_code == 200:
                dfs_vet = pd.read_html(r_vet.content)
                for df in dfs_vet:
                    if df.shape[1] == 3 and 'Details' in df.columns and not df.empty:
                        details = str(df.iloc[0].get('Details', '')).lower()
                        vet_keywords = ['lame', 'blood', 'trachea', 'heart', 'irregularity', 'mucus', 'surgery', 'abnormal', 'infection', 'fever']
                        if any(k in details for k in vet_keywords):
                            data["prev_run_vet_finding"] = 1
                        break
        except Exception:
            pass
            
        return data
        
    except Exception as e:
        print(f"Error harvesting {name} ({code}): {e}")
        return data

def run_offseason_harvest(limit=100):
    print("=== STARTING COMPREHENSIVE OFF-SEASON DATA HARVEST ===")
    active_horses = get_active_horses(limit=limit)
    print(f"Harvesting off-season telemetry for {len(active_horses)} active racehorses...")
    
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(harvest_single_horse, code, name): (code, name) for code, name in active_horses}
        
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            code, name = futures[future]
            try:
                res = future.result()
                results.append(res)
                completed += 1
                if completed % 15 == 0 or completed == len(active_horses):
                    print(f"[{completed}/{len(active_horses)}] Harvested: {name} ({code}) - Gallops: {res.get('gallops_30d')}, Swims: {res.get('swims_30d')}")
            except Exception as e:
                print(f"Error processing {name} ({code}): {e}")
                
    if results:
        df_new = pd.DataFrame(results)
        stats_path = 'data/latest_horse_stats.csv'
        if os.path.exists(stats_path):
            existing_df = pd.read_csv(stats_path)
            combined = pd.merge(existing_df, df_new, on='clean_name', how='outer', suffixes=('', '_new'))
            for col in df_new.columns:
                if col != 'clean_name':
                    if f'{col}_new' in combined.columns:
                        combined[col] = combined[f'{col}_new'].combine_first(combined.get(col))
                        combined = combined.drop(columns=[f'{col}_new'])
                    elif col not in combined.columns:
                        combined[col] = df_new[col]
            combined = combined.drop_duplicates(subset=['clean_name'], keep='last')
            combined.to_csv(stats_path, index=False)
        else:
            df_new.to_csv(stats_path, index=False)
            
        print(f"\nSuccessfully harvested and updated {len(df_new)} active horse profiles with real-time off-season telemetry.")
        
    print("=== OFF-SEASON HARVEST COMPLETE ===")

if __name__ == '__main__':
    limit_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    run_offseason_harvest(limit=limit_arg)

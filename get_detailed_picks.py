import os
import pandas as pd
import numpy as np
import json
import odds_tracker

from scraper import get_live_meeting_data, get_live_tips_index
from model import predict_probabilities, load_model

def run():
    data = get_live_meeting_data()
    tips_data = get_live_tips_index()
    
    try:
        with open('data/gemini_intel.json', 'r') as f:
            intel_data = json.load(f)
            key_runners = [runner['horse_name'].upper() for runner in intel_data.get('key_runners', [])]
    except Exception:
        key_runners = []
    
    if data.get('status') != 'success' or not data.get('meetings'):
        print("Failed to get live meeting data.")
        return
        
    meeting = data['meetings'][0]
    load_model()
    
    # Load running styles once outside the loop
    running_styles = {}
    try:
        df_styles = pd.read_csv('data/results.csv', usecols=['horse', 'runningpos'])
        df_styles['clean_name'] = df_styles['horse'].str.extract(r'^(.*?)\(')[0].str.strip().str.upper()
        def parse_first_pos(x):
            if not isinstance(x, str): return np.nan
            parts = x.strip().split()
            if not parts: return np.nan
            try: return float(parts[0])
            except: return np.nan
        df_styles['first_pos'] = df_styles['runningpos'].apply(parse_first_pos)
        running_styles = df_styles.groupby('clean_name')['first_pos'].mean().to_dict()
    except Exception as e:
        print("Error parsing running styles:", e)

    # Load sectional bursts
    sectional_bursts = {}
    
    # Compile winning gears from results database
    winning_gears = {}
    try:
        if os.path.exists('data/results.csv') and os.path.exists('data/comments.csv'):
            results = pd.read_csv('data/results.csv', usecols=['date', 'raceno', 'horseno', 'horse'])
            comments = pd.read_csv('data/comments.csv', usecols=['date', 'raceno', 'horseno', 'plc', 'gear'])
            parse_won = lambda x: 1 if str(x).strip() in ['1', '1.0', '1 DH'] or '1 DH' in str(x) else 0
            comments['won_calc'] = comments['plc'].apply(parse_won)
            wins_comments = comments[comments['won_calc'] == 1]
            wins_df = pd.merge(wins_comments, results, on=['date', 'raceno', 'horseno'], how='inner')
            
            if wins_df['horse'].str.contains(r'\(', na=False).any():
                wins_df['clean_name'] = wins_df['horse'].str.extract(r'^(.*?)\(')[0].str.strip().str.upper()
            else:
                wins_df['clean_name'] = wins_df['horse'].astype(str).str.strip().str.upper()
            wins_df['clean_gear'] = wins_df['gear'].fillna('').astype(str).str.strip().str.upper()
            wins_df.loc[wins_df['clean_gear'] == '-', 'clean_gear'] = ''
            for name, group in wins_df.groupby('clean_name'):
                winning_gears[name] = set(group['clean_gear'].unique())
    except Exception as e:
        print("Error compiling winning gears:", e)
    try:
        if os.path.exists('data/runs.csv') and os.path.exists('data/horse_info.csv'):
            runs_df = pd.read_csv('data/runs.csv', usecols=['horse_id', 'time1', 'time2', 'time3', 'time4', 'time5', 'time6'])
            h_info = pd.read_csv('data/horse_info.csv', usecols=['Unnamed: 0', 'horse'])
            h_info['clean_name'] = h_info['horse'].str.extract(r'^(.*?)\(')[0].str.strip().str.upper()
            h_map = h_info[['Unnamed: 0', 'clean_name']].rename(columns={'Unnamed: 0': 'horse_id'}).drop_duplicates()
            m_df = pd.merge(runs_df, h_map, on='horse_id', how='inner')
            
            def parse_last_sec(row):
                for col in ['time6', 'time5', 'time4', 'time3', 'time2']:
                    val = pd.to_numeric(row[col], errors='coerce')
                    if not pd.isna(val) and val > 0:
                        return val
                return pd.to_numeric(row['time1'], errors='coerce')
                
            m_df['last_sec_val'] = m_df.apply(parse_last_sec, axis=1)
            m_df = m_df[m_df['last_sec_val'] > 10.0]
            sectional_bursts = m_df.groupby('clean_name')['last_sec_val'].min().to_dict()
    except Exception as e:
        print("Error loading sectional bursts:", e)

    # Load historical comments to check for troubled runs
    last_comments = {}
    try:
        results = pd.read_csv('data/results.csv', usecols=['date', 'raceno', 'horseno', 'horse'])
        comments = pd.read_csv('data/comments.csv', usecols=['date', 'raceno', 'horseno', 'comment'])
        df_comm = pd.merge(comments, results, on=['date', 'raceno', 'horseno'], how='inner')
        df_comm['clean_name'] = df_comm['horse'].str.extract(r'^(.*?)\(')[0].str.strip().str.upper()
        df_comm = df_comm.sort_values(by='date', ascending=False)
        last_comments = df_comm.drop_duplicates(subset=['clean_name'], keep='first').set_index('clean_name')['comment'].to_dict()
    except Exception as e:
        print("Error loading comments:", e)

    global_best_bets = []
    
    for race in meeting.get('races', []):
        if not race.get('runners'): continue
        
        df_runners = pd.DataFrame(race['runners'])
        if 'win_odds' in df_runners.columns:
            df_runners['scraped_win_odds'] = df_runners['win_odds'].copy()
        else:
            df_runners['scraped_win_odds'] = 0.0
        
        # Check time to post for this race
        minutes_to_post = 999.0
        from datetime import datetime, timezone, timedelta
        try:
            post_time_str = race.get('time')
            if post_time_str:
                post_time = datetime.fromisoformat(post_time_str)
                now_hkt = datetime.now(timezone(timedelta(hours=8)))
                minutes_to_post = (post_time - now_hkt).total_seconds() / 60.0
        except Exception as e:
            print(f"Error parsing post time for race {race.get('race_no')}: {e}")

        current_race_tips = tips_data.get(race.get('race_no', 0), {})
        df_runners['consensus_score'] = df_runners['no'].map(lambda x: current_race_tips.get(x, 0))
        
        class_str = race.get("class_dist", "")
        class_int = 4
        if "Class 1" in class_str: class_int = 1
        elif "Class 2" in class_str: class_int = 2
        elif "Class 3" in class_str: class_int = 3
        elif "Class 4" in class_str: class_int = 4
        elif "Class 5" in class_str: class_int = 5
        elif "Group" in class_str or "G" in class_str: class_int = 0
            
        # Parse distance
        import re
        dist_match = re.search(r'(\d+)m', class_str, re.IGNORECASE)
        distance = int(dist_match.group(1)) if dist_match else 0

        race_going = race.get('going', meeting.get('going', 'GOOD'))
        probs, df_runners = predict_probabilities(df_runners, venue=meeting.get('venue'), going=race_going, race_date=meeting.get('date'), race_class_int=class_int, track_type=race.get('track', 'TURF'))
        
        if 'clean_name' not in df_runners.columns:
            df_runners['clean_name'] = df_runners['name'].str.upper().str.strip()
            
        # Map last comments and check for troubled runs (interference, etc.)
        df_runners['last_comment'] = df_runners['clean_name'].map(last_comments).fillna("").str.lower()
        trouble_keywords = ['interference', 'blocked', 'held up', 'checked', 'crowded', 'hampered', 'stumble', 'clipt', 'clip ', 'check ']
        df_runners['had_trouble'] = df_runners['last_comment'].apply(lambda c: any(kw in c for kw in trouble_keywords)).astype(int)

        df_runners['model_prob'] = probs
        df_runners['implied_raw'] = 1 / df_runners['win_odds'].replace(0, 1.0)
        sum_implied = df_runners['implied_raw'].sum()
        df_runners['implied_prob'] = df_runners['implied_raw'] / sum_implied if sum_implied > 0 else (1/len(df_runners))
        
        
        if key_runners:
            df_runners['consensus_score'] += np.where(df_runners['name'].str.upper().isin(key_runners), 10, 0)

        recent_pos = pd.to_numeric(df_runners.get('recent_avg_pos', 7.0), errors='coerce').fillna(7.0)
        recent_win = pd.to_numeric(df_runners.get('recent_win_rate', 0.0), errors='coerce').fillna(0.0)
        track_match = (df_runners.get('ST_vs_HV_pref', 'Neutral') == meeting.get('venue')).astype(int)
        going_match = (df_runners.get('last_form_going', 'Unknown') == race_going).astype(int)
        vet_issue = pd.to_numeric(df_runners.get('prev_run_vet_finding', 0), errors='coerce').fillna(0)
        class_drop = pd.to_numeric(df_runners.get('class_diff', 0), errors='coerce').fillna(0)
        
        # Super Standout condition: 
        is_super_standout = (recent_pos <= 3.5) & ((track_match == 1) | (going_match == 1)) & (vet_issue == 0)
        
        # Secondary edge: Class droppers who are in decent form (<= 5.0) and healthy
        is_class_dropper_standout = (class_drop > 0) & (recent_pos <= 5.0) & (vet_issue == 0)
        
        # Map sectional times and find fastest last sectional
        df_runners['best_last_sec'] = df_runners['clean_name'].map(sectional_bursts).fillna(99.0)

        # Scale debutant penalty:
        is_debutant = (recent_pos == 7.0) & (recent_win == 0.0)
        debutant_penalty_val = np.where(is_debutant, -0.05, 0.0)
        if class_int == 5:
            debutant_penalty_val = debutant_penalty_val * 0.5
        # If consensus from trials is strong, waive it
        consensus = pd.to_numeric(df_runners.get('consensus_score', 0), errors='coerce').fillna(0)
        debutant_penalty = np.where(consensus > 5.0, 0.0, debutant_penalty_val)

        # First-Time Gear Boost (Blinkers B1 / Visor V1 split):
        if 'horse_gear' in df_runners.columns:
            has_B1 = df_runners['horse_gear'].astype(str).str.contains('B1')
            has_V1 = df_runners['horse_gear'].astype(str).str.contains('V1')
            first_time_gear_boost = np.where(has_B1, 0.04, np.where(has_V1, 0.03, 0.0))
        else:
            first_time_gear_boost = 0.0

        # False Favorite Penalty: Reduced to 5% penalty (-0.05) based on Ronan's feedback
        # EXEMPTION: Class droppers (class_drop > 0) and horses with trouble/interference (had_trouble == 1)
        false_fav_penalty = np.where(
            (df_runners['implied_prob'] > 0.20) & 
            (recent_pos > 6.0) & 
            (class_drop <= 0) & 
            (df_runners['had_trouble'] == 0), 
            -0.05, 
            0.0
        )
        
        standout_boost = np.where(is_super_standout, 0.08, 0.0)
        standout_boost += np.where(is_class_dropper_standout, 0.05, 0.0)
        
        # Consensus intel boost (gentle tie breaker)
        consensus_boost = np.where(consensus > 0, 0.01 * np.minimum(consensus, 12), 0.0)
        
        if 'clean_name' not in df_runners.columns:
            df_runners['clean_name'] = df_runners['name'].str.upper().str.strip()
        df_runners['avg_first_pos'] = df_runners['clean_name'].map(running_styles).fillna(6.0)

        # Pace Pressure Index: Count runners with avg_first_pos <= 3.5 (true speed horses)
        speed_count = (df_runners['avg_first_pos'] <= 3.5).sum()
        
        closer_pace_boost = 0.0
        closer_pace_penalty = 0.0
        lone_speed_boost = 0.0
        
        # Late-Closer Boost: Closers who have a proven elite sectional burst (< 22.5s)
        is_elite_closer = (df_runners['avg_first_pos'] > 5.5) & (df_runners['best_last_sec'] < 22.5)
        late_closer_boost = np.where(is_elite_closer, 0.02, 0.0)
        
        # Smart Wet Turf Adjustments
        race_track_type = str(race.get('track', 'TURF')).upper()
        is_wet_turf = (str(race_going).upper() in ["YIELDING", "GOOD TO YIELDING", "SOFT", "HEAVY"]) and ("ALL WEATHER" not in race_track_type and "AWT" not in race_track_type)
        
        on_speed_wet_boost = 0.0
        yielding_form_boost = 0.0
        
        if is_wet_turf:
            on_speed_wet_boost = np.where(df_runners['avg_first_pos'] <= 4.5, 0.03, 0.0)
            has_yielding_form = df_runners['last_form_going'].astype(str).str.upper().str.contains("YIELD|SOFT|HEAVY|WET")
            yielding_form_boost = np.where(has_yielding_form, 0.02, 0.0)
            
        # Apply Pace Pressure Refinements (Tuned down to 2% to ensure balanced split)
        # 1. Pace collapse trigger raised to 4+ speed horses
        if speed_count >= 4:
            # High Pace Pressure: pace collapse likely. Boost closers, neutralize on-speed wet boost.
            on_speed_wet_boost = 0.0
            closer_pace_boost = np.where((df_runners['avg_first_pos'] > 5.5) & (recent_pos <= 5.5), 0.02, 0.0)
        elif speed_count <= 1:
            # Low Pace Pressure: speed bias highly likely. Boost lone speed (if in decent form), penalize deep closers (only in sprints, exempt elite closers)
            # Lone leader boost limited to competitive horses (recent_pos <= 5.0)
            lone_speed_boost = np.where((df_runners['avg_first_pos'] <= 3.5) & (recent_pos <= 5.0), 0.02, 0.0)
            # Closer penalty limited to sprints (<=1200m) and non-elite closers (recent_pos > 4.0, no elite sectional burst)
            closer_pace_penalty = np.where(
                (df_runners['avg_first_pos'] > 6.0) & 
                (distance <= 1200) & 
                (recent_pos > 4.0) & 
                (df_runners['best_last_sec'] >= 22.5), 
                -0.02, 
                0.0
            )
            
        # Jockey/Trainer Combo Partnership Boost (Ronan's conservative 3% boost):
        jockey_trainer_boost = 0.0
        try:
            if os.path.exists('data/jockey_trainer_partnerships.csv') and 'jockey' in df_runners.columns and 'trainer' in df_runners.columns:
                jt_df = pd.read_csv('data/jockey_trainer_partnerships.csv')
                jt_df['jockey_clean'] = jt_df['jockey'].astype(str).str.strip().str.upper()
                jt_df['trainer_clean'] = jt_df['trainer'].astype(str).str.strip().str.upper()
                
                df_runners['jockey_clean'] = df_runners['jockey'].astype(str).str.strip().str.upper()
                df_runners['trainer_clean'] = df_runners['trainer'].astype(str).str.strip().str.upper()
                
                # Check for existing column before merging to avoid duplicate columns
                if 'win_rate_jt' in df_runners.columns:
                    df_runners = df_runners.drop(columns=['win_rate_jt'])
                df_runners = pd.merge(df_runners, jt_df[['jockey_clean', 'trainer_clean', 'win_rate']], on=['jockey_clean', 'trainer_clean'], how='left')
                df_runners = df_runners.rename(columns={'win_rate': 'win_rate_jt'})
                df_runners['win_rate_jt'] = df_runners['win_rate_jt'].fillna(0.0)
            else:
                df_runners['win_rate_jt'] = 0.0
        except Exception as e:
            print(f"Error loading partnerships: {e}")
            df_runners['win_rate_jt'] = 0.0
            
        MODERN_ELITE = {
            ('Z PURTON', 'C S SHUM'), ('Z PURTON', 'K W LUI'), ('Z PURTON', 'J SIZE'),
            ('Z PURTON', 'P C NG'), ('Z PURTON', 'C FOWNES'), ('H BOWMAN', 'C FOWNES'),
            ('H BOWMAN', 'C S SHUM'), ('C Y HO', 'K W LUI'), ('K TEETAN', 'P C NG'),
            ('J MOREIRA', 'J SIZE'), ('J MOREIRA', 'C FOWNES'), ('J MOREIRA', 'C S SHUM'),
            ('A ATZENI', 'P C NG')
        }
        
        is_elite_jt = (
            (df_runners['win_rate_jt'] >= 0.18) | 
            df_runners.apply(lambda r: (str(r.get('jockey', '')).strip().upper(), str(r.get('trainer', '')).strip().upper()) in MODERN_ELITE, axis=1)
        )
        jockey_trainer_boost = np.where(is_elite_jt, 0.03, 0.0)
        
        multiplier = 1.0 + standout_boost + consensus_boost + false_fav_penalty + debutant_penalty + first_time_gear_boost + on_speed_wet_boost + yielding_form_boost + closer_pace_boost + closer_pace_penalty + lone_speed_boost + late_closer_boost + jockey_trainer_boost
        multiplier = np.maximum(multiplier, 0.1)
        df_runners['model_prob'] = df_runners['model_prob'] * multiplier
            
        total_b = df_runners['model_prob'].sum()
        if total_b > 0:
            df_runners['model_prob'] = df_runners['model_prob'] / total_b
            
        df_runners['value_diff'] = df_runners['model_prob'] - df_runners['implied_prob']
        
        df_runners['baseline_odds'] = df_runners.apply(lambda row: odds_tracker.get_baseline_odds(
            meeting.get('date', 'today'), meeting.get('venue', 'HK'), race.get('race_no', 0), row['no'], row['scraped_win_odds'], minutes_to_post), axis=1)

        df_runners['shift_bonus'] = df_runners.apply(lambda row: odds_tracker.calculate_odds_shift_bonus(
            row['baseline_odds'], row['scraped_win_odds'], pd.to_numeric(row.get('recent_avg_pos', 7.0)), 
            pd.to_numeric(row.get('prev_run_vet_finding', 0))), axis=1)

        # Time-Based Liquidity Check: Only apply smart money shifts if within 60 minutes of post time
        if minutes_to_post > 60:
            # Lock to core structural probability
            df_runners['gs_score'] = df_runners['model_prob'] * 100
        else:
            # Unlock smart money shifts (incorporating shift_bonus, excluding raw value bias)
            df_runners['gs_score'] = (df_runners['model_prob'] * 100) + df_runners['shift_bonus']
        
        p_min = df_runners['model_prob'].min()
        p_max = df_runners['model_prob'].max()
        if p_max > p_min:
            df_runners['confidence'] = (15.0 + ((df_runners['model_prob'] - p_min) / (p_max - p_min)) * 70).round(0).astype(int)
        else:
            df_runners['confidence'] = 50
            
        race_picks = df_runners.sort_values(by='gs_score', ascending=False)
        
        best = race_picks.iloc[0].to_dict()
        best.update({"race_no": race.get("race_no"), "class_dist": class_str})
        global_best_bets.append(best)

    global_best_bets = sorted(global_best_bets, key=lambda x: x.get('gs_score', 0), reverse=True)
    
    print("TOP 5 DETAILED PICKS:")
    for i in range(min(5, len(global_best_bets))):
        bb = global_best_bets[i]
        print(f"\n--- PICK {i+1} : Race {bb['race_no']} - {bb['name']} ---")
        for k in ['no', 'name', 'jockey', 'trainer', 'draw', 'actual_weight', 'horse_rating', 'win_odds', 'confidence', 'value_diff', 'jockey_win_rate', 'trainer_win_rate', 'recent_avg_pos', 'ST_vs_HV_pref', 'last_form_going', 'track_pref_match', 'going_pref_match']:
            if k in bb:
                print(f"{k}: {bb[k]}")
        # Check overseas gear consistent win comment
        tonight_gear = str(bb.get('horse_gear', '')).strip().upper()
        if tonight_gear in ['', '-']:
            tonight_gear = ''
        horse_win_gears = winning_gears.get(str(bb.get('clean_name', bb.get('name', ''))).strip().upper(), set())
        is_gear_matched = (tonight_gear in horse_win_gears) or (tonight_gear == '' and '' in horse_win_gears)
        
        if bb.get('has_overseas_form') == 1 and is_gear_matched:
            print("Note: This horse had form overseas and won with the same consistent gear in the Hong Kong environment.")

if __name__ == '__main__':
    run()

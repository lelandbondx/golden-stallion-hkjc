import os
import pandas as pd
import numpy as np

from scraper import get_live_meeting_data, get_live_tips_index
from model import predict_probabilities, load_model

import json
import odds_tracker
def run():
    print("Loading data...")
    data = get_live_meeting_data()
    tips_data = get_live_tips_index()
    
    # Load private expert intel
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
    print(f"Meeting: {meeting['venue']} - {meeting['date']} - Going: {meeting['going']}")
    
    # Cache live odds for this meeting (if any are scraped/positive)
    try:
        odds_tracker.cache_live_odds(meeting.get('date'), meeting.get('venue'), meeting.get('races', []))
    except Exception as e:
        print("Failed to cache live odds:", e)
        
    # Load model
    load_model()
    
    # Load precomputed running styles, comments, and sectional bursts
    running_styles = {}
    last_comments = {}
    sectional_bursts = {}
    try:
        with open('data/precomputed_features.json', 'r', encoding='utf-8') as f:
            precomputed = json.load(f)
            running_styles = precomputed.get('running_styles', {})
            last_comments = precomputed.get('last_comments', {})
            sectional_bursts = precomputed.get('sectional_bursts', {})
    except Exception as e:
        print("Error loading precomputed features:", e)

    global_best_bets = []
    dual_staking_wagers = []
    
    for race in meeting.get('races', []):
        if not race.get('runners'): continue
        
        df_runners = pd.DataFrame(race['runners'])
        # Load win_odds from cache if the scraper returns 0.0 (completed races)
        if 'win_odds' in df_runners.columns:
            df_runners['win_odds'] = df_runners.apply(
                lambda row: odds_tracker.get_cached_odds(
                    meeting.get('date', 'today'), meeting.get('venue', 'HK'), race.get('race_no', 0), row['no'], row['win_odds']
                ), axis=1
            )
            df_runners['scraped_win_odds'] = df_runners['win_odds'].copy()
        else:
            df_runners['win_odds'] = 20.0
            df_runners['scraped_win_odds'] = 20.0
        
        current_race_tips = tips_data.get(race.get('race_no', 0), {})
        df_runners['consensus_score'] = df_runners['no'].map(lambda x: current_race_tips.get(x, 0))
        if key_runners:
            df_runners['consensus_score'] += np.where(df_runners['name'].str.upper().isin(key_runners), 10, 0)
        
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
            
        class_str = race.get("class_dist", "")
        
        # Check if we have a frozen prediction for this race
        frozen_runners = odds_tracker.get_frozen_predictions(meeting.get('date'), meeting.get('venue'), race.get('race_no'))
        
        # Determine if we should defrost (recalculate) due to scratches or track change
        is_defrost = False
        if frozen_runners is not None:
            live_going = race.get('going', meeting.get('going', 'GOOD'))
            frozen_going = frozen_runners[0].get('current_going', 'GOOD') if len(frozen_runners) > 0 else 'GOOD'
            is_defrost = odds_tracker.should_defrost_predictions(frozen_runners, race.get('runners', []), frozen_going, live_going)
            
        if minutes_to_post <= 60 and frozen_runners is not None and not is_defrost:
            df_runners = pd.DataFrame(frozen_runners)
            # Print picks as normal from the frozen cache
            race_picks = df_runners.sort_values(by='gs_score', ascending=False)
            print(f"\n--- RACE {race.get('race_no')} : {class_str} ---")
            for i in range(min(5, len(race_picks))):
                pick = race_picks.iloc[i]
                print(f"{i+1}st Pick: #{pick['no']} {pick['name']} (Odds: {pick['win_odds']:.1f}) - Conf: {pick['confidence']}% - EV: {pick['value_diff']:.3f} - Jockey: {pick['jockey']}")
                
            if len(race_picks) > 4:
                p1 = race_picks.iloc[0]
                p5 = race_picks.iloc[4]
                dual_staking_wagers.append({
                    "race_no": race.get("race_no"),
                    "p1_no": p1['no'],
                    "p1_name": p1['name'],
                    "p1_odds": float(p1.get('win_odds', 20.0)),
                    "p5_no": p5['no'],
                    "p5_name": p5['name'],
                    "p5_odds": float(p5.get('win_odds', 20.0))
                })
            
            best = race_picks.iloc[0].to_dict()
            best.update({"race_no": race.get("race_no"), "class_dist": class_str})
            global_best_bets.append(best)
            continue
        class_int = 4
        if "Class 1" in class_str: class_int = 1
        elif "Class 2" in class_str: class_int = 2
        elif "Class 3" in class_str: class_int = 3
        elif "Class 4" in class_str: class_int = 4
        elif "Class 5" in class_str: class_int = 5
        elif "Group" in class_str or "G" in class_str: class_int = 0
            
        race_going = race.get('going', meeting.get('going', 'GOOD'))
        probs, df_runners = predict_probabilities(df_runners, venue=meeting.get('venue'), going=race_going, race_date=meeting.get('date'), race_class_int=class_int, track_type=race.get('track', 'TURF'))
        
        if 'clean_name' not in df_runners.columns:
            df_runners['clean_name'] = df_runners['name'].str.upper().str.strip()
            
        # Parse distance
        import re
        dist_match = re.search(r'(\d+)m', class_str, re.IGNORECASE)
        distance = int(dist_match.group(1)) if dist_match else 0
        
        # Map last comments and check for troubled runs (interference, etc.)
        df_runners['last_comment'] = df_runners['clean_name'].map(last_comments).fillna("").str.lower()
        trouble_keywords = ['interference', 'blocked', 'held up', 'checked', 'crowded', 'hampered', 'stumble', 'clipt', 'clip ', 'check ']
        df_runners['had_trouble'] = df_runners['last_comment'].apply(lambda c: any(kw in c for kw in trouble_keywords)).astype(int)

        df_runners['model_prob'] = probs
        df_runners['implied_raw'] = 1 / df_runners['win_odds'].replace(0, 1.0)
        sum_implied = df_runners['implied_raw'].sum()
        df_runners['implied_prob'] = df_runners['implied_raw'] / sum_implied if sum_implied > 0 else (1/len(df_runners))
        
        
        
        # Targeted Standout Boost: Only boost if there is a confluence of strong indicators
        recent_pos = pd.to_numeric(df_runners.get('recent_avg_pos', 7.0), errors='coerce').fillna(7.0)
        recent_win = pd.to_numeric(df_runners.get('recent_win_rate', 0.0), errors='coerce').fillna(0.0)
        track_match = (df_runners.get('ST_vs_HV_pref', 'Neutral') == meeting.get('venue')).astype(int)
        going_match = (df_runners.get('last_form_going', 'Unknown') == race_going).astype(int)
        vet_issue = pd.to_numeric(df_runners.get('prev_run_vet_finding', 0), errors='coerce').fillna(0)
        class_drop = pd.to_numeric(df_runners.get('class_diff', 0), errors='coerce').fillna(0)
        
        # Super Standout condition: 
        # Extremely good recent form (<= 3.5 avg pos) AND proven at this track/going AND healthy
        is_super_standout = (recent_pos <= 3.5) & ((track_match == 1) | (going_match == 1)) & (vet_issue == 0)
        
        # Secondary edge: Class droppers who are in decent form (<= 5.0) and healthy
        is_class_dropper_standout = (class_drop > 0) & (recent_pos <= 5.0) & (vet_issue == 0)
        
        standout_boost = np.where(is_super_standout, 0.08, 0.0) # 8% boost for true standouts
        standout_boost += np.where(is_class_dropper_standout, 0.05, 0.0) # 5% boost for dangerous class droppers
        
        # Scale debutant penalty:
        is_debutant = (recent_pos == 7.0) & (recent_win == 0.0)
        debutant_penalty_val = np.where(is_debutant, -0.05, 0.0)
        if class_int == 5:
            debutant_penalty_val = debutant_penalty_val * 0.5
            
        # Load engineered trials
        trial_features = {}
        if os.path.exists('data/engineered_trial_features.json'):
            try:
                with open('data/engineered_trial_features.json', 'r', encoding='utf-8') as f:
                    trial_features = json.load(f)
            except Exception as e:
                print(f"Error loading engineered trial features: {e}")
                
        # Determine if debutant has strong trials
        has_strong_trial = []
        for name in df_runners['clean_name'].astype(str).str.upper().str.strip():
            strong = False
            if name in trial_features:
                t_pos = trial_features[name].get('best_trial_pos_ratio', 1.0)
                t_speed = trial_features[name].get('best_trial_speed_diff', 0.0)
                if t_pos <= 0.35 or t_speed > 0.0:
                    strong = True
            has_strong_trial.append(strong)
        has_strong_trial = np.array(has_strong_trial)
            
        # If consensus from trials is strong OR we have a strong trial, waive it
        consensus = pd.to_numeric(df_runners.get('consensus_score', 0), errors='coerce').fillna(0)
        debutant_penalty = np.where((consensus > 5.0) | has_strong_trial, 0.0, debutant_penalty_val)
        
        # Map sectional times and find fastest last sectional
        df_runners['best_last_sec'] = df_runners['clean_name'].map(sectional_bursts).fillna(99.0)

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
        
        # Consensus intel boost (gentle tie breaker)
        consensus_boost = np.where(consensus > 0, 0.01 * np.minimum(consensus, 12), 0.0)
        
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
        
        # Happy Valley C-Course Draw Bias Adjustments
        is_hv = meeting.get('venue') == 'Happy Valley'
        hv_c_course_boost = 0.0
        hv_c_course_penalty = 0.0
        if is_hv and "ALL WEATHER" not in race_track_type and "AWT" not in race_track_type:
            # Inside gate speed bias: Front runners (avg_first_pos <= 3.5) drawn 1-4
            is_inside_speed = (df_runners['avg_first_pos'] <= 3.5) & (df_runners['draw'] <= 4)
            hv_c_course_boost = np.where(is_inside_speed, 0.03, 0.0)
            
            # Wide draw penalty in sprints (<= 1200m) for gates 9-12
            is_wide_sprinter = (distance <= 1200) & (df_runners['draw'] >= 9)
            hv_c_course_penalty = np.where(is_wide_sprinter, -0.04, 0.0)
            
        # Quantitative Barrier Trial Multipliers
        trial_boost = []
        trial_penalty = []
        
        for idx, r in df_runners.iterrows():
            clean_name = str(r.get('clean_name', '')).strip().upper()
            t_boost = 0.0
            t_penalty = 0.0
            
            if clean_name in trial_features:
                t_data = trial_features[clean_name]
                t_pos = t_data.get('best_trial_pos_ratio', 1.0)
                t_speed = t_data.get('best_trial_speed_diff', 0.0)
                t_jockeys = [j.upper() for j in t_data.get('trial_jockeys', [])]
                r_jockey = str(r.get('jockey', '')).strip().upper()
                
                jockey_match = r_jockey in t_jockeys
                
                # 1. Elite trial (placed top 35% with raceday jockey commitment)
                if t_pos <= 0.35 and jockey_match:
                    t_boost += 0.03
                    
                # 2. Raw speed trial (speed diff >= 0.5s faster than standard)
                if t_speed >= 0.5:
                    t_boost += 0.02
                    
                # 3. Poor trial (bottom 10% and slow)
                if t_pos >= 0.90 and t_speed <= -1.0:
                    t_penalty -= 0.03
                    
            trial_boost.append(t_boost)
            trial_penalty.append(t_penalty)
            
        trial_boost = np.array(trial_boost)
        trial_penalty = np.array(trial_penalty)
        
        multiplier = 1.0 + standout_boost + consensus_boost + false_fav_penalty + debutant_penalty + first_time_gear_boost + on_speed_wet_boost + yielding_form_boost + closer_pace_boost + closer_pace_penalty + lone_speed_boost + late_closer_boost + jockey_trainer_boost + hv_c_course_boost + hv_c_course_penalty + trial_boost + trial_penalty
        # Ensure multiplier doesn't go below 0.1
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
        print(f"\n--- RACE {race.get('race_no')} : {class_str} ---")
        
        for i in range(min(5, len(race_picks))):
            pick = race_picks.iloc[i]
            print(f"{i+1}st Pick: #{pick['no']} {pick['name']} (Odds: {pick['win_odds']:.1f}) - Conf: {pick['confidence']}% - EV: {pick['value_diff']:.3f} - Jockey: {pick['jockey']}")
            
        # Compile dual-staking wagers for this race: Rank 1 + Rank 5
        if len(race_picks) > 4:
            p1 = race_picks.iloc[0]
            p5 = race_picks.iloc[4]
            dual_staking_wagers.append({
                "race_no": race.get("race_no"),
                "p1_no": p1['no'],
                "p1_name": p1['name'],
                "p1_odds": float(p1['win_odds']),
                "p5_no": p5['no'],
                "p5_name": p5['name'],
                "p5_odds": float(p5['win_odds'])
            })
            
        best = race_picks.iloc[0].to_dict()
        best.update({"race_no": race.get("race_no"), "class_dist": class_str})
        global_best_bets.append(best)
        
        # Always freeze predictions once they are generated, so they don't change overnight
        try:
            odds_tracker.save_frozen_predictions(meeting.get('date'), meeting.get('venue'), race.get('race_no'), df_runners.to_dict(orient='records'))
        except Exception as e:
            print("Failed to save frozen predictions:", e)

    global_best_bets = sorted(global_best_bets, key=lambda x: x.get('gs_score', 0), reverse=True)
    
    print("\n\n--- OVERALL GLOBAL BEST BETS ---")
    for i in range(min(3, len(global_best_bets))):
        bb = global_best_bets[i]
        print(f"Top Pick {i+1}: Race {bb['race_no']} - #{bb['no']} {bb['name']} (Odds: {bb['win_odds']:.1f}, Conf: {bb['confidence']}%, EV: {bb['value_diff']:.3f})")

    print("\n\n--- RECOMMENDED DUAL-STAKING BETS (RANK 1 + RANK 5) ---")
    for bet in dual_staking_wagers:
        print(f"Race {bet['race_no']} Bet Selection: Anchor #{bet['p1_no']} {bet['p1_name']} ({bet['p1_odds']:.1f}) | Sleeper #{bet['p5_no']} {bet['p5_name']} ({bet['p5_odds']:.1f})")

if __name__ == '__main__':
    run()

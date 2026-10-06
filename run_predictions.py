import os
import sys
import pandas as pd
import numpy as np
import json
import re
from datetime import datetime, timezone, timedelta

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from scraper import get_live_meeting_data, get_live_tips_index
from model import predict_probabilities, load_model
import odds_tracker

def check_stewards_excuse(comment, vet_status=0):
    if not comment or pd.isna(comment):
        return vet_status != 0
    c = str(comment).lower()
    
    # Check for negations / clean run phrases
    clean_phrases = ['without interruption', 'no interference', 'not checked', 'no incident', 'clear run throughout', 'without impediment']
    if any(cp in c for cp in clean_phrases):
        return False
        
    # True excuses:
    excuse_keywords = [
        'badly checked', 'severely checked', 'checked', 'check ', 'crowded', 'hampered', 
        'held up', 'no clear run', 'denied a clear run', 'pocketed', 'clipped heels', 'clip heels',
        'lost ground at start', 'slow to begin', 'stumbled', 'stumble', 'lost shoe', 'lost plate', 
        'lost a plate', 'saddle slipped', 'blood in trachea', 'trachea', 'forced wide',
        'bleeder', 'irregular heart', 'heart irregularity', 'lame', 'lameness', 'mucus'
    ]
    
    has_excuse = any(kw in c for kw in excuse_keywords)
    if vet_status != 0:
        has_excuse = True
    return has_excuse

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
    venue_name = meeting.get('venue', 'Happy Valley')
    print(f"Meeting: {venue_name} - {meeting.get('date')} - Going: {meeting.get('going')}")
    
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
            race_picks = df_runners.sort_values(by='gs_score', ascending=False).reset_index(drop=True)
            print(f"\n--- RACE {race.get('race_no')} : {class_str} ---")
            for i in range(min(5, len(race_picks))):
                pick = race_picks.iloc[i]
                print(f"Pick {i+1}: #{pick['no']} {pick['name']} (Odds: {pick['win_odds']:.1f}) - Conf: {pick['confidence']}% - EV: {pick['value_diff']:.3f} - Jockey: {pick['jockey']}")
                
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
        dist_match = re.search(r'(\d+)m', class_str, re.IGNORECASE)
        distance = int(dist_match.group(1)) if dist_match else 0
        
        # Map last comments and check for troubled runs (interference, etc.)
        df_runners['last_comment'] = df_runners['clean_name'].map(last_comments).fillna("").str.lower()
        trouble_keywords = [
            'interference', 'blocked', 'held up', 'checked', 'crowded', 'hampered', 
            'stumble', 'clipt', 'clip ', 'check ', 'wide without cover', 'no cover', 
            'raced wide', 'severely check', 'tight room', 'unbalanced', 'lost ground'
        ]
        df_runners['had_trouble'] = df_runners['last_comment'].apply(lambda c: any(kw in c for kw in trouble_keywords)).astype(int)

        # Store pure raw model probability before multipliers
        df_runners['raw_model_prob'] = probs.copy() if hasattr(probs, 'copy') else np.array(probs)
        df_runners['raw_rank'] = df_runners['raw_model_prob'].rank(ascending=False, method='min').astype(int)

        df_runners['model_prob'] = probs.copy() if hasattr(probs, 'copy') else np.array(probs)
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
        
        standout_boost = np.where(is_super_standout, 0.02, 0.0) # 2% boost for true standouts
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

        # First-Time Gear Boost (Blinkers B1 3.0% / Visor V1 2.5%):
        if 'horse_gear' in df_runners.columns:
            has_B1 = df_runners['horse_gear'].astype(str).str.contains('B1')
            has_V1 = df_runners['horse_gear'].astype(str).str.contains('V1')
            first_time_gear_boost = np.where(has_B1, 0.03, np.where(has_V1, 0.025, 0.0))
        else:
            first_time_gear_boost = 0.0
        
        # False Favorite Penalty: -3.0% only if odds < 5.0 / implied > 20%, recent_pos > 6.0, no class drop, and run is not excused
        df_runners['had_excuse'] = df_runners.apply(
            lambda r: check_stewards_excuse(r.get('last_comment', ''), r.get('prev_run_vet_finding', 0)), axis=1
        )
        false_fav_penalty = np.where(
            ((df_runners['implied_prob'] > 0.20) | ((df_runners['win_odds'] > 0) & (df_runners['win_odds'] < 5.0))) & 
            (recent_pos > 6.0) & 
            (class_drop <= 0) & 
            (~df_runners['had_excuse']), 
            -0.03, 
            0.0
        )
        
        # Consensus intel boost (gentle tie breaker capped at +3.5%)
        consensus_boost = np.where(consensus > 0, 0.01 * np.minimum(consensus, 3.5), 0.0)
        
        df_runners['avg_first_pos'] = df_runners['clean_name'].map(running_styles).fillna(6.0)

        # Pace Pressure Index: Count runners with avg_first_pos <= 3.5 (true speed horses)
        speed_count = (df_runners['avg_first_pos'] <= 3.5).sum()
        
        closer_pace_boost = 0.0
        frontrunner_pace_penalty = 0.0
        closer_pace_penalty = 0.0
        lone_speed_boost = 0.0
        
        # Late-Closer Boost: Closers who have a proven elite sectional burst (< 22.5s) (Tuned to +1.0%)
        is_elite_closer = (df_runners['avg_first_pos'] > 5.5) & (df_runners['best_last_sec'] < 22.5)
        late_closer_boost = np.where(is_elite_closer, 0.01, 0.0)
        
        # Smart Wet Turf & Overseas Surface Adjustments
        race_track_type = str(race.get('track', 'TURF')).upper()
        is_wet_turf = (str(race_going).upper() in ["YIELDING", "GOOD TO YIELDING", "SOFT", "HEAVY"]) and ("ALL WEATHER" not in race_track_type and "AWT" not in race_track_type)
        is_awt_race = ("ALL WEATHER" in race_track_type) or ("AWT" in race_track_type)
        
        on_speed_wet_boost = 0.0
        yielding_form_boost = 0.0
        polytrack_awt_boost = 0.0
        
        if is_wet_turf:
            on_speed_wet_boost = np.where(df_runners['avg_first_pos'] <= 4.5, 0.03, 0.0)
            has_yielding_form = df_runners['last_form_going'].astype(str).str.upper().str.contains("YIELD|SOFT|HEAVY|WET|^S$|^H$|HVY")
            yielding_form_boost = np.where(has_yielding_form, 0.025, 0.0)
            
        if is_awt_race:
            has_poly_form = (df_runners.get('has_overseas_form', 0) == 1) & (
                df_runners['last_form_going'].astype(str).str.upper().str.contains("POLY|SYNTH|AWT|STAND|TAPETA") |
                (df_runners.get('AWT_win_rate', 0) > 0) |
                (df_runners.get('AWT_vs_Turf_pref', '') == 'AWT')
            )
            polytrack_awt_boost = np.where(has_poly_form, 0.025, 0.0)
            
        # Apply Pace Pressure Refinements
        is_hv = ('HAPPY VALLEY' in str(meeting.get('venue', '')).upper()) or (meeting.get('venue') == 'Happy Valley')
        is_st = ('SHA TIN' in str(meeting.get('venue', '')).upper()) or (meeting.get('venue') == 'Sha Tin')

        # 1. Pace collapse trigger (4+ speed horses): Frontrunners penalized (-2.5%), closers boosted (+2.0%)
        if speed_count >= 4:
            on_speed_wet_boost = 0.0
            frontrunner_pace_penalty = np.where(df_runners['avg_first_pos'] <= 3.5, -0.025, 0.0)
            closer_pace_boost = np.where((df_runners['avg_first_pos'] > 5.5) & (recent_pos <= 5.5), 0.02, 0.0)
        elif speed_count <= 1:
            # Low Pace Pressure: speed bias likely. Boost lone speed (2% if recent_pos <= 5.5, or Z Purton), penalize deep closers
            is_purton_leader = df_runners['jockey'].astype(str).str.strip().str.upper() == 'Z PURTON'
            lone_speed_boost = np.where((df_runners['avg_first_pos'] <= 3.5) & ((recent_pos <= 5.5) | is_purton_leader), 0.02, 0.0)
            
            # Race-proven gate speed check (Races outrank trials: trials cannot exempt closer penalty)
            has_race_gate_speed = (df_runners['avg_first_pos'] <= 4.5) | df_runners['last_comment'].str.contains('jumped well|began speedily|led early|raced prominently', case=False, na=False)
            
            # Closer penalty in sprints (<=1200m)
            is_sprint_slow_closer = (distance <= 1200) & (df_runners['avg_first_pos'] > 6.0) & (recent_pos > 4.0) & (df_runners['best_last_sec'] >= 22.5) & (~has_race_gate_speed)
            # Closer penalty on HV 1650/1800/2200m only if avg_first_pos >= 8.0 AND draw 9-12 AND best_last_sec >= 22.5 (waived if verified sub-22.5s last 400m)
            is_hv_route_slow_closer = is_hv & (distance >= 1650) & (df_runners['avg_first_pos'] >= 8.0) & (df_runners['draw'] >= 9) & (df_runners['best_last_sec'] >= 22.5)
            
            closer_pace_penalty = np.where(is_sprint_slow_closer | is_hv_route_slow_closer, -0.03, 0.0)
            
        actual_weights = pd.to_numeric(df_runners.get('actual_weight', 125), errors='coerce').fillna(125)
        draws = pd.to_numeric(df_runners.get('draw', 6), errors='coerce').fillna(6)

        # Wide Topweight flag at Happy Valley (Gates 9-12 AND Weight >= 132)
        is_hv_wide_heavy = is_hv & (draws >= 9) & (actual_weights >= 132)

        # Jockey/Trainer Combo Partnership Boost (2.0% strictly for Z PURTON pairs, ZERO on wide topweight at HV):
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
            ('A ATZENI', 'P C NG'), ('Z PURTON', 'D A HAYES'), ('H BOWMAN', 'M NEWNHAM'),
            ('Z PURTON', 'A S CRUZ'), ('Z PURTON', 'W Y SO'), ('Z PURTON', 'F C LOR'),
            ('H BOWMAN', 'J SIZE'), ('K TEETAN', 'W K MO'), ('A ATZENI', 'J SIZE')
        }
        
        is_elite_jt = (
            (df_runners['win_rate_jt'] >= 0.18) | 
            df_runners.apply(lambda r: (str(r.get('jockey', '')).strip().upper(), str(r.get('trainer', '')).strip().upper()) in MODERN_ELITE, axis=1)
        )
        is_purton_jt = is_elite_jt & (df_runners['jockey'].astype(str).str.strip().str.upper() == 'Z PURTON')
        jockey_trainer_boost = np.where(is_purton_jt & (~is_hv_wide_heavy), 0.02, 0.0)

        # Standalone Elite Jockey Win Conversion Boost (2.0% strictly for Z PURTON on in-form runners, ZERO on wide topweight at HV)
        is_purton_jockey = df_runners['jockey'].astype(str).str.strip().str.upper() == 'Z PURTON'
        elite_jockey_boost = np.where(is_purton_jockey & (recent_pos <= 4.0) & (vet_issue == 0) & (~is_hv_wide_heavy), 0.02, 0.0)
        
        # Happy Valley C-Course Draw Bias Adjustments
        hv_c_course_boost = 0.0
        hv_c_course_penalty = 0.0
        if is_hv and "ALL WEATHER" not in race_track_type and "AWT" not in race_track_type:
            # 1. hv_c_course_penalty:
            # 1000m / 1200m: gates 9-12 -4.0%. If weight >= 132: extra -2.0% (total -6.0%).
            # 1650m / 1800m / 2200m: gates 9-12 -2.0%. If weight >= 132: extra -1.0% (total -3.0%).
            # If avg_first_pos <= 3.5: halve the weight extra only (do not zero draw penalty).
            is_wide_gate = (draws >= 9)
            is_sprint = (distance <= 1200)
            base_draw_pen = np.where(is_wide_gate, np.where(is_sprint, -0.04, -0.02), 0.0)
            
            is_heavy = (actual_weights >= 132)
            base_wt_extra = np.where(is_wide_gate & is_heavy, np.where(is_sprint, -0.02, -0.01), 0.0)
            is_on_pace_crosser = (df_runners['avg_first_pos'] <= 3.5) | (pd.to_numeric(df_runners.get('recent_avg_pos', 7.0), errors='coerce').fillna(7.0) <= 3.5)
            eff_wt_extra = np.where(is_on_pace_crosser, base_wt_extra * 0.5, base_wt_extra)
            
            hv_c_course_penalty = base_draw_pen + eff_wt_extra
            hv_c_course_penalty = np.clip(hv_c_course_penalty, -0.06, 0.0)
            
            # 2. hv_c_course_boost:
            # Gates 1-4 & avg_first_pos <= 3.5: +3.0%.
            # On C or C+3, if also weight <= 124 lb: set to +4.0% (replaces +3.0%, does not stack).
            # Geometry boost cap +5.0%.
            is_inside_speed = (df_runners['avg_first_pos'] <= 3.5) & (draws <= 4)
            is_c_rail = ('C' in str(race.get('course', '')).upper()) or ('C' in str(meeting.get('course', '')).upper()) or True
            is_light_c = is_inside_speed & is_c_rail & (actual_weights <= 124)
            hv_c_course_boost = np.where(is_light_c, 0.04, np.where(is_inside_speed, 0.03, 0.0))
            hv_c_course_boost = np.clip(hv_c_course_boost, 0.0, 0.05)
            
        # Caspar Fownes Happy Valley Specialist Boost (+0.03 on home track)
        # ZERO on wide topweight (Gates 9-12 & >= 132 lbs), and ZERO if jockey_trainer_boost already fired
        fownes_hv_boost = 0.0
        if is_hv:
            is_fownes = df_runners['trainer'].astype(str).str.strip().str.upper() == 'C FOWNES'
            fownes_hv_boost = np.where(is_fownes & (~is_hv_wide_heavy) & (jockey_trainer_boost == 0), 0.03, 0.0)

        # Sha Tin Straight 1000m Outside Rail Draw Bias (Races 2 & 8)
        is_st_straight_1000 = is_st and (distance == 1000) and ("ALL WEATHER" not in race_track_type and "AWT" not in race_track_type)
        st_1000_draw_boost = np.where(is_st_straight_1000 & (draws >= 10), 0.027, 0.0)
        st_1000_draw_penalty = np.where(is_st_straight_1000 & (draws <= 4), -0.025, 0.0)

        # Sha Tin 1200m-1600m Bend Draw Bias (Inside Rail Advantage Gates 1-4 vs Wide Trap Gates 11-14)
        is_st_bend = is_st and (distance >= 1200) and (distance <= 1600) and ("ALL WEATHER" not in race_track_type and "AWT" not in race_track_type)
        st_inside_draw_boost = np.where(is_st_bend & (draws <= 4), 0.02, 0.0)
        st_wide_draw_penalty = np.where(is_st_bend & (draws >= 11) & (df_runners['avg_first_pos'] > 3.5), -0.025, 0.0)

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
                
                # 1. Raw speed trial (speed diff >= 0.5s faster than standard)
                if t_speed >= 0.5:
                    t_boost += 0.02
                    
                # 2. High quality trial vs top competition
                if t_data.get('high_quality_trial', False):
                    t_boost += 0.02
                    
                # 3. Poor trial (bottom 10% and slow)
                if t_pos >= 0.90 and t_speed <= -1.0:
                    t_penalty -= 0.03
                    
            trial_boost.append(t_boost)
            trial_penalty.append(t_penalty)
            
        trial_boost = np.array(trial_boost)
        trial_penalty = np.array(trial_penalty)

        # Weight-Spread Agility Escalator: When weight gap >= 14 lbs, boost in-form lightweights (<= 122 lbs)
        weight_spread = actual_weights.max() - actual_weights.min() if len(actual_weights) > 0 else 0
        is_in_form_lightweight = (actual_weights <= 122) & (recent_pos <= 5.0) & (vet_issue == 0) & (weight_spread >= 14)
        lightweight_agility_boost = np.where(is_in_form_lightweight, 0.025, 0.0)

        # Sha Tin Long Straight Closer Boost (Turf races >= 1200m at Sha Tin only)
        is_st_turf = is_st and ("ALL WEATHER" not in race_track_type and "AWT" not in race_track_type)
        st_closer_boost = np.where(is_st_turf & (df_runners['avg_first_pos'] > 5.0) & (df_runners['best_last_sec'] <= 22.8) & (distance >= 1200), 0.01, 0.0)

        # Rating Dominance in Open/Group or Top Class races (Rating >= 15 pts above field median) (Calibrated to 5% boost)
        median_rtg = pd.to_numeric(df_runners['horse_rating'], errors='coerce').fillna(40).median()
        rating_dom_boost = np.where((pd.to_numeric(df_runners['horse_rating'], errors='coerce').fillna(40) - median_rtg >= 15) & (recent_pos <= 4.0) & (vet_issue == 0), 0.05, 0.0)

        # Non-First Start for New Trainer with Good Rating (1.5% Boost)
        good_rating_thresh = 38 if class_int == 5 else 50
        is_good_rating = (df_runners.get('rtg', 40) >= good_rating_thresh) | (pd.to_numeric(df_runners.get('horse_rating', 40), errors='coerce').fillna(40) >= good_rating_thresh)
        is_settled_stable_horse = is_good_rating & (recent_pos <= 6.0) & (vet_issue == 0) & (~is_debutant)
        trainer_transfer_2nd_up_boost = np.where(is_settled_stable_horse, 0.015, 0.0)

        # Fresh Horses Distance Fitness Sweet Spot (within 250m of optimal distance with form) (1.5% Boost)
        is_fit_fresh = (recent_pos <= 5.0) & (vet_issue == 0) & (
            (df_runners.get('distance_win_rate', 0) > 0) | 
            (distance >= 1400) |
            (pd.to_numeric(df_runners.get('days_since_last_run', 0), errors='coerce').fillna(0) >= 28)
        )
        fresh_distance_fitness_boost = np.where(is_fit_fresh, 0.015, 0.0)

        # Recent Throat Surgery Recovery Boost (+3.5% Boost with verified strong trial)
        has_throat_surgery = df_runners['last_comment'].str.contains('tieback|tie-back|throat|epiglottic|wind op', case=False, na=False)
        throat_surgery_boost = np.where(has_throat_surgery & has_strong_trial, 0.035, 0.0)

        # Optimal Body Weight Condition Zone (within 15 lbs of historical peak / winning weight) (+1.0% Boost)
        declared_weights = pd.to_numeric(df_runners.get('declared_weight', 1100), errors='coerce').fillna(1100)
        opt_body_weights = pd.to_numeric(df_runners.get('latest_body_weight', np.nan), errors='coerce')
        is_optimal_weight_zone = (opt_body_weights.notna()) & (opt_body_weights > 800) & (np.abs(declared_weights - opt_body_weights) <= 15)
        optimal_weight_boost = np.where(is_optimal_weight_zone, 0.01, 0.0)

        # Disguised Form & Weight-Carrying Resilience Cushion (Sha Tin only, 0.0% at Happy Valley)
        is_resilient_weight_carrier = (actual_weights >= 130) & (draws >= 8) & (recent_pos <= 6.0) & (vet_issue == 0) & (
            (df_runners.get('avg_first_pos', 6.0) >= 7.0) | (df_runners.get('recent_win_rate', 0) > 0) | (df_runners.get('gear_win_rate', 0) > 0.10)
        )
        weight_resilience_boost = np.where(is_st & is_resilient_weight_carrier, 0.025, 0.0)

        # Surface Switch & Trial Delta Boost (+2.0% Boost for true 1st-time switchers, 0 if poor trial or if trial_boost already fired)
        awt_starts = pd.to_numeric(df_runners['AWT_starts'], errors='coerce').fillna(0) if 'AWT_starts' in df_runners.columns else 0
        turf_starts = pd.to_numeric(df_runners['Turf_starts'], errors='coerce').fillna(0) if 'Turf_starts' in df_runners.columns else 0
        is_first_time_surface = (
            (is_awt_race & (awt_starts == 0)) | 
            ((not is_awt_race) & (turf_starts == 0))
        )
        is_poor_trial = np.array([
            (clean_name in trial_features and (trial_features[clean_name].get('best_trial_pos_ratio', 0.5) >= 0.90 or trial_features[clean_name].get('best_trial_speed_diff', 0.0) <= -1.0))
            for clean_name in df_runners['clean_name'].astype(str).str.upper().str.strip()
        ])
        surface_switch_trial_boost = np.where(is_first_time_surface & (~is_poor_trial) & (trial_boost == 0.0), 0.02, 0.0)

        # Late-Closer Win Conversion Boost: Closers who possess elite closing burst (<= 22.4s) in races >= 1200m
        is_elite_finisher = (df_runners['avg_first_pos'] > 5.0) & (df_runners['best_last_sec'] <= 22.4) & (distance >= 1200)
        finisher_win_conversion_boost = np.where(is_elite_finisher, 0.025, 0.0)

        # Early-Season 2nd-Up Peak Fitness Sweet Spot (+2.0% Boost for horses with 1 run 14-35 days ago)
        days_since = pd.to_numeric(df_runners.get('days_since_last_run', 0), errors='coerce').fillna(0)
        is_second_up_fitness = (days_since >= 14) & (days_since <= 35) & (recent_pos <= 6.0) & (vet_issue == 0) & (~is_debutant)
        second_up_fitness_boost = np.where(is_second_up_fitness, 0.02, 0.0)

        # Cumulative Closer Boost Ceiling: Cap all stacked closer multipliers at +2.0% max at Happy Valley, +3.5% at Sha Tin
        raw_closer_boost = closer_pace_boost + late_closer_boost + st_closer_boost + finisher_win_conversion_boost
        closer_cap = 0.02 if is_hv else 0.035
        total_closer_boost = np.minimum(raw_closer_boost, closer_cap)

        # Stacked Geometry Penalty Cap: max -10.0%
        stacked_geom_pen = np.clip(hv_c_course_penalty + st_1000_draw_penalty + st_wide_draw_penalty, -0.10, 0.0)

        multiplier = 1.0 + standout_boost + rating_dom_boost + consensus_boost + false_fav_penalty + debutant_penalty + first_time_gear_boost + on_speed_wet_boost + yielding_form_boost + polytrack_awt_boost + total_closer_boost + frontrunner_pace_penalty + closer_pace_penalty + lone_speed_boost + elite_jockey_boost + jockey_trainer_boost + hv_c_course_boost + stacked_geom_pen + st_1000_draw_boost + st_inside_draw_boost + fownes_hv_boost + trial_boost + trial_penalty + trainer_transfer_2nd_up_boost + second_up_fitness_boost + fresh_distance_fitness_boost + throat_surgery_boost + lightweight_agility_boost + optimal_weight_boost + weight_resilience_boost + surface_switch_trial_boost

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
        
        df_runners['gs_rank'] = df_runners['gs_score'].rank(ascending=False, method='min').astype(int)

        p_min = df_runners['model_prob'].min()
        p_max = df_runners['model_prob'].max()
        if p_max > p_min:
            df_runners['confidence'] = (15.0 + ((df_runners['model_prob'] - p_min) / (p_max - p_min)) * 70).round(0).astype(int)
        else:
            df_runners['confidence'] = 50

        # Class 5 Volatility Guard: Cap confidence to maximum 68% in volatile Class 5 races
        if class_int == 5:
            df_runners['confidence'] = np.clip(df_runners['confidence'], 15, 68)

        # EV calculation and strict Fractional Kelly Criterion (1/4 Kelly for safety)
        # Price Test: live market odds check (model_prob * win_odds > 1.0)
        b = df_runners['win_odds'] - 1
        p = df_runners['model_prob']
        q = 1.0 - p
        has_live_price = (df_runners['win_odds'] > 0) & (df_runners['win_odds'] < 20.0)
        passes_price = has_live_price & (df_runners['model_prob'] * df_runners['win_odds'] > 1.0)
        f = np.where((b > 0) & passes_price, (b * p - q) / b, 0)
        df_runners['kelly_stake'] = np.clip(f * 0.25, 0, 1)
        if class_int == 5:
            df_runners['kelly_stake'] = df_runners['kelly_stake'] * 0.5
            
        # MANDATES & 5-HORSE SELECTION CARD ARCHITECTURE:
        # Sort runners strictly by gs_score descending
        df_sorted_gs = df_runners.sort_values(by='gs_score', ascending=False).reset_index(drop=True)
        
        p1 = df_sorted_gs.iloc[0]
        p2 = df_sorted_gs.iloc[1] if len(df_sorted_gs) > 1 else None
        p3 = df_sorted_gs.iloc[2] if len(df_sorted_gs) > 2 else None
        p4 = df_sorted_gs.iloc[3] if len(df_sorted_gs) > 3 else None
        
        # Pick 5 is highest EV survivor (model_prob - implied_prob) not wide+heavy vetoed
        top4_nos = [p1['no']]
        if p2 is not None: top4_nos.append(p2['no'])
        if p3 is not None: top4_nos.append(p3['no'])
        if p4 is not None: top4_nos.append(p4['no'])
        
        rem = df_runners[~df_runners['no'].isin(top4_nos)].copy()
        if is_hv:
            rem_eligible = rem[~((rem['draw'] >= 9) & (pd.to_numeric(rem.get('actual_weight', 125), errors='coerce').fillna(125) >= 132))]
            if rem_eligible.empty:
                rem_eligible = rem
        else:
            rem_eligible = rem
            
        if not rem_eligible.empty:
            p5 = rem_eligible.sort_values(by='value_diff', ascending=False).iloc[0]
        else:
            p5 = df_sorted_gs.iloc[4] if len(df_sorted_gs) > 4 else df_sorted_gs.iloc[-1]
            
        # Price Test & Split Rule on Sprints (1000m / 1200m) for Pick 1:
        p1_odds = float(p1.get('win_odds', 20.0))
        p1_prob = float(p1.get('model_prob', 0.0))
        p1_draw = int(pd.to_numeric(p1.get('draw', 6), errors='coerce'))
        p1_wt = float(pd.to_numeric(p1.get('actual_weight', 125), errors='coerce'))
        p1_first_pos = float(pd.to_numeric(p1.get('avg_first_pos', 6.0), errors='coerce'))
        p1_live = (p1_odds > 0) and (p1_odds < 20.0)
        p1_passes_val = p1_live and (p1_prob * p1_odds > 1.0)
        
        # Check sprint wide+heavy split rule:
        is_sprint = (distance <= 1200)
        is_p1_wide_heavy = is_hv and is_sprint and (p1_draw >= 9) and (p1_wt >= 132)
        p1_recent_pos = float(pd.to_numeric(p1.get('recent_avg_pos', 7.0), errors='coerce'))
        p1_is_crosser = (p1_first_pos <= 3.5) or (p1_recent_pos <= 3.5)
        
        shifted_win_runner = None
        
        if is_p1_wide_heavy and (not p1_is_crosser):
            # Condition 1: Wide topweight, NOT an on-pace crosser (e.g. Aurora Lady) -> Win stake LOCKED
            p1_passes_test = False
            p1_status = "Winning-horse pick / exotic key only — no win stake. Wide topweight, not an on-pace crosser."
            df_runners.loc[df_runners['no'] == p1['no'], 'kelly_stake'] = 0.0
            
            # Shift win stake to highest positive-EV horse that survives wide+heavy
            all_eligible_survivors = df_runners[
                ~((df_runners['draw'] >= 9) & (pd.to_numeric(df_runners.get('actual_weight', 125), errors='coerce').fillna(125) >= 132)) &
                (df_runners['win_odds'] > 0) & (df_runners['win_odds'] < 20.0) &
                (df_runners['value_diff'] > 0)
            ].copy()
            if not all_eligible_survivors.empty:
                shifted_win_runner = all_eligible_survivors.sort_values(by='value_diff', ascending=False).iloc[0]
                
        elif is_p1_wide_heavy and p1_is_crosser:
            # Condition 2: Wide topweight, IS an on-pace crosser (e.g. Motor) -> Speed exception, Half-Unit Win
            if p1_passes_val:
                p1_passes_test = True
                p1_status = f"WIN STAKE ACTIVE (Half-Unit Win + Place — Crosser Draw {p1_draw}, {int(p1_wt)}lb)"
                df_runners.loc[df_runners['no'] == p1['no'], 'kelly_stake'] = df_runners.loc[df_runners['no'] == p1['no'], 'kelly_stake'] * 0.5
            else:
                p1_passes_test = False
                p1_status = "Winning-horse pick / exotic key only — no win stake"
                df_runners.loc[df_runners['no'] == p1['no'], 'kelly_stake'] = 0.0
        else:
            # Standard runner
            if p1_passes_val:
                p1_passes_test = True
                p1_status = "WIN STAKE ACTIVE (Half Unit Win + Place)"
            else:
                p1_passes_test = False
                p1_status = "Winning-horse pick / exotic key only — no win stake"
                df_runners.loc[df_runners['no'] == p1['no'], 'kelly_stake'] = 0.0

        # Assign card rank (1 to 5)
        card_picks = [p1, p2, p3, p4, p5]
        df_runners['card_rank'] = 99
        for rank_idx, runner_obj in enumerate(card_picks):
            if runner_obj is not None:
                df_runners.loc[df_runners['no'] == runner_obj['no'], 'card_rank'] = rank_idx + 1
                
        # Primary is strictly Pick 1 (Winning Horse Pick = highest gs_score)
        df_runners['is_primary'] = (df_runners['no'] == p1['no']).astype(int)
        df_runners['primary_reason'] = np.where(df_runners['no'] == p1['no'], f"Top GS Score ({p1['gs_score']:.1f}) - {p1_status}", "")
        df_runners['win_stake_active'] = np.where((df_runners['no'] == p1['no']) & p1_passes_test, 1, 0)
        
        # If win stake shifted to another runner, flag it
        if shifted_win_runner is not None:
            df_runners.loc[df_runners['no'] == shifted_win_runner['no'], 'win_stake_active'] = 1
            df_runners.loc[df_runners['no'] == shifted_win_runner['no'], 'primary_reason'] = f"Shifted Win Stake (EV +{shifted_win_runner['value_diff']:.3f})"

        print(f"\n--- RACE {race.get('race_no')} : {class_str} ---")
        print(f"🏆 PICK 1 (WINNING HORSE PICK): #{p1['no']} {p1['name']} (Odds: {p1['win_odds']:.1f}) - GS Score: {p1['gs_score']:.1f} - Conf: {p1['confidence']}% - Status: [{p1_status}]")
        if shifted_win_runner is not None:
            print(f"⚡ SHIFTED WIN STAKE: #{shifted_win_runner['no']} {shifted_win_runner['name']} (Odds: {shifted_win_runner['win_odds']:.1f}) - EV: +{shifted_win_runner['value_diff']:.3f}")
        if p2 is not None:
            print(f"🎯 PICK 2 (EXACTA/QUINELLA): #{p2['no']} {p2['name']} (Odds: {p2['win_odds']:.1f}) - GS Score: {p2['gs_score']:.1f}")
        if p3 is not None:
            print(f"💠 PICK 3 (TRIO PODIUM): #{p3['no']} {p3['name']} (Odds: {p3['win_odds']:.1f}) - GS Score: {p3['gs_score']:.1f}")
        if p4 is not None:
            print(f"📊 PICK 4 (TRIO 4TH LEG): #{p4['no']} {p4['name']} (Odds: {p4['win_odds']:.1f}) - GS Score: {p4['gs_score']:.1f}")
        if p5 is not None:
            print(f"💣 PICK 5 (DUAL-STAKE SLEEPER / HIGHEST EV): #{p5['no']} {p5['name']} (Odds: {p5['win_odds']:.1f}) - EV: {p5['value_diff']:.3f} - GS Score: {p5['gs_score']:.1f}")
            
        # Exotic Tickets:
        q_nos = [str(x['no']) for x in [p1, p2, p3] if x is not None]
        trio_nos = [str(x['no']) for x in [p1, p2, p3, p4] if x is not None]
        print(f"🎫 TICKETS: Quinella Box 1-3 ({', '.join(q_nos)}) | Trio Box 1-4 ({', '.join(trio_nos)}) | Dual-Stake: #{p1['no']} + #{p5['no']}")

        dual_staking_wagers.append({
            "race_no": race.get("race_no"),
            "p1_no": p1['no'],
            "p1_name": p1['name'],
            "p1_odds": float(p1.get('win_odds', 20.0)),
            "p1_status": p1_status,
            "p5_no": p5['no'],
            "p5_name": p5['name'],
            "p5_odds": float(p5.get('win_odds', 20.0)),
            "p5_ev": float(p5.get('value_diff', 0.0))
        })
            
        best = p1.to_dict()
        best.update({"race_no": race.get("race_no"), "class_dist": class_str, "primary_reason": p1_status})
        global_best_bets.append(best)
        
        # Save frozen predictions
        try:
            odds_tracker.save_frozen_predictions(meeting.get('date'), meeting.get('venue'), race.get('race_no'), df_runners.to_dict(orient='records'))
        except Exception as e:
            print("Failed to save frozen predictions:", e)

    global_best_bets = sorted(global_best_bets, key=lambda x: x.get('gs_score', 0), reverse=True)
    
    print("\n\n--- OVERALL GLOBAL BEST BETS ---")
    for i in range(min(3, len(global_best_bets))):
        bb = global_best_bets[i]
        print(f"Top Pick {i+1}: Race {bb['race_no']} - #{bb['no']} {bb['name']} (Odds: {bb['win_odds']:.1f}, Conf: {bb['confidence']}%, EV: {bb['value_diff']:.3f})")

    print("\n\n--- RECOMMENDED DUAL-STAKING BETS (PICK 1 + PICK 5) ---")
    for bet in dual_staking_wagers:
        print(f"Race {bet['race_no']} Bet Selection: Anchor #{bet['p1_no']} {bet['p1_name']} ({bet['p1_odds']:.1f}) | Sleeper #{bet['p5_no']} {bet['p5_name']} ({bet['p5_odds']:.1f})")

if __name__ == '__main__':
    run()

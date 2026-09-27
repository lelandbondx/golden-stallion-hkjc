import os
import sys
import json
import pandas as pd
import numpy as np

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from model import predict_probabilities, load_model
import odds_tracker

def main():
    filename = 'data/last_scraped_meeting.json'
    if not os.path.exists(filename):
        print(f"Error: {filename} does not exist.")
        return

    with open(filename, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not data or 'meetings' not in data:
        print("Invalid data format.")
        return

    meeting = data['meetings'][0]
    
    # Load running styles and comments
    running_styles = {}
    last_comments = {}
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
        
        results = pd.read_csv('data/results.csv', usecols=['date', 'raceno', 'horseno', 'horse'])
        comments = pd.read_csv('data/comments.csv', usecols=['date', 'raceno', 'horseno', 'comment'])
        df_comm = pd.merge(comments, results, on=['date', 'raceno', 'horseno'], how='inner')
        df_comm['clean_name'] = df_comm['horse'].str.extract(r'^(.*?)\(')[0].str.strip().str.upper()
        df_comm = df_comm.sort_values(by='date', ascending=False)
        last_comments = df_comm.drop_duplicates(subset=['clean_name'], keep='first').set_index('clean_name')['comment'].to_dict()
    except Exception as e:
        print("Error loading styles/comments:", e)

    # Pre-sleep predictions for comparison
    pre_sleep_picks = {
        1: 5, # RAPID PHANTOM
        2: 2, # WINNING MACHINE
        3: 1, # PACKING GLORY
        4: 3, # OLDTOWN
        5: 2, # SKY DEEP
        6: 1, # CALIFORNIA WAVES
        7: 10, # SIX PACK
        8: 7, # MIGHTY STRENGTH
        9: 11, # ROMANTIC THOR
        10: 13, # PACKING KING
        11: 3 # COOL BOY
    }

    results_report = []

    for race in meeting.get('races', []):
        race_no = int(race.get('race_no'))
        class_str = race.get("class_dist", "")
        runners = race.get('runners', [])
        if not runners:
            continue

        df_runners = pd.DataFrame(runners)
        
        # Load cached odds if win_odds is 0 or completed
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

        # Parse class
        class_int = 4
        if "Class 1" in class_str: class_int = 1
        elif "Class 2" in class_str: class_int = 2
        elif "Class 3" in class_str: class_int = 3
        elif "Class 4" in class_str: class_int = 4
        elif "Class 5" in class_str: class_int = 5
        elif "Group" in class_str or "G" in class_str: class_int = 0

        race_going = race.get('going', meeting.get('going', 'GOOD'))
        
        # Run predict_probabilities
        try:
            probs, df_runners = predict_probabilities(df_runners, venue=meeting.get('venue'), going=race_going, race_date=meeting.get('date'), race_class_int=class_int)
        except Exception as e:
            probs = np.ones(len(df_runners)) / len(df_runners)

        if 'clean_name' not in df_runners.columns:
            df_runners['clean_name'] = df_runners['name'].str.upper().str.strip()

        # Parse distance
        import re
        dist_match = re.search(r'(\d+)m', class_str, re.IGNORECASE)
        distance = dist_match.group(1) if dist_match else "0"
        distance = int(distance)

        # Map last comments and check for troubled runs
        df_runners['last_comment'] = df_runners['clean_name'].map(last_comments).fillna("").str.lower()
        trouble_keywords = ['interference', 'blocked', 'held up', 'checked', 'crowded', 'hampered', 'stumble', 'clipt', 'clip ', 'check ']
        df_runners['had_trouble'] = df_runners['last_comment'].apply(lambda c: any(kw in c for kw in trouble_keywords)).astype(int)

        df_runners['model_prob'] = probs
        df_runners['implied_raw'] = 1 / df_runners['win_odds'].replace(0, 1.0)
        sum_implied = df_runners['implied_raw'].sum()
        df_runners['implied_prob'] = df_runners['implied_raw'] / sum_implied if sum_implied > 0 else (1/len(df_runners))
        
        # Standout and penalties
        recent_pos = pd.to_numeric(df_runners.get('recent_avg_pos', 7.0), errors='coerce').fillna(7.0)
        recent_win = pd.to_numeric(df_runners.get('recent_win_rate', 0.0), errors='coerce').fillna(0.0)
        track_match = (df_runners.get('ST_vs_HV_pref', 'Neutral') == meeting.get('venue')).astype(int)
        going_match = (df_runners.get('last_form_going', 'Unknown') == race_going).astype(int)
        vet_issue = pd.to_numeric(df_runners.get('prev_run_vet_finding', 0), errors='coerce').fillna(0)
        class_drop = pd.to_numeric(df_runners.get('class_diff', 0), errors='coerce').fillna(0)
        
        is_super_standout = (recent_pos <= 3.5) & ((track_match == 1) | (going_match == 1)) & (vet_issue == 0)
        is_class_dropper_standout = (class_drop > 0) & (recent_pos <= 5.0) & (vet_issue == 0)
        
        standout_boost = np.where(is_super_standout, 0.08, 0.0)
        standout_boost += np.where(is_class_dropper_standout, 0.05, 0.0)
        
        is_debutant = (recent_pos == 7.0) & (recent_win == 0.0)
        debutant_penalty_val = np.where(is_debutant, -0.05, 0.0)
        if class_int == 5:
            debutant_penalty_val = debutant_penalty_val * 0.5
        consensus = pd.to_numeric(df_runners.get('consensus_score', 0), errors='coerce').fillna(0)
        debutant_penalty = np.where(consensus > 5.0, 0.0, debutant_penalty_val)
        
        if 'horse_gear' in df_runners.columns:
            has_first_time_gear = df_runners['horse_gear'].astype(str).str.contains('B1|V1')
            first_time_gear_boost = np.where(has_first_time_gear, 0.04, 0.0)
        else:
            first_time_gear_boost = 0.0
        
        false_fav_penalty = np.where(
            (df_runners['implied_prob'] > 0.20) & 
            (recent_pos > 6.0) & 
            (class_drop <= 0) & 
            (df_runners['had_trouble'] == 0), 
            -0.15, 
            0.0
        )
        
        consensus_boost = np.where(consensus > 0, 0.01 * np.minimum(consensus, 12), 0.0)
        
        df_runners['avg_first_pos'] = df_runners['clean_name'].map(running_styles).fillna(6.0)
        speed_count = (df_runners['avg_first_pos'] <= 3.5).sum()
        
        closer_pace_boost = 0.0
        closer_pace_penalty = 0.0
        lone_speed_boost = 0.0
        
        race_track_type = str(race.get('track', 'TURF')).upper()
        is_wet_turf = (str(race_going).upper() in ["YIELDING", "GOOD TO YIELDING", "SOFT", "HEAVY"]) and ("ALL WEATHER" not in race_track_type and "AWT" not in race_track_type)
        
        on_speed_wet_boost = 0.0
        yielding_form_boost = 0.0
        
        if is_wet_turf:
            on_speed_wet_boost = np.where(df_runners['avg_first_pos'] <= 4.5, 0.04, 0.0)
            has_yielding_form = df_runners['last_form_going'].astype(str).str.upper().str.contains("YIELD|SOFT|HEAVY|WET")
            yielding_form_boost = np.where(has_yielding_form, 0.03, 0.0)
            
        if speed_count >= 4:
            on_speed_wet_boost = 0.0
            closer_pace_boost = np.where((df_runners['avg_first_pos'] > 5.5) & (recent_pos <= 5.5), 0.04, 0.0)
        elif speed_count <= 1:
            lone_speed_boost = np.where((df_runners['avg_first_pos'] <= 3.5) & (recent_pos <= 5.0), 0.04, 0.0)
            closer_pace_penalty = np.where((df_runners['avg_first_pos'] > 6.0) & (distance <= 1200) & (recent_pos > 4.0), -0.04, 0.0)
            
        multiplier = 1.0 + standout_boost + consensus_boost + false_fav_penalty + debutant_penalty + first_time_gear_boost + on_speed_wet_boost + yielding_form_boost + closer_pace_boost + closer_pace_penalty + lone_speed_boost
        multiplier = np.maximum(multiplier, 0.1)
        df_runners['model_prob'] = df_runners['model_prob'] * multiplier
        
        total_b = df_runners['model_prob'].sum()
        if total_b > 0:
            df_runners['model_prob'] = df_runners['model_prob'] / total_b
            
        df_runners['value_diff'] = df_runners['model_prob'] - df_runners['implied_prob']
        
        df_runners['baseline_odds'] = df_runners.apply(lambda row: odds_tracker.get_baseline_odds(
            meeting.get('date', 'today'), meeting.get('venue', 'HK'), race.get('race_no', 0), row['no'], row['scraped_win_odds']), axis=1)

        df_runners['shift_bonus'] = df_runners.apply(lambda row: odds_tracker.calculate_odds_shift_bonus(
            row['baseline_odds'], row['scraped_win_odds'], pd.to_numeric(row.get('recent_avg_pos', 7.0)), 
            pd.to_numeric(row.get('prev_run_vet_finding', 0))), axis=1)
            
        df_runners['gs_score'] = (df_runners['model_prob'] * 100) + df_runners['shift_bonus']
        
        p_min = df_runners['model_prob'].min()
        p_max = df_runners['model_prob'].max()
        if p_max > p_min:
            df_runners['confidence'] = (15.0 + ((df_runners['model_prob'] - p_min) / (p_max - p_min)) * 70).round(0).astype(int)
        else:
            df_runners['confidence'] = 50

        # Sort and evaluate
        race_picks = df_runners.sort_values(by='gs_score', ascending=False)
        top_pick = race_picks.iloc[0]
        
        # Check actual winner
        winner = df_runners[df_runners['final_position'].astype(str) == '1']
        winner_name = winner.iloc[0]['name'] if not winner.empty else "Unknown"
        winner_no = int(winner.iloc[0]['no']) if not winner.empty else 0
        winner_odds = float(winner.iloc[0]['win_odds']) if not winner.empty else 0.0

        # Check if our top pick won
        top_pick_won = (str(top_pick['final_position']) == '1')
        top_pick_pos = str(top_pick['final_position'])
        
        # Check if our pick was different from pre-sleep
        pre_sleep_num = pre_sleep_picks.get(race_no, 0)
        is_changed = (pre_sleep_num != int(top_pick['no']))

        # Find place positions (top 3)
        actual_runners = {int(r.get('no')): r for r in runners}
        
        results_report.append({
            "race_no": race_no,
            "class_dist": class_str,
            "pick_no": int(top_pick['no']),
            "pick_name": top_pick['name'],
            "pick_odds": float(top_pick['win_odds']),
            "pick_conf": int(top_pick['confidence']),
            "pick_ev": float(top_pick['value_diff']),
            "pre_sleep_no": pre_sleep_num,
            "is_changed": is_changed,
            "actual_pos": top_pick_pos,
            "winner_no": winner_no,
            "winner_name": winner_name,
            "winner_odds": winner_odds,
            "is_win": top_pick_won,
            "all_picks": race_picks.head(3)[['no', 'name', 'win_odds', 'final_position', 'confidence', 'value_diff']].to_dict('records'),
            "runners": runners
        })

    # Print markdown report
    print("# GOLDEN STALLION AI - SHA TIN PERFORMANCE REPORT (JUNE 21, 2026)")
    print("## 1st Selection Results vs. Pre-Sleep Predictions")
    print("| Race | Class/Dist | Pre-Sleep Pick | Final Live Pick | Odds | Conf | Live Pos | Winner | Odds | Status |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    
    wins = 0
    total = 0
    total_staked = 0.0
    total_returned = 0.0
    
    for r in results_report:
        status_str = "❌ LOSE"
        if r['is_win']:
            status_str = "🏆 WIN"
            wins += 1
            total_returned += r['winner_odds']
        total += 1
        total_staked += 1.0
        
        changed_flag = "⚠️" if r['is_changed'] else ""
        pre_sleep_name = pre_sleep_picks.get(r['race_no'], 0) # Fallback key lookup
        # Find name of pre-sleep horse
        pre_name = "Unknown"
        for run in r['runners']:
            if int(run.get('no')) == pre_sleep_name:
                pre_name = run.get('name')
                break
        
        pre_sleep_str = f"#{pre_sleep_name} {pre_name}"
        final_pick_str = f"#{r['pick_no']} {r['pick_name']} {changed_flag}"
        winner_str = f"#{r['winner_no']} {r['winner_name']}"
        
        print(f"| R{r['race_no']} | {r['class_dist']} | {pre_sleep_str} | {final_pick_str} | {r['pick_odds']:.1f} | {r['pick_conf']}% | {r['actual_pos']} | {winner_str} | {r['winner_odds']:.1f} | {status_str} |")
        
    win_rate = (wins / total) * 100 if total > 0 else 0
    roi = ((total_returned - total_staked) / total_staked) * 100 if total_staked > 0 else 0
    print(f"\n**Win Rate:** {win_rate:.1f}% ({wins}/{total}) | **Flat Betting ROI:** {roi:.1f}% (Staked: {total_staked} units, Returned: {total_returned} units)")
    
    print("\n## Selections that Changed During the Night (Dynamic Defrost)")
    changed_count = 0
    for r in results_report:
        if r['is_changed']:
            changed_count += 1
            print(f"- **Race {r['race_no']}**: Pre-sleep pick was #{r['pre_sleep_no']} but shifted to #{r['pick_no']} {r['pick_name']} (Finished: {r['actual_pos']}). Winner: #{r['winner_no']} {r['winner_name']} ({r['winner_odds']:.1f}).")
    if changed_count == 0:
        print("No picks changed during the night. The dynamic defrost safety valve did not trigger scratches or substitutions on our selections.")

if __name__ == '__main__':
    main()

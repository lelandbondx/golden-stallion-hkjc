import os
import json

def get_baseline_odds(date_str, venue, race_no, horse_no, current_odds):
    """
    Loads baseline odds from file. If not found, saves current odds as baseline.
    Returns the baseline odds.
    """
    filename = f"data/baseline_odds_{date_str.replace('-', '')}.json"
    
    # Load existing baseline data
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                baseline_data = json.load(f)
        except:
            baseline_data = {}
    else:
        baseline_data = {}
        
    key = f"{venue}_R{race_no}_H{horse_no}"
    
    # If the horse is missing from baseline, or baseline odds are 0 (invalid), set it to current
    if key not in baseline_data or baseline_data[key] <= 0:
        if current_odds > 0:
            baseline_data[key] = current_odds
            # Save updated baseline safely (prevent crashes in read-only environments)
            try:
                os.makedirs(os.path.dirname(filename), exist_ok=True)
                with open(filename, 'w') as f:
                    json.dump(baseline_data, f)
            except Exception as e:
                print(f"[WARNING] Could not save baseline odds to file: {e}")
            return current_odds
        else:
            return 20.0 # Fallback
            
    return baseline_data[key]

def calculate_odds_shift_bonus(baseline_odds, current_odds, recent_pos, vet_issue):
    """
    Intelligently analyzes the shift and returns a gs_score modifier.
    """
    if baseline_odds <= 0 or current_odds <= 0:
        return 0.0
        
    shift_pct = (current_odds - baseline_odds) / baseline_odds
    
    bonus = 0.0
    
    # SMART STEAM: Odds drop by > 15%, horse has elite form (recent pos <= 4.0)
    # Dampened from 4.0 to 1.5
    if shift_pct < -0.15 and recent_pos <= 4.0:
        bonus += 1.5
        
    # RED FLAG DRIFT: Odds rise by > 30%, horse has a known vet issue
    # Dampened from -3.0 to -1.5
    if shift_pct > 0.30 and vet_issue > 0:
        bonus -= 1.5
        
    # VALUE DRIFT: Odds rise by > 25%, horse has elite form and NO vet issues
    # Dampened from 2.0 to 0.75
    if shift_pct > 0.25 and recent_pos <= 3.5 and vet_issue == 0:
        bonus += 0.75
        
    return bonus

def cache_live_odds(date_str, venue, races):
    """
    Saves the scraped win odds of all runners if they are > 0.
    """
    filename = f"data/odds_cache_{date_str.replace('-', '')}.json"
    cache = {}
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        except:
            pass
    
    updated = False
    for race in races:
        race_no = race.get('race_no')
        for runner in race.get('runners', []):
            horse_no = runner.get('no')
            win_odds = runner.get('win_odds', 0.0)
            if win_odds > 0:
                key = f"{venue}_R{race_no}_H{horse_no}"
                cache[key] = win_odds
                updated = True
                
    if updated:
        try:
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(cache, f, indent=4)
        except Exception as e:
            print(f"[WARNING] Failed to write odds cache: {e}")

def get_cached_odds(date_str, venue, race_no, horse_no, current_odds):
    """
    Returns the cached odds if current_odds is 0 or invalid, else returns current_odds.
    """
    if current_odds > 0:
        return current_odds
        
    filename = f"data/odds_cache_{date_str.replace('-', '')}.json"
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                key = f"{venue}_R{race_no}_H{horse_no}"
                if key in cache and cache[key] > 0:
                    return cache[key]
        except:
            pass
    return 20.0 # Fallback

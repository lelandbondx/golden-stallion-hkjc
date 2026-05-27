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
    if shift_pct < -0.15 and recent_pos <= 4.0:
        bonus += 4.0  # Proportionate intelligent promotion
        
    # RED FLAG DRIFT: Odds rise by > 30%, horse has a known vet issue
    if shift_pct > 0.30 and vet_issue > 0:
        bonus -= 3.0  # Proportionate demotion (insiders are abandoning)
        
    # VALUE DRIFT: Odds rise by > 25%, horse has elite form and NO vet issues
    if shift_pct > 0.25 and recent_pos <= 3.5 and vet_issue == 0:
        bonus += 2.0  # Slight bump for unexpected overlay value
        
    return bonus

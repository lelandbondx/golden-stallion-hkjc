import os
import sys
import time
import json
import subprocess
from datetime import datetime

# Add current directory to path just in case
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scraper import get_live_meeting_data

LOG_FILE = "data/track_monitor_log.txt"
STATE_FILE = "data/current_going_state.json"
PREDICTIONS_SNAPSHOT = "data/overnight_predictions_snapshot.txt"

def log_message(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_msg = f"[{timestamp}] {msg}"
    try:
        print(formatted_msg)
    except UnicodeEncodeError:
        try:
            print(formatted_msg.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding))
        except Exception:
            print(formatted_msg.encode('ascii', errors='replace').decode('ascii'))
    
    # Write to log file
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted_msg + "\n")
    except Exception as e:
        try:
            print(f"Failed to write to log file: {e}")
        except Exception:
            pass

def run_prediction_update():
    log_message("🔄 Triggering prediction update...")
    try:
        # Run run_predictions.py and capture output
        res = subprocess.run(
            [sys.executable, "run_predictions.py"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True
        )
        
        # Write stdout to snapshot file
        with open(PREDICTIONS_SNAPSHOT, "w", encoding="utf-8") as f:
            f.write(res.stdout)
            
        log_message(f"✅ Predictions successfully updated. Selections written to {PREDICTIONS_SNAPSHOT}")
    except subprocess.CalledProcessError as e:
        log_message(f"❌ Error running predictions script: {e.stderr}")
    except Exception as e:
        log_message(f"❌ Unexpected error updating predictions: {e}")

def load_previous_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log_message(f"Warning: Failed to load state file: {e}")
    return {}

def save_current_state(state):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        log_message(f"Error saving state file: {e}")

def main():
    log_message("🚀 Golden Stallion AI Track Condition Monitor Initialized")
    log_message("Monitoring Sha Tin turf and dirt track goings live from HKJC API...")
    
    # Load previously stored track state
    previous_state = load_previous_state()
    is_first_run = not bool(previous_state)
    
    while True:
        try:
            # Poll live data
            data = get_live_meeting_data()
            if data.get('status') != 'success' or not data.get('meetings'):
                log_message("⚠️ Failed to poll live meeting data from HKJC. Retrying in 120s...")
                time.sleep(120)
                continue
                
            meeting = data['meetings'][0]
            venue = meeting.get('venue', 'HK')
            date_str = meeting.get('date', 'today')
            races = meeting.get('races', [])
            
            # Construct current going state mapping
            current_state = {}
            for race in races:
                race_no = race.get('race_no')
                if race_no is not None:
                    # Prefer race-specific going, fall back to meeting going, default to GOOD
                    going_desc = race.get('going', meeting.get('going', 'GOOD')).upper().strip()
                    current_state[str(race_no)] = going_desc
            
            if not current_state:
                log_message("⚠️ Scraped state returned no races. Retrying in 120s...")
                time.sleep(120)
                continue
                
            # If first run, initialize and print current goings
            if is_first_run:
                log_message(f"📊 Initializing Track Goings for {venue} - {date_str}:")
                for race_no, going in sorted(current_state.items(), key=lambda x: int(x[0])):
                    log_message(f"   Race {race_no}: {going}")
                
                save_current_state(current_state)
                previous_state = current_state.copy()
                is_first_run = False
                
                # Run predictions on start to ensure files are fresh
                run_prediction_update()
            else:
                # Compare state
                has_changed = False
                for race_no, going in current_state.items():
                    prev_going = previous_state.get(race_no)
                    
                    if prev_going is None:
                        log_message(f"🆕 Race {race_no} registered with going: {going}")
                        has_changed = True
                    elif prev_going != going:
                        log_message(f"🚨 ALERT: Race {race_no} track condition changed from '{prev_going}' to '{going}'!")
                        has_changed = True
                        
                if has_changed:
                    save_current_state(current_state)
                    previous_state = current_state.copy()
                    
                    # Trigger prediction updates
                    run_prediction_update()
                else:
                    # Print normal heartbeat message
                    going_summary = ", ".join([f"R{r}:{g}" for r, g in sorted(current_state.items(), key=lambda x: int(x[0]))])
                    log_message(f"💓 Heartbeat: Checked {len(current_state)} races. Goings: {going_summary}. No changes.")
                    
        except Exception as e:
            log_message(f"❌ Exception in monitoring loop: {e}")
            
        # Poll every 2 minutes
        time.sleep(120)

if __name__ == "__main__":
    main()

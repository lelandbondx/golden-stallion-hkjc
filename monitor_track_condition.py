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
        
        # Immediate Git Push Protocol to sync live Streamlit app
        try:
            log_message("📡 Auto-syncing updated data to origin main...")
            subprocess.run(["git", "add", "data/"], check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Auto-sync live race day predictions and going state"], check=False, capture_output=True)
            subprocess.run(["git", "pull", "origin", "main", "-X", "ours"], check=False, capture_output=True)
            push_res = subprocess.run(["git", "push", "origin", "main"], check=False, capture_output=True, text=True)
            if push_res.returncode == 0:
                log_message("🚀 Live Streamlit app successfully synchronized with origin main.")
            else:
                log_message(f"⚠️ Git push note: {push_res.stderr.strip()}")
        except Exception as git_err:
            log_message(f"⚠️ Git auto-sync exception: {git_err}")
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
    log_message("🚀 Golden Stallion AI Live Telemetry Monitor Initialized")
    log_message("Monitoring Happy Valley & Sha Tin goings, scratches, and jockey changes live from HKJC API...")
    
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
            
            # Construct comprehensive state mapping: goings, active runners, and jockeys
            current_state = {
                "goings": {},
                "runners": {},
                "jockeys": {}
            }
            for race in races:
                race_no = race.get('race_no')
                if race_no is not None:
                    going_desc = race.get('going', meeting.get('going', 'GOOD')).upper().strip()
                    current_state["goings"][str(race_no)] = going_desc
                    
                    r_list = []
                    j_map = {}
                    for runner in race.get('runners', []):
                        r_no = runner.get('no')
                        if r_no:
                            r_list.append(int(r_no))
                            j_map[str(r_no)] = str(runner.get('jockey', '')).strip().upper()
                    current_state["runners"][str(race_no)] = sorted(r_list)
                    current_state["jockeys"][str(race_no)] = j_map
            
            if not current_state["goings"]:
                log_message("⚠️ Scraped state returned no races. Retrying in 120s...")
                time.sleep(120)
                continue
                
            # If first run, initialize and log current state
            if is_first_run:
                log_message(f"📊 Initialized Live Monitor for {venue} - {date_str}:")
                for race_no, going in sorted(current_state["goings"].items(), key=lambda x: int(x[0])):
                    r_count = len(current_state["runners"].get(race_no, []))
                    log_message(f"   Race {race_no}: Going={going} | Active Runners={r_count}")
                
                save_current_state(current_state)
                previous_state = current_state.copy()
                is_first_run = False
                
                # Run predictions on start to ensure files are fresh
                run_prediction_update()
            else:
                has_changed = False
                prev_goings = previous_state.get("goings", {}) if isinstance(previous_state, dict) and "goings" in previous_state else previous_state
                prev_runners = previous_state.get("runners", {}) if isinstance(previous_state, dict) else {}
                prev_jockeys = previous_state.get("jockeys", {}) if isinstance(previous_state, dict) else {}
                
                # 1. Check going changes
                for race_no, going in current_state["goings"].items():
                    prev_going = prev_goings.get(race_no)
                    if prev_going is None:
                        log_message(f"🆕 Race {race_no} registered with going: {going}")
                        has_changed = True
                    elif prev_going != going:
                        log_message(f"🚨 ALERT: Race {race_no} track condition changed from '{prev_going}' to '{going}'!")
                        has_changed = True
                        
                # 2. Check scratches / runner withdrawals
                for race_no, curr_r_list in current_state["runners"].items():
                    prev_r_list = prev_runners.get(race_no, [])
                    if prev_r_list and set(prev_r_list) != set(curr_r_list):
                        scratched = set(prev_r_list) - set(curr_r_list)
                        log_message(f"🚨 ALERT: Scratching detected in Race {race_no}: Horses #{scratched}")
                        has_changed = True
                        
                # 3. Check jockey changes
                for race_no, curr_j_map in current_state["jockeys"].items():
                    prev_j_map = prev_jockeys.get(race_no, {})
                    for r_no, j_name in curr_j_map.items():
                        prev_j = prev_j_map.get(r_no)
                        if prev_j and j_name and prev_j != j_name:
                            log_message(f"🚨 ALERT: Jockey change in Race {race_no} on #{r_no}: '{prev_j}' -> '{j_name}'")
                            has_changed = True
                        
                if has_changed:
                    save_current_state(current_state)
                    previous_state = current_state.copy()
                    run_prediction_update()
                else:
                    going_summary = ", ".join([f"R{r}:{g}" for r, g in sorted(current_state["goings"].items(), key=lambda x: int(x[0]))])
                    log_message(f"💓 Heartbeat: Checked {len(current_state['goings'])} races ({sum(len(v) for v in current_state['runners'].values())} runners). Goings: {going_summary}. 0 changes.")
                    
        except Exception as e:
            log_message(f"❌ Exception in monitoring loop: {e}")
            
        time.sleep(120)

if __name__ == "__main__":
    main()

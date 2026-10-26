import os
from scraper import get_live_meeting_data
from odds_tracker import get_baseline_odds
from monitoring.health import record as record_health


def initialize_baseline():
    print("=== INITIALIZING BASELINE ODDS ===")
    data = get_live_meeting_data()

    if data.get('status') != 'success' or not data.get('meetings'):
        print("[ERROR] Failed to fetch live meeting data for baseline odds initialization.")
        record_health("baseline_odds", "fail", error="Failed to fetch live meeting data")
        return

    meeting = data['meetings'][0]
    date_str = meeting.get('date')
    venue = meeting.get('venue')

    if not date_str or not venue:
        print("[ERROR] Date or Venue is missing from live meeting data.")
        record_health("baseline_odds", "fail", error="Date or Venue missing from live meeting data")
        return

    filename = f"data/baseline_odds_{date_str.replace('-', '')}.json"
    print(f"Raceday Date: {date_str}")
    print(f"Venue: {venue}")
    print(f"Target Baseline File: {filename}")

    file_exists = os.path.exists(filename)
    if file_exists:
        print(f"[INFO] Baseline file {filename} already exists. Appending any missing runners without overwriting existing ones.")
    else:
        print(f"[INFO] Creating new baseline file {filename}.")

    initialized_count = 0
    priced_count = 0

    for race in meeting.get('races', []):
        race_no = race.get('race_no')
        for runner in race.get('runners', []):
            horse_no = runner.get('no')
            current_odds = float(runner.get('win_odds', 0.0) or 0.0)
            val = get_baseline_odds(date_str, venue, race_no, horse_no, current_odds)
            initialized_count += 1
            if val and val > 0:
                priced_count += 1

    record_health(
        "baseline_odds",
        "ok",
        metrics={
            "meeting_date": date_str,
            "venue": venue,
            "runners_checked": initialized_count,
            "runners_with_live_baseline_price": priced_count,
            "file": filename,
        },
    )
    print(f"[OK] Completed initialization. Checked {initialized_count} runners ({priced_count} with active baseline price).")


if __name__ == '__main__':
    initialize_baseline()

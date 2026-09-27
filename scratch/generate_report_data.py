import json

def get_runner_info(runners, no):
    for r in runners:
        if r.get('no') == no:
            return r
    return {}

with open('data/last_scraped_meeting.json', 'r') as f:
    data = json.load(f)

meeting = data['meetings'][0]
races = meeting['races']

print("--- OVERNIGHT / PRE-SLEEP SELECTIONS DETAILS ---")
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

for race_no, horse_no in pre_sleep_picks.items():
    race = races[race_no - 1]
    runner = get_runner_info(race['runners'], horse_no)
    print(f"Race {race_no}: #{horse_no} {runner.get('name')} - Jockey: {runner.get('jockey')} - Trainer: {runner.get('trainer')} - Final Position: {runner.get('final_position')} - Odds: {runner.get('win_odds')}")

print("\n--- FINAL LIVE SELECTIONS DETAILS ---")
final_live_picks = {
    1: 4, # PRIME WINISTER
    2: 8, # SUPERB GUY
    3: 5, # ACE EAGLE
    4: 7, # HOT AIR BALLON
    5: 2, # SKY DEEP
    6: 1, # CALIFORNIA WAVES
    7: 10, # SIX PACK
    8: 7, # MIGHTY STRENGTH
    9: 11, # ROMANTIC THOR
    10: 13, # PACKING KING
    11: 3 # COOL BOY
}

for race_no, horse_no in final_live_picks.items():
    race = races[race_no - 1]
    runner = get_runner_info(race['runners'], horse_no)
    print(f"Race {race_no}: #{horse_no} {runner.get('name')} - Jockey: {runner.get('jockey')} - Trainer: {runner.get('trainer')} - Final Position: {runner.get('final_position')} - Odds: {runner.get('win_odds')}")

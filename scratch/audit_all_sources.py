import os, sys, json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import numpy as np

# Load meeting data
from scraper import get_live_meeting_data
from model import predict_probabilities, load_model

data = get_live_meeting_data()
if not data.get('meetings'):
    print("No live meeting data found.")
    sys.exit(0)

meeting = data['meetings'][0]
print(f"Auditing Meeting: {meeting.get('venue')} - {meeting.get('date')} ({len(meeting.get('races', []))} races)")

# Check precomputed features
precomputed_path = 'data/precomputed_features.json'
with open(precomputed_path, 'r', encoding='utf-8') as f:
    precomputed = json.load(f)
print(f"Precomputed features loaded: {list(precomputed.keys())}")
print(f"Running styles: {len(precomputed.get('running_styles', {}))}")
print(f"Winning gears: {len(precomputed.get('winning_gears', {}))}")
print(f"Sectional bursts: {len(precomputed.get('sectional_bursts', {}))}")
print(f"Last comments: {len(precomputed.get('last_comments', {}))}")

# Check trials
with open('data/engineered_trial_features.json', 'r', encoding='utf-8') as f:
    trials = json.load(f)
print(f"Engineered trials loaded: {len(trials)} horses")

# Check training telemetry
with open('data/active_horses_training.json', 'r', encoding='utf-8') as f:
    training = json.load(f)
print(f"Active horses training telemetry: {len(training)} horses")

# Check live vet records
with open('data/live_vet_records.json', 'r', encoding='utf-8') as f:
    vet = json.load(f)
print(f"Live vet records: {len(vet)} records")

# Check horse profiles
with open('data/horse_profiles.json', 'r', encoding='utf-8') as f:
    profiles = json.load(f)
print(f"Horse profiles loaded: {len(profiles)} horses")

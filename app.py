import streamlit as st
import pandas as pd
import numpy as np
import os
import re
import json
from streamlit_autorefresh import st_autorefresh
import threading
import time
import requests
import odds_tracker
import textwrap

def clean_html(html_str):
    return "\n".join(line.lstrip() for line in html_str.split("\n"))


def keep_alive():
    while True:
        try:
            requests.get("https://hkjcbotlee.streamlit.app/", timeout=10)
        except:
            pass
        try:
            requests.get("https://huggingface.co/spaces/lelandbondx/golden-stallion", timeout=10)
        except:
            pass
        try:
            requests.get("https://huggingface.co/spaces/lelandbondx/golden-stallion-hkjc", timeout=10)
        except:
            pass
        time.sleep(600)

if not any(t.name == "KeepAlive" for t in threading.enumerate()):
    threading.Thread(target=keep_alive, name="KeepAlive", daemon=True).start()

try:
    from scraper import get_live_meeting_data, get_hkjc_news, get_live_tips_index
except ImportError:
    def get_live_meeting_data():
        return {"status": "error"}
    def get_hkjc_news():
        return []
    def get_live_tips_index():
        return {}

try:
    from model import predict_probabilities, load_model
except ImportError:
    def predict_probabilities(df, venue=None, going=None, race_date=None, race_class_int=None):
        return np.ones(len(df)) / len(df), df
    def load_model():
        pass


st.set_page_config(page_title="Golden Stallion AI", layout="wide", page_icon="🐎")

# --- PAUSE SWITCH ---
APP_PAUSED = False
if APP_PAUSED:
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@600;800&family=Inter:wght@400;500;600;700&display=swap');
        .hero-title {
            font-family: 'Montserrat', sans-serif;
            font-size: 3.5rem;
            font-weight: 800;
            background: linear-gradient(180deg, #FFFFFF 0%, #ffe066 50%, #FFD700 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-align: center;
            letter-spacing: 2px;
            margin-bottom: 0px;
        }
        .stApp { 
            background: radial-gradient(circle at top, #1a0f12 0%, #080405 100%);
            color: #f8fafc; 
        }
    </style>
    """, unsafe_allow_html=True)
    st.image("golden_stallion_banner.png", use_container_width=True)
    st.markdown('<div class="hero-title">GOLDEN STALLION AI</div>', unsafe_allow_html=True)
    st.error("⚠️ The AI Engine is currently paused for mid-meeting recalibration and results reporting. Please check back shortly.")
    st.stop()
# --------------------

# Run the autorefresh about every 20 seconds
st_autorefresh(interval=20000, limit=1000, key="hkjc_live_refresh")

# Removed NPM initialization since we are now natively using Python

# CSS Injection for Chinese-Friendly Ruby/Gold 3D UI
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@600;800&family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    /* Institutional Dark Ruby Background */
    .stApp { 
        background: radial-gradient(circle at top, #1a0f12 0%, #080405 100%);
        color: #f8fafc; 
    }
    
    /* Ultra-readable Headers */
    .hero-title {
        font-family: 'Montserrat', sans-serif;
        font-size: 3.5rem;
        font-weight: 800;
        background: linear-gradient(180deg, #FFFFFF 0%, #ffe066 50%, #FFD700 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        letter-spacing: 2px;
        margin-bottom: 0px;
        filter: drop-shadow(0px 4px 6px rgba(0,0,0,0.8));
    }
    .hero-subtitle {
        font-family: 'Montserrat', sans-serif;
        font-size: 1.1rem;
        color: #ef4444;
        text-align: center;
        letter-spacing: 6px;
        margin-bottom: 35px;
        font-weight: 700;
        text-shadow: 0 2px 4px rgba(0,0,0,0.5);
    }
    
    /* 3D Glassy Ruby/Dark Slate Panels */
    .tech-panel { 
        position: relative;
        background: linear-gradient(145deg, rgba(31, 15, 18, 0.8), rgba(15, 8, 10, 0.95));
        backdrop-filter: blur(10px);
        padding: 22px; 
        border-radius: 12px;
        border: 1px solid rgba(255, 215, 0, 0.15); 
        margin: 12px 0; 
        box-shadow: 0 15px 30px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,215,0,0.1);
        transition: all 0.2s cubic-bezier(0.25, 0.8, 0.25, 1);
        overflow: hidden;
    }
    .tech-panel:hover {
        transform: translateY(-3px);
        box-shadow: 0 20px 40px rgba(0,0,0,0.7), inset 0 1px 0 rgba(255,215,0,0.25);
    }

    /* Edge Lighting Effects (Ruby and Gold) */
    .border-accent-gold { border-left: 5px solid #FFD700; box-shadow: -4px 0 15px rgba(255, 215, 0, 0.15), 0 15px 30px rgba(0,0,0,0.5); }
    .border-accent-red { border-left: 5px solid #ef4444; box-shadow: -4px 0 15px rgba(239, 68, 68, 0.15), 0 15px 30px rgba(0,0,0,0.5); }

    .data-label {
        font-family: 'Inter', sans-serif;
        font-size: 0.80rem;
        color: #9ca3af;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        margin-bottom: 5px;
        font-weight: 700;
    }
    .data-value {
        font-family: 'Inter', sans-serif;
        font-size: 1.25rem;
        color: #ffffff;
        font-weight: 600;
    }
    
    /* 3D Expanders */
    .streamlit-expanderHeader { 
        font-family: 'Montserrat', sans-serif;
        color: #ffffff !important; 
        font-weight: 600;
        border: 1px solid rgba(255,215,0,0.1);
        border-radius: 8px;
        background: linear-gradient(180deg, #1f0f12, #080405);
        box-shadow: 0 4px 6px rgba(0,0,0,0.4);
    }
    
    /* 3D Progress Bar in Gold */
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #facc15, #fef08a);
        box-shadow: 0 0 10px rgba(255,215,0,0.5);
        border-radius: 10px;
    }
    
    /* Elegant Tabs */
    .stTabs [data-baseweb="tab-list"] { gap: 10px; border-bottom: 1px solid rgba(239, 68, 68, 0.3); }
    .stTabs [data-baseweb="tab"] {
        font-family: 'Montserrat', sans-serif;
        font-weight: 700;
        letter-spacing: 1px;
        font-size: 0.95rem;
        color: #9ca3af;
    }
    .stTabs [aria-selected="true"] { 
        color: #FFD700 !important; 
        border-bottom-color: #FFD700 !important; 
    }
</style>
""", unsafe_allow_html=True)

# Central Banner
col_b1, col_b2, col_b3 = st.columns([1.2, 2, 1.2])
with col_b2:
    st.image("golden_stallion_banner.png", use_container_width=True)

st.markdown('<div class="hero-title">GOLDEN STALLION AI</div>', unsafe_allow_html=True)
st.markdown('<div class="hero-subtitle">金金驹AI__香港赛马会预测</div>', unsafe_allow_html=True)

@st.cache_data(ttl=20)
def fetch_data():
    return get_live_meeting_data()

@st.cache_data(ttl=900)
def fetch_news():
    return get_hkjc_news()

@st.cache_data(ttl=3600)
def fetch_historical_comments():
    try:
        results = pd.read_csv('data/results.csv', usecols=['date', 'raceno', 'horseno', 'horse'])
        comments = pd.read_csv('data/comments.csv', usecols=['date', 'raceno', 'horseno', 'comment'])
        df = pd.merge(comments, results, on=['date', 'raceno', 'horseno'], how='inner')
        df['clean_name'] = df['horse'].str.extract(r'^(.*?)\(')[0].str.strip().str.upper()
        df = df.sort_values(by='date', ascending=False)
        return df
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=86400)
def fetch_standard_times():
    try:
        return pd.read_csv('data/course_standard_times.csv')
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=86400)
def fetch_horse_stats():
    try:
        df = pd.read_csv('data/latest_horse_stats.csv')
        df['clean_name'] = df['clean_name'].str.upper().str.strip()
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=900)
def fetch_tips():
    return get_live_tips_index()

@st.cache_data(ttl=86400)
def fetch_running_styles():
    try:
        df = pd.read_csv('data/results.csv', usecols=['horse', 'runningpos'])
        df['clean_name'] = df['horse'].str.extract(r'^(.*?)\(')[0].str.strip().str.upper()
        
        def parse_first_pos(x):
            if not isinstance(x, str): return np.nan
            parts = x.strip().split()
            if not parts: return np.nan
            try:
                return float(parts[0])
            except:
                return np.nan
                
        df['first_pos'] = df['runningpos'].apply(parse_first_pos)
        style_series = df.groupby('clean_name')['first_pos'].mean()
        return style_series.to_dict()
    except Exception as e:
        print("Error fetching running styles:", e)
        return {}

@st.cache_data(ttl=86400)
def fetch_sectional_bursts():
    try:
        if not os.path.exists('data/runs.csv') or not os.path.exists('data/horse_info.csv'):
            return {}
        runs = pd.read_csv('data/runs.csv', usecols=['horse_id', 'time1', 'time2', 'time3', 'time4', 'time5', 'time6'])
        horse_info = pd.read_csv('data/horse_info.csv', usecols=['Unnamed: 0', 'horse'])
        horse_info['clean_name'] = horse_info['horse'].str.extract(r'^(.*?)\(')[0].str.strip().str.upper()
        horse_map = horse_info[['Unnamed: 0', 'clean_name']].rename(columns={'Unnamed: 0': 'horse_id'}).drop_duplicates()
        df = pd.merge(runs, horse_map, on='horse_id', how='inner')
        
        def parse_last_sec(row):
            for col in ['time6', 'time5', 'time4', 'time3', 'time2']:
                val = pd.to_numeric(row[col], errors='coerce')
                if not pd.isna(val) and val > 0:
                    return val
            return pd.to_numeric(row['time1'], errors='coerce')
            
        df['last_sec_val'] = df.apply(parse_last_sec, axis=1)
        df = df[df['last_sec_val'] > 10.0]
        
        best_secs = df.groupby('clean_name')['last_sec_val'].min().to_dict()
        return best_secs
    except Exception as e:
        print("Error fetching sectional bursts:", e)
        return {}

# Initialize variables
data = fetch_data()
historical_df = fetch_historical_comments()
last_comments = {}
if not historical_df.empty:
    try:
        last_comments = historical_df.drop_duplicates(subset=['clean_name'], keep='first').set_index('clean_name')['comment'].to_dict()
    except Exception as e:
        print("Error compiling last comments lookup:", e)
std_times_df = fetch_standard_times()
horse_stats_df = fetch_horse_stats()
tips_data = fetch_tips()
running_styles = fetch_running_styles()
sectional_bursts = fetch_sectional_bursts()
meetings = data.get('meetings', [])

try:
    with open('data/gemini_intel.json', 'r') as f:
        intel_data = json.load(f)
        key_runners = [runner['horse_name'].upper() for runner in intel_data.get('key_runners', [])]
except Exception:
    key_runners = []

if not meetings:
    st.error("No active or recently closed meetings found on HKJC.")
    st.stop()

# Build meeting selectbox options
meeting_options = [f"{m.get('date')} - {m.get('venue')}" for m in meetings]

default_index = 0
from datetime import datetime, timedelta
# Calculate today's date in Hong Kong Time (HKT is UTC+8)
hkt_today = (datetime.utcnow() + timedelta(hours=8)).strftime('%Y-%m-%d')

found_today = False
for i, m in enumerate(meetings):
    if m.get('date') == hkt_today:
        default_index = i
        found_today = True
        break

if not found_today:
    for i, m in enumerate(meetings):
        if str(m.get('status', 'UPCOMING')).upper() != "CLOSED":
            default_index = i
            break


selected_meeting_str = st.selectbox("📅 Select Race Meeting Date & Venue", meeting_options, index=default_index)
selected_index = meeting_options.index(selected_meeting_str)
meeting = meetings[selected_index]
races = meeting.get('races', [])

# Cache live odds for this meeting (if any are scraped/positive)
try:
    odds_tracker.cache_live_odds(meeting.get('date'), meeting.get('venue'), races)
except Exception as e:
    print("Failed to cache live odds:", e)

def check_highlight(runner, search_term):
    if not search_term:
        return ""
    jockey_str = str(runner.get('jockey', '')).upper()
    trainer_str = str(runner.get('trainer', '')).upper()
    if search_term in jockey_str or search_term in trainer_str:
        return "border: 2px solid #22c55e !important; box-shadow: 0 0 15px rgba(34, 197, 94, 0.5) !important;"
    return ""

def get_match_badge(runner, search_term):
    if not search_term:
        return ""
    jockey_str = str(runner.get('jockey', '')).upper()
    trainer_str = str(runner.get('trainer', '')).upper()
    if search_term in jockey_str or search_term in trainer_str:
        return '<span style="background:#22c55e; color:#ffffff; padding:2px 6px; border-radius:4px; font-size:0.75rem; font-weight:bold; float:right;">🔍 MATCH</span>'
    return ""

search_term = st.text_input("🔍 Highlight Jockey or Trainer (e.g., PURTON, FOWNES)", "").strip().upper()

# TABS
tab1, tab2, tab3 = st.tabs(["🔴 Live Matrix", "📊 Archive", "📰 HKJC News"])

with tab1:
    col_act1, col_act2, col_act3 = st.columns([1, 2, 1])
    with col_act2:
        if st.button("INITIALIZE LIVE SYNC", use_container_width=True):
            with st.spinner("Synchronizing live official stats..."):
                try:
                    from hkjc_profile_scraper import update_latest_stats
                    update_latest_stats()
                except Exception as e:
                    print("Failed to update stats:", e)
            st.cache_data.clear()
            st.rerun()

    if data.get('status') != 'success':
        st.warning("Live connection failed. Secure fallback models initialized.")
        
    # Meeting Status Grid
    col_st1, col_st2, col_st3, col_st4 = st.columns(4)
    with col_st1:
        st.markdown('<div class="tech-panel border-accent-red"><div class="data-label">Venue</div><div class="data-value">{}</div></div>'.format(meeting.get('venue')), unsafe_allow_html=True)
    with col_st2:
        st.markdown('<div class="tech-panel border-accent-red"><div class="data-label">Date</div><div class="data-value">{}</div></div>'.format(meeting.get('date')), unsafe_allow_html=True)
    with col_st3:
        st.markdown('<div class="tech-panel border-accent-gold"><div class="data-label" style="color:#FFD700;">Track Conditions</div><div class="data-value" style="color:#FFD700;">{}</div></div>'.format(meeting.get('going')), unsafe_allow_html=True)
    with col_st4:
        st.markdown('<div class="tech-panel border-accent-red"><div class="data-label">Weather</div><div class="data-value">{}</div></div>'.format(meeting.get('weather')), unsafe_allow_html=True)

    if not os.path.exists('model.joblib'):
        with st.spinner("Compiling structural probability models..."):
            try:
                load_model()
            except Exception:
                pass 

    global_best_bets = []
    parlay_candidates = []
    
    # Process models
    for race in races:
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
        
        # Map consensus score from tips data
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
            
        # Check if we have a frozen prediction for this race
        frozen_runners = odds_tracker.get_frozen_predictions(meeting.get('date'), meeting.get('venue'), race.get('race_no'))
        
        # Determine if we should defrost (recalculate) due to scratches or track change
        is_defrost = False
        if frozen_runners is not None:
            live_going = race.get('going', meeting.get('going', 'GOOD'))
            frozen_going = frozen_runners[0].get('current_going', 'GOOD') if len(frozen_runners) > 0 else 'GOOD'
            is_defrost = odds_tracker.should_defrost_predictions(frozen_runners, race.get('runners', []), frozen_going, live_going)
            
        if frozen_runners is not None and not is_defrost:
            df_runners = pd.DataFrame(frozen_runners)
            
            # Map latest live odds from race['runners'] and update dynamically
            if 'runners' in race and isinstance(race['runners'], list):
                live_odds_dict = {r.get('no'): r.get('win_odds', 0.0) for r in race['runners'] if r.get('no') is not None}
                
                if 'no' in df_runners.columns:
                    df_runners['scraped_win_odds'] = df_runners['no'].map(live_odds_dict).fillna(df_runners.get('win_odds', 20.0))
                    df_runners['scraped_win_odds'] = df_runners.apply(
                        lambda row: odds_tracker.get_cached_odds(
                            meeting.get('date', 'today'), meeting.get('venue', 'HK'), race.get('race_no', 0), row['no'], row['scraped_win_odds']
                        ), axis=1
                    )
                    df_runners['win_odds'] = df_runners['scraped_win_odds'].copy()
                    
                    # Recalculate implied probability and EV
                    df_runners['implied_raw'] = 1 / df_runners['win_odds'].replace(0, 1.0)
                    sum_implied = df_runners['implied_raw'].sum()
                    df_runners['implied_prob'] = df_runners['implied_raw'] / sum_implied if sum_implied > 0 else (1/len(df_runners))
                    
                    if 'model_prob' in df_runners.columns:
                        df_runners['value_diff'] = df_runners['model_prob'] - df_runners['implied_prob']
                        
                        # Recalculate Kelly stake
                        b = df_runners['win_odds'] - 1
                        p = df_runners['model_prob']
                        q = 1.0 - p
                        f = np.where(b > 0, (b * p - q) / b, 0)
                        df_runners['kelly_stake'] = np.clip(f * 0.25, 0, 1)
                        
                        # Recalculate baseline odds dynamically if the race is still early (>120 mins out)
                        df_runners['baseline_odds'] = df_runners.apply(
                            lambda row: odds_tracker.get_baseline_odds(
                                meeting.get('date', 'today'), meeting.get('venue', 'HK'), race.get('race_no', 0), row['no'], row['scraped_win_odds'], minutes_to_post
                            ), axis=1
                        )

                        # Recalculate gs_score incorporating dynamic shift_bonus
                        if 'baseline_odds' in df_runners.columns:
                            df_runners['shift_bonus'] = df_runners.apply(
                                lambda row: odds_tracker.calculate_odds_shift_bonus(
                                    row['baseline_odds'], row['scraped_win_odds'], 
                                    pd.to_numeric(row.get('recent_avg_pos', 7.0)), 
                                    pd.to_numeric(row.get('prev_run_vet_finding', 0))
                                ), axis=1
                            )
                            # Keep core score stable, just update with dynamic shift bonus if within 60 minutes of post time
                            if minutes_to_post > 60:
                                df_runners['gs_score'] = df_runners['model_prob'] * 100
                            else:
                                df_runners['gs_score'] = (df_runners['model_prob'] * 100) + df_runners['shift_bonus']
            
            if 'clean_name' not in df_runners.columns:
                df_runners['clean_name'] = df_runners['name'].str.upper().str.strip()
            race['processed_runners'] = df_runners
            
            # Add all runners to global pool for summaries
            for _, row in df_runners.iterrows():
                r_dict = row.to_dict()
                r_dict.update({"race_no": race.get("race_no")})
                global_best_bets.append(r_dict)
                
            # Parlay candidate is the 1st Pick of this race
            race_picks_gs = df_runners.sort_values(by='gs_score', ascending=False)
            if not race_picks_gs.empty:
                best_gs = race_picks_gs.iloc[0].to_dict()
                best_gs.update({"race_no": race.get("race_no")})
                parlay_candidates.append(best_gs)
            continue
            
        try:
            # Parse class_int from race
            class_str = race.get("class_dist", "")
            class_int = 4
            if "Class 1" in class_str: class_int = 1
            elif "Class 2" in class_str: class_int = 2
            elif "Class 3" in class_str: class_int = 3
            elif "Class 4" in class_str: class_int = 4
            elif "Class 5" in class_str: class_int = 5
            elif "Group" in class_str or "G" in class_str: class_int = 0
            
            # Use race-specific going
            race_going = race.get('going', meeting.get('going', 'GOOD'))
            probs, df_runners = predict_probabilities(df_runners, venue=meeting.get('venue'), going=race_going, race_date=meeting.get('date'), race_class_int=class_int)
        except Exception as e:
            print(f"Prediction Error for race {race.get('race_no')}: {e}")
            probs = np.ones(len(df_runners)) / len(df_runners)
            df_runners = df_runners
            
        if 'clean_name' not in df_runners.columns:
            df_runners['clean_name'] = df_runners['name'].str.upper().str.strip()
            
        # Parse distance
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
        
        # Targeted Standout Boost Logic (replaces blind point additions)
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
        # If consensus from trials is strong, waive it
        consensus = pd.to_numeric(df_runners.get('consensus_score', 0), errors='coerce').fillna(0)
        debutant_penalty = np.where(consensus > 5.0, 0.0, debutant_penalty_val)
        
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
            
        multiplier = 1.0 + standout_boost + consensus_boost + false_fav_penalty + debutant_penalty + first_time_gear_boost + on_speed_wet_boost + yielding_form_boost + closer_pace_boost + closer_pace_penalty + lone_speed_boost + late_closer_boost
        multiplier = np.maximum(multiplier, 0.1) # Floor at 10% of original model_prob
        
        df_runners['model_prob'] = df_runners['model_prob'] * multiplier
        
        # Normalize the blended probability
        total_b = df_runners['model_prob'].sum()
        if total_b > 0:
            df_runners['model_prob'] = df_runners['model_prob'] / total_b
            
        df_runners['implied_odds'] = df_runners['implied_raw'] # Fallback compatibility
        
        # EV calculation and strict Fractional Kelly Criterion (1/4 Kelly for safety)
        b = df_runners['win_odds'] - 1
        p = df_runners['model_prob']
        q = 1.0 - p
        f = np.where(b > 0, (b * p - q) / b, 0)
        df_runners['kelly_stake'] = np.clip(f * 0.25, 0, 1) 
        
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
        
        # Scale to a realistically solid 15-85% range. Round to nearest integer.
        p_min = df_runners['model_prob'].min()
        p_max = df_runners['model_prob'].max()
        if p_max > p_min:
            df_runners['confidence'] = (15.0 + ((df_runners['model_prob'] - p_min) / (p_max - p_min)) * 70).round(0).astype(int)
        else:
            df_runners['confidence'] = 50

        # Add historical records
        if 'clean_name' not in df_runners.columns:
            df_runners['clean_name'] = df_runners['name'].str.upper().str.strip()
            
        vet_notes = []
        steward_notes = []
        photo_hist = []
        
        for _, row in df_runners.iterrows():
            if not historical_df.empty:
                horse_hist = historical_df[historical_df['clean_name'] == row['clean_name']]
                if not horse_hist.empty:
                    last_run = horse_hist.iloc[0]
                    comment = str(last_run['comment']).strip()
                    
                    photo = "✅ Yes" if any(x in comment.lower() for x in ["photo", "nose", "short head"]) else "❌ No"
                    
                    vet = "No Findings"
                    steward = comment
                    if "(" in comment and ")" in comment:
                        matches = re.findall(r'\((.*?)\)', comment)
                        if matches:
                            last_match = matches[-1]
                            if "vet" in last_match.lower() or "finding" in last_match.lower():
                                vet = last_match
                            else:
                                vet = "No Findings"
                    
                    vet_notes.append(vet)
                    steward_notes.append(steward)
                    photo_hist.append(photo)
                else:
                    vet_notes.append("No active findings")
                    steward_notes.append("Clear Record")
                    photo_hist.append("None")
            else:
                vet_notes.append("No active findings")
                steward_notes.append("No DB connection")
                photo_hist.append("None")

                
        df_runners['vet_findings'] = vet_notes
        df_runners['steward_notes'] = steward_notes
        df_runners['photo_finish'] = photo_hist
        
        race['processed_runners'] = df_runners
        
        # Always freeze predictions once they are generated, so they don't change overnight
        try:
            odds_tracker.save_frozen_predictions(meeting.get('date'), meeting.get('venue'), race.get('race_no'), df_runners.to_dict(orient='records'))
        except Exception as e:
            print("Failed to save frozen predictions:", e)
        
        # Add all runners of this race to global pool for summaries
        for _, row in df_runners.iterrows():
            r_dict = row.to_dict()
            r_dict.update({"race_no": race.get("race_no")})
            global_best_bets.append(r_dict)
            
        # Parlay candidate is the 1st Pick of this race
        race_picks_gs = df_runners.sort_values(by='gs_score', ascending=False)
        if not race_picks_gs.empty:
            best_gs = race_picks_gs.iloc[0].to_dict()
            best_gs.update({"race_no": race.get("race_no")})
            parlay_candidates.append(best_gs)

    # Collect market steam alerts
    steam_alerts = []
    for r in races:
        if 'processed_runners' not in r: continue
        for _, row in r['processed_runners'].iterrows():
            base_odds = float(row.get('baseline_odds', 0.0))
            curr_odds = float(row.get('win_odds', 0.0))
            if base_odds > 0 and curr_odds > 0:
                shift_pct = (curr_odds - base_odds) / base_odds
                if shift_pct < -0.15: # dropped by more than 15%
                    steam_alerts.append({
                        "race_no": r.get("race_no"),
                        "no": row['no'],
                        "name": row['name'],
                        "jockey": row['jockey'],
                        "base": base_odds,
                        "curr": curr_odds,
                        "pct": shift_pct
                    })

    global_best_bets_sorted_by_gs = sorted(global_best_bets, key=lambda x: x.get('gs_score', 0), reverse=True)
    global_best_bets_sorted_by_ev = sorted(global_best_bets, key=lambda x: x.get('value_diff', 0), reverse=True)
    top_pick_today = global_best_bets_sorted_by_ev[0] if global_best_bets_sorted_by_ev else None
    
    # Sort parlay candidates strictly from the 1st Picks of each race
    parlay_sorted = sorted(parlay_candidates, key=lambda x: x.get('gs_score', 0), reverse=True)

    with st.expander("Macro Insights & Global Best Bets", expanded=True):
        if top_pick_today:
            col_bb1, col_bb2 = st.columns(2)
            with col_bb1:
                st.markdown(clean_html(f'''
                <div class="tech-panel border-accent-gold" style="background: linear-gradient(145deg, rgba(30,20,5, 0.9), rgba(15, 8, 10, 0.9)); min-height: 160px; {check_highlight(top_pick_today, search_term)}">
                    {get_match_badge(top_pick_today, search_term)}
                    <div class="data-label" style="color:#FFD700; font-size:0.90rem;">🏆 HIGHEST EXPECTED VALUE (EV) SELECTION</div>
                    <div class="data-value" style="font-size:1.8rem; font-family:'Montserrat'; font-weight:800; margin-top: 5px; color:#FFDF00; text-shadow: 0 4px 10px rgba(255,215,0,0.4);">Race {top_pick_today['race_no']} – #{top_pick_today['no']} {top_pick_today['name']}</div>
                    <div class="data-value" style="font-size:1.0rem; color:#f8fafc; margin-top: 5px;">Live Odds: <b>{top_pick_today['win_odds']:.1f}</b> &nbsp;|&nbsp; AI Confidence: <b style="color:#ef4444;">{top_pick_today['confidence']}%</b></div>
                </div>
                '''), unsafe_allow_html=True)
            with col_bb2:
                top_gs_pick = global_best_bets_sorted_by_gs[0] if global_best_bets_sorted_by_gs else None
                if top_gs_pick:
                    st.markdown(clean_html(f'''
                    <div class="tech-panel border-accent-red" style="background: linear-gradient(145deg, rgba(40,10,15, 0.9), rgba(15, 8, 10, 0.9)); min-height: 160px; {check_highlight(top_gs_pick, search_term)}">
                        {get_match_badge(top_gs_pick, search_term)}
                        <div class="data-label" style="color:#ef4444; font-size:0.90rem;">🔥 AI STRONGEST CONFIDENCE (BEST BET)</div>
                        <div class="data-value" style="font-size:1.8rem; font-family:'Montserrat'; font-weight:800; margin-top: 5px; color:#ffffff; text-shadow: 0 4px 10px rgba(239,68,68,0.4);">Race {top_gs_pick['race_no']} – #{top_gs_pick['no']} {top_gs_pick['name']}</div>
                        <div class="data-value" style="font-size:1.0rem; color:#f8fafc; margin-top: 5px;">Live Odds: <b>{top_gs_pick['win_odds']:.1f}</b> &nbsp;|&nbsp; AI Confidence: <b style="color:#FFD700;">{top_gs_pick['confidence']}%</b></div>
                    </div>
                    '''), unsafe_allow_html=True)
            parlay_str = " + ".join([f"R{bb.get('race_no')} #{bb.get('no')}" for bb in parlay_sorted[:3]])
            st.markdown(f"<div style='margin-top:10px; font-family:\"Inter\"; font-size:1.15rem;'><b>Optimized Multi-Leg Sequence:</b> <span style='color:#ef4444; font-weight:700;'>{parlay_str}</span></div>", unsafe_allow_html=True)
            
            # Display Steam Alerts inside expander
            if steam_alerts:
                steam_html = '<div style="margin-top:20px; font-family:\'Montserrat\'; font-weight:700; font-size:1.1rem; color:#ffffff; letter-spacing:0.5px;">🔥 LIVE MARKET STEAM ALERTS (SMART MONEY ACTION)</div>'
                steam_html += '<div style="display:flex; flex-wrap:wrap; gap:10px; margin-top:8px;">'
                sorted_steam = sorted(steam_alerts, key=lambda x: x['pct'])
                for alert in sorted_steam[:6]: # Show top 6
                    pct_str = f"{alert['pct'] * 100:.0f}%"
                    steam_html += clean_html(f'''
                    <div style="background: rgba(239, 68, 68, 0.12); padding: 8px 14px; border-radius: 6px; border: 1px solid rgba(239, 68, 68, 0.4); font-size:0.95rem; color:#ffffff; line-height:1.4;">
                        <b>R{alert['race_no']} #{alert['no']} {alert['name']}</b><br>
                        <span style="color:#ef4444; font-weight:700;">Steam: {pct_str}</span> ({alert['base']:.1f} → {alert['curr']:.1f}) | <i>{alert['jockey']}</i>
                    </div>
                    ''')
                steam_html += '</div>'
                st.markdown(steam_html, unsafe_allow_html=True)
    
    st.markdown("---")
    
    def get_shift_badge(row):
        base = float(row.get('baseline_odds', 0.0))
        curr = float(row.get('win_odds', 0.0))
        if base > 0 and curr > 0:
            pct = (curr - base) / base
            if pct < -0.15:
                return f' <span style="background:#ef4444; color:#ffffff; padding:2px 6px; border-radius:4px; font-size:0.75rem; font-weight:bold; vertical-align:middle;">🔥 STEAM {pct*100:.0f}%</span>'
            elif pct > 0.25:
                return f' <span style="background:#4b5563; color:#ffffff; padding:2px 6px; border-radius:4px; font-size:0.75rem; font-weight:bold; vertical-align:middle;">💨 DRIFT +{pct*100:.0f}%</span>'
        return ''

    st.markdown("<h3 style='font-family:\"Montserrat\"; letter-spacing:1px; color:#ffffff; font-weight:700;'>AI RACE-BY-RACE PREDICTIONS</h3>", unsafe_allow_html=True)

    for race in races:
        if not race.get('runners'): continue
        df_runners = race['processed_runners']
        
        with st.container():
            
            class_dist = str(race.get("class_dist", ""))
            
            # parse distance
            dist_match = re.search(r'(\d+)m', class_dist, re.IGNORECASE)
            distance = int(dist_match.group(1)) if dist_match else 0
            
            # parse class
            c_val = "1"
            if "Class 1" in class_dist: c_val = "1"
            elif "Class 2" in class_dist: c_val = "2"
            elif "Class 3" in class_dist: c_val = "3"
            elif "Class 4" in class_dist: c_val = "4"
            elif "Class 5" in class_dist: c_val = "5"
            elif "Group" in class_dist or "G1" in class_dist or "G2" in class_dist or "G3" in class_dist: c_val = "Group"
            elif "Griffin" in class_dist: c_val = "Griffin"
            
            venue_str = meeting.get('venue', 'Sha Tin')
            race_track_type = str(race.get('track', 'TURF')).upper()
            race_going_type = str(race.get('going', 'GOOD')).upper()
            
            if "HAPPY VALLEY" in venue_str.upper():
                target_venue = "Happy Valley Turf Track"
            else:
                if "ALL WEATHER" in race_track_type or "AWT" in race_track_type:
                    target_venue = "Sha Tin All Weather Track"
                else:
                    target_venue = "Sha Tin Turf Track"
                    
            std_time = "N/A"
            rec_time = "N/A"
            rec_horse = "-"
            
            if not std_times_df.empty:
                match = std_times_df[(std_times_df['Venue'] == target_venue) & 
                                     (std_times_df['Distance'] == distance) & 
                                     (std_times_df['Class'] == c_val)]
                if not match.empty:
                    std_time = str(match.iloc[0]['Standard_Time'])
                    rec_time = str(match.iloc[0]['Record_Time'])
                    rec_horse = str(match.iloc[0]['Record_Horse'])
                    if pd.isna(match.iloc[0]['Record_Time']): rec_time = "N/A"
                    if pd.isna(match.iloc[0]['Record_Horse']): rec_horse = "-"

            st.markdown(clean_html(f'''
            <div style="font-family:'Montserrat'; font-size:1.6rem; font-weight:800; color:#ef4444; margin-top:30px; margin-bottom:5px; text-shadow: 0 2px 5px rgba(239,68,68,0.4);">
                RACE {race.get("race_no", "")} – <span style="font-family:'Inter'; font-weight:500; font-size:1.2rem; color:#d1d5db;">{class_dist}</span>
            </div>
            <div style="display:flex; gap: 20px; margin-bottom:15px;">
                <div style="background: rgba(255, 215, 0, 0.1); padding: 5px 12px; border-radius: 6px; border: 1px solid rgba(255, 215, 0, 0.3);">
                    <span style="font-size:0.8rem; color:#9ca3af; text-transform:uppercase; font-weight:600;">⏱️ Standard Time:</span>
                    <span style="font-size:0.95rem; color:#FFD700; font-weight:700; margin-left:5px;">{std_time}</span>
                </div>
                <div style="background: rgba(239, 68, 68, 0.1); padding: 5px 12px; border-radius: 6px; border: 1px solid rgba(239, 68, 68, 0.3);">
                    <span style="font-size:0.8rem; color:#9ca3af; text-transform:uppercase; font-weight:600;">🏆 Course Record:</span>
                    <span style="font-size:0.95rem; color:#ffffff; font-weight:700; margin-left:5px;">{rec_time} ({rec_horse})</span>
                </div>
            </div>
            '''), unsafe_allow_html=True)
            
            # Show Track Bias Warning Alerts
            if "ALL WEATHER" in race_track_type or "AWT" in race_track_type:
                if "SEALED" in race_going_type:
                    st.markdown(clean_html('''
                    <div style="background: rgba(255, 215, 0, 0.08); padding: 10px 16px; border-radius: 6px; border: 1px dashed rgba(255, 215, 0, 0.5); margin-bottom: 15px; font-size:0.95rem; color:#FFD700; font-family:'Inter', sans-serif;">
                        ⚡ <b>TRACK BIAS ALERT (AWT SEALED)</b>: The dirt track is compacted/sealed due to wet weather. Expect strong speed bias favoring low draws and on-speed runners.
                    </div>
                    '''), unsafe_allow_html=True)
            else:
                if race_going_type in ["YIELDING", "SOFT", "HEAVY"]:
                    st.markdown(clean_html(f'''
                    <div style="background: rgba(239, 68, 68, 0.08); padding: 10px 16px; border-radius: 6px; border: 1px dashed rgba(239, 68, 68, 0.5); margin-bottom: 15px; font-size:0.95rem; color:#ef4444; font-family:'Inter', sans-serif;">
                        🌧️ <b>TRACK BIAS ALERT (WET TURF - {race_going_type})</b>: Turf track has degraded. On-speed runners (leaders) are highly favored; off-pace closers may struggle to make ground.
                    </div>
                    '''), unsafe_allow_html=True)
            
                    # Show dynamic pace summaries
                    speed_count = (df_runners['avg_first_pos'] <= 3.5).sum()
                    if speed_count >= 4:
                        pace_summary = "⚡ <b>HIGH PACE</b>: We assess this race to have a lot of speed. Front-runners may tire late, but they can still hold on based on form. Be wary of back-markers unless they have elite acceleration."
                        pace_color = "rgba(239, 68, 68, 0.08)"
                        border_color = "rgba(239, 68, 68, 0.4)"
                        text_color = "#ef4444"
                    elif speed_count <= 1:
                        pace_summary = "🐌 <b>ON SPEED</b>: Slow pace expected. Speed bias favors front-runners/leaders who can take off. Closers and late finishers may struggle to make up ground."
                        pace_color = "rgba(255, 215, 0, 0.08)"
                        border_color = "rgba(255, 215, 0, 0.4)"
                        text_color = "#FFD700"
                    else:
                        pace_summary = "⚖️ <b>GOOD PACE</b>: Balanced pace expected. Fair conditions; both speed horses and late finishers have equal opportunity based on form and odds."
                        pace_color = "rgba(255, 255, 255, 0.05)"
                        border_color = "rgba(255, 255, 255, 0.2)"
                        text_color = "#ffffff"
                        
                    st.markdown(clean_html(f'''
                    <div style="background: {pace_color}; padding: 10px 16px; border-radius: 6px; border: 1px solid {border_color}; margin-bottom: 15px; font-size:0.95rem; color:{text_color}; font-family:'Inter', sans-serif;">
                        {pace_summary}
                    </div>
                    '''), unsafe_allow_html=True)
                    
                    # Special Exotic Sleeper Alert for DO YOU JUST (L094)
                    has_do_you_just = any(str(r.get('code', '')).upper() == 'L094' for r in race.get('runners', []))
                    if has_do_you_just:
                        do_you_just_no = next((r.get('no') for r in race.get('runners', []) if str(r.get('code', '')).upper() == 'L094'), 12)
                        st.markdown(clean_html(f'''
                        <div style="background: rgba(239, 68, 68, 0.12); padding: 12px 18px; border-radius: 8px; border: 2px solid #ef4444; margin-bottom: 15px; font-size:0.95rem; color:#ffffff; font-family:'Inter', sans-serif;">
                            🚨 <b>EXOTIC SLEEPER ALERT (RONAN'S PICK)</b>: <b>#{do_you_just_no} DO YOU JUST</b> (Code L094) has won his last 2 races. Form indicates high effectiveness when putting Cheek Pieces (CP) back on and removing the Hood. Crucial exotic addition for exotic ticket structures!
                        </div>
                        '''), unsafe_allow_html=True)
            
            race_picks = df_runners.sort_values(by='gs_score', ascending=False)
            
            # Ensure we have at least 5 runners
            if len(race_picks) < 5:
                continue

            best = race_picks.iloc[0]
            second = race_picks.iloc[1]
            third = race_picks.iloc[2]
            fourth = race_picks.iloc[3]
            fifth = race_picks.iloc[4]
            
            pc1, pc2, pc3, pc4, pc5 = st.columns(5)
            with pc1:
                st.markdown(clean_html(f'''
                <div class="tech-panel border-accent-gold" style="{check_highlight(best, search_term)}">
                    {get_match_badge(best, search_term)}
                    <div class="data-label" style="color:#FFD700; font-size:0.85rem;">⭐ PRIMARY WIN PROBABILITY</div>
                    <div class="data-value" style="font-size:1.35rem;">{best['no']}. {best['name']}</div>
                    <div class="data-value" style="font-size:0.9rem; color:#d1d5db; margin-top:8px;">
                        J: <span style="color:#ffffff;">{best['jockey']}</span> | T: <span style="color:#ffffff;">{best['trainer']}</span>
                        <br><span style="color:#d1d5db;">Odds:</span> <span style="color:#ffffff;">{best['win_odds']:.1f}</span>{get_shift_badge(best)}
                    </div>
                    <div class="data-value" style="font-size:0.95rem; margin-top:10px; color:#FFD700; font-weight:700;">AI Conf: {best['confidence']}% &nbsp;|&nbsp; Tip Pts: {best.get('consensus_score', 0)}</div>
                </div>
                '''), unsafe_allow_html=True)
            with pc2:
                st.markdown(clean_html(f'''
                <div class="tech-panel border-accent-red" style="{check_highlight(second, search_term)}">
                    {get_match_badge(second, search_term)}
                    <div class="data-label" style="font-size:0.85rem;">🎯 OPTIMAL EXACTA</div>
                    <div class="data-value" style="font-size:1.25rem;">{second['no']}. {second['name']}</div>
                    <div class="data-value" style="font-size:0.9rem; color:#d1d5db; margin-top:8px;">
                        J: <span style="color:#ffffff;">{second['jockey']}</span> | T: <span style="color:#ffffff;">{second['trainer']}</span>
                        <br><span style="color:#d1d5db;">Odds:</span> <span style="color:#ffffff;">{second['win_odds']:.1f}</span>{get_shift_badge(second)}
                    </div>
                    <div class="data-value" style="font-size:0.95rem; margin-top:10px; color:#ef4444;">AI Conf: {second['confidence']}% &nbsp;|&nbsp; Tip Pts: {second.get('consensus_score', 0)}</div>
                </div>
                '''), unsafe_allow_html=True)
            with pc3:
                st.markdown(clean_html(f'''
                <div class="tech-panel" style="border-left: 5px solid #4b5563; {check_highlight(third, search_term)}">
                    {get_match_badge(third, search_term)}
                    <div class="data-label" style="font-size:0.85rem;">💠 TRIFECTA CONSIDERATION</div>
                    <div class="data-value" style="font-size:1.25rem;">{third['no']}. {third['name']}</div>
                    <div class="data-value" style="font-size:0.9rem; color:#d1d5db; margin-top:8px;">
                        J: <span style="color:#ffffff;">{third['jockey']}</span> | T: <span style="color:#ffffff;">{third['trainer']}</span>
                        <br><span style="color:#d1d5db;">Odds:</span> <span style="color:#ffffff;">{third['win_odds']:.1f}</span>{get_shift_badge(third)}
                    </div>
                    <div class="data-value" style="font-size:0.95rem; margin-top:10px; color:#9ca3af;">AI Conf: {third['confidence']}% &nbsp;|&nbsp; Tip Pts: {third.get('consensus_score', 0)}</div>
                </div>
                '''), unsafe_allow_html=True)
            with pc4:
                st.markdown(clean_html(f'''
                <div class="tech-panel" style="border-left: 5px solid #4b5563; {check_highlight(fourth, search_term)}">
                    {get_match_badge(fourth, search_term)}
                    <div class="data-label" style="font-size:0.85rem;">4TH PREDICTION</div>
                    <div class="data-value" style="font-size:1.25rem;">{fourth['no']}. {fourth['name']}</div>
                    <div class="data-value" style="font-size:0.9rem; color:#d1d5db; margin-top:8px;">
                        J: <span style="color:#ffffff;">{fourth['jockey']}</span> | T: <span style="color:#ffffff;">{fourth['trainer']}</span>
                        <br><span style="color:#d1d5db;">Odds:</span> <span style="color:#ffffff;">{fourth['win_odds']:.1f}</span>{get_shift_badge(fourth)}
                    </div>
                    <div class="data-value" style="font-size:0.95rem; margin-top:10px; color:#9ca3af;">AI Conf: {fourth['confidence']}%</div>
                </div>
                '''), unsafe_allow_html=True)
            with pc5:
                st.markdown(clean_html(f'''
                <div class="tech-panel" style="border-left: 5px solid #4b5563; {check_highlight(fifth, search_term)}">
                    {get_match_badge(fifth, search_term)}
                    <div class="data-label" style="font-size:0.85rem;">5TH PREDICTION</div>
                    <div class="data-value" style="font-size:1.25rem;">{fifth['no']}. {fifth['name']}</div>
                    <div class="data-value" style="font-size:0.9rem; color:#d1d5db; margin-top:8px;">
                        J: <span style="color:#ffffff;">{fifth['jockey']}</span> | T: <span style="color:#ffffff;">{fifth['trainer']}</span>
                        <br><span style="color:#d1d5db;">Odds:</span> <span style="color:#ffffff;">{fifth['win_odds']:.1f}</span>{get_shift_badge(fifth)}
                    </div>
                    <div class="data-value" style="font-size:0.95rem; margin-top:10px; color:#9ca3af;">AI Conf: {fifth['confidence']}%</div>
                </div>
                '''), unsafe_allow_html=True)
                
            # Prevent the outlier from being the exact same horse as the primary leader, and require positive edge
            longshots = df_runners[(df_runners['win_odds'] >= 12.0) & (df_runners['no'] != best['no']) & (df_runners['value_diff'] > 0.0)].sort_values(by='value_diff', ascending=False)
            if not longshots.empty:
                bold_pick = longshots.iloc[0]
                with st.expander(f"🔥 HIGH-CONVEXITY OPPORTUNITIES & EXOTIC STRUCTURES", expanded=True):
                    st.markdown(clean_html(f'''
                    <div style="background: rgba(239, 68, 68, 0.08); padding: 20px; border-radius: 8px; border: 1px dashed rgba(239, 68, 68, 0.4); margin-bottom: 5px;">
                        <div style="color:#ef4444; font-family:'Montserrat'; font-weight:800; font-size:1.15rem; margin-bottom:8px; letter-spacing: 1px;">STATISTICAL OUTLIER DETECTED: #{bold_pick['no']} {bold_pick['name']}</div>
                        <div style="color:#f8fafc; font-size:1rem; margin-bottom: 15px; line-height:1.5;">
                            Our quantitative models have identified a significant probabilistic upside on <b>#{bold_pick['no']} {bold_pick['name']}</b> relative to the current market implied probability at <b>{bold_pick['win_odds']:.0f}</b> odds. 
                            (Jockey: <i>{bold_pick['jockey']}</i> | Trainer: <i>{bold_pick['trainer']}</i>)
                        </div>
                        <div style="color:#FFD700; font-size:1rem; margin-top:8px;">⭐ <b>Optimal Exacta/Quinella Pairing:</b> Couple the primary statistical leader <b>#{best['no']}</b> with the identified outlier <b>#{bold_pick['no']}</b> for maximal expected value.</div>
                        <div style="color:#FFD700; font-size:1rem; margin-top:8px;">⭐ <b>Trifecta Structure:</b> Use <b>#{best['no']}</b> and <b>#{bold_pick['no']}</b> as dual bankers, combined with <b>#{second['no']}</b> and <b>#{third['no']}</b> for the remaining legs.</div>
                        <div style="color:#FFD700; font-size:1rem; margin-top:8px;">⭐ <b>Cross-Race Leverage Target:</b> Deploy <b>#{bold_pick['no']}</b> strictly as a <u>Place (To Finish Top 3)</u> anchor in sequential combinations to compound probabilistic edge.</div>
                    </div>
                    '''), unsafe_allow_html=True)

            with st.expander(f"EXPAND FULL RACE DATA – RACE {race.get('race_no')}", expanded=True):
                # Ensure missing columns exist
                for col in ['last_win_rating', 'ST_vs_HV_pref', 'last_form_going', 'class_diff', 'rating_diff', 'days_since_last_run', 'gear_changed', 'recent_avg_pos', 'distance_win_rate', 'gear_win_rate', 'last_gear', 'photo_finish', 'vet_findings', 'steward_notes']:
                    if col not in df_runners.columns:
                        df_runners[col] = '-'

                df_display = df_runners[['no', 'name', 'jockey', 'trainer', 'draw', 'rtg', 'win_odds', 'consensus_score', 'class_diff', 'rating_diff', 'recent_avg_pos', 'distance_win_rate', 'gear_win_rate', 'last_gear', 'days_since_last_run', 'gear_changed', 'last_win_rating', 'ST_vs_HV_pref', 'last_form_going', 'confidence', 'photo_finish', 'vet_findings', 'steward_notes', 'gs_score']].copy()
                df_display = df_display.sort_values(by='gs_score', ascending=False)
                
                # Fill NAs and ensure string type for object columns to avoid PyArrow serialization errors
                df_display['last_win_rating'] = df_display['last_win_rating'].astype(str).replace('nan', '-')
                df_display['ST_vs_HV_pref'] = df_display['ST_vs_HV_pref'].fillna('Neutral').astype(str)
                df_display['last_form_going'] = df_display['last_form_going'].fillna('Unknown').astype(str)
                
                st.dataframe(
                    df_display,
                    column_config={
                        "no": st.column_config.NumberColumn("No.", width="small"),
                        "name": st.column_config.TextColumn("Horse Name", width="medium"),
                        "jockey": st.column_config.TextColumn("Jockey", width="small"),
                        "trainer": st.column_config.TextColumn("Trainer", width="medium"),
                        "draw": st.column_config.NumberColumn("Draw", width="small"),
                        "rtg": st.column_config.NumberColumn("Rating", width="small"),
                        "win_odds": st.column_config.NumberColumn("Odds", format="%.1f", width="small"),
                        "consensus_score": st.column_config.NumberColumn("Tipster Pts", width="small"),
                        "class_diff": st.column_config.NumberColumn("Class Diff", width="small"),
                        "rating_diff": st.column_config.NumberColumn("Rtg Diff", width="small"),
                        "recent_avg_pos": st.column_config.NumberColumn("Rec Pos", format="%.1f", width="small"),
                        "distance_win_rate": st.column_config.NumberColumn("Dist Win%", format="%.2f", width="small"),
                        "gear_win_rate": st.column_config.NumberColumn("Gear Win%", format="%.2f", width="small"),
                        "last_gear": st.column_config.TextColumn("Gear", width="small"),
                        "days_since_last_run": st.column_config.NumberColumn("Days Off", width="small"),
                        "gear_changed": st.column_config.NumberColumn("Gear Chg", width="small"),
                        "last_win_rating": st.column_config.TextColumn("Last Win Rtg", width="small"),
                        "ST_vs_HV_pref": st.column_config.TextColumn("Track Pref", width="medium"),
                        "last_form_going": st.column_config.TextColumn("Fav Cond", width="medium"),
                        "gs_score": st.column_config.NumberColumn("GS Score", format="%.1f", width="small"),
                        "confidence": st.column_config.ProgressColumn(
                            "AI Confidence %",
                            min_value=0,
                            max_value=100,
                        ),
                        "photo_finish": st.column_config.TextColumn("Photo Finish Hist?", width="small"),
                        "vet_findings": st.column_config.TextColumn("Vet Findings", width="medium"),
                        "steward_notes": st.column_config.TextColumn("Steward Notes", width="large"),
                    },
                    hide_index=True,
                    use_container_width=True
                )

with tab2:
    st.markdown("<h3 style='font-family:\"Montserrat\";'>Historical Archive & Gallery</h3>", unsafe_allow_html=True)
    st.write("Browse and analyze past race outcomes, field variables, and iconic moments from our data servers.")
    
    st.markdown("#### 📸 Classic Race Gallery")
    gal_col1, gal_col2, gal_col3 = st.columns(3)
    with gal_col1:
        if os.path.exists("data/images/shatin.png"):
            st.image("data/images/shatin.png", caption="Thrilling Finish at Sha Tin", use_container_width=True)
    with gal_col2:
        if os.path.exists("data/images/happy_valley.png"):
            st.image("data/images/happy_valley.png", caption="Night Racing at Happy Valley", use_container_width=True)
    with gal_col3:
        if os.path.exists("data/images/winner.png"):
            st.image("data/images/winner.png", caption="Winner's Circle Celebration", use_container_width=True)
            
    st.markdown("---")
    
    try:
        if os.path.exists('data/runs.csv'):
            df_runs = pd.read_csv('data/runs.csv', nrows=1000) 
            st.markdown('<div class="tech-panel border-accent-red">', unsafe_allow_html=True)
            st.write("##### INDIVIDUAL RUNS LOG")
            st.dataframe(df_runs, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
            if os.path.exists('data/races.csv'):
                df_races = pd.read_csv('data/races.csv', nrows=250)
                st.markdown('<div class="tech-panel border-accent-gold">', unsafe_allow_html=True)
                st.write("##### RACE CONDITIONS LOG")
                st.dataframe(df_races, use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("Historical data not found in ./data directory.")
    except Exception as e:
        st.error(f"Error reading local data assets: {str(e)}")

with tab3:
    st.markdown("<h3 style='font-family:\"Montserrat\"; margin-top:10px;'>HKJC News & Media</h3>", unsafe_allow_html=True)
    
    news_items = fetch_news()
    if news_items:
        for news in news_items:
            st.markdown(clean_html(f'''
            <div class="tech-panel hover-effect border-accent-red" style="padding:22px; margin-bottom:20px;">
                <div style="font-size:1.3rem; font-weight:700; font-family:'Montserrat'; margin-bottom: 12px;"><a href='{news['link']}' style='color: #ffffff; text-decoration: none;'>{news['title']}</a></div>
                <div><a href='{news['link']}' style='color: #FFD700; font-family:"Inter", sans-serif; font-weight:600; font-size:0.95rem; text-decoration:none;'>[ Read Full Article &rarr; ]</a></div>
            </div>
            '''), unsafe_allow_html=True)
    else:
        st.info("News feed temporarily unavailable.")
        
st.markdown("---")
st.markdown("<p style='text-align: center; color: #6b7280; font-family:\"Inter\"; font-weight: 500; font-size: 0.85rem; letter-spacing: 1px;'>GOLDEN STALLION AI • INSTITUTIONAL TERMINAL • RESPONSIBLE GAMBLING 18+</p>", unsafe_allow_html=True)
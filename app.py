import streamlit as st
import pandas as pd
import numpy as np
import os
import re
import json
import time
import requests
from streamlit_autorefresh import st_autorefresh
import odds_tracker
import textwrap
import base64

try:
    from patch_index import patch_index
    patch_index()
except Exception:
    pass

def clean_html(html_str):
    return "\n".join(line.lstrip() for line in html_str.split("\n"))

def check_stewards_excuse(comment, vet_status=0):
    if not comment or pd.isna(comment):
        return vet_status != 0
    c = str(comment).lower()
    
    clean_phrases = ['without interruption', 'no interference', 'not checked', 'no incident', 'clear run throughout', 'without impediment']
    if any(cp in c for cp in clean_phrases):
        return False
        
    # True excuses:
    excuse_keywords = [
        'badly checked', 'severely checked', 'checked', 'check ', 'crowded', 'hampered', 
        'held up', 'no clear run', 'denied a clear run', 'pocketed', 'clipped heels', 'clip heels',
        'lost ground at start', 'slow to begin', 'stumbled', 'stumble', 'lost shoe', 'lost plate', 
        'lost a plate', 'saddle slipped', 'blood in trachea', 'trachea', 'forced wide', 'no room', 'blocked',
        'bleeder', 'irregular heart', 'heart irregularity', 'lame', 'lameness', 'mucus'
    ]
    
    has_excuse = any(kw in c for kw in excuse_keywords)
    if vet_status != 0:
        has_excuse = True
    return has_excuse

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


st.set_page_config(
    page_title="SILKS.AI | Quantitative HKJC Intelligence", 
    layout="wide", 
    page_icon="🐎",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': None
    }
)

@st.cache_data
def get_hero_banner_b64():
    banner_filename = "silks_ai_banner.jpg"
    candidates = [
        banner_filename,
        os.path.join(os.path.dirname(__file__), banner_filename),
        os.path.join("data", banner_filename),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    return base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                pass
    return ""

def render_hero_banner():
    b64 = get_hero_banner_b64()
    if b64:
        st.markdown(clean_html(f'''
        <div class="banner-outer-hero">
            <img src="data:image/jpeg;base64,{b64}" alt="SILKS.AI Banner" class="banner-hero-img" />
        </div>
        <div class="hero-chinese-subtitle">香港賽馬會智能預測終端</div>
        '''), unsafe_allow_html=True)
    else:
        col_l, col_center, col_r = st.columns([0.5, 11, 0.5])
        with col_center:
            st.image("silks_ai_banner.jpg", width="stretch")
        st.markdown('<div class="hero-chinese-subtitle">香港賽馬會智能預測終端</div>', unsafe_allow_html=True)

# --- PAUSE SWITCH ---
APP_PAUSED = False
if APP_PAUSED:
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@600;800&family=Inter:wght@400;500;600;700&display=swap');
        .hero-chinese-subtitle {
            font-family: 'Montserrat', 'Inter', sans-serif;
            font-size: 1.45rem;
            font-weight: 800;
            color: #38bdf8 !important;
            text-align: center;
            letter-spacing: 5px;
            margin-top: 8px;
            margin-bottom: 24px;
            text-shadow: 0 2px 10px rgba(0,0,0,0.9), 0 0 15px rgba(56, 189, 248, 0.4);
        }
        .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] { 
            background: radial-gradient(circle at 50% 8%, #780d1a 0%, #520812 50%, #35040a 100%) !important;
            background-color: #520812 !important;
            color: #ffffff; 
        }
        [data-testid="stMain"] {
            display: flex !important;
            flex-direction: column !important;
            align-items: center !important;
            width: 100% !important;
        }
        .block-container, [data-testid="stMainBlockContainer"] {
            padding-top: 0.5rem !important;
            max-width: 1300px !important;
            width: 100% !important;
            margin: 0 auto !important;
        }
        .banner-outer-hero {
            display: flex !important;
            justify-content: center !important;
            align-items: center !important;
            width: 100% !important;
            margin: 0 auto 8px auto !important;
            text-align: center !important;
        }
        .banner-hero-img {
            border-radius: 16px !important;
            border: 2.5px solid #38bdf8 !important;
            box-shadow: 0 14px 40px rgba(0, 0, 0, 0.65), 0 0 25px rgba(56, 189, 248, 0.35) !important;
            width: 100% !important;
            max-width: 1200px !important;
            height: auto !important;
            max-height: 520px !important;
            margin: 0 auto !important;
            display: block !important;
            object-fit: cover !important;
            object-position: center 35% !important;
        }
    </style>
    """, unsafe_allow_html=True)
    render_hero_banner()
    st.error("⚠️ The AI Engine is currently paused for mid-meeting recalibration and results reporting. Please check back shortly.")
    st.stop()
# --------------------

# Ultra-smooth live odds refresh every 20 seconds (keeps session live and odds fresh)
st_autorefresh(interval=20000, key="hkjc_live_refresh_pulse")

# CSS Injection for Chinese-Friendly Ruby/Gold 3D UI
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@600;800&family=Inter:wght@400;500;600;700&display=swap');
    
    /* Suppress Streamlit's dimming/greying out during background refresh */
    [data-testid="stAppViewContainer"] > .main {
        opacity: 1 !important;
        transition: none !important;
        filter: none !important;
    }
    div[data-testid="stAppViewBlockContainer"] {
        opacity: 1 !important;
        filter: none !important;
    }
    
    /* Hide Streamlit Header, Main Menu, Deploy Button, and Footer */
    #MainMenu {visibility: hidden; display: none !important;}
    header {visibility: hidden; display: none !important;}
    footer {visibility: hidden; display: none !important;}
    .stDeployButton {display: none !important;}
    [data-testid="stToolbar"] {display: none !important;}
    [data-testid="stDecoration"] {display: none !important;}
    [data-testid="stStatusWidget"] {display: none !important;}
    div[class*="viewerBadge"] {display: none !important;}
    div[data-testid="stActionButton"] {display: none !important;}

    html, body, [class*="css"], [data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] span, label, [data-testid="stWidgetLabel"] p {
        font-family: 'Inter', sans-serif;
        color: #ffffff;
    }
    
    /* Imperial Crimson Institutional Canvas */
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] { 
        background: radial-gradient(circle at 50% 8%, #780d1a 0%, #520812 50%, #35040a 100%) !important;
        background-color: #520812 !important;
        color: #ffffff !important; 
    }
    
    /* Center the main container in the viewport */
    [data-testid="stAppViewContainer"] > .main,
    [data-testid="stMain"] {
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        width: 100% !important;
    }

    /* Ensure page content starts cleanly at the very top and is horizontally centered */
    .block-container, [data-testid="stMainBlockContainer"] {
        padding-top: 0.5rem !important;
        padding-bottom: 2.5rem !important;
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
        max-width: 1300px !important;
        width: 100% !important;
        margin-left: auto !important;
        margin-right: auto !important;
    }
    
    /* Top Hero Banner - Big, Horizontal, and Strictly Centered */
    .banner-outer-hero {
        display: flex !important;
        justify-content: center !important;
        align-items: center !important;
        width: 100% !important;
        margin-left: auto !important;
        margin-right: auto !important;
        margin-top: 0 !important;
        margin-bottom: 8px !important;
        text-align: center !important;
    }

    .banner-hero-img {
        display: block !important;
        margin-left: auto !important;
        margin-right: auto !important;
        width: 100% !important;
        max-width: 1200px !important;
        height: auto !important;
        max-height: 520px !important;
        object-fit: cover !important;
        object-position: center 35% !important;
        border-radius: 16px !important;
        border: 2.5px solid #38bdf8 !important;
        box-shadow: 0 14px 40px rgba(0, 0, 0, 0.65), 0 0 25px rgba(56, 189, 248, 0.35) !important;
    }

    /* Force all container wrappers around hero banner and images to be full-width and centered */
    div[data-testid="stElementContainer"]:has(.banner-outer-hero),
    div.element-container:has(.banner-outer-hero),
    div[data-testid="stElementContainer"]:has([data-testid="stImage"]),
    div.element-container:has([data-testid="stImage"]) {
        width: 100% !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        justify-content: center !important;
        margin-left: auto !important;
        margin-right: auto !important;
    }

    div[data-testid="stElementContainer"]:has([data-testid="stImage"]) > div,
    div[data-testid="stImage"],
    div[data-testid="stImageContainer"],
    div[data-testid="stImage"] > div {
        width: 100% !important;
        display: flex !important;
        justify-content: center !important;
        align-items: center !important;
        margin-left: auto !important;
        margin-right: auto !important;
        text-align: center !important;
    }

    div[data-testid="stImage"] img {
        border-radius: 16px !important;
        border: 2.5px solid #38bdf8 !important;
        box-shadow: 0 14px 40px rgba(0, 0, 0, 0.65), 0 0 25px rgba(56, 189, 248, 0.35) !important;
        width: 100% !important;
        max-width: 1200px !important;
        height: auto !important;
        max-height: 520px !important;
        margin-left: auto !important;
        margin-right: auto !important;
        margin-bottom: 12px !important;
        display: block !important;
        object-fit: cover !important;
        object-position: center 35% !important;
    }
    
    /* Gallery images inside tabs stay proportionate */
    .stTabs [data-testid="stImage"] img {
        max-width: 100% !important;
        height: 200px !important;
        aspect-ratio: auto !important;
        object-fit: cover !important;
        border-radius: 10px !important;
        border: 1.5px solid rgba(56, 189, 248, 0.4) !important;
        box-shadow: none !important;
    }
    
    /* Chinese Subtitle under Banner */
    .hero-chinese-subtitle {
        font-family: 'Montserrat', 'Inter', sans-serif;
        font-size: 1.45rem;
        color: #38bdf8 !important;
        text-align: center;
        letter-spacing: 5px;
        margin-top: 8px;
        margin-bottom: 24px;
        font-weight: 800;
        text-shadow: 0 2px 10px rgba(0, 0, 0, 0.9), 0 0 15px rgba(56, 189, 248, 0.4);
    }
    
    /* Responsive adjustments for mobile and tablets */
    @media (max-width: 768px) {
        .block-container, [data-testid="stMainBlockContainer"] {
            padding-top: 0.4rem !important;
            padding-left: 0.6rem !important;
            padding-right: 0.6rem !important;
        }
        .banner-hero-img,
        div[data-testid="stImage"] > img {
            max-height: 240px !important;
            border-radius: 12px !important;
        }
        .hero-chinese-subtitle {
            font-size: 1.05rem !important;
            letter-spacing: 2px !important;
        }
        .tech-panel {
            padding: 15px 16px !important;
            margin: 8px 0 !important;
        }
        /* Mobile Card Stacking: Guarantee cards stack full-width for effortless phone scrolling */
        div[data-testid="stHorizontalBlock"] > div[data-testid="column"],
        div[data-testid="column"] {
            min-width: 100% !important;
            width: 100% !important;
            flex: 1 1 100% !important;
        }
        .data-value {
            font-size: 1.15rem !important;
        }
    }
    
    /* VIP Obsidian Crimson Glass Panels with Light Blue Accents */
    .tech-panel { 
        position: relative;
        background: linear-gradient(145deg, rgba(35, 6, 11, 0.94), rgba(20, 3, 6, 0.98)) !important;
        backdrop-filter: blur(12px);
        padding: 22px; 
        border-radius: 14px;
        border: 1.5px solid rgba(56, 189, 248, 0.4); 
        margin: 12px 0; 
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45), inset 0 1px 0 rgba(56, 189, 248, 0.2);
        transition: all 0.2s cubic-bezier(0.25, 0.8, 0.25, 1);
        overflow: hidden;
    }
    .tech-panel:hover {
        transform: translateY(-3px);
        box-shadow: 0 16px 36px rgba(0, 0, 0, 0.6), 0 0 18px rgba(56, 189, 248, 0.4);
        border-color: rgba(56, 189, 248, 0.8);
    }

    /* Edge Lighting Effects (Light Blue, Cyan, and Rose) */
    .border-accent-gold { border-left: 5px solid #38bdf8 !important; box-shadow: -4px 0 14px rgba(56, 189, 248, 0.35), 0 10px 30px rgba(0,0,0,0.45); }
    .border-accent-blue { border-left: 5px solid #38bdf8 !important; box-shadow: -4px 0 14px rgba(56, 189, 248, 0.35), 0 10px 30px rgba(0,0,0,0.45); }
    .border-accent-red { border-left: 5px solid #f43f5e !important; box-shadow: -4px 0 14px rgba(244, 63, 94, 0.35), 0 10px 30px rgba(0,0,0,0.45); }

    .data-label {
        font-family: 'Inter', sans-serif;
        font-size: 0.82rem;
        color: #38bdf8 !important;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        margin-bottom: 5px;
        font-weight: 800;
    }
    .data-value {
        font-family: 'Inter', sans-serif;
        font-size: 1.25rem;
        color: #ffffff !important;
        font-weight: 800;
    }
    
    /* 3D Expanders */
    .streamlit-expanderHeader { 
        font-family: 'Montserrat', sans-serif;
        color: #38bdf8 !important; 
        font-weight: 800;
        border: 1.5px solid rgba(56, 189, 248, 0.45) !important;
        border-radius: 8px;
        background: linear-gradient(145deg, #3d050a, #240206) !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
    }
    [data-testid="stExpander"] details {
        background: rgba(30, 4, 8, 0.75);
        border-radius: 8px;
        border: 1px solid rgba(56, 189, 248, 0.3);
    }
    
    /* 3D Progress Bar in Light Blue */
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #0284c7, #38bdf8);
        box-shadow: 0 0 12px rgba(56, 189, 248, 0.4);
        border-radius: 10px;
    }
    
    /* Elegant Tabs */
    .stTabs [data-baseweb="tab-list"] { gap: 10px; border-bottom: 2px solid rgba(56, 189, 248, 0.3); }
    .stTabs [data-baseweb="tab"] {
        font-family: 'Montserrat', sans-serif;
        font-weight: 800;
        letter-spacing: 1px;
        font-size: 0.95rem;
        color: #e2e8f0;
    }
    .stTabs [aria-selected="true"] { 
        color: #38bdf8 !important; 
        border-bottom-color: #38bdf8 !important; 
        text-shadow: 0 0 10px rgba(56, 189, 248, 0.5);
    }

    /* Official HKJC Horse Profile Direct Links */
    .horse-profile-link,
    .horse-profile-link:link,
    .horse-profile-link:visited {
        color: #ffffff !important;
        text-decoration: none !important;
        transition: color 0.15s ease, text-shadow 0.15s ease;
        cursor: pointer;
    }
    .horse-profile-link:hover,
    .horse-profile-link:active {
        color: #38bdf8 !important;
        text-shadow: 0 0 12px rgba(56, 189, 248, 0.6);
        text-decoration: none !important;
    }
    .hkjc-link-arrow {
        font-size: 0.78em;
        color: #38bdf8 !important;
        font-weight: 800;
        margin-left: 3px;
        display: inline-block;
        transition: transform 0.15s ease;
    }
    .horse-profile-link:hover .hkjc-link-arrow {
        transform: translate(2px, -2px);
    }

    /* Distinct Non-Distracting Pick Card Accents & Quick-Glance Ticket Pills */
    .pick-card-1 {
        border-left: 5px solid #38bdf8 !important;
        border-top: 2px solid rgba(56, 189, 248, 0.85) !important;
        box-shadow: -4px 0 16px rgba(56, 189, 248, 0.4), 0 10px 30px rgba(0, 0, 0, 0.5) !important;
    }
    .pick-card-2 {
        border-left: 5px solid #0ea5e9 !important;
        box-shadow: -4px 0 14px rgba(14, 165, 233, 0.35), 0 10px 30px rgba(0, 0, 0, 0.45) !important;
    }
    .pick-card-3 {
        border-left: 5px solid #0284c7 !important;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45) !important;
    }
    .pick-card-4 {
        border-left: 5px solid #0369a1 !important;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45) !important;
    }
    .pick-card-5 {
        border-left: 5px solid #7dd3fc !important;
        border-top: 1.5px dashed rgba(125, 211, 252, 0.6) !important;
        box-shadow: -4px 0 14px rgba(125, 211, 252, 0.3), 0 10px 30px rgba(0, 0, 0, 0.45) !important;
    }
    .ticket-pill {
        background: rgba(56, 189, 248, 0.14);
        border: 1px solid rgba(56, 189, 248, 0.5);
        color: #ffffff !important;
        padding: 2px 9px;
        border-radius: 6px;
        font-weight: 800;
        display: inline-block;
        margin: 2px 0;
    }
</style>
""", unsafe_allow_html=True)

# Central Banner (Big, Horizontal, Beautiful & Strictly Centered)
render_hero_banner()

@st.cache_data(ttl=20)
def fetch_data():
    return get_live_meeting_data(force_network=False)

@st.cache_data(ttl=3600)
def fetch_news():
    return get_hkjc_news()

@st.cache_data(ttl=86400)
def load_precomputed_data():
    try:
        with open('data/precomputed_features.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print("Error loading precomputed features:", e)
        return {}

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

@st.cache_data(ttl=3600)
def fetch_tips():
    return get_live_tips_index()

@st.cache_data(ttl=86400)
def fetch_trial_features():
    try:
        with open('data/engineered_trial_features.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

@st.cache_data(ttl=86400)
def fetch_horse_memory():
    try:
        from data.incident_engine import load_horse_memory
        return load_horse_memory()
    except Exception:
        return {}

@st.cache_data(ttl=86400)
def fetch_jt_partnerships():
    try:
        if os.path.exists('data/jockey_trainer_partnerships.csv'):
            return pd.read_csv('data/jockey_trainer_partnerships.csv')
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

# Initialize variables
data = fetch_data()
precomputed = load_precomputed_data()
last_comments = precomputed.get('last_comments', {})
winning_gears = {k: set(v) for k, v in precomputed.get('winning_gears', {}).items()}
running_styles = precomputed.get('running_styles', {})
sectional_bursts = precomputed.get('sectional_bursts', {})

std_times_df = fetch_standard_times()
horse_stats_df = fetch_horse_stats()
tips_data = fetch_tips()
trial_features = fetch_trial_features()
horse_memory = fetch_horse_memory()
jt_partnerships_df = fetch_jt_partnerships()
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


col_sel, col_ref = st.columns([4, 1])
with col_sel:
    selected_meeting_str = st.selectbox("📅 Select Race Meeting Date & Venue", meeting_options, index=default_index)
with col_ref:
    st.write("")
    st.write("")
    if st.button("🔄 Refresh Live Data", use_container_width=True):
        st.cache_data.clear()
        with st.spinner("Fetching latest live odds from HKJC..."):
            get_live_meeting_data(force_network=True)
        st.rerun()

selected_index = meeting_options.index(selected_meeting_str)
meeting = meetings[selected_index]
races = meeting.get('races', [])

# Proactively ensure all runners on the selected meeting card have complete HKJC profiles synced
try:
    from hkjc_profile_scraper import ensure_meeting_profiles_synced
    synced_count = ensure_meeting_profiles_synced(meeting)
    if synced_count > 0:
        fetch_horse_stats.clear()
        load_precomputed_data.clear()
        horse_stats_df = fetch_horse_stats()
        precomputed = load_precomputed_data()
        last_comments = precomputed.get('last_comments', {})
        winning_gears = {k: set(v) for k, v in precomputed.get('winning_gears', {}).items()}
        running_styles = precomputed.get('running_styles', {})
        sectional_bursts = precomputed.get('sectional_bursts', {})
except Exception as e:
    print("Warning in ensure_meeting_profiles_synced:", e)

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

# Build fast horse code lookup from horse_stats_df for official HKJC profile links
horse_code_lookup = {}
if not horse_stats_df.empty and 'clean_name' in horse_stats_df.columns and 'horse_code' in horse_stats_df.columns:
    for _, h_row in horse_stats_df.iterrows():
        c_name = str(h_row.get('clean_name', '')).strip().upper()
        h_code = str(h_row.get('horse_code', '')).strip().upper()
        if c_name and h_code and h_code not in ['', 'NAN', 'NONE', '-']:
            horse_code_lookup[c_name] = h_code

def get_hkjc_profile_url(runner):
    import urllib.parse
    code = runner.get('code') if hasattr(runner, 'get') else None
    if not code or pd.isna(code) or str(code).strip() in ['', 'nan', 'None', '-']:
        code = runner.get('horse_code') if hasattr(runner, 'get') else None
    if not code or pd.isna(code) or str(code).strip() in ['', 'nan', 'None', '-']:
        r_name = (runner.get('clean_name') or runner.get('name') or '') if hasattr(runner, 'get') else ''
        code = horse_code_lookup.get(str(r_name).strip().upper())
    if code and not pd.isna(code) and str(code).strip() not in ['', 'nan', 'None', '-']:
        clean_code = str(code).strip().upper()
        if clean_code.startswith('HK_'):
            return f"https://racing.hkjc.com/racing/information/English/Horse/Horse.aspx?HorseId={clean_code}"
        return f"https://racing.hkjc.com/racing/information/English/Horse/Horse.aspx?HorseNo={clean_code}"
    name = str(runner.get('name', '') if hasattr(runner, 'get') else '').strip()
    if name:
        return f"https://racing.hkjc.com/racing/information/English/Horse/SelectHorse.aspx?HorseName={urllib.parse.quote(name)}"
    return "https://racing.hkjc.com/racing/information/English/Horse/SelectHorse.aspx"

def format_horse_link(runner, prefix="", show_arrow=True):
    url = get_hkjc_profile_url(runner)
    name = runner.get('name', 'Unknown') if hasattr(runner, 'get') else str(runner)
    no_val = runner.get('no', '') if hasattr(runner, 'get') else ''
    if prefix == "#":
        prefix_str = f"#{no_val} "
    elif prefix == ".":
        prefix_str = f"{no_val}. "
    else:
        prefix_str = prefix
    arrow_html = '<span class="hkjc-link-arrow">↗</span>' if show_arrow else ''
    return f'<a href="{url}" target="_blank" rel="noopener noreferrer" class="horse-profile-link" title="View Official HKJC Horse Profile">{prefix_str}{name}{arrow_html}</a>'

search_term = st.text_input("🔍 Highlight Jockey or Trainer (e.g., PURTON, FOWNES)", "").strip().upper()

# TABS
tab1, tab2, tab3 = st.tabs(["🔴 Live Matrix", "📊 Archive", "📰 HKJC News"])

with tab1:
    if data.get('status') != 'success':
        st.warning("Live connection failed. Secure fallback models initialized.")

    # Meeting Status Grid
    col_st1, col_st2, col_st3, col_st4 = st.columns(4)
    with col_st1:
        st.markdown('<div class="tech-panel border-accent-blue"><div class="data-label" style="color:#38bdf8; font-weight:800;">Venue</div><div class="data-value" style="color:#ffffff; font-weight:800;">{}</div></div>'.format(meeting.get('venue')), unsafe_allow_html=True)
    with col_st2:
        st.markdown('<div class="tech-panel border-accent-blue"><div class="data-label" style="color:#38bdf8; font-weight:800;">Date</div><div class="data-value" style="color:#ffffff; font-weight:800;">{}</div></div>'.format(meeting.get('date')), unsafe_allow_html=True)
    with col_st3:
        going_display = meeting.get('going') or 'GOOD'
        course_display = meeting.get('course') or ''
        if course_display and course_display not in going_display:
            cond_label = f"{going_display} ({course_display} Course)" if "COURSE" not in course_display.upper() else f"{going_display} ({course_display})"
        else:
            cond_label = going_display
        st.markdown('<div class="tech-panel border-accent-gold"><div class="data-label" style="color:#38bdf8; font-weight:800;">Track Conditions</div><div class="data-value" style="color:#ffffff; font-weight:800;">{}</div></div>'.format(cond_label), unsafe_allow_html=True)
    with col_st4:
        st.markdown('<div class="tech-panel border-accent-blue"><div class="data-label" style="color:#38bdf8; font-weight:800;">Weather</div><div class="data-value" style="color:#ffffff; font-weight:800;">{}</div></div>'.format(meeting.get('weather')), unsafe_allow_html=True)

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
                        
                        # Parse class_int to apply Class 5 Volatility Guard
                        class_str_frozen = race.get("class_dist", "")
                        class_int_frozen = 4
                        if "Class 1" in class_str_frozen: class_int_frozen = 1
                        elif "Class 2" in class_str_frozen: class_int_frozen = 2
                        elif "Class 3" in class_str_frozen: class_int_frozen = 3
                        elif "Class 4" in class_str_frozen: class_int_frozen = 4
                        elif "Class 5" in class_str_frozen: class_int_frozen = 5
                        elif "Group" in class_str_frozen or "G" in class_str_frozen: class_int_frozen = 0
                        
                        if class_int_frozen == 5:
                            df_runners['kelly_stake'] = df_runners['kelly_stake'] * 0.5
                            if 'confidence' in df_runners.columns:
                                df_runners['confidence'] = np.clip(df_runners['confidence'], 15, 74)
                        
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
                            # Keep core rankings completely stable and frozen based on model_prob so picks never jump around before post time
                            df_runners['gs_score'] = df_runners['model_prob'] * 100

                        # Dynamic win stake shift check on live odds update
                        if 'card_rank' in df_runners.columns:
                            p1_mask = df_runners['card_rank'] == 1
                            if p1_mask.any():
                                p1_idx = df_runners[p1_mask].index[0]
                                p1_o = float(df_runners.loc[p1_idx, 'win_odds'])
                                p1_p = float(df_runners.loc[p1_idx, 'model_prob'])
                                p1_live = (p1_o > 0) and (p1_o < 20.0)
                                p1_pass = p1_live and (p1_p * p1_o > 1.0)
                                
                                df_runners['win_stake_active'] = 0
                                if p1_pass:
                                    df_runners.loc[p1_idx, 'win_stake_active'] = 1
                                    df_runners.loc[p1_idx, 'primary_reason'] = f"Top GS Score ({df_runners.loc[p1_idx, 'gs_score']:.1f}) - WIN STAKE ACTIVE (Half Unit Win + Place)"
                                elif p1_live:
                                    df_runners.loc[p1_idx, 'primary_reason'] = f"Top GS Score ({df_runners.loc[p1_idx, 'gs_score']:.1f}) - Winning-horse pick / exotic key only — no win stake"
                                    # Pick 1 failed -> find best passing candidate among Picks 2-4
                                    p24_mask = df_runners['card_rank'].isin([2, 3, 4])
                                    p24_df = df_runners[p24_mask].copy()
                                    if not p24_df.empty:
                                        p24_pass = p24_df[(p24_df['win_odds'] > 0) & (p24_df['win_odds'] < 20.0) & (p24_df['model_prob'] * p24_df['win_odds'] > 1.0)].copy()
                                        if not p24_pass.empty:
                                            p24_pass['ev_mult'] = p24_pass['model_prob'] * p24_pass['win_odds']
                                            best_s = p24_pass.sort_values(by='ev_mult', ascending=False).iloc[0]
                                            df_runners.loc[df_runners['no'] == best_s['no'], 'win_stake_active'] = 1
                                            df_runners.loc[df_runners['no'] == best_s['no'], 'primary_reason'] = f"Shifted Win Stake (Pick {int(best_s['card_rank'])} - EV +{best_s.get('value_diff', 0):.3f})"
            
            if 'clean_name' not in df_runners.columns:
                df_runners['clean_name'] = df_runners['name'].str.upper().str.strip()
            race['processed_runners'] = df_runners
            
            # Add all runners to global pool for summaries
            for _, row in df_runners.iterrows():
                r_dict = row.to_dict()
                r_dict.update({"race_no": race.get("race_no")})
                global_best_bets.append(r_dict)
                
            # Parlay candidate is the Primary Pick of this race
            if 'is_primary' in df_runners.columns:
                race_picks_gs = df_runners.sort_values(by=['is_primary', 'gs_score'], ascending=[False, False])
            else:
                race_picks_gs = df_runners.sort_values(by='gs_score', ascending=False)
            if not race_picks_gs.empty:
                best_gs = race_picks_gs.iloc[0].to_dict()
                if len(race_picks_gs) > 1:
                    p2_dict = race_picks_gs.iloc[1].to_dict()
                    best_gs['p2_no'] = p2_dict.get('no')
                    best_gs['p2_name'] = p2_dict.get('name')
                    best_gs['p2_odds'] = float(p2_dict.get('win_odds', 20.0))
                    best_gs['p2_gs'] = float(p2_dict.get('gs_score', 0.0))
                class_str_frozen = str(race.get("class_dist", ""))
                best_gs.update({"race_no": race.get("race_no"), "class_dist": class_str_frozen})
                # Strictly veto volatile Class 5 races from All Up / Parlay multi-leg bankers
                if "class 5" not in class_str_frozen.lower():
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
            
            race_going = race.get('going', meeting.get('going', 'GOOD'))
            probs, df_runners = predict_probabilities(df_runners, venue=meeting.get('venue'), going=race_going, race_date=meeting.get('date'), race_class_int=class_int, track_type=race.get('track', 'TURF'))
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
        
        # Helper functions to safely extract series from df_runners
        def get_series(df, col, default=0.0):
            if col in df.columns:
                return pd.to_numeric(df[col], errors='coerce').fillna(default)
            return pd.Series(default, index=df.index)

        def get_str_series(df, col, default=''):
            if col in df.columns:
                return df[col].fillna(default).astype(str)
            return pd.Series(default, index=df.index)

        # Targeted Standout Boost Logic
        recent_pos = get_series(df_runners, 'recent_avg_pos', 7.0)
        recent_win = get_series(df_runners, 'recent_win_rate', 0.0)
        track_match = (get_str_series(df_runners, 'ST_vs_HV_pref', 'Neutral') == meeting.get('venue')).astype(int)
        going_match = (get_str_series(df_runners, 'last_form_going', 'Unknown') == race_going).astype(int)
        vet_issue = get_series(df_runners, 'prev_run_vet_finding', 0)
        class_drop = get_series(df_runners, 'class_diff', 0)
        
        # Super Standout condition: 
        is_super_standout = (recent_pos <= 3.5) & ((track_match == 1) | (going_match == 1)) & (vet_issue == 0)
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
        consensus = get_series(df_runners, 'consensus_score', 0)
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
            has_poly_form = (get_series(df_runners, 'has_overseas_form', 0) == 1) & (
                get_str_series(df_runners, 'last_form_going', '').str.upper().str.contains("POLY|SYNTH|AWT|STAND|TAPETA") |
                (get_series(df_runners, 'AWT_win_rate', 0) > 0) |
                (get_str_series(df_runners, 'AWT_vs_Turf_pref', '') == 'AWT')
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
            
        actual_weights = get_series(df_runners, 'actual_weight', 125)
        draws = get_series(df_runners, 'draw', 6)

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
        
        # Purton Total Boost Cap: Cap Purton at +2.0% total (elite_jockey_boost and jockey_trainer_boost must not stack past +2.0%)
        purton_total_boost = np.minimum(jockey_trainer_boost + elite_jockey_boost, 0.02)
        
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
            is_on_pace_crosser = (get_series(df_runners, 'avg_first_pos', 6.0) <= 3.5) | (recent_pos <= 3.5)
            eff_wt_extra = np.where(is_on_pace_crosser, base_wt_extra * 0.5, base_wt_extra)
            
            hv_c_course_penalty = base_draw_pen + eff_wt_extra
            hv_c_course_penalty = np.clip(hv_c_course_penalty, -0.06, 0.0)
            
            # Iron-Horse Class-Dropper Top-4 Consistency Rule (e.g. proven wide-draw/weight top-4 consistency dropping in class)
            is_iron_horse_dropper = (class_drop > 0) & (recent_pos <= 3.0) & (vet_issue == 0)
            hv_c_course_penalty = np.where(is_iron_horse_dropper, 0.0, hv_c_course_penalty)
            frontrunner_pace_penalty = np.where(is_iron_horse_dropper, 0.0, frontrunner_pace_penalty)
            standout_boost += np.where(is_iron_horse_dropper, 0.14, 0.0)
            
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

        # Sha Tin Straight 1000m Outside Rail Draw Bias
        is_st_straight_1000 = is_st and (distance == 1000) and ("ALL WEATHER" not in race_track_type and "AWT" not in race_track_type)
        st_1000_draw_boost = np.where(is_st_straight_1000 & (draws >= 10), 0.027, 0.0)
        st_1000_draw_penalty = np.where(is_st_straight_1000 & (draws <= 4), -0.025, 0.0)

        # Sha Tin 1200m-1600m Bend Draw Bias
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
        horse_ratings = get_series(df_runners, 'rtg', 40) if 'rtg' in df_runners.columns else get_series(df_runners, 'horse_rating', 40)
        median_rtg = horse_ratings.median()
        rating_dom_boost = np.where((horse_ratings - median_rtg >= 15) & (recent_pos <= 4.0) & (vet_issue == 0), 0.05, 0.0)

        # Non-First Start for New Trainer with Good Rating (1.5% Boost)
        good_rating_thresh = 38 if class_int == 5 else 50
        is_good_rating = (get_series(df_runners, 'rtg', 40) >= good_rating_thresh) | (get_series(df_runners, 'horse_rating', 40) >= good_rating_thresh)
        is_settled_stable_horse = is_good_rating & (recent_pos <= 6.0) & (vet_issue == 0) & (~is_debutant)
        trainer_transfer_2nd_up_boost = np.where(is_settled_stable_horse, 0.015, 0.0)

        # Fresh Horses Distance Fitness Sweet Spot (within 250m of optimal distance with form) (1.5% Boost)
        is_fit_fresh = (recent_pos <= 5.0) & (vet_issue == 0) & (
            (get_series(df_runners, 'distance_win_rate', 0) > 0) | 
            (distance >= 1400) |
            (get_series(df_runners, 'days_since_last_run', 0) >= 28)
        )
        fresh_distance_fitness_boost = np.where(is_fit_fresh, 0.015, 0.0)

        # Recent Throat Surgery Recovery Boost (+3.5% Boost with verified strong trial)
        has_throat_surgery = df_runners['last_comment'].str.contains('tieback|tie-back|throat|epiglottic|wind op', case=False, na=False)
        throat_surgery_boost = np.where(has_throat_surgery & has_strong_trial, 0.035, 0.0)

        # Optimal Body Weight Condition Zone (within 15 lbs of historical peak / winning weight) (+1.0% Boost)
        declared_weights = get_series(df_runners, 'declared_weight', 1100)
        opt_body_weights = get_series(df_runners, 'latest_body_weight', np.nan)
        is_optimal_weight_zone = (opt_body_weights.notna()) & (opt_body_weights > 800) & (np.abs(declared_weights - opt_body_weights) <= 15)
        optimal_weight_boost = np.where(is_optimal_weight_zone, 0.01, 0.0)

        # Disguised Form & Weight-Carrying Resilience Cushion (Sha Tin only, 0.0% at Happy Valley)
        is_resilient_weight_carrier = (actual_weights >= 130) & (draws >= 8) & (recent_pos <= 6.0) & (vet_issue == 0) & (
            (get_series(df_runners, 'avg_first_pos', 6.0) >= 7.0) | (get_series(df_runners, 'recent_win_rate', 0) > 0) | (get_series(df_runners, 'gear_win_rate', 0) > 0.10)
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
        days_since = get_series(df_runners, 'days_since_last_run', 0)
        is_second_up_fitness = (days_since >= 14) & (days_since <= 35) & (recent_pos <= 6.0) & (vet_issue == 0) & (~is_debutant)
        second_up_fitness_boost = np.where(is_second_up_fitness, 0.02, 0.0)

        # Cumulative Closer Boost Ceiling: Cap all stacked closer multipliers at +2.0% max at Happy Valley, +3.5% at Sha Tin
        raw_closer_boost = closer_pace_boost + late_closer_boost + st_closer_boost + finisher_win_conversion_boost
        closer_cap = 0.02 if is_hv else 0.035
        total_closer_boost = np.minimum(raw_closer_boost, closer_cap)

        # Stacked Geometry Penalty Cap: max -10.0%
        stacked_geom_pen = np.clip(hv_c_course_penalty + st_1000_draw_penalty + st_wide_draw_penalty, -0.10, 0.0)

        multiplier = 1.0 + standout_boost + rating_dom_boost + consensus_boost + false_fav_penalty + debutant_penalty + first_time_gear_boost + on_speed_wet_boost + yielding_form_boost + polytrack_awt_boost + total_closer_boost + frontrunner_pace_penalty + closer_pace_penalty + lone_speed_boost + purton_total_boost + hv_c_course_boost + stacked_geom_pen + st_1000_draw_boost + st_inside_draw_boost + fownes_hv_boost + trial_boost + trial_penalty + trainer_transfer_2nd_up_boost + second_up_fitness_boost + fresh_distance_fitness_boost + throat_surgery_boost + lightweight_agility_boost + optimal_weight_boost + weight_resilience_boost + surface_switch_trial_boost

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
        has_live_price = (df_runners['win_odds'] > 0) & (df_runners['win_odds'] < 20.0)
        passes_price = has_live_price & (df_runners['model_prob'] * df_runners['win_odds'] > 1.0)
        f = np.where((b > 0) & passes_price, (b * p - q) / b, 0)
        df_runners['kelly_stake'] = np.clip(f * 0.25, 0, 1) 
        
        # Apply Class 5 Volatility Guard: scale down recommended Kelly stakes on low-grade Class 5 races to protect capital
        if class_int == 5:
            df_runners['kelly_stake'] = df_runners['kelly_stake'] * 0.5
            
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

        # Scale to a realistically solid 15-85% range. Round to nearest integer.
        p_min = df_runners['model_prob'].min()
        p_max = df_runners['model_prob'].max()
        if p_max > p_min:
            df_runners['confidence'] = (15.0 + ((df_runners['model_prob'] - p_min) / (p_max - p_min)) * 70).round(0).astype(int)
        else:
            df_runners['confidence'] = 50

        # Class 5 Volatility Guard: Cap confidence to maximum 74% in volatile Class 5 races
        if class_int == 5:
            df_runners['confidence'] = np.clip(df_runners['confidence'], 15, 74)

        # MANDATES & 5-HORSE SELECTION CARD ARCHITECTURE:
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
        p1_recent_pos = float(pd.to_numeric(p1.get('recent_avg_pos', 7.0), errors='coerce'))
        p1_is_crosser = (p1_first_pos <= 3.5) or (p1_recent_pos <= 3.5)
        p1_live = (p1_odds > 0) and (p1_odds < 20.0)
        p1_passes_val = p1_live and (p1_prob * p1_odds > 1.0)
        
        # Check sprint wide+heavy split rule:
        is_sprint = (distance <= 1200)
        is_p1_wide_heavy = is_hv and is_sprint and (p1_draw >= 9) and (p1_wt >= 132)
        
        shifted_win_runner = None
        shifted_from_rank = None
        
        # Helper to find best candidate among Picks 2-4 that passes price test (model_prob * decimal_odds > 1.0)
        def get_best_p24_shifted():
            p24_cands = [(p2, 2), (p3, 3), (p4, 4)]
            valid = []
            for cand, r_idx in p24_cands:
                if cand is not None:
                    c_odds = float(cand.get('win_odds', 20.0))
                    c_prob = float(cand.get('model_prob', 0.0))
                    if (c_odds > 0) and (c_odds < 20.0) and (c_prob * c_odds > 1.0):
                        valid.append((cand, r_idx, c_prob * c_odds))
            if valid:
                valid.sort(key=lambda x: x[2], reverse=True)
                return valid[0][0], valid[0][1]
            return None, None
            
        if not p1_live:
            # Pre-market placeholder odds (e.g. 20.0) -> Awaiting live odds
            p1_passes_test = False
            p1_status = "Winning-horse pick / exotic key only — awaiting live odds (pre-market placeholder 20.0)"
            df_runners.loc[df_runners['no'] == p1['no'], 'kelly_stake'] = 0.0
            shifted_win_runner = None
            
        elif is_p1_wide_heavy and (not p1_is_crosser):
            # Condition 1: Wide topweight, NOT an on-pace crosser -> Win stake LOCKED
            p1_passes_test = False
            p1_status = "Winning-horse pick / exotic key only — no win stake. Wide topweight, not an on-pace crosser."
            df_runners.loc[df_runners['no'] == p1['no'], 'kelly_stake'] = 0.0
            shifted_win_runner, shifted_from_rank = get_best_p24_shifted()
                
        elif is_p1_wide_heavy and p1_is_crosser:
            # Condition 2: Wide topweight, IS an on-pace crosser -> Speed exception, Half-Unit Win
            if p1_passes_val:
                p1_passes_test = True
                p1_status = f"WIN STAKE ACTIVE (Half-Unit Win + Place — Crosser Draw {p1_draw}, {int(p1_wt)}lb)"
                df_runners.loc[df_runners['no'] == p1['no'], 'kelly_stake'] = df_runners.loc[df_runners['no'] == p1['no'], 'kelly_stake'] * 0.5
            else:
                p1_passes_test = False
                p1_status = "Winning-horse pick / exotic key only — no win stake"
                df_runners.loc[df_runners['no'] == p1['no'], 'kelly_stake'] = 0.0
                shifted_win_runner, shifted_from_rank = get_best_p24_shifted()
        else:
            # Standard runner (including Sha Tin races)
            if p1_passes_val:
                p1_passes_test = True
                p1_status = "WIN STAKE ACTIVE (Half Unit Win + Place)"
            else:
                p1_passes_test = False
                p1_status = "Winning-horse pick / exotic key only — no win stake"
                df_runners.loc[df_runners['no'] == p1['no'], 'kelly_stake'] = 0.0
                shifted_win_runner, shifted_from_rank = get_best_p24_shifted()

        # Assign card rank (1 to 5)
        card_picks = [p1, p2, p3, p4, p5]
        df_runners['card_rank'] = 99
        for rank_idx, runner_obj in enumerate(card_picks):
            if runner_obj is not None:
                df_runners.loc[df_runners['no'] == runner_obj['no'], 'card_rank'] = rank_idx + 1

        df_runners['is_primary'] = (df_runners['no'] == p1['no']).astype(int)
        df_runners['primary_reason'] = np.where(df_runners['no'] == p1['no'], f"Top GS Score ({p1['gs_score']:.1f}) - {p1_status}", "")
        df_runners['win_stake_active'] = np.where((df_runners['no'] == p1['no']) & p1_passes_test, 1, 0)
        
        # If win stake shifted to another runner in Picks 2-4, flag it
        if shifted_win_runner is not None:
            df_runners.loc[df_runners['no'] == shifted_win_runner['no'], 'win_stake_active'] = 1
            df_runners.loc[df_runners['no'] == shifted_win_runner['no'], 'primary_reason'] = f"Shifted Win Stake (Pick {shifted_from_rank} - EV +{shifted_win_runner['value_diff']:.3f})"

        # Add historical records
        if 'clean_name' not in df_runners.columns:
            df_runners['clean_name'] = df_runners['name'].str.upper().str.strip()
            
        vet_notes = []
        steward_notes = []
        photo_hist = []
        
        for _, row in df_runners.iterrows():
            c_name = row['clean_name']
            comment = last_comments.get(c_name, '').strip()
            raw_vet_note = str(row.get('latest_vet_note', '')).strip()
            raw_photo = str(row.get('photo_finish_hist', '')).strip()
            raw_summary = str(row.get('last_run_summary', '')).strip()
            
            tonight_gear = str(row.get('horse_gear', '')).strip().upper()
            if tonight_gear in ['', '-', '--', 'NAN', 'NONE']:
                tonight_gear = ''
            horse_win_gears = winning_gears.get(c_name, set())
            is_gear_matched = (tonight_gear in horse_win_gears) or (tonight_gear == '' and '' in horse_win_gears)
            
            # 1. Vet Findings
            if raw_vet_note and raw_vet_note.lower() not in ['', 'nan', 'none', 'no findings']:
                vet = raw_vet_note
            elif comment and "(" in comment and ")" in comment:
                matches = re.findall(r'\((.*?)\)', comment)
                last_match = matches[-1] if matches else ""
                vet = last_match if ("vet" in last_match.lower() or "finding" in last_match.lower()) else "No Active Findings"
            elif pd.to_numeric(row.get('prev_run_vet_finding', 0), errors='coerce') == 1:
                vet = "Passed Official HKJC Vet Exam"
            else:
                vet = "No Active Findings"
                
            # 2. Photo Finish History
            if raw_photo in ["✅ Yes", "❌ No", "Debutant"]:
                photo = raw_photo
            elif comment:
                photo = "✅ Yes" if any(x in comment.lower() for x in ["photo", "nose", "short head"]) else "❌ No"
            else:
                photo = "❌ No"
                
            # 3. Steward / Form Notes
            mem_entry = horse_memory.get(c_name, {}) if isinstance(horse_memory, dict) else {}
            mem_runs = mem_entry.get('runs', []) if isinstance(mem_entry, dict) else []
            mem_snippet = ""
            if mem_runs and isinstance(mem_runs[0], dict):
                flags = mem_runs[0].get('incident_flags', [])
                if flags and isinstance(flags[0], dict):
                    mem_snippet = str(flags[0].get('snippet', '')).strip()
                    
            if comment:
                steward = comment
            elif mem_snippet:
                steward = f"{mem_snippet} | {raw_summary}" if (raw_summary and raw_summary.lower() not in ['', 'nan', 'none']) else mem_snippet
            elif raw_summary and raw_summary.lower() not in ['', 'nan', 'none']:
                steward = raw_summary
            else:
                steward = "Clear Record"
                
            if row.get('has_overseas_form') == 1 and is_gear_matched:
                steward = f"Overseas Form + Proven HK Winning Gear | {steward}"
                
            vet_notes.append(vet)
            steward_notes.append(steward)
            photo_hist.append(photo)

                
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
            
        # Parlay candidate is Pick 1 of this race (strictly vetoing volatile Class 5 races)
        best_gs = p1.to_dict()
        if p2 is not None:
            best_gs['p2_no'] = p2.get('no')
            best_gs['p2_name'] = p2.get('name')
            best_gs['p2_odds'] = float(p2.get('win_odds', 20.0))
            best_gs['p2_gs'] = float(p2.get('gs_score', 0.0))
        best_gs.update({"race_no": race.get("race_no"), "primary_reason": p1_status, "class_dist": class_str})
        if "class 5" not in str(class_str).lower():
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
                        "link": format_horse_link(row, prefix="#"),
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
    
    dual_staking_bets = []
    for r in races:
        if 'processed_runners' not in r: continue
        df_p = r['processed_runners']
        if len(df_p) > 4:
            df_p_sorted = df_p.sort_values(by='gs_score', ascending=False).reset_index(drop=True)
            p1_match = df_p[df_p['card_rank'] == 1]
            p1_sel = p1_match.iloc[0] if not p1_match.empty else df_p_sorted.iloc[0]
            p5_match = df_p[df_p['card_rank'] == 5]
            p5_sel = p5_match.iloc[0] if not p5_match.empty else (df_p_sorted.iloc[4] if len(df_p_sorted) > 4 else df_p_sorted.iloc[-1])
            dual_staking_bets.append({
                "race_no": r.get("race_no"),
                "p1_no": p1_sel['no'],
                "p1_name": p1_sel['name'],
                "p1_link": format_horse_link(p1_sel, prefix="#"),
                "p1_odds": float(p1_sel.get('win_odds', 20.0)),
                "p1_status": p1_sel.get('primary_reason', ''),
                "p5_no": p5_sel['no'],
                "p5_name": p5_sel['name'],
                "p5_link": format_horse_link(p5_sel, prefix="#"),
                "p5_odds": float(p5_sel.get('win_odds', 20.0)),
                "p5_ev": float(p5_sel.get('value_diff', 0.0))
            })

    with st.expander("Macro Insights & Global Best Bets", expanded=True):
        if top_pick_today:
            col_bb1, col_bb2 = st.columns(2)
            with col_bb1:
                st.markdown(clean_html(f'''
                <div class="tech-panel pick-card-1" style="background: linear-gradient(145deg, rgba(42, 6, 13, 0.96), rgba(24, 3, 7, 0.98)); min-height: 160px; {check_highlight(top_pick_today, search_term)}">
                    {get_match_badge(top_pick_today, search_term)}
                    <div class="data-label" style="color:#38bdf8; font-size:0.90rem; font-weight:800;">🏆 HIGHEST EXPECTED VALUE (EV) SELECTION</div>
                    <div class="data-value" style="font-size:1.8rem; font-family:'Montserrat'; font-weight:800; margin-top: 5px; color:#ffffff;">Race {top_pick_today['race_no']} – {format_horse_link(top_pick_today, '#')}</div>
                    <div class="data-value" style="font-size:1.0rem; color:#cbd5e1; margin-top: 5px;">Live Odds: <b style="color:#38bdf8;">{top_pick_today['win_odds']:.1f}</b> &nbsp;|&nbsp; AI Confidence: <b style="color:#38bdf8;">{top_pick_today['confidence']}%</b></div>
                </div>
                '''), unsafe_allow_html=True)
            with col_bb2:
                top_gs_pick = global_best_bets_sorted_by_gs[0] if global_best_bets_sorted_by_gs else None
                if top_gs_pick:
                    st.markdown(clean_html(f'''
                    <div class="tech-panel pick-card-1" style="background: linear-gradient(145deg, rgba(42, 6, 13, 0.96), rgba(24, 3, 7, 0.98)); min-height: 160px; {check_highlight(top_gs_pick, search_term)}">
                        {get_match_badge(top_gs_pick, search_term)}
                        <div class="data-label" style="color:#38bdf8; font-size:0.90rem; font-weight:800;">💎 AI STRONGEST CONFIDENCE (BEST BET)</div>
                        <div class="data-value" style="font-size:1.8rem; font-family:'Montserrat'; font-weight:800; margin-top: 5px; color:#ffffff;">Race {top_gs_pick['race_no']} – {format_horse_link(top_gs_pick, '#')}</div>
                        <div class="data-value" style="font-size:1.0rem; color:#cbd5e1; margin-top: 5px;">Live Odds: <b style="color:#38bdf8;">{top_gs_pick['win_odds']:.1f}</b> &nbsp;|&nbsp; AI Confidence: <b style="color:#38bdf8;">{top_gs_pick['confidence']}%</b></div>
                    </div>
                    '''), unsafe_allow_html=True)
            parlay_str = " + ".join([f"R{bb.get('race_no')} " + format_horse_link(bb, "#") for bb in parlay_sorted[:3]])
            st.markdown(f"<div style='margin-top:12px; font-family:\"Inter\"; font-size:1.15rem; color:#f1f5f9;'><b>Optimized Multi-Leg Sequence (Excl. Class 5):</b> <span style='color:#38bdf8; font-weight:800;'>{parlay_str}</span></div>", unsafe_allow_html=True)
            if len(parlay_sorted) >= 2:
                b1 = parlay_sorted[0]
                b2 = parlay_sorted[1]

                def get_leg_bet_type(runner):
                    ev = float(runner.get('value_diff', 0.0))
                    odds = float(runner.get('win_odds', 20.0))
                    reason = str(runner.get('primary_reason', ''))
                    win_active = bool(runner.get('win_stake_active', 0)) or ('WIN STAKE ACTIVE' in reason)
                    p2_no = runner.get('p2_no')
                    p2_name = runner.get('p2_name')
                    p2_gs = float(runner.get('p2_gs', 0.0))
                    p1_gs = float(runner.get('gs_score', 0.0))
                    combined_gs = p1_gs + p2_gs
                    r_link = format_horse_link(runner, "#")

                    if win_active and ev >= 0.035:
                        return {
                            "pool": "WIN (獨贏)",
                            "badge_bg": "#15803d",
                            "pick": r_link,
                            "odds_label": f"{odds:.1f}",
                            "rationale": f"High Expected Value (+{ev:.3f} EV) & dominant win conversion"
                        }
                    elif p2_no and combined_gs >= 36.0:
                        p2_link = format_horse_link({'no': p2_no, 'name': p2_name}, "#")
                        return {
                            "pool": "QUINELLA (連贏 Q)",
                            "badge_bg": "#b45309",
                            "pick": f"{r_link} + {p2_link}",
                            "odds_label": f"Q Box ({odds:.1f} / {runner.get('p2_odds', 0):.1f})",
                            "rationale": f"1-2 Lock: Combined GS Score {combined_gs:.1f} across top two runners"
                        }
                    else:
                        est_place = max(1.3, round(1.0 + (odds - 1.0) * 0.28, 1))
                        return {
                            "pool": "PLACE (位置)",
                            "badge_bg": "#0284c7",
                            "pick": r_link,
                            "odds_label": f"Est. ~{est_place:.1f}",
                            "rationale": f"Top GS Score ({p1_gs:.1f}) podium anchor (>80% top-3 safety buffer)"
                        }

                l1 = get_leg_bet_type(b1)
                l2 = get_leg_bet_type(b2)

                st.markdown(clean_html(f'''
                <div style="margin-top:10px; padding: 16px 20px; background: linear-gradient(145deg, rgba(38, 5, 12, 0.95), rgba(20, 3, 6, 0.98)); border-radius: 10px; border: 1.5px solid rgba(56, 189, 248, 0.55); font-family:'Inter'; color:#f8fafc; box-shadow: 0 6px 18px rgba(0,0,0,0.5);">
                    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; margin-bottom:8px;">
                        <span style="color:#38bdf8; font-family:'Montserrat'; font-weight:800; font-size:1.15rem; letter-spacing:0.5px;">🎯 AI-CALCULATED 2x3 ALL UP (過關 2串3 BANKER)</span>
                        <span style="font-size:0.80rem; background:rgba(56, 189, 248, 0.15); border:1px solid #38bdf8; border-radius:4px; padding:2px 8px; color:#38bdf8; font-weight:700;">CROSS-POOL INTELLIGENCE</span>
                    </div>
                    <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:12px; margin-top:8px;">
                        <div style="background:rgba(255,255,255,0.04); border-radius:8px; padding:10px 14px; border-left:3px solid {l1['badge_bg']};">
                            <div style="font-size:0.80rem; color:#94a3b8; font-weight:700;">🏛️ LEG 1 BANKER (Race {b1.get('race_no')})</div>
                            <div style="margin-top:2px; font-size:1.05rem; font-weight:800; color:#ffffff;">
                                <span style="background:{l1['badge_bg']}; color:#ffffff; font-size:0.75rem; font-weight:800; padding:2px 6px; border-radius:4px; vertical-align:middle; margin-right:4px;">{l1['pool']}</span>
                                {l1['pick']} <span style="color:#38bdf8;">({l1['odds_label']})</span>
                            </div>
                            <div style="font-size:0.80rem; color:#cbd5e1; margin-top:4px;"><i>💡 {l1['rationale']}</i></div>
                        </div>
                        <div style="background:rgba(255,255,255,0.04); border-radius:8px; padding:10px 14px; border-left:3px solid {l2['badge_bg']};">
                            <div style="font-size:0.80rem; color:#94a3b8; font-weight:700;">🥈 LEG 2 PARTNER (Race {b2.get('race_no')})</div>
                            <div style="margin-top:2px; font-size:1.05rem; font-weight:800; color:#ffffff;">
                                <span style="background:{l2['badge_bg']}; color:#ffffff; font-size:0.75rem; font-weight:800; padding:2px 6px; border-radius:4px; vertical-align:middle; margin-right:4px;">{l2['pool']}</span>
                                {l2['pick']} <span style="color:#38bdf8;">({l2['odds_label']})</span>
                            </div>
                            <div style="font-size:0.80rem; color:#cbd5e1; margin-top:4px;"><i>💡 {l2['rationale']}</i></div>
                        </div>
                    </div>
                    <div style="margin-top:10px; padding-top:8px; border-top:1px solid rgba(255,255,255,0.08); font-size:0.85rem; color:#94a3b8; display:flex; flex-wrap:wrap; gap:16px;">
                        <span>🛡️ <b>Safe Option (PLACE 2x3):</b> R{b1.get('race_no')} #{b1.get('no')} Pl × R{b2.get('race_no')} #{b2.get('no')} Pl</span>
                        <span>⚡ <b>AI Optimal:</b> R{b1.get('race_no')} ({l1['pool']}) × R{b2.get('race_no')} ({l2['pool']})</span>
                        <span>🚀 <b>Alpha Option (WIN 2x3):</b> R{b1.get('race_no')} #{b1.get('no')} Win ({b1.get('win_odds', 0):.1f}) × R{b2.get('race_no')} #{b2.get('no')} Win ({b2.get('win_odds', 0):.1f})</span>
                    </div>
                </div>
                '''), unsafe_allow_html=True)
            
            if dual_staking_bets:
                st.markdown("<div style='margin-top:15px; font-family:\"Montserrat\"; font-weight:800; font-size:1.15rem; color:#38bdf8;'>🐎 RECOMMENDED DUAL-STAKING BETS (WIN/PLACE)</div>", unsafe_allow_html=True)
                dual_html = '<div style="display:flex; flex-wrap:wrap; gap:10px; margin-top:8px;">'
                for bet in dual_staking_bets:
                    dual_html += clean_html(f'''
                    <div style="background: linear-gradient(145deg, rgba(38, 5, 12, 0.95), rgba(20, 3, 6, 0.98)); padding: 12px 18px; border-radius: 8px; border: 1.5px solid rgba(56, 189, 248, 0.45); font-size:0.95rem; color:#f8fafc; line-height:1.5; min-width: 250px; box-shadow: 0 4px 14px rgba(0,0,0,0.4);">
                        <b style="color:#38bdf8;">Race {bet['race_no']} Bet Selection:</b><br>
                        🎯 Anchor (Rank 1): <span style="color:#ffffff; font-weight:800;">{bet['p1_link']}</span> (<span style="color:#38bdf8; font-weight:700;">{bet['p1_odds']:.1f}</span>)<br>
                        💣 Sleeper (Rank 5): <span style="color:#38bdf8; font-weight:800;">{bet['p5_link']}</span> (<span style="color:#38bdf8; font-weight:700;">{bet['p5_odds']:.1f}</span>)
                    </div>
                    ''')
                dual_html += '</div>'
                st.markdown(dual_html, unsafe_allow_html=True)
            
            # Display Steam Alerts inside expander
            if steam_alerts:
                steam_html = '<div style="margin-top:20px; font-family:\'Montserrat\'; font-weight:800; font-size:1.1rem; color:#38bdf8; letter-spacing:0.5px;">⚡ LIVE MARKET STEAM ALERTS (SMART MONEY ACTION)</div>'
                steam_html += '<div style="display:flex; flex-wrap:wrap; gap:10px; margin-top:8px;">'
                sorted_steam = sorted(steam_alerts, key=lambda x: x['pct'])
                for alert in sorted_steam[:6]: # Show top 6
                    pct_str = f"{alert['pct'] * 100:.0f}%"
                    steam_html += clean_html(f'''
                    <div style="background: linear-gradient(145deg, rgba(38, 5, 12, 0.95), rgba(20, 3, 6, 0.98)); padding: 12px 18px; border-radius: 8px; border: 1.5px solid rgba(56, 189, 248, 0.5); font-size:0.95rem; color:#f8fafc; line-height:1.5; box-shadow: 0 4px 14px rgba(0,0,0,0.4);">
                        <b style="color:#ffffff;">R{alert['race_no']} {alert['link']}</b><br>
                        <span style="color:#38bdf8; font-weight:800;">Steam: {pct_str}</span> (<span style="color:#cbd5e1;">{alert['base']:.1f} → <b style="color:#38bdf8;">{alert['curr']:.1f}</b></span>) | <i style="color:#94a3b8;">{alert['jockey']}</i>
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
                return f' <span style="background:linear-gradient(135deg, #0284c7, #38bdf8); color:#ffffff; padding:2px 7px; border-radius:4px; font-size:0.75rem; font-weight:bold; vertical-align:middle; box-shadow: 0 0 8px rgba(56,189,248,0.5);">⚡ STEAM {pct*100:.0f}%</span>'
            elif pct > 0.25:
                return f' <span style="background:#1e293b; color:#94a3b8; border:1px solid rgba(148,163,184,0.3); padding:2px 7px; border-radius:4px; font-size:0.75rem; font-weight:bold; vertical-align:middle;">💨 DRIFT +{pct*100:.0f}%</span>'
        return ''

    col_hdr, col_flt = st.columns([1.5, 1])
    with col_hdr:
        st.markdown("<h3 style='font-family:\"Montserrat\"; letter-spacing:1px; color:#38bdf8; font-weight:800; margin-top:5px; text-shadow: 0 2px 10px rgba(56,189,248,0.3);'>AI RACE PREDICTIONS</h3>", unsafe_allow_html=True)
    with col_flt:
        race_options = ["All Races"] + [f"Race {r.get('race_no')}" for r in races]
        selected_race_view = st.selectbox("🏇 Jump to Specific Race", race_options, index=0)

    for race in races:
        if not race.get('runners'): continue
        race_num_label = f"Race {race.get('race_no')}"
        if selected_race_view != "All Races" and selected_race_view != race_num_label:
            continue
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
            <div style="font-family:'Montserrat'; font-size:1.6rem; font-weight:800; color:#38bdf8; margin-top:30px; margin-bottom:8px; text-shadow: 0 2px 8px rgba(0,0,0,0.5);">
                RACE {race.get("race_no", "")} – <span style="font-family:'Inter'; font-weight:700; font-size:1.2rem; color:#ffffff;">{class_dist}</span>
            </div>
            <div style="display:flex; gap: 15px; margin-bottom:15px; flex-wrap:wrap;">
                <div style="background: linear-gradient(145deg, rgba(38, 5, 12, 0.95), rgba(20, 3, 6, 0.98)); padding: 8px 16px; border-radius: 8px; border: 1.5px solid rgba(56, 189, 248, 0.45); box-shadow: 0 4px 14px rgba(0,0,0,0.4);">
                    <span style="font-size:0.85rem; color:#38bdf8; text-transform:uppercase; font-weight:700;">⏱️ Standard Time:</span>
                    <span style="font-size:0.95rem; color:#ffffff; font-weight:800; margin-left:5px;">{std_time}</span>
                </div>
                <div style="background: linear-gradient(145deg, rgba(38, 5, 12, 0.95), rgba(20, 3, 6, 0.98)); padding: 8px 16px; border-radius: 8px; border: 1.5px solid rgba(56, 189, 248, 0.45); box-shadow: 0 4px 14px rgba(0,0,0,0.4);">
                    <span style="font-size:0.85rem; color:#38bdf8; text-transform:uppercase; font-weight:700;">🏆 Course Record:</span>
                    <span style="font-size:0.95rem; color:#ffffff; font-weight:800; margin-left:5px;">{rec_time} ({rec_horse})</span>
                </div>
            </div>
            '''), unsafe_allow_html=True)
            
            # Show Track Bias Warning Alerts
            if "ALL WEATHER" in race_track_type or "AWT" in race_track_type:
                if "SEALED" in race_going_type:
                    st.markdown(clean_html('''
                    <div style="background: linear-gradient(145deg, rgba(45, 12, 8, 0.95), rgba(25, 4, 4, 0.98)); padding: 12px 18px; border-radius: 8px; border: 1.5px dashed #f59e0b; margin-bottom: 15px; font-size:0.95rem; color:#fef3c7; font-family:'Inter', sans-serif; box-shadow: 0 4px 14px rgba(0,0,0,0.4);">
                        ⚡ <b style="color:#f59e0b;">TRACK BIAS ALERT (AWT SEALED)</b>: The dirt track is compacted/sealed due to wet weather. Expect strong speed bias favoring low draws and on-speed runners.
                    </div>
                    '''), unsafe_allow_html=True)
            else:
                if race_going_type in ["YIELDING", "SOFT", "HEAVY"]:
                    st.markdown(clean_html(f'''
                    <div style="background: linear-gradient(145deg, rgba(12, 28, 48, 0.95), rgba(6, 15, 28, 0.98)); padding: 12px 18px; border-radius: 8px; border: 1.5px dashed #38bdf8; margin-bottom: 15px; font-size:0.95rem; color:#e0f2fe; font-family:'Inter', sans-serif; box-shadow: 0 4px 14px rgba(0,0,0,0.4);">
                        🌧️ <b style="color:#38bdf8;">TRACK BIAS ALERT (WET TURF - {race_going_type})</b>: Turf track has degraded. On-speed runners (leaders) are highly favored; off-pace closers may struggle to make ground.
                    </div>
                    '''), unsafe_allow_html=True)
            
            # Show dynamic pace summaries
            speed_count = (df_runners['avg_first_pos'] <= 3.5).sum()
            if speed_count >= 4:
                pace_summary = "⚡ <b style='color:#38bdf8;'>HIGH PACE</b>: We assess this race to have a lot of speed. Front-runners may tire late, but they can still hold on based on form. Be wary of back-markers unless they have elite acceleration."
                border_color = "rgba(56, 189, 248, 0.5)"
            elif speed_count <= 1:
                pace_summary = "🐌 <b style='color:#38bdf8;'>ON SPEED</b>: Slow pace expected. Speed bias favors front-runners/leaders who can take off. Closers and late finishers may struggle to make up ground."
                border_color = "rgba(56, 189, 248, 0.5)"
            else:
                pace_summary = "⚖️ <b style='color:#cbd5e1;'>GOOD PACE</b>: Balanced pace expected. Fair conditions; both speed horses and late finishers have equal opportunity based on form and odds."
                border_color = "rgba(56, 189, 248, 0.3)"
                
            st.markdown(clean_html(f'''
            <div style="background: linear-gradient(145deg, rgba(38, 5, 12, 0.95), rgba(20, 3, 6, 0.98)); padding: 12px 18px; border-radius: 8px; border: 1.5px solid {border_color}; margin-bottom: 15px; font-size:0.95rem; color:#f8fafc; font-family:'Inter', sans-serif; box-shadow: 0 4px 14px rgba(0,0,0,0.4);">
                {pace_summary}
            </div>
            '''), unsafe_allow_html=True)
            
            # Open Contest / Class 5 Volatility Alert
            is_class_5 = (c_val == "5") or ("Class 5" in class_dist)
            sorted_probs = df_runners['model_prob'].sort_values(ascending=False).values if 'model_prob' in df_runners.columns and len(df_runners) > 0 else []
            top_prob = sorted_probs[0] if len(sorted_probs) > 0 else 0.20
            # Only trigger in actual Class 5 races or extreme dead-heats where top probability is below 11%
            is_open_contest = is_class_5 or (top_prob < 0.11)
            if is_open_contest:
                contest_reason = "Class 5 contest with compressed ratings and historically volatile outcomes." if is_class_5 else "Wide-open field with tightly compressed win probabilities."
                st.markdown(clean_html(f'''
                <div style="background: linear-gradient(145deg, rgba(45, 12, 8, 0.95), rgba(25, 4, 4, 0.98)); padding: 12px 18px; border-radius: 8px; border: 1.5px dashed #f59e0b; margin-bottom: 15px; font-size:0.95rem; color:#fef3c7; font-family:'Inter', sans-serif; box-shadow: 0 4px 14px rgba(0,0,0,0.4);">
                    ⚠️ <b style="color:#f59e0b;">HIGH VOLATILITY / OPEN CONTEST ALERT</b>: {contest_reason} AI confidence is guarded. We recommend conservative single-win stakes and prioritizing Dual-Staking (Win/Place) and exotic structures (Quinella Place / Tierce).
                </div>
                '''), unsafe_allow_html=True)

            # ⚡ Tactical Edge & Outlier Radar (Stewards, Vet, First-Up, Trial Outliers)
            trouble_keywords = ['interference', 'blocked', 'held up', 'checked', 'crowded', 'hampered', 'stumble', 'clipt', 'clip ', 'check ', 'wide without cover', 'hung out', 'slow to begin', 'denied a clear run', 'untested']
            
            tactical_radar_items = []
            for _, r_item in df_runners.iterrows():
                r_no = r_item.get('no')
                r_name = str(r_item.get('name', '')).strip().upper()
                r_item_link = format_horse_link(r_item, '#')
                r_comment = str(last_comments.get(r_name, '')).strip()
                r_vet_status = pd.to_numeric(r_item.get('prev_run_vet_finding', 0), errors='coerce')
                r_vet_notes = str(r_item.get('vet_findings', '')).strip()
                r_days_off = pd.to_numeric(r_item.get('days_since_last_run', 0), errors='coerce')
                
                # 1. Stewards Trouble / Hidden Run
                if any(kw in r_comment.lower() for kw in trouble_keywords):
                    clean_snippet = ' '.join(r_comment.split())
                    if len(clean_snippet) > 85: clean_snippet = clean_snippet[:85] + '...'
                    tactical_radar_items.append({
                        'type': '🚨 STEWARDS INCIDENT / HIDDEN RUN',
                        'color': '#ef4444',
                        'bg': 'rgba(239, 68, 68, 0.10)',
                        'border': 'rgba(239, 68, 68, 0.4)',
                        'text': f"<b>{r_item_link}</b>: {clean_snippet}"
                    })
                    
                # 2. Specific Medical / Veterinary Recovery Tag
                med_text = (str(r_comment) + ' ' + str(r_vet_notes)).lower()
                specific_vet_tag = None
                detail_note = "Officially recorded on file"
                if 'tieback' in med_text or 'tie-back' in med_text or 'throat' in med_text or 'epiglottic' in med_text:
                    specific_vet_tag = 'THROAT SURGERY'
                    detail_note = "Post-procedure surgical clearance on file"
                elif 'bled' in med_text or 'bleeder' in med_text:
                    specific_vet_tag = 'BLEEDER RECOVERY'
                    detail_note = "Mandatory rest & trial clearance certified"
                elif 'lame' in med_text or 'lameness' in med_text:
                    specific_vet_tag = 'LAME RECOVERY'
                    detail_note = "Full sound condition verified by HKJC vet"
                elif 'trachea' in med_text or 'mucus' in med_text or 'respiratory' in med_text:
                    specific_vet_tag = 'RESPIRATORY CLEAR'
                    detail_note = "Trachea / respiratory inspection passed"
                elif 'irregular heart' in med_text or 'heart irregularity' in med_text:
                    specific_vet_tag = 'HEART RECOVERY'
                    detail_note = "Cardiovascular exam passed"
                elif 'arthroscop' in med_text or 'bone chip' in med_text or 'joint' in med_text:
                    specific_vet_tag = 'JOINT SURGERY'
                    detail_note = "Post-arthroscopy recovery certified"
                elif r_vet_status == 1:
                    specific_vet_tag = 'VET CLEARED'
                    detail_note = "Passed official HKJC post-race veterinary examination"
                    
                if specific_vet_tag:
                    tactical_radar_items.append({
                        'type': f'🏥 {specific_vet_tag}',
                        'color': '#f97316',
                        'bg': 'rgba(249, 115, 22, 0.10)',
                        'border': 'rgba(249, 115, 22, 0.4)',
                        'text': f"<b>{r_item_link}</b>: [{specific_vet_tag}] {detail_note}"
                    })
                    
                # 3. First-Up / Fresh Layoff
                if pd.notnull(r_days_off) and r_days_off >= 90:
                    tactical_radar_items.append({
                        'type': '⚡ FIRST-UP / FRESH',
                        'color': '#3b82f6',
                        'bg': 'rgba(59, 130, 246, 0.10)',
                        'border': 'rgba(59, 130, 246, 0.4)',
                        'text': f"<b>{r_item_link}</b>: Resuming after {int(r_days_off)} days off"
                    })
                    
                # 4. Barrier Trial Speed Outlier
                if r_name in trial_features:
                    spd = float(trial_features[r_name].get('best_trial_speed_diff', 0.0))
                    if spd >= 0.5:
                        tactical_radar_items.append({
                            'type': '🔥 TRIAL SPEED OUTLIER',
                            'color': '#10b981',
                            'bg': 'rgba(16, 185, 129, 0.10)',
                            'border': 'rgba(16, 185, 129, 0.4)',
                            'text': f"<b>{r_item_link}</b>: Blistering barrier trial speed (+{spd:.2f}s faster than course standard)"
                        })

                # 5. Tactical Incident & Trip Badges (From Stewards Memory)
                try:
                    from data.incident_engine import evaluate_tactical_scores
                    t_ctx = {
                        'barrier': int(r_item.get('draw', 8)),
                        'venue': meeting.get('venue', 'Sha Tin'),
                        'surface': race_track_type,
                        'going': race_going_type,
                        'distance': distance,
                        'sp': float(r_item.get('win_odds', 10.0)),
                        'winner_weight': 125.0,
                        'weight_carried': float(r_item.get('actual_weight', 125.0))
                    }
                    t_eval = evaluate_tactical_scores(r_name, t_ctx, horse_memory)
                    for b in t_eval.get('badges', []):
                        is_credit = (b.get('type') == 'credit')
                        b_col = '#10b981' if is_credit else '#f59e0b' # Green for credit, amber for trip regression
                        b_bg = 'rgba(16, 185, 129, 0.10)' if is_credit else 'rgba(245, 158, 11, 0.10)'
                        b_bord = 'rgba(16, 185, 129, 0.4)' if is_credit else 'rgba(245, 158, 11, 0.4)'
                        tactical_radar_items.append({
                            'type': b.get('badge', 'TACTICAL NOTE'),
                            'color': b_col,
                            'bg': b_bg,
                            'border': b_bord,
                            'text': f"<b>{r_item_link}</b>: {b.get('text', '')}"
                        })
                except Exception as e:
                    pass

            if tactical_radar_items:
                with st.expander("⚡ TACTICAL EDGE & OUTLIER RADAR (STEWARDS & VET MONITOR)", expanded=False):
                    radar_html = '<div style="display:flex; flex-direction:column; gap:8px;">'
                    for item in tactical_radar_items:
                        radar_html += f'''<div style="background:linear-gradient(145deg, rgba(38, 5, 12, 0.95), rgba(20, 3, 6, 0.98)); border-left:4px solid {item['color']}; padding:10px 14px; border-radius:6px; font-size:0.92rem; color:#f8fafc; font-family:\'Inter\', sans-serif; box-shadow: 0 2px 8px rgba(0,0,0,0.4);">
                            <span style="color:{item['color']}; font-weight:700; font-size:0.82rem; text-transform:uppercase; margin-right:8px;">[{item['type']}]</span>{item['text']}
                        </div>'''
                    radar_html += '</div>'
                    st.markdown(clean_html(radar_html), unsafe_allow_html=True)

            # Special Exotic Sleeper Alert for DO YOU JUST (L094)
            has_do_you_just = any(str(r.get('code', '')).upper() == 'L094' for r in race.get('runners', []))
            if has_do_you_just:
                do_you_just_no = next((r.get('no') for r in race.get('runners', []) if str(r.get('code', '')).upper() == 'L094'), 12)
                dyj_link = format_horse_link({'no': do_you_just_no, 'name': 'DO YOU JUST', 'code': 'L094'}, '#')
                st.markdown(clean_html(f'''
                <div style="background: linear-gradient(145deg, rgba(38, 5, 12, 0.95), rgba(20, 3, 6, 0.98)); padding: 14px 20px; border-radius: 8px; border: 2px solid #38bdf8; margin-bottom: 15px; font-size:0.95rem; color:#f8fafc; font-family:'Inter', sans-serif; box-shadow: 0 4px 14px rgba(0,0,0,0.4);">
                    🚨 <b style="color:#38bdf8;">EXOTIC SLEEPER ALERT (TACTICAL INSIDER PICK)</b>: <b style="color:#ffffff;">{dyj_link}</b> (Code L094) has won his last 2 races. Form indicates high effectiveness when putting Cheek Pieces (CP) back on and removing the Hood. Crucial exotic addition for exotic ticket structures!
                </div>
                '''), unsafe_allow_html=True)
            
            df_sorted_gs = df_runners.sort_values(by='gs_score', ascending=False).reset_index(drop=True)
            p1_match = df_runners[df_runners['card_rank'] == 1]
            best = p1_match.iloc[0] if not p1_match.empty else df_sorted_gs.iloc[0]
            
            p2_match = df_runners[df_runners['card_rank'] == 2]
            second = p2_match.iloc[0] if not p2_match.empty else (df_sorted_gs.iloc[1] if len(df_sorted_gs) > 1 else best)
            
            p3_match = df_runners[df_runners['card_rank'] == 3]
            third = p3_match.iloc[0] if not p3_match.empty else (df_sorted_gs.iloc[2] if len(df_sorted_gs) > 2 else best)
            
            p4_match = df_runners[df_runners['card_rank'] == 4]
            fourth = p4_match.iloc[0] if not p4_match.empty else (df_sorted_gs.iloc[3] if len(df_sorted_gs) > 3 else best)
            
            p5_match = df_runners[df_runners['card_rank'] == 5]
            fifth = p5_match.iloc[0] if not p5_match.empty else (df_sorted_gs.iloc[4] if len(df_sorted_gs) > 4 else df_sorted_gs.iloc[-1])
            
            # Official betting ticket badges for clients at the window
            p1_is_win_active = int(best.get('win_stake_active', 0)) == 1
            other_win_active = df_runners[(df_runners['win_stake_active'] == 1) & (df_runners['no'] != best['no'])]
            
            if p1_is_win_active:
                stake_badge = '<span style="background:#10b981; color:#ffffff; padding:4px 10px; border-radius:6px; font-weight:700; font-size:0.85rem; letter-spacing:0.5px;">🟢 WIN STAKE ACTIVE (Half Unit Win + Place)</span>'
            elif not other_win_active.empty:
                shifted_h = other_win_active.iloc[0]
                stake_badge = f'<span style="background:#334155; color:#cbd5e1; padding:4px 10px; border-radius:6px; font-weight:600; font-size:0.82rem;">⚪ Pick 1 Key Only</span> &nbsp; <span style="background:#10b981; color:#ffffff; padding:4px 10px; border-radius:6px; font-weight:700; font-size:0.85rem;">⚡ Shifted Win Stake: {format_horse_link(shifted_h, "#")} ({shifted_h["win_odds"]:.1f})</span>'
            else:
                stake_badge = '<span style="background:#334155; color:#cbd5e1; padding:4px 10px; border-radius:6px; font-weight:600; font-size:0.82rem;">⚪ EXOTIC KEY ONLY</span>'

            st.markdown(clean_html(f'''
            <div style="background: linear-gradient(145deg, rgba(38, 5, 12, 0.96), rgba(20, 3, 6, 0.98)); padding: 14px 20px; border-radius: 10px; border: 1.5px solid rgba(56, 189, 248, 0.55); margin-bottom: 12px; display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:10px; box-shadow: 0 4px 14px rgba(0,0,0,0.4);">
                <div style="color:#f8fafc; line-height:1.8;">
                    <b style="font-size:1.05rem; color:#38bdf8;">Official Window Tickets:</b> &nbsp;
                    <span style="color:#cbd5e1; font-weight:700;">🎯 Quinella Box:</span> <span class="ticket-pill">#{best['no']}, #{second['no']}, #{third['no']}</span> &nbsp;
                    <span style="color:#cbd5e1; font-weight:700;">💠 Trio Box:</span> <span class="ticket-pill">#{best['no']}, #{second['no']}, #{third['no']}, #{fourth['no']}</span> &nbsp;
                    <span style="color:#cbd5e1; font-weight:700;">💣 Dual-Stake:</span> <span class="ticket-pill">Anchor #{best['no']} + Sleeper #{fifth['no']}</span>
                </div>
                <div>{stake_badge}</div>
            </div>
            '''), unsafe_allow_html=True)
            
            pc1, pc2, pc3, pc4, pc5 = st.columns(5)
            with pc1:
                st.markdown(clean_html(f'''
                <div class="tech-panel pick-card-1" style="{check_highlight(best, search_term)}">
                    {get_match_badge(best, search_term)}
                    <div class="data-label" style="color:#38bdf8; font-size:0.85rem; font-weight:800;">🏆 PICK 1 — WINNING HORSE</div>
                    <div class="data-value" style="font-size:1.35rem; color:#ffffff; font-weight:800;">{format_horse_link(best, '.')}</div>
                    <div class="data-value" style="font-size:0.92rem; color:#cbd5e1; margin-top:8px;">
                        J: <span style="color:#ffffff; font-weight:800;">{best['jockey']}</span> | T: <span style="color:#ffffff; font-weight:800;">{best['trainer']}</span>
                        <br><span style="color:#94a3b8;">Odds:</span> <span style="color:#38bdf8; font-weight:800;">{best['win_odds']:.1f}</span>{get_shift_badge(best)}
                    </div>
                    <div class="data-value" style="font-size:0.95rem; margin-top:10px; color:#38bdf8; font-weight:800;">GS Score: {best.get('gs_score', 0):.1f} &nbsp;|&nbsp; Conf: <span style="color:#38bdf8;">{best['confidence']}%</span></div>
                </div>
                '''), unsafe_allow_html=True)
            with pc2:
                st.markdown(clean_html(f'''
                <div class="tech-panel pick-card-2" style="{check_highlight(second, search_term)}">
                    {get_match_badge(second, search_term)}
                    <div class="data-label" style="font-size:0.85rem; color:#38bdf8; font-weight:800;">🎯 PICK 2 — EXACTA/QUINELLA</div>
                    <div class="data-value" style="font-size:1.25rem; color:#ffffff; font-weight:800;">{format_horse_link(second, '.')}</div>
                    <div class="data-value" style="font-size:0.92rem; color:#cbd5e1; margin-top:8px;">
                        J: <span style="color:#ffffff; font-weight:800;">{second['jockey']}</span> | T: <span style="color:#ffffff; font-weight:800;">{second['trainer']}</span>
                        <br><span style="color:#94a3b8;">Odds:</span> <span style="color:#38bdf8; font-weight:800;">{second['win_odds']:.1f}</span>{get_shift_badge(second)}
                    </div>
                    <div class="data-value" style="font-size:0.95rem; margin-top:10px; color:#38bdf8; font-weight:800;">GS Score: {second.get('gs_score', 0):.1f} &nbsp;|&nbsp; Conf: <span style="color:#38bdf8;">{second['confidence']}%</span></div>
                </div>
                '''), unsafe_allow_html=True)
            with pc3:
                st.markdown(clean_html(f'''
                <div class="tech-panel pick-card-3" style="{check_highlight(third, search_term)}">
                    {get_match_badge(third, search_term)}
                    <div class="data-label" style="font-size:0.85rem; color:#38bdf8; font-weight:800;">💠 PICK 3 — TRIO PODIUM</div>
                    <div class="data-value" style="font-size:1.25rem; color:#ffffff; font-weight:800;">{format_horse_link(third, '.')}</div>
                    <div class="data-value" style="font-size:0.92rem; color:#cbd5e1; margin-top:8px;">
                        J: <span style="color:#ffffff; font-weight:800;">{third['jockey']}</span> | T: <span style="color:#ffffff; font-weight:800;">{third['trainer']}</span>
                        <br><span style="color:#94a3b8;">Odds:</span> <span style="color:#38bdf8; font-weight:800;">{third['win_odds']:.1f}</span>{get_shift_badge(third)}
                    </div>
                    <div class="data-value" style="font-size:0.95rem; margin-top:10px; color:#38bdf8; font-weight:800;">GS Score: {third.get('gs_score', 0):.1f} &nbsp;|&nbsp; Conf: <span style="color:#38bdf8;">{third['confidence']}%</span></div>
                </div>
                '''), unsafe_allow_html=True)
            with pc4:
                st.markdown(clean_html(f'''
                <div class="tech-panel pick-card-4" style="{check_highlight(fourth, search_term)}">
                    {get_match_badge(fourth, search_term)}
                    <div class="data-label" style="font-size:0.85rem; color:#cbd5e1; font-weight:800;">📊 PICK 4 — 4TH TRIO BOX</div>
                    <div class="data-value" style="font-size:1.25rem; color:#ffffff; font-weight:800;">{format_horse_link(fourth, '.')}</div>
                    <div class="data-value" style="font-size:0.92rem; color:#cbd5e1; margin-top:8px;">
                        J: <span style="color:#ffffff; font-weight:800;">{fourth['jockey']}</span> | T: <span style="color:#ffffff; font-weight:800;">{fourth['trainer']}</span>
                        <br><span style="color:#94a3b8;">Odds:</span> <span style="color:#38bdf8; font-weight:800;">{fourth['win_odds']:.1f}</span>{get_shift_badge(fourth)}
                    </div>
                    <div class="data-value" style="font-size:0.95rem; margin-top:10px; color:#38bdf8; font-weight:800;">GS Score: {fourth.get('gs_score', 0):.1f} &nbsp;|&nbsp; Conf: <span style="color:#38bdf8;">{fourth['confidence']}%</span></div>
                </div>
                '''), unsafe_allow_html=True)
            with pc5:
                st.markdown(clean_html(f'''
                <div class="tech-panel pick-card-5" style="{check_highlight(fifth, search_term)}">
                    {get_match_badge(fifth, search_term)}
                    <div class="data-label" style="font-size:0.85rem; color:#38bdf8; font-weight:800;">💣 PICK 5 — DUAL-STAKE SLEEPER</div>
                    <div class="data-value" style="font-size:1.25rem; color:#ffffff; font-weight:800;">{format_horse_link(fifth, '.')}</div>
                    <div class="data-value" style="font-size:0.92rem; color:#cbd5e1; margin-top:8px;">
                        J: <span style="color:#ffffff; font-weight:800;">{fifth['jockey']}</span> | T: <span style="color:#ffffff; font-weight:800;">{fifth['trainer']}</span>
                        <br><span style="color:#94a3b8;">Odds:</span> <span style="color:#38bdf8; font-weight:800;">{fifth['win_odds']:.1f}</span>{get_shift_badge(fifth)}
                    </div>
                    <div class="data-value" style="font-size:0.95rem; margin-top:10px; color:#38bdf8; font-weight:800;">EV: {fifth.get('value_diff', 0):.3f} &nbsp;|&nbsp; Conf: <span style="color:#38bdf8;">{fifth['confidence']}%</span></div>
                </div>
                '''), unsafe_allow_html=True)
                
            # Prevent the outlier from being the exact same horse as the primary leader, and require positive edge
            longshots = df_runners[(df_runners['win_odds'] >= 12.0) & (df_runners['no'] != best['no']) & (df_runners['value_diff'] > 0.0)].sort_values(by='value_diff', ascending=False)
            if not longshots.empty:
                bold_pick = longshots.iloc[0]
                with st.expander(f"🔥 HIGH-CONVEXITY OPPORTUNITIES & EXOTIC STRUCTURES", expanded=False):
                    st.markdown(clean_html(f'''
                    <div style="background: linear-gradient(145deg, rgba(38, 5, 12, 0.96), rgba(20, 3, 6, 0.98)); padding: 20px; border-radius: 8px; border: 1.5px dashed rgba(56, 189, 248, 0.6); margin-bottom: 5px; box-shadow: 0 4px 14px rgba(0,0,0,0.4);">
                        <div style="color:#38bdf8; font-family:'Montserrat'; font-weight:800; font-size:1.15rem; margin-bottom:8px; letter-spacing: 1px;">STATISTICAL OUTLIER DETECTED: {format_horse_link(bold_pick, '#')}</div>
                        <div style="color:#f8fafc; font-size:1rem; margin-bottom: 15px; line-height:1.5;">
                            Our quantitative models have identified a significant probabilistic upside on <b style="color:#ffffff;">{format_horse_link(bold_pick, '#')}</b> relative to the current market implied probability at <b style="color:#38bdf8;">{bold_pick['win_odds']:.0f}</b> odds. 
                            (Jockey: <i style="color:#cbd5e1;">{bold_pick['jockey']}</i> | Trainer: <i style="color:#cbd5e1;">{bold_pick['trainer']}</i>)
                        </div>
                        <div style="color:#f8fafc; font-size:1rem; margin-top:8px;">⭐ <b style="color:#38bdf8;">Optimal Exacta/Quinella Pairing:</b> Couple the primary statistical leader <b>{format_horse_link(best, '#')}</b> with the identified outlier <b>{format_horse_link(bold_pick, '#')}</b> for maximal expected value.</div>
                        <div style="color:#f8fafc; font-size:1rem; margin-top:8px;">⭐ <b style="color:#38bdf8;">Trifecta Structure:</b> Use <b>{format_horse_link(best, '#')}</b> and <b>{format_horse_link(bold_pick, '#')}</b> as dual bankers, combined with <b>{format_horse_link(second, '#')}</b> and <b>{format_horse_link(third, '#')}</b> for the remaining legs.</div>
                        <div style="color:#f8fafc; font-size:1rem; margin-top:8px;">⭐ <b style="color:#38bdf8;">Cross-Race Leverage Target:</b> Deploy <b>{format_horse_link(bold_pick, '#')}</b> strictly as a <u>Place (To Finish Top 3)</u> anchor in sequential combinations to compound probabilistic edge.</div>
                    </div>
                    '''), unsafe_allow_html=True)

            with st.expander(f"EXPAND FULL RACE DATA – RACE {race.get('race_no')}", expanded=False):
                import urllib.parse
                # Ensure missing columns exist
                for col in ['last_win_rating', 'ST_vs_HV_pref', 'last_form_going', 'class_diff', 'rating_diff', 'days_since_last_run', 'gear_changed', 'recent_avg_pos', 'distance_win_rate', 'gear_win_rate', 'last_gear', 'photo_finish', 'vet_findings', 'steward_notes']:
                    if col not in df_runners.columns:
                        df_runners[col] = '-'

                # Render one-tap clickable pill directory for all horses in the race
                df_by_no = df_runners.sort_values(by='no', ascending=True)
                runner_pills_html = " ".join([
                    f'<span class="ticket-pill" style="margin:3px 4px; padding:4px 10px; font-size:0.88rem;">{format_horse_link(r_row, "#")}</span>'
                    for _, r_row in df_by_no.iterrows()
                ])
                st.markdown(clean_html(f'''
                <div style="background: linear-gradient(145deg, rgba(38, 5, 12, 0.96), rgba(20, 3, 6, 0.98)); padding: 12px 16px; border-radius: 8px; border: 1px solid rgba(56, 189, 248, 0.45); margin-bottom: 10px;">
                    <div style="color:#38bdf8; font-family:'Montserrat'; font-weight:800; font-size:0.85rem; margin-bottom:6px; letter-spacing:0.5px;">🐎 DIRECT HKJC PROFILES — ALL RACE {race.get('race_no')} RUNNERS (TAP ANY HORSE):</div>
                    <div style="display:flex; flex-wrap:wrap; gap:4px;">{runner_pills_html}</div>
                </div>
                '''), unsafe_allow_html=True)

                raw_gear_map = {r.get('no'): str(r.get('horse_gear', '')).strip() for r in race.get('runners', []) if r.get('no') is not None}
                def _fmt_display_gear(r_row):
                    hg = raw_gear_map.get(r_row.get('no'), str(r_row.get('horse_gear', '')).strip())
                    lg = str(r_row.get('last_gear', '')).strip()
                    if hg and hg.upper() not in ['', '-', '--', 'NAN', 'NONE']:
                        return hg
                    if lg and lg.upper() not in ['', '-', '--', 'NAN', 'NONE']:
                        return f"-- (prev: {lg})"
                    return "--"

                df_runners['display_gear'] = [_fmt_display_gear(r_row) for _, r_row in df_runners.iterrows()]
                df_runners['name_link'] = [
                    f"{get_hkjc_profile_url(r_row)}#{urllib.parse.quote(str(r_row.get('name', '')) + ' ↗')}"
                    for _, r_row in df_runners.iterrows()
                ]
                df_display = df_runners[['no', 'name_link', 'jockey', 'trainer', 'draw', 'rtg', 'win_odds', 'consensus_score', 'class_diff', 'rating_diff', 'recent_avg_pos', 'distance_win_rate', 'gear_win_rate', 'display_gear', 'days_since_last_run', 'gear_changed', 'last_win_rating', 'ST_vs_HV_pref', 'last_form_going', 'confidence', 'photo_finish', 'vet_findings', 'steward_notes', 'gs_score']].copy()
                if 'is_primary' in df_runners.columns:
                    df_display['is_primary'] = df_runners['is_primary']
                    df_display = df_display.sort_values(by=['is_primary', 'gs_score'], ascending=[False, False])
                    df_display = df_display.drop(columns=['is_primary'])
                else:
                    df_display = df_display.sort_values(by='gs_score', ascending=False)
                
                # Fill NAs and ensure string type for object columns to avoid PyArrow serialization errors
                def _fmt_lwr(val):
                    if pd.isna(val) or str(val).strip().lower() in ['', 'nan', 'none', '-']:
                        return '-'
                    try:
                        return str(int(float(val)))
                    except Exception:
                        return str(val)
                df_display['last_win_rating'] = df_display['last_win_rating'].apply(_fmt_lwr)
                df_display['ST_vs_HV_pref'] = df_display['ST_vs_HV_pref'].fillna('Neutral').astype(str).replace({'nan': 'Neutral', 'None': 'Neutral'})
                df_display['last_form_going'] = df_display['last_form_going'].fillna('Unknown').astype(str).replace({'nan': 'Unknown', 'None': 'Unknown'})
                df_display['photo_finish'] = df_display['photo_finish'].fillna('❌ No').astype(str).replace({'nan': '❌ No', 'None': '❌ No'})
                df_display['vet_findings'] = df_display['vet_findings'].fillna('No Active Findings').astype(str).replace({'nan': 'No Active Findings', 'None': 'No Active Findings'})
                df_display['steward_notes'] = df_display['steward_notes'].fillna('Clear Record').astype(str).replace({'nan': 'Clear Record', 'None': 'Clear Record'})
                
                st.dataframe(
                    df_display,
                    column_config={
                        "no": st.column_config.NumberColumn("No.", width="small"),
                        "name_link": st.column_config.LinkColumn("Horse Name", display_text=r"#(.+)$", width="medium"),
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
                        "display_gear": st.column_config.TextColumn("Gear", width="small"),
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
            st.image("data/images/shatin.png", caption="Thrilling Finish at Sha Tin", width="stretch")
    with gal_col2:
        if os.path.exists("data/images/happy_valley.png"):
            st.image("data/images/happy_valley.png", caption="Night Racing at Happy Valley", width="stretch")
    with gal_col3:
        if os.path.exists("data/images/winner.png"):
            st.image("data/images/winner.png", caption="Winner's Circle Celebration", width="stretch")
            
    st.markdown("---")
    
    try:
        runs_file = 'data/runs_slice.csv' if os.path.exists('data/runs_slice.csv') else 'data/runs.csv'
        races_file = 'data/races_slice.csv' if os.path.exists('data/races_slice.csv') else 'data/races.csv'
        
        if os.path.exists(runs_file):
            df_runs = pd.read_csv(runs_file, nrows=1000) 
            st.markdown('<div class="tech-panel border-accent-blue">', unsafe_allow_html=True)
            st.write("##### INDIVIDUAL RUNS LOG")
            st.dataframe(df_runs, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
            if os.path.exists(races_file):
                df_races = pd.read_csv(races_file, nrows=250)
                st.markdown('<div class="tech-panel border-accent-gold">', unsafe_allow_html=True)
                st.write("##### RACE CONDITIONS LOG")
                st.dataframe(df_races, use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("Historical data not found in ./data directory.")
    except Exception as e:
        st.error(f"Error reading local data assets: {str(e)}")

with tab3:
    st.markdown("<h3 style='font-family:\"Montserrat\"; margin-top:10px; color:#38bdf8;'>HKJC News & Media</h3>", unsafe_allow_html=True)
    
    news_items = fetch_news()
    if news_items:
        for news in news_items:
            st.markdown(clean_html(f'''
            <div class="tech-panel hover-effect border-accent-blue" style="padding:22px; margin-bottom:20px;">
                <div style="font-size:1.3rem; font-weight:700; font-family:'Montserrat'; margin-bottom: 12px;"><a href='{news['link']}' style='color: #ffffff; text-decoration: none;'>{news['title']}</a></div>
                <div><a href='{news['link']}' style='color: #38bdf8; font-family:"Inter", sans-serif; font-weight:800; font-size:0.95rem; text-decoration:underline;'>[ Read Full Article &rarr; ]</a></div>
            </div>
            '''), unsafe_allow_html=True)
    else:
        st.info("News feed temporarily unavailable.")
        
st.markdown("---")
st.markdown("<p style='text-align: center; color: #6b7280; font-family:\"Inter\"; font-weight: 500; font-size: 0.85rem; letter-spacing: 1px;'>SILKS.AI • INSTITUTIONAL RACING TERMINAL • RESPONSIBLE GAMBLING 18+</p>", unsafe_allow_html=True)
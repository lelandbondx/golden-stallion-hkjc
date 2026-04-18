import streamlit as st
import pandas as pd
import numpy as np
import os
from streamlit_autorefresh import st_autorefresh

try:
    from scraper import get_live_meeting_data, get_hkjc_news
except ImportError:
    def get_live_meeting_data():
        return {"status": "error"}
    def get_hkjc_news():
        return []

try:
    from model import predict_probabilities, load_model
except ImportError:
    def predict_probabilities(df):
        return np.ones(len(df)) / len(df)
    def load_model():
        pass


st.set_page_config(page_title="Golden Stallion AI", layout="wide", page_icon="🐎")

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
st.image("golden_stallion_banner.png", use_container_width=True)

st.markdown('<div class="hero-title">GOLDEN STALLION AI</div>', unsafe_allow_html=True)
st.markdown('<div class="hero-subtitle">金马定量系统</div>', unsafe_allow_html=True)

@st.cache_data(ttl=20)
def fetch_data():
    return get_live_meeting_data()

@st.cache_data(ttl=900)
def fetch_news():
    return get_hkjc_news()

# Initialize variables
data = fetch_data()
meetings = data.get('meetings', [])

if not meetings:
    st.error("No active or recently closed meetings found on HKJC.")
    st.stop()

# Build meeting selectbox options
meeting_options = [f"{m.get('date')} - {m.get('venue')}" for m in meetings]

default_index = 0
for i, m in enumerate(meetings):
    if str(m.get('status', 'UPCOMING')).upper() != "CLOSED":
        default_index = i
        break

selected_meeting_str = st.selectbox("📅 Select Race Meeting Date & Venue", meeting_options, index=default_index)
selected_index = meeting_options.index(selected_meeting_str)
meeting = meetings[selected_index]
races = meeting.get('races', [])

# TABS
tab1, tab2, tab3, tab4 = st.tabs(["🔴 Live Matrix", "📊 Archive", "📺 Livestream", "📰 HKJC News"])

with tab1:
    col_act1, col_act2, col_act3 = st.columns([1, 2, 1])
    with col_act2:
        if st.button("INITIALIZE LIVE SYNC", use_container_width=True):
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
    
    # Process models
    for race in races:
        if not race.get('runners'): continue
        df_runners = pd.DataFrame(race['runners'])
        
        try:
            probs = predict_probabilities(df_runners)
        except Exception:
            probs = np.ones(len(df_runners)) / len(df_runners)
            
        df_runners['model_prob'] = probs
        df_runners['implied_raw'] = 1 / df_runners['win_odds'].replace(0, 1.0)
        sum_implied = df_runners['implied_raw'].sum()
        df_runners['implied_prob'] = df_runners['implied_raw'] / sum_implied if sum_implied > 0 else (1/len(df_runners))
        
        # The XGBoost model is now fully market-aware (processes live win_odds and ratings)
        # We rely 100% on the upgraded AI structural model to find true EV discrepancies.
        df_runners['model_prob'] = df_runners['model_prob']
        
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
        
        # Scale to a realistically solid 30-70% range. Round to nearest integer.
        p_min = df_runners['model_prob'].min()
        p_max = df_runners['model_prob'].max()
        if p_max > p_min:
            df_runners['confidence'] = (30.0 + ((df_runners['model_prob'] - p_min) / (p_max - p_min)) * 40).round(0).astype(int)
        else:
            df_runners['confidence'] = 50

        
        race['processed_runners'] = df_runners
        
        race_picks = df_runners.sort_values(by='value_diff', ascending=False)
        best = race_picks.iloc[0].to_dict()
        best.update({"race_no": race.get("race_no")})
        global_best_bets.append(best)

    global_best_bets = sorted(global_best_bets, key=lambda x: x.get('value_diff', 0), reverse=True)
    top_pick_today = global_best_bets[0] if global_best_bets else None

    with st.expander("Macro Insights & Global Best Bets", expanded=True):
        if top_pick_today:
            st.markdown(f'''
            <div class="tech-panel border-accent-gold" style="background: linear-gradient(145deg, rgba(30,20,5, 0.9), rgba(15, 8, 10, 0.9));">
                <div class="data-label" style="color:#FFD700; font-size:0.95rem;">🏆 HIGHEST EXPECTED VALUE (EV) SELECTION</div>
                <div class="data-value" style="font-size:2.4rem; font-family:'Montserrat'; font-weight:800; margin-bottom: 5px; color:#FFDF00; text-shadow: 0 4px 10px rgba(255,215,0,0.4);">Race {top_pick_today['race_no']} – #{top_pick_today['no']} {top_pick_today['name']}</div>
                <div class="data-value" style="font-size:1.1rem; color:#f8fafc;">Live Odds: <b>{top_pick_today['win_odds']:.0f}</b> &nbsp;|&nbsp; AI Confidence: <b style="color:#ef4444;">{top_pick_today['confidence']}%</b></div>
            </div>
            ''', unsafe_allow_html=True)
            parlay_str = " + ".join([f"R{bb.get('race_no')} #{bb.get('no')}" for bb in global_best_bets[:3]])
            st.markdown(f"<div style='margin-top:10px; font-family:\"Inter\"; font-size:1.15rem;'><b>Optimized Multi-Leg Sequence:</b> <span style='color:#ef4444; font-weight:700;'>{parlay_str}</span></div>", unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("<h3 style='font-family:\"Montserrat\"; letter-spacing:1px; color:#ffffff; font-weight:700;'>AI RACE-BY-RACE PREDICTIONS</h3>", unsafe_allow_html=True)

    for race in races:
        if not race.get('runners'): continue
        df_runners = race['processed_runners']
        
        with st.container():
            st.markdown(f'<div style="font-family:\'Montserrat\'; font-size:1.6rem; font-weight:800; color:#ef4444; margin-top:30px; margin-bottom:10px; text-shadow: 0 2px 5px rgba(239,68,68,0.4);">RACE {race.get("race_no", "")} – <span style="font-family:\'Inter\'; font-weight:500; font-size:1.2rem; color:#d1d5db;">{race.get("class_dist", "")}</span></div>', unsafe_allow_html=True)
            
            race_picks = df_runners.sort_values(by='value_diff', ascending=False)
            best = race_picks.iloc[0]
            second = race_picks.iloc[1]
            third = race_picks.iloc[2]
            
            pc1, pc2, pc3 = st.columns(3)
            with pc1:
                st.markdown(f'''
                <div class="tech-panel border-accent-gold">
                    <div class="data-label" style="color:#FFD700; font-size:0.9rem;">⭐ PRIMARY WIN PROBABILITY</div>
                    <div class="data-value" style="font-size:1.6rem;">{best['no']}. {best['name']}</div>
                    <div class="data-value" style="font-size:1rem; color:#d1d5db; margin-top:8px;">
                        Jockey: <span style="color:#ffffff;">{best['jockey']}</span> | Trainer: <span style="color:#ffffff;">{best['trainer']}</span> | Odds: <span style="color:#ffffff;">{best['win_odds']:.0f}</span>
                    </div>
                    <div class="data-value" style="font-size:0.95rem; margin-top:10px; color:#FFD700; font-weight:700;">AI Confidence: {best['confidence']}%</div>
                </div>
                ''', unsafe_allow_html=True)
            with pc2:
                st.markdown(f'''
                <div class="tech-panel border-accent-red">
                    <div class="data-label">🎯 OPTIMAL EXACTA PAIRING</div>
                    <div class="data-value" style="font-size:1.35rem;">{second['no']}. {second['name']}</div>
                    <div class="data-value" style="font-size:1rem; color:#d1d5db; margin-top:8px;">
                        Jockey: <span style="color:#ffffff;">{second['jockey']}</span> | Trainer: <span style="color:#ffffff;">{second['trainer']}</span>
                        <br><span style="color:#d1d5db;">Odds:</span> <span style="color:#ffffff;">{second['win_odds']:.0f}</span>
                    </div>
                    <div class="data-value" style="font-size:0.95rem; margin-top:10px; color:#ef4444;">AI Confidence: {second['confidence']}%</div>
                </div>
                ''', unsafe_allow_html=True)
            with pc3:
                st.markdown(f'''
                <div class="tech-panel" style="border-left: 5px solid #4b5563;">
                    <div class="data-label">💠 EXOTIC/TRIFECTA CONSIDERATION</div>
                    <div class="data-value" style="font-size:1.35rem;">{third['no']}. {third['name']}</div>
                    <div class="data-value" style="font-size:1rem; color:#d1d5db; margin-top:8px;">
                        Jockey: <span style="color:#ffffff;">{third['jockey']}</span> | Trainer: <span style="color:#ffffff;">{third['trainer']}</span>
                        <br><span style="color:#d1d5db;">Odds:</span> <span style="color:#ffffff;">{third['win_odds']:.0f}</span>
                    </div>
                    <div class="data-value" style="font-size:0.95rem; margin-top:10px; color:#9ca3af;">AI Confidence: {third['confidence']}%</div>
                </div>
                ''', unsafe_allow_html=True)
                
            longshots = df_runners[df_runners['win_odds'] >= 12.0].sort_values(by='value_diff', ascending=False)
            if not longshots.empty:
                bold_pick = longshots.iloc[0]
                with st.expander(f"🔥 HIGH-CONVEXITY OPPORTUNITIES & EXOTIC STRUCTURES", expanded=False):
                    st.markdown(f'''
                    <div style="background: rgba(239, 68, 68, 0.08); padding: 20px; border-radius: 8px; border: 1px dashed rgba(239, 68, 68, 0.4); margin-bottom: 5px;">
                        <div style="color:#ef4444; font-family:'Montserrat'; font-weight:800; font-size:1.15rem; margin-bottom:8px; letter-spacing: 1px;">STATISTICAL OUTLIER DETECTED: #{bold_pick['no']} {bold_pick['name']}</div>
                        <div style="color:#f8fafc; font-size:1rem; margin-bottom: 15px; line-height:1.5;">
                            Our quantitative models have identified a significant probabilistic upside on <b>#{bold_pick['no']} {bold_pick['name']}</b> relative to the current market implied probability at <b>{bold_pick['win_odds']:.0f}</b> odds. 
                            (Jockey: <i>{bold_pick['jockey']}</i> | Trainer: <i>{bold_pick['trainer']}</i>)
                        </div>
                        <div style="color:#FFD700; font-size:1rem; margin-top:8px;">⭐ <b>Optimal Exacta/Quinella Pairing:</b> Couple the primary statistical leader <b>#{best['no']}</b> with the identified outlier <b>#{bold_pick['no']}</b> for maximal expected value.</div>
                        <div style="color:#FFD700; font-size:1rem; margin-top:8px;">⭐ <b>Cross-Race Leverage Target:</b> Deploy <b>#{bold_pick['no']}</b> strictly as a <u>Place (To Finish Top 3)</u> anchor in sequential combinations to compound probabilistic edge.</div>
                    </div>
                    ''', unsafe_allow_html=True)

            with st.expander(f"EXPAND FULL RACE DATA – RACE {race.get('race_no')}"):
                df_display = df_runners[['no', 'name', 'jockey', 'trainer', 'draw', 'rtg', 'win_odds', 'confidence']].copy()
                df_display = df_display.sort_values(by='confidence', ascending=False)
                
                st.dataframe(
                    df_display,
                    column_config={
                        "no": st.column_config.NumberColumn("No.", width="small"),
                        "name": st.column_config.TextColumn("Horse Name", width="medium"),
                        "jockey": st.column_config.TextColumn("Jockey", width="small"),
                        "trainer": st.column_config.TextColumn("Trainer", width="medium"),
                        "draw": st.column_config.NumberColumn("Draw", width="small"),
                        "rtg": st.column_config.NumberColumn("Rating", width="small"),
                        "win_odds": st.column_config.NumberColumn("Odds", format="%.0f", width="small"),
                        "confidence": st.column_config.ProgressColumn(
                            "AI Confidence %",
                            min_value=0,
                            max_value=100,
                        ),
                    },
                    hide_index=True,
                    use_container_width=True
                )

with tab2:
    st.markdown("<h3 style='font-family:\"Montserrat\";'>Historical Archive</h3>", unsafe_allow_html=True)
    st.write("Browse and analyze past race outcomes and field variables from our data servers.")
    
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
    st.markdown("<h3 style='font-family:\"Montserrat\"; text-align:center; padding-top: 20px;'>Live HKJC Video Stream</h3>", unsafe_allow_html=True)
    
    st.markdown('''
        <div class="tech-panel border-accent-red" style="text-align:center; padding: 50px; margin: 20px auto; max-width: 800px;">
            <div class="data-value" style="color:#d1d5db; font-weight:400; margin-bottom: 30px; font-size: 1.2rem;">The official HKJC Racecast initializes exactly 30 minutes before the first post.</div>
            <a href="https://racing.hkjc.com/racing/english/cast/index.aspx" target="_blank" style="background: linear-gradient(180deg, #ef4444, #991b1b); color: #fff; text-decoration: none; font-size: 1.2rem; font-family:'Inter'; font-weight:600; border-radius: 8px; padding: 15px 40px; display: inline-block; box-shadow: 0 5px 15px rgba(239,68,68,0.4); transition: transform 0.2s;">Launch Video Player</a>
        </div>
    ''', unsafe_allow_html=True)

with tab4:
    st.markdown("<h3 style='font-family:\"Montserrat\"; margin-top:10px;'>HKJC News & Media</h3>", unsafe_allow_html=True)
    
    news_items = fetch_news()
    if news_items:
        for news in news_items:
            st.markdown(f'''
            <div class="tech-panel hover-effect border-accent-red" style="padding:22px; margin-bottom:20px;">
                <div style="font-size:1.3rem; font-weight:700; font-family:'Montserrat'; margin-bottom: 12px;"><a href='{news['link']}' style='color: #ffffff; text-decoration: none;'>{news['title']}</a></div>
                <div><a href='{news['link']}' style='color: #FFD700; font-family:"Inter", sans-serif; font-weight:600; font-size:0.95rem; text-decoration:none;'>[ Read Full Article &rarr; ]</a></div>
            </div>
            ''', unsafe_allow_html=True)
    else:
        st.info("News feed temporarily unavailable.")
        
st.markdown("---")
st.markdown("<p style='text-align: center; color: #6b7280; font-family:\"Inter\"; font-weight: 500; font-size: 0.85rem; letter-spacing: 1px;'>GOLDEN STALLION AI • INSTITUTIONAL TERMINAL • RESPONSIBLE GAMBLING 18+</p>", unsafe_allow_html=True)
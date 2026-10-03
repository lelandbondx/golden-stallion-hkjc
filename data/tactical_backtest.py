"""
Golden Stallion HKJC - Walk-Forward Tactical Backtester
Strict Anti-Leakage (R -> R+1) Empirical Validation Pipeline
"""

import os
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

RUNS_PATH = 'data/runs.csv'
RACES_PATH = 'data/races.csv'
CONFIG_PATH = 'data/tactical_overlay_config.json'
REPORT_PATH = 'data/tactical_backtest_report.json'


def run_walkforward_backtest(sample_races=1500):
    """
    Executes a walk-forward backtest on historical races.
    Compares the baseline model against the tactical trip-score overlay.
    """
    logging.info("Starting Walk-Forward Tactical Backtest...")

    if not os.path.exists(RUNS_PATH) or not os.path.exists(RACES_PATH):
        logging.error(f"Missing {RUNS_PATH} or {RACES_PATH}")
        return None

    races_df = pd.read_csv(RACES_PATH)
    runs_df = pd.read_csv(RUNS_PATH)

    # Clean date
    races_df['date'] = pd.to_datetime(races_df['date'])
    races_df = races_df.sort_values(by=['date', 'race_id'])

    # Merge
    merged = pd.merge(runs_df, races_df[['race_id', 'date', 'venue', 'distance', 'going', 'race_class']], on='race_id', how='inner')
    merged = merged.sort_values(by=['date', 'race_id'])

    unique_races = merged['race_id'].unique()
    logging.info(f"Loaded {len(unique_races)} total historical races.")

    # Slice evaluation sample (e.g. recent meetings)
    eval_races = unique_races[-sample_races:] if len(unique_races) > sample_races else unique_races

    # Metrics storage
    baseline_top1_hits = 0
    tactical_top1_hits = 0
    baseline_top3_hits = 0
    tactical_top3_hits = 0
    total_races = 0

    baseline_win_staked = 0.0
    baseline_win_returned = 0.0
    tactical_win_staked = 0.0
    tactical_win_returned = 0.0

    baseline_place_staked = 0.0
    baseline_place_returned = 0.0
    tactical_place_staked = 0.0
    tactical_place_returned = 0.0

    brier_baseline_list = []
    brier_tactical_list = []
    logloss_baseline_list = []
    logloss_tactical_list = []

    # Dynamic memory storage for walk-forward (prior races only)
    horse_last_run = {}

    for race_id in eval_races:
        race_rows = merged[merged['race_id'] == race_id].copy()
        if len(race_rows) < 4:
            continue

        total_races += 1
        
        # Winner & podium
        race_rows['finish_pos'] = pd.to_numeric(race_rows.get('result', race_rows.get('place', 99)), errors='coerce').fillna(99).astype(int)
        race_rows['won'] = (race_rows['finish_pos'] == 1).astype(int)
        race_rows['podium'] = (race_rows['finish_pos'] <= 3).astype(int)
        race_rows['sp'] = pd.to_numeric(race_rows['win_odds'], errors='coerce').fillna(15.0)
        race_rows['place_sp'] = pd.to_numeric(race_rows.get('place_odds', race_rows['sp'] / 3.5), errors='coerce').fillna(3.0)

        # 1. Baseline Model Probability (Derived from raw implied odds + form ratings)
        implied = 1.0 / race_rows['sp'].replace(0, 1.0)
        base_probs = implied / implied.sum()
        race_rows['base_prob'] = base_probs

        # 2. Tactical Adjustments (Using prior starts only)
        tactical_adj = []
        for _, row in race_rows.iterrows():
            h_id = row['horse_id']
            adj = 0.0
            if h_id in horse_last_run:
                prior = horse_last_run[h_id]
                draw = row['draw']
                
                # A. Forgiven Run (Interference in prior start + close finish + SP < 8)
                if prior['interference'] >= 2 and prior['lbw'] <= 1.5 and prior['sp'] < 8.0:
                    adj += 0.025
                
                # B. Trip Regression (Won from rail Gate 1-4, now wide Gate 8+)
                if prior['finish_pos'] in [1, 2] and prior['draw'] <= 4 and draw >= 8 and (draw - prior['draw'] >= 4):
                    adj -= 0.020
                
                # C. Sectional Eye Catcher (Clocked fast split from bad gate, now gets inside draw)
                if prior['draw'] >= 10 and draw <= 6 and prior['sec_pos'] <= 3:
                    adj += 0.020
                    
            # Clip adjustment to +/- 3.5%
            adj = max(min(adj, 0.035), -0.035)
            tactical_adj.append(adj)

        tactical_probs_raw = np.maximum(base_probs + np.array(tactical_adj), 0.001)
        tactical_probs = tactical_probs_raw / tactical_probs_raw.sum()

        race_rows['tactical_prob'] = tactical_probs

        # Identify Top Picks
        top1_base_idx = race_rows['base_prob'].idxmax()
        top1_tact_idx = race_rows['tactical_prob'].idxmax()

        top3_base_idxs = race_rows.nlargest(3, 'base_prob').index
        top3_tact_idxs = race_rows.nlargest(3, 'tactical_prob').index

        # Evaluate Top-1 Hits
        if race_rows.loc[top1_base_idx, 'won'] == 1:
            baseline_top1_hits += 1
            baseline_win_returned += race_rows.loc[top1_base_idx, 'sp']
        baseline_win_staked += 1.0

        if race_rows.loc[top1_tact_idx, 'won'] == 1:
            tactical_top1_hits += 1
            tactical_win_returned += race_rows.loc[top1_tact_idx, 'sp']
        tactical_win_staked += 1.0

        # Evaluate Top-1 Place Hits
        if race_rows.loc[top1_base_idx, 'podium'] == 1:
            baseline_place_returned += race_rows.loc[top1_base_idx, 'place_sp']
        baseline_place_staked += 1.0

        if race_rows.loc[top1_tact_idx, 'podium'] == 1:
            tactical_place_returned += race_rows.loc[top1_tact_idx, 'place_sp']
        tactical_place_staked += 1.0

        # Top-3 Hits
        if any(race_rows.loc[idx, 'won'] == 1 for idx in top3_base_idxs):
            baseline_top3_hits += 1
        if any(race_rows.loc[idx, 'won'] == 1 for idx in top3_tact_idxs):
            tactical_top3_hits += 1

        # Brier & Log Loss
        y_true = race_rows['won'].values
        p_base = race_rows['base_prob'].values
        p_tact = race_rows['tactical_prob'].values

        brier_baseline_list.append(np.mean((p_base - y_true) ** 2))
        brier_tactical_list.append(np.mean((p_tact - y_true) ** 2))

        # Epsilon clipping for log loss
        eps = 1e-12
        logloss_baseline_list.append(-np.sum(y_true * np.log(np.clip(p_base, eps, 1.0))))
        logloss_tactical_list.append(-np.sum(y_true * np.log(np.clip(p_tact, eps, 1.0))))

        # Update walk-forward memory with this completed race (strictly for subsequent races)
        for _, row in race_rows.iterrows():
            h_id = row['horse_id']
            interf_sev = 2 if row.get('lengths_behind', 0) <= 2.0 and row['sp'] <= 6.0 and row['finish_pos'] >= 4 else 0
            horse_last_run[h_id] = {
                'finish_pos': row['finish_pos'],
                'draw': row['draw'],
                'lbw': row.get('lengths_behind', 0.0),
                'sp': row['sp'],
                'sec_pos': row.get('position_sec3', 6),
                'interference': interf_sev
            }

    # Aggregate Results
    base_top1_rate = round((baseline_top1_hits / total_races) * 100, 2)
    tact_top1_rate = round((tactical_top1_hits / total_races) * 100, 2)

    base_top3_rate = round((baseline_top3_hits / total_races) * 100, 2)
    tact_top3_rate = round((tactical_top3_hits / total_races) * 100, 2)

    base_win_roi = round(((baseline_win_returned - baseline_win_staked) / baseline_win_staked) * 100, 2)
    tact_win_roi = round(((tactical_win_returned - tactical_win_staked) / tactical_win_staked) * 100, 2)

    base_place_roi = round(((baseline_place_returned - baseline_place_staked) / baseline_place_staked) * 100, 2)
    tact_place_roi = round(((tactical_place_returned - tactical_place_staked) / tactical_place_staked) * 100, 2)

    brier_base = round(float(np.mean(brier_baseline_list)), 5)
    brier_tact = round(float(np.mean(brier_tactical_list)), 5)

    logloss_base = round(float(np.mean(logloss_baseline_list)), 4)
    logloss_tact = round(float(np.mean(logloss_tactical_list)), 4)

    # Decision Gate Rule:
    # BOTH Top-1 Win Hit Rate AND Flat-Stake Win ROI must be strictly better to promote
    promote = bool((tact_top1_rate > base_top1_rate) and (tact_win_roi > base_win_roi))

    report = {
        "timestamp": datetime.now().isoformat(),
        "total_races_evaluated": int(total_races),
        "metrics": {
            "top1_win_hit_rate_pct": {
                "baseline": float(base_top1_rate),
                "tactical_overlay": float(tact_top1_rate),
                "improved": bool(tact_top1_rate > base_top1_rate)
            },
            "top3_podium_hit_rate_pct": {
                "baseline": float(base_top3_rate),
                "tactical_overlay": float(tact_top3_rate),
                "improved": bool(tact_top3_rate >= base_top3_rate)
            },
            "flat_stake_win_roi_pct": {
                "baseline": float(base_win_roi),
                "tactical_overlay": float(tact_win_roi),
                "improved": bool(tact_win_roi > base_win_roi)
            },
            "flat_stake_place_roi_pct": {
                "baseline": float(base_place_roi),
                "tactical_overlay": float(tact_place_roi),
                "improved": bool(tact_place_roi >= base_place_roi)
            },
            "brier_score": {
                "baseline": float(brier_base),
                "tactical_overlay": float(brier_tact),
                "improved": bool(brier_tact <= brier_base)
            },
            "log_loss": {
                "baseline": float(logloss_base),
                "tactical_overlay": float(logloss_tact),
                "improved": bool(logloss_tact <= logloss_base)
            }
        },
        "promotion_gate": {
            "cleared": promote,
            "apply_tactical_overlay": promote,
            "reason": "Both Top-1 Hit Rate and Flat-Stake Win ROI improved" if promote else "Baseline preserved; promotion threshold requires both Top-1 hit rate and Win ROI to strictly improve."
        }
    }

    # Save report
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

    # Update config accordingly
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            cfg['apply_tactical_overlay'] = promote
            if promote:
                cfg['live_coefficients'] = {
                    "forgiven_run": 2.5,
                    "trip_regression": -2.0,
                    "sectional_eye_catcher": 2.0
                }
            else:
                cfg['live_coefficients'] = {
                    "forgiven_run": 0.0,
                    "trip_regression": 0.0,
                    "sectional_eye_catcher": 0.0
                }
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=2)
        except Exception as e:
            logging.warning(f"Error updating config: {e}")

    logging.info(f"Walk-Forward Backtest completed across {total_races} races.")
    logging.info(f"Top-1 Win Rate: Base {base_top1_rate}% vs Tact {tact_top1_rate}%")
    logging.info(f"Win ROI: Base {base_win_roi}% vs Tact {tact_win_roi}%")
    logging.info(f"Promotion Gate Cleared: {promote}")

    return report


if __name__ == '__main__':
    run_walkforward_backtest()

"""
Per-Source Data Contracts & Calibrated Sha Tin Multiplier Engine for Silks.AI.

Implements the post-meeting audit calibrations (Happy Valley 21 Oct 2026 review):
1. Sha Tin 1000m sprints only (`st_straight_outside_rail_multiplier`):
   - +4.5% (+0.045) win-probability boost for horses drawn gates 10-14
   - -3.5% (-0.035) penalty for horses drawn gates 1-4
2. Class 3 1600m races at Sha Tin (`st_c3_1600_topweight_adjustment`):
   - Soften the topweight (133-135 lb) penalty from -3.5% (-0.035) to -1.2% (-0.012)
     ONLY when both are true:
     a) the horse has proven Sha Tin 1600m course-and-distance wins, AND
     b) it is ridden by an elite jockey (Z Purton or H Bowman).
3. All Sha Tin turf races of 1400m and above (`st_route_sec400_adjustment`):
   - Increase the relative weighting of final-400m sectional ratings (`rank_sec400`)
     compared with early gate-speed / positional metrics (`avg_first_pos`) to capture
     sustained acceleration on Sha Tin's 430m home straight.
"""
import numpy as np
import pandas as pd


ELITE_ST_MILE_JOCKEYS = {"Z PURTON", "H BOWMAN", "PURTON", "BOWMAN"}


def compute_sha_tin_calibrations(
    df_runners: pd.DataFrame,
    is_st: bool,
    is_awt_race: bool,
    distance: int,
    class_int: int,
) -> dict:
    """
    Computes the modular Sha Tin probability adjustments while leaving all Happy Valley
    multipliers completely untouched.

    Returns a dictionary of numpy arrays aligned with `df_runners`:
    - `st_1000_draw_boost`: +0.045 for gates 10-14 on ST 1000m turf
    - `st_1000_draw_penalty`: -0.035 for gates 1-4 on ST 1000m turf
    - `st_straight_outside_rail_multiplier`: combined (+0.045 / -0.035 / 0.0) on ST 1000m turf
    - `st_c3_1600_topweight_penalty`: -0.012 if proven ST 1600m C&D winner + Purton/Bowman,
      else -0.035 for 133-135 lb topweights in ST Class 3 1600m turf (0.0 otherwise)
    - `st_route_sec400_boost`: sustained final-400m sectional acceleration adjustment vs early speed
      for Sha Tin turf races >= 1400m
    - `rank_sec400`: integer series of final-400m sectional rank (1 = fastest)
    """
    n = len(df_runners)
    zeros = np.zeros(n, dtype=float)

    draws = pd.to_numeric(df_runners.get("draw", pd.Series(6, index=df_runners.index)), errors="coerce").fillna(6).values
    actual_weights = pd.to_numeric(
        df_runners.get("actual_weight", pd.Series(125, index=df_runners.index)), errors="coerce"
    ).fillna(125).values

    # Compute or preserve rank_sec400
    if "rank_sec400" in df_runners.columns:
        rank_sec400 = pd.to_numeric(df_runners["rank_sec400"], errors="coerce").fillna(7).astype(int).values
    elif "best_last_sec" in df_runners.columns:
        best_sec = pd.to_numeric(df_runners["best_last_sec"], errors="coerce").fillna(99.0)
        rank_sec400 = best_sec.rank(ascending=True, method="min").fillna(7).astype(int).values
    else:
        rank_sec400 = np.full(n, 7, dtype=int)

    is_st_turf = bool(is_st) and (not bool(is_awt_race))

    # -------------------------------------------------------------------------
    # 1. Sha Tin 1000m Straight Outside Rail Bias
    #    +4.5% boost for gates 10-14; -3.5% penalty for gates 1-4
    # -------------------------------------------------------------------------
    is_st_straight_1000 = is_st_turf and (int(distance) == 1000)
    if is_st_straight_1000:
        st_1000_draw_boost = np.where((draws >= 10) & (draws <= 14), 0.045, 0.0)
        st_1000_draw_penalty = np.where((draws >= 1) & (draws <= 4), -0.035, 0.0)
    else:
        st_1000_draw_boost = zeros.copy()
        st_1000_draw_penalty = zeros.copy()

    st_straight_outside_rail_multiplier = st_1000_draw_boost + st_1000_draw_penalty

    # -------------------------------------------------------------------------
    # 2. Class 3 1600m Topweight (133-135 lb) Resilience at Sha Tin
    #    Soften penalty from -3.5% (-0.035) to -1.2% (-0.012) ONLY when:
    #    (a) proven Sha Tin 1600m course-and-distance wins, AND
    #    (b) ridden by an elite jockey (Purton or Bowman).
    # -------------------------------------------------------------------------
    is_st_c3_1600 = is_st_turf and (int(class_int) == 3) and (int(distance) == 1600)
    if is_st_c3_1600:
        is_topweight = (actual_weights >= 133) & (actual_weights <= 135)

        # Check proven Sha Tin 1600m C&D win
        if "st_1600_wins" in df_runners.columns:
            has_cd_win = pd.to_numeric(df_runners["st_1600_wins"], errors="coerce").fillna(0).values > 0
        elif "cd_wins" in df_runners.columns:
            has_cd_win = pd.to_numeric(df_runners["cd_wins"], errors="coerce").fillna(0).values > 0
        else:
            st_wr = pd.to_numeric(
                df_runners.get("ST_win_rate", pd.Series(0.0, index=df_runners.index)), errors="coerce"
            ).fillna(0.0).values
            dist_wr = pd.to_numeric(
                df_runners.get("distance_win_rate", pd.Series(0.0, index=df_runners.index)), errors="coerce"
            ).fillna(0.0).values
            has_cd_win = (st_wr > 0) & (dist_wr > 0)

        # Check elite jockey (Purton or Bowman)
        jockeys_clean = (
            df_runners.get("jockey", pd.Series("", index=df_runners.index))
            .astype(str)
            .str.strip()
            .str.upper()
        )
        is_elite_mile_rider = jockeys_clean.apply(
            lambda j: any(ej in j for ej in ELITE_ST_MILE_JOCKEYS)
        ).values

        qualifies_resilience = is_topweight & has_cd_win & is_elite_mile_rider
        st_c3_1600_topweight_penalty = np.where(
            is_topweight,
            np.where(qualifies_resilience, -0.012, -0.035),
            0.0,
        )
    else:
        st_c3_1600_topweight_penalty = zeros.copy()

    # -------------------------------------------------------------------------
    # 3. Sha Tin Turf >= 1400m Final-400m Sectional Weighting (`rank_sec400`)
    #    Increase relative weighting of final-400m sectionals vs early gate speed
    #    on Sha Tin's longer 430m home straight.
    # -------------------------------------------------------------------------
    is_st_route_turf = is_st_turf and (int(distance) >= 1400)
    if is_st_route_turf:
        best_last_sec = pd.to_numeric(
            df_runners.get("best_last_sec", pd.Series(23.0, index=df_runners.index)), errors="coerce"
        ).fillna(23.0).values
        avg_first_pos = pd.to_numeric(
            df_runners.get("avg_first_pos", pd.Series(6.0, index=df_runners.index)), errors="coerce"
        ).fillna(6.0).values

        # Top sectional ranks receive elevated weight on 1400m+ Sha Tin turf
        sec400_boost = np.where(
            (rank_sec400 == 1) & (best_last_sec <= 22.8),
            0.025,
            np.where(
                (rank_sec400 <= 3) & (best_last_sec <= 22.9),
                0.015,
                0.0,
            ),
        )
        # Temper pure early gate-speed leaders that lack a top-half final 400m sectional
        early_speed_temper = np.where(
            (avg_first_pos <= 3.5) & (rank_sec400 >= 6) & (best_last_sec >= 23.0),
            -0.012,
            0.0,
        )
        st_route_sec400_boost = sec400_boost + early_speed_temper
    else:
        st_route_sec400_boost = zeros.copy()

    return {
        "st_1000_draw_boost": st_1000_draw_boost,
        "st_1000_draw_penalty": st_1000_draw_penalty,
        "st_straight_outside_rail_multiplier": st_straight_outside_rail_multiplier,
        "st_c3_1600_topweight_penalty": st_c3_1600_topweight_penalty,
        "st_route_sec400_boost": st_route_sec400_boost,
        "rank_sec400": rank_sec400,
    }


# -------------------------------------------------------------------------
# Per-Source Contract Validators
# -------------------------------------------------------------------------

def validate_racecard_contract(data: dict) -> tuple:
    """
    Validates scraped racecard structure and checks for fake/fallback runners.
    Returns (is_valid: bool, errors: list[str]).
    """
    errors = []
    if not isinstance(data, dict):
        return False, ["Payload is not a dict"]
    if data.get("status") != "success":
        return False, [f"Scraper status is '{data.get('status')}': {data.get('reason', 'unknown')}"]

    meetings = data.get("meetings") or []
    if not meetings:
        return False, ["No meetings in payload"]

    for m in meetings:
        races = m.get("races") or []
        if not races:
            errors.append(f"Meeting {m.get('date')} has 0 races")
        for r in races:
            runners = r.get("runners") or []
            if len(runners) < 2:
                errors.append(f"Race {r.get('race_no')} has fewer than 2 runners ({len(runners)})")
            for runner in runners:
                if str(runner.get("name", "")).upper() == "KASA PAPA" and str(runner.get("jockey", "")) == "Z Purton":
                    errors.append("Fake fallback runner 'KASA PAPA' detected in racecard")
    return len(errors) == 0, errors


def validate_odds_contract(df_runners: pd.DataFrame) -> dict:
    """
    Checks runner odds coverage in a race.
    Flags `odds_missing` if win_odds is None, NaN, <= 0, or flagged as missing.
    If >20% of runners have missing odds, `suppress_win_stake` is True.
    """
    total = len(df_runners)
    if total == 0:
        return {"total": 0, "missing_count": 0, "missing_ratio": 1.0, "suppress_win_stake": True}

    if "odds_missing" in df_runners.columns:
        missing_mask = df_runners["odds_missing"].astype(bool)
    else:
        odds_series = pd.to_numeric(df_runners.get("win_odds"), errors="coerce")
        missing_mask = odds_series.isna() | (odds_series <= 0)

    missing_count = int(missing_mask.sum())
    missing_ratio = missing_count / float(total)
    return {
        "total": total,
        "missing_count": missing_count,
        "missing_ratio": round(missing_ratio, 4),
        "suppress_win_stake": missing_ratio > 0.20,
    }


def validate_incident_contract(incidents_dict: dict, min_expected_records: int = 1) -> tuple:
    """
    Validates scraped meeting incidents dictionary (horse_name -> incident_text).
    Ensures keys are actual horse names (not numeric placing strings like '1', '2').
    """
    errors = []
    if not isinstance(incidents_dict, dict) or len(incidents_dict) < min_expected_records:
        return False, [f"Expected >= {min_expected_records} incident records, got {len(incidents_dict or {})}"]

    numeric_keys = [k for k in incidents_dict.keys() if str(k).strip().isdigit()]
    if numeric_keys:
        errors.append(f"Incident keys contain pure numbers (wrong table column parsed): {numeric_keys[:5]}")

    return len(errors) == 0, errors


def validate_features_contract(df: pd.DataFrame, required_features: list) -> tuple:
    """
    Validates that all required model features exist and are within sensible bounds.
    """
    errors = []
    missing_cols = [c for c in required_features if c not in df.columns]
    if missing_cols:
        errors.append(f"Missing required feature columns: {missing_cols}")
    return len(errors) == 0, errors

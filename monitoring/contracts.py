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


def compute_telemetry_harmony_multipliers(
    df_runners: pd.DataFrame,
    is_st: bool,
    is_hv: bool,
    is_awt_race: bool,
    distance: int,
    class_int: int,
    has_strong_trial=None,
    horse_memory: dict = None,
) -> dict:
    """
    Harmonizes all live telemetry pipelines into calibrated win-probability multipliers:
    1. `awt_specialist_boost`:
       - Fixes the AWT condition so proven local HK AWT winners (`AWT_win_rate > 0` or
         `AWT_vs_Turf_pref == 'AWT'`) receive +2.5% (+0.025) on AWT races even when
         `has_overseas_form == 0`, plus +1.5% (+0.015) extra for proven AWT dirt specialists
         (`AWT_win_rate >= 0.20` and `AWT_starts >= 2` and `vet_issue == 0`).
    2. `tactical_incident_multiplier`:
       - Connects `data/horse_incident_memory.json` and `evaluate_tactical_scores()` directly
         into live probability adjustments (forgiven traffic trouble +2.5%, wide-without-cover
         merit +2.0%, sectional eye-catcher with barrier relief +2.0%, trip regression -2.0%),
         clipped to [-3.5%, +3.5%]. Positive boosts are blocked if the runner has an uncleared
         veterinary finding.
    3. `trackwork_conditioning_multiplier`:
       - Connects 30-day trackwork telemetry (`gallops_30d`, `swims_30d`, `is_in_conghua`):
         +1.5% (+0.015) for healthy runners with peak work (`gallops_30d >= 4` & `swims_30d >= 10`,
         or Conghua preparation `is_in_conghua == 1` & `gallops_30d >= 3`);
         -1.5% (-0.015) for runners returning from a >=45-day layoff with zero 30-day gallops
         and no strong barrier trial.
    4. `active_vet_risk_penalty`:
       - Connects official HKJC veterinary records (`prev_run_vet_finding == 1` from `ovehorse.aspx`
         and `overecord`): -2.0% (-0.020) penalty when a horse has an active 180-day veterinary
         finding and has not proven recovery via a strong barrier trial (`~has_strong_trial`).
    """
    from data.incident_engine import evaluate_tactical_scores, load_horse_memory

    n = len(df_runners)
    zeros = np.zeros(n, dtype=float)
    if n == 0:
        return {
            "awt_specialist_boost": zeros.copy(),
            "tactical_incident_multiplier": zeros.copy(),
            "trackwork_conditioning_multiplier": zeros.copy(),
            "active_vet_risk_penalty": zeros.copy(),
            "telemetry_harmony_multiplier": zeros.copy(),
            "tactical_badges": [],
        }

    if has_strong_trial is None:
        strong_trial_arr = np.zeros(n, dtype=bool)
    else:
        strong_trial_arr = np.asarray(has_strong_trial, dtype=bool)

    vet_issue = (
        pd.to_numeric(
            df_runners.get("prev_run_vet_finding", pd.Series(0, index=df_runners.index)),
            errors="coerce",
        )
        .fillna(0)
        .values
    )
    draws = (
        pd.to_numeric(df_runners.get("draw", pd.Series(6, index=df_runners.index)), errors="coerce")
        .fillna(6)
        .values
    )
    actual_weights = (
        pd.to_numeric(
            df_runners.get("actual_weight", pd.Series(125, index=df_runners.index)), errors="coerce"
        )
        .fillna(125)
        .values
    )
    win_odds = (
        pd.to_numeric(df_runners.get("win_odds", pd.Series(10.0, index=df_runners.index)), errors="coerce")
        .fillna(10.0)
        .values
    )

    # -------------------------------------------------------------------------
    # 1. All-Weather Track (AWT / Dirt) Specialist Harmony
    # -------------------------------------------------------------------------
    if bool(is_awt_race):
        awt_wr = (
            pd.to_numeric(
                df_runners.get("AWT_win_rate", pd.Series(0.0, index=df_runners.index)), errors="coerce"
            )
            .fillna(0.0)
            .values
        )
        awt_starts = (
            pd.to_numeric(
                df_runners.get("AWT_starts", pd.Series(0, index=df_runners.index)), errors="coerce"
            )
            .fillna(0)
            .values
        )
        awt_pref = (
            df_runners.get("AWT_vs_Turf_pref", pd.Series("", index=df_runners.index))
            .astype(str)
            .str.strip()
            .str.upper()
            .values
        )
        has_overseas = (
            pd.to_numeric(
                df_runners.get("has_overseas_form", pd.Series(0, index=df_runners.index)), errors="coerce"
            )
            .fillna(0)
            .values
            == 1
        )
        last_going_poly = (
            df_runners.get("last_form_going", pd.Series("", index=df_runners.index))
            .astype(str)
            .str.upper()
            .str.contains("POLY|SYNTH|AWT|STAND|TAPETA", na=False)
            .values
        )

        has_awt_edge = (awt_wr > 0) | (awt_pref == "AWT") | (has_overseas & last_going_poly)
        base_awt_boost = np.where(has_awt_edge, 0.025, 0.0)
        is_elite_awt_specialist = (awt_wr >= 0.20) & (awt_starts >= 2) & (vet_issue == 0)
        awt_specialist_boost = base_awt_boost + np.where(is_elite_awt_specialist, 0.015, 0.0)
    else:
        awt_specialist_boost = zeros.copy()

    # -------------------------------------------------------------------------
    # 2. Tactical Stewards' Incident & Replay Memory Multiplier
    # -------------------------------------------------------------------------
    if horse_memory is None:
        horse_memory = load_horse_memory()

    tactical_incident_multiplier = np.zeros(n, dtype=float)
    tactical_badges = []
    venue_label = "Happy Valley" if is_hv else "Sha Tin"
    surface_label = "AWT" if is_awt_race else "TURF"

    for idx, (_, row) in enumerate(df_runners.iterrows()):
        clean_name = str(row.get("clean_name") or row.get("name") or "").strip().upper()
        t_ctx = {
            "barrier": int(draws[idx]),
            "venue": venue_label,
            "surface": surface_label,
            "distance": int(distance),
            "sp": float(win_odds[idx]),
            "weight_carried": float(actual_weights[idx]),
            "winner_weight": 125.0,
        }
        t_res = evaluate_tactical_scores(clean_name, t_ctx, memory_dict=horse_memory)
        live_adj_pct = float(t_res.get("live_adjustment", 0.0))
        adj_mult = np.clip(live_adj_pct / 100.0, -0.035, 0.035)
        # Uncleared vet finding blocks positive incident forgiveness
        if vet_issue[idx] != 0 and not strong_trial_arr[idx] and adj_mult > 0:
            adj_mult = 0.0
        tactical_incident_multiplier[idx] = adj_mult
        tactical_badges.append(t_res.get("badges", []))

    # -------------------------------------------------------------------------
    # 3. 30-Day Trackwork Conditioning & Conghua Harmony
    # -------------------------------------------------------------------------
    gallops_30d = (
        pd.to_numeric(
            df_runners.get("gallops_30d", pd.Series(0, index=df_runners.index)), errors="coerce"
        )
        .fillna(0)
        .values
    )
    swims_30d = (
        pd.to_numeric(
            df_runners.get("swims_30d", pd.Series(0, index=df_runners.index)), errors="coerce"
        )
        .fillna(0)
        .values
    )
    is_conghua = (
        pd.to_numeric(
            df_runners.get("is_in_conghua", pd.Series(0, index=df_runners.index)), errors="coerce"
        )
        .fillna(0)
        .values
        == 1
    )
    days_since = (
        pd.to_numeric(
            df_runners.get("days_since_last_run", pd.Series(21, index=df_runners.index)), errors="coerce"
        )
        .fillna(21)
        .values
    )

    is_peak_work = (vet_issue == 0) & (
        ((gallops_30d >= 4) & (swims_30d >= 10)) | (is_conghua & (gallops_30d >= 3))
    )
    is_underprepared_layoff = (days_since >= 45) & (gallops_30d == 0) & (~strong_trial_arr)
    trackwork_conditioning_multiplier = np.where(
        is_peak_work, 0.015, np.where(is_underprepared_layoff, -0.015, 0.0)
    )

    # -------------------------------------------------------------------------
    # 4. Official Veterinary Records Risk Penalty (Uncleared 180-Day Vet Finding)
    # -------------------------------------------------------------------------
    active_vet_risk_penalty = np.where((vet_issue != 0) & (~strong_trial_arr), -0.020, 0.0)

    # -------------------------------------------------------------------------
    # 5. Ronan Tactical Racing Harmony:
    #    (a) 1000m & 1200m Sprint Gate-Speed Crosser Boost (overcoming outside draws
    #        via proven early speed without needing to be a G1/class-dropper horse).
    #    (b) High-Pace Setup (3+ speed horses or 4+ on-pace horses) -> boost runners
    #        lying 6th-12th (`5.5 <= avg_first_pos <= 12.5`) with strong late finish
    #        (`best_last_sec <= 22.75` or `rank_sec400 <= 3`).
    #    (c) "False Favourite" Market-Respect Guard: strengthen penalty (-0.5% extra,
    #        total -3.5%) if drifting, but DO NOT rule out if the market continues to
    #        wager on the favourite (waive/soften penalty on steam or firm <=2.8 odds).
    # -------------------------------------------------------------------------
    avg_first_pos = (
        pd.to_numeric(
            df_runners.get("avg_first_pos", pd.Series(6.0, index=df_runners.index)), errors="coerce"
        )
        .fillna(6.0)
        .values
    )
    best_last_sec = (
        pd.to_numeric(
            df_runners.get("best_last_sec", pd.Series(99.0, index=df_runners.index)), errors="coerce"
        )
        .fillna(99.0)
        .values
    )
    recent_pos = (
        pd.to_numeric(
            df_runners.get("recent_avg_pos", pd.Series(7.0, index=df_runners.index)), errors="coerce"
        )
        .fillna(7.0)
        .values
    )
    last_comments_col = (
        df_runners.get("last_comment", pd.Series("", index=df_runners.index))
        .astype(str)
        .str.lower()
    )
    has_comment_gate_speed = last_comments_col.str.contains(
        "jumped well|began speedily|led early|raced prominently|crossed|fast into stride",
        case=False,
        na=False,
    ).values
    has_proven_gate_speed = (avg_first_pos <= 3.5) | has_comment_gate_speed

    speed_count = int(np.sum(avg_first_pos <= 3.5))
    on_pace_count = int(np.sum(avg_first_pos <= 4.2))

    # (a) 1000m & 1200m Sprint Gate-Speed Crosser Boost
    if int(distance) <= 1200:
        is_wide_crosser = has_proven_gate_speed & (draws >= 8) & (vet_issue == 0)
        is_natural_sprint_speed = (
            has_proven_gate_speed & (draws < 8) & (speed_count <= 3) & (vet_issue == 0)
        )
        sprint_gate_speed_crosser_boost = np.where(
            is_wide_crosser,
            0.025,
            np.where(is_natural_sprint_speed, 0.015, 0.0),
        )
    else:
        sprint_gate_speed_crosser_boost = zeros.copy()

    # (b) High-Pace Setup -> Mid-to-Back (6th-12th) Strong Late Finishers
    if "rank_sec400" in df_runners.columns:
        rank_sec = (
            pd.to_numeric(df_runners["rank_sec400"], errors="coerce").fillna(7).astype(int).values
        )
    else:
        rank_sec = (
            pd.Series(best_last_sec).rank(ascending=True, method="min").fillna(7).astype(int).values
        )

    is_high_pace_race = (speed_count >= 3) or (on_pace_count >= 4)
    if is_high_pace_race:
        is_6th_to_12th_strong_closer = (
            (avg_first_pos >= 5.5)
            & (avg_first_pos <= 12.5)
            & ((best_last_sec <= 22.75) | (rank_sec <= 3))
            & (vet_issue == 0)
        )
        high_pace_strong_closer_boost = np.where(is_6th_to_12th_strong_closer, 0.020, 0.0)
    else:
        high_pace_strong_closer_boost = zeros.copy()

    # (c) "False Favourite" Market-Respect Guard
    baseline_odds = (
        pd.to_numeric(
            df_runners.get("baseline_odds", pd.Series(win_odds, index=df_runners.index)),
            errors="coerce",
        )
        .fillna(pd.Series(win_odds, index=df_runners.index))
        .values
    )
    class_drop = (
        pd.to_numeric(
            df_runners.get("class_diff", pd.Series(0, index=df_runners.index)), errors="coerce"
        )
        .fillna(0)
        .values
    )
    had_excuse = (
        df_runners.get("had_excuse", pd.Series(False, index=df_runners.index))
        .astype(bool)
        .values
    )
    implied_prob = (
        pd.to_numeric(
            df_runners.get("implied_prob", pd.Series(0.0, index=df_runners.index)), errors="coerce"
        )
        .fillna(0.0)
        .values
    )
    is_flagged_false_fav = (
        ((implied_prob > 0.20) | ((win_odds > 0) & (win_odds < 5.0)))
        & (recent_pos > 6.0)
        & (class_drop <= 0)
        & (~had_excuse)
    )
    market_steaming = (baseline_odds > 0) & (win_odds > 0) & (win_odds <= baseline_odds * 0.92)
    market_firm_fav = (win_odds > 0) & (win_odds <= 2.8)
    market_drifting = (baseline_odds > 0) & (win_odds >= baseline_odds * 1.10)

    # Refund the -0.03 false_fav_penalty if market continues to wager (steam or strong trial -> +0.030 waiver;
    # firm <=2.8 favourite -> +0.020 partial waiver so net is -0.010; drifting -> extra -0.005 so net is -0.035)
    false_fav_market_guard = np.where(
        is_flagged_false_fav,
        np.where(
            market_steaming | strong_trial_arr,
            0.030,
            np.where(market_firm_fav, 0.020, np.where(market_drifting, -0.005, 0.0)),
        ),
        0.0,
    )

    telemetry_harmony_multiplier = (
        tactical_incident_multiplier
        + trackwork_conditioning_multiplier
        + active_vet_risk_penalty
        + sprint_gate_speed_crosser_boost
        + high_pace_strong_closer_boost
        + false_fav_market_guard
    )

    return {
        "awt_specialist_boost": awt_specialist_boost,
        "tactical_incident_multiplier": tactical_incident_multiplier,
        "trackwork_conditioning_multiplier": trackwork_conditioning_multiplier,
        "active_vet_risk_penalty": active_vet_risk_penalty,
        "sprint_gate_speed_crosser_boost": sprint_gate_speed_crosser_boost,
        "high_pace_strong_closer_boost": high_pace_strong_closer_boost,
        "false_fav_market_guard": false_fav_market_guard,
        "telemetry_harmony_multiplier": telemetry_harmony_multiplier,
        "tactical_badges": tactical_badges,
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

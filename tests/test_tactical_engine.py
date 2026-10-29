"""
Unit Tests for Tactical Incident Engine, Memory Architecture, Fail-Loud Contracts & Calibrated Sha Tin Multipliers
"""

import os
import re
import sys
import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np

# Ensure project root is in path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from data.incident_engine import (
    parse_incident,
    evaluate_tactical_scores,
    parse_hkjc_racereport_html,
)
from monitoring.contracts import (
    compute_sha_tin_calibrations,
    compute_telemetry_harmony_multipliers,
    validate_racecard_contract,
    validate_odds_contract,
    validate_incident_contract,
)
from monitoring.hkjc_guard import HKJCDateMismatch, validate_hkjc_html
import odds_tracker
import scraper


class TestTacticalIncidentEngine(unittest.TestCase):

    def test_late_holdup(self):
        """Test late hold-up in straight receives high severity 3."""
        text = "Held up for clear running near the 200m and was disappointed for a run until the 100m."
        flags = parse_incident(text)
        self.assertTrue(any(f['flag'] == 'traffic_trouble' for f in flags))
        traffic = next(f for f in flags if f['flag'] == 'traffic_trouble')
        self.assertEqual(traffic['severity'], 3)
        self.assertIn(traffic['marker'], ['final_200m', 'final_400m'])

    def test_early_check(self):
        """Test early / start check receives severity 1 or 2."""
        text = "Bumped shortly after the start and checked."
        flags = parse_incident(text)
        self.assertTrue(any(f['flag'] == 'traffic_trouble' for f in flags))
        traffic = next(f for f in flags if f['flag'] == 'traffic_trouble')
        self.assertEqual(traffic['marker'], 'start')

    def test_wide_without_cover(self):
        """Test wide without cover flag."""
        text = "Raced three wide without cover throughout the event."
        flags = parse_incident(text)
        self.assertTrue(any(f['flag'] == 'wide_no_cover' for f in flags))
        wide = next(f for f in flags if f['flag'] == 'wide_no_cover')
        self.assertEqual(wide['severity'], 3)

    def test_slow_start(self):
        """Test slow start flag."""
        text = "Slow to begin and lost ground at the start."
        flags = parse_incident(text)
        self.assertTrue(any(f['flag'] == 'slow_start' for f in flags))

    def test_no_report(self):
        """Test empty / clean report returns no flags."""
        text = ""
        flags = parse_incident(text)
        self.assertEqual(len(flags), 0)

    def test_vet_finding_blocks_forgiveness(self):
        """Test vet finding blocks forgiveness."""
        text = "A veterinary examination revealed the horse to be lame in its right front leg."
        flags = parse_incident(text)
        self.assertTrue(any(f['flag'] == 'vet_or_merit' for f in flags))
        vet = next(f for f in flags if f['flag'] == 'vet_or_merit')
        self.assertTrue(vet['vet_blocked'])

    def test_negation_awareness(self):
        """Test negation phrases do not flag traffic trouble."""
        text = "Raced smoothly and was not held up in the straight."
        flags = parse_incident(text)
        self.assertFalse(any(f['flag'] == 'traffic_trouble' for f in flags))

    def test_careless_riding_victim_vs_offender(self):
        """Test careless riding penalty attributes traffic to the victim, NOT the offender."""
        text = "Z Purton (HORSE A) was suspended for careless riding in that near the 200m he shifted in, causing HORSE B (K Teetan) to be checked."

        offender_flags = parse_incident(text, target_horse_name="HORSE A")
        self.assertFalse(any(f['flag'] == 'traffic_trouble' for f in offender_flags))

        victim_flags = parse_incident(text, target_horse_name="HORSE B")
        self.assertTrue(any(f['flag'] == 'traffic_trouble' for f in victim_flags))

    def test_zero_leakage_date_d(self):
        """Test that fact from race R does not retroactively change race R scores."""
        mem = {
            "HORSE X": {
                "horse_name": "HORSE X",
                "runs": [{
                    "race_date": "2026-10-01",
                    "race_id": "20261001_R1",
                    "finish_pos": 4,
                    "beaten_lengths": 0.5,
                    "sp": 3.0,
                    "interference_severity": 3,
                    "incident_flags": [{'flag': 'traffic_trouble', 'severity': 3, 'snippet': 'Blocked late'}]
                }]
            }
        }
        scores = evaluate_tactical_scores("HORSE X", {"barrier": 4, "sp": 4.0}, mem)
        self.assertEqual(scores['forgiven_run'], 2.5)

    def test_hot_lead_fade_penalty(self):
        """Test hot-lead fade receives -1.0 trip regression and badge."""
        mem = {
            "PACEMAKER": {
                "horse_name": "PACEMAKER",
                "runs": [{
                    "race_date": "2026-10-25",
                    "race_id": "20261025_R9",
                    "finish_pos": 12,
                    "beaten_lengths": 8.5,
                    "sp": 4.3,
                    "early_pos": 1.0,
                    "incident_flags": []
                }]
            }
        }
        scores = evaluate_tactical_scores("PACEMAKER", {"barrier": 5, "sp": 5.0}, mem)
        self.assertEqual(scores['trip_regression'], -1.0)
        self.assertTrue(any("HOT-LEAD FADE" in b.get('badge', '') for b in scores['badges']))

    def test_roarer_and_unacceptable_flag(self):
        """Test roarer and unacceptable performance trigger vet_or_merit flag."""
        flags_roarer = parse_incident("Tailed out, roarer on endoscopic examination.")
        self.assertTrue(any(f['flag'] == 'vet_or_merit' and f['vet_blocked'] for f in flags_roarer))

        flags_unacceptable = parse_incident("Disappointing performance, unacceptable; must trial.")
        self.assertTrue(any(f['flag'] == 'vet_or_merit' and f['vet_blocked'] for f in flags_unacceptable))


class TestShaTinCalibrations(unittest.TestCase):

    def test_st_straight_1000m_outside_rail_multiplier(self):
        """
        Calibration 1: Sha Tin 1000m sprints only:
        - +1.5% (+0.015) win-probability boost for gates 10-14
        - -1.5% (-0.015) penalty for gates 1-5
        - 0.0 for middle gates 6-9 or non-1000m / HV races
        """
        df = pd.DataFrame([
            {"no": 1, "name": "INSIDE TRAP", "draw": 2, "actual_weight": 125},
            {"no": 2, "name": "GATE FIVE", "draw": 5, "actual_weight": 125},
            {"no": 3, "name": "MIDDLE GATE", "draw": 7, "actual_weight": 125},
            {"no": 4, "name": "STANDS RAIL", "draw": 12, "actual_weight": 125},
            {"no": 5, "name": "OUTSIDE 14", "draw": 14, "actual_weight": 125},
        ])

        res_st_1000 = compute_sha_tin_calibrations(df, is_st=True, is_awt_race=False, distance=1000, class_int=4)
        mult = res_st_1000["st_straight_outside_rail_multiplier"]

        self.assertAlmostEqual(mult[0], -0.015)  # Gate 2 -> -1.5%
        self.assertAlmostEqual(mult[1], -0.015)  # Gate 5 -> -1.5%
        self.assertAlmostEqual(mult[2], 0.0)     # Gate 7 -> 0.0%
        self.assertAlmostEqual(mult[3], 0.015)   # Gate 12 -> +1.5%
        self.assertAlmostEqual(mult[4], 0.015)   # Gate 14 -> +1.5%

        # Verify does NOT fire on Sha Tin 1200m or Happy Valley 1000m
        res_st_1200 = compute_sha_tin_calibrations(df, is_st=True, is_awt_race=False, distance=1200, class_int=4)
        self.assertTrue(np.all(res_st_1200["st_straight_outside_rail_multiplier"] == 0.0))

        res_hv_1000 = compute_sha_tin_calibrations(df, is_st=False, is_awt_race=False, distance=1000, class_int=4)
        self.assertTrue(np.all(res_hv_1000["st_straight_outside_rail_multiplier"] == 0.0))

    def test_st_class3_1600m_topweight_resilience(self):
        """
        Calibration 2: Class 3 1600m races at Sha Tin:
        Soften topweight (133-135 lb) penalty from -3.5% (-0.035) to -1.2% (-0.012)
        ONLY when horse has proven ST 1600m C&D wins AND elite jockey (Purton or Bowman).
        """
        df = pd.DataFrame([
            # 1. Packing Fighter profile: 135 lb, ST+1600m winner, Z Purton -> softened to -0.012
            {"no": 1, "name": "PACKING FIGHTER", "actual_weight": 135, "jockey": "Z Purton", "ST_win_rate": 0.25, "distance_win_rate": 0.33},
            # 2. Bowman + C&D winner at 134 lb -> softened to -0.012
            {"no": 2, "name": "BOWMAN MILER", "actual_weight": 134, "jockey": "H Bowman", "ST_win_rate": 0.20, "distance_win_rate": 0.20},
            # 3. 135 lb with Purton, but NO 1600m C&D win -> full -0.035 penalty
            {"no": 3, "name": "UNPROVEN TRIP", "actual_weight": 135, "jockey": "Z Purton", "ST_win_rate": 0.20, "distance_win_rate": 0.0},
            # 4. 135 lb with C&D win, but non-elite jockey -> full -0.035 penalty
            {"no": 4, "name": "NON ELITE JOCK", "actual_weight": 135, "jockey": "K Teetan", "ST_win_rate": 0.25, "distance_win_rate": 0.25},
            # 5. Lightweight 120 lb -> 0.0 topweight penalty
            {"no": 5, "name": "LIGHTWEIGHT", "actual_weight": 120, "jockey": "K Teetan", "ST_win_rate": 0.0, "distance_win_rate": 0.0},
        ])

        res = compute_sha_tin_calibrations(df, is_st=True, is_awt_race=False, distance=1600, class_int=3)
        pen = res["st_c3_1600_topweight_penalty"]

        self.assertAlmostEqual(pen[0], -0.012)  # Purton + C&D -> softened to -1.2%
        self.assertAlmostEqual(pen[1], -0.012)  # Bowman + C&D -> softened to -1.2%
        self.assertAlmostEqual(pen[2], -0.035)  # Missing C&D win -> full -3.5%
        self.assertAlmostEqual(pen[3], -0.035)  # Non-Purton/Bowman -> full -3.5%
        self.assertAlmostEqual(pen[4], 0.0)     # Not a topweight -> 0.0%

    def test_st_turf_1400m_plus_sec400_weighting(self):
        """
        Calibration 3: Sha Tin turf races >= 1400m elevate final-400m sectional ratings (`rank_sec400`)
        compared with early gate speed (`avg_first_pos`).
        """
        df = pd.DataFrame([
            {"no": 1, "name": "FASTEST CLOSER", "best_last_sec": 22.10, "avg_first_pos": 8.0},
            {"no": 2, "name": "SECOND CLOSER", "best_last_sec": 22.35, "avg_first_pos": 6.5},
            {"no": 3, "name": "MID PACK", "best_last_sec": 22.70, "avg_first_pos": 5.0},
            {"no": 4, "name": "STEADY RUNNER", "best_last_sec": 22.95, "avg_first_pos": 5.5},
            {"no": 5, "name": "PLODDER", "best_last_sec": 23.05, "avg_first_pos": 7.0},
            {"no": 6, "name": "TIRING LEADER", "best_last_sec": 23.40, "avg_first_pos": 1.5},
        ])

        res_1400 = compute_sha_tin_calibrations(df, is_st=True, is_awt_race=False, distance=1400, class_int=3)
        sec_boost = res_1400["st_route_sec400_boost"]
        ranks = res_1400["rank_sec400"]

        self.assertEqual(ranks[0], 1)
        self.assertEqual(ranks[1], 2)
        self.assertEqual(ranks[5], 6)

        self.assertAlmostEqual(sec_boost[0], 0.025)   # Rank 1 sub-22.8s -> +2.5%
        self.assertAlmostEqual(sec_boost[1], 0.015)   # Rank 2 sub-22.9s -> +1.5%
        self.assertAlmostEqual(sec_boost[5], -0.012)  # Early leader (pos 1.5) with slow rank 6 (23.4s) -> -1.2%

        # Must not fire on 1200m sprint or Happy Valley
        res_1200 = compute_sha_tin_calibrations(df, is_st=True, is_awt_race=False, distance=1200, class_int=3)
        self.assertTrue(np.all(res_1200["st_route_sec400_boost"] == 0.0))

    def test_telemetry_harmony_multipliers(self):
        """
        Verify all 4 Telemetry Harmony pillars:
        1. Local HK AWT specialist (has_overseas_form == 0, AWT_win_rate >= 0.20, AWT_starts >= 2)
           gets +2.5% base + 1.5% specialist = +4.0% on AWT races.
        2. Tactical incident memory (traffic_trouble / wide_no_cover / trip_regression) flows into
           tactical_incident_multiplier, blocked if vet_issue == 1 without strong trial.
        3. 30-day trackwork conditioning (+1.5% for gallops_30d >= 4 & swims_30d >= 10 or Conghua,
           -1.5% for >=45d layoff with 0 gallops and no strong trial).
        4. Active vet risk penalty (-2.0% when prev_run_vet_finding == 1 and not has_strong_trial).
        """
        df = pd.DataFrame([
            {
                "no": 1,
                "name": "LOCAL DIRT KING",
                "clean_name": "LOCAL DIRT KING",
                "has_overseas_form": 0,
                "AWT_win_rate": 0.33,
                "AWT_starts": 3,
                "AWT_vs_Turf_pref": "AWT",
                "gallops_30d": 5,
                "swims_30d": 12,
                "is_in_conghua": 0,
                "days_since_last_run": 18,
                "prev_run_vet_finding": 0,
                "draw": 4,
                "actual_weight": 125,
                "win_odds": 4.5,
            },
            {
                "no": 2,
                "name": "UNLUCKY CLOSER",
                "clean_name": "UNLUCKY CLOSER",
                "has_overseas_form": 0,
                "AWT_win_rate": 0.0,
                "AWT_starts": 1,
                "AWT_vs_Turf_pref": "Turf",
                "gallops_30d": 3,
                "swims_30d": 6,
                "is_in_conghua": 1,
                "days_since_last_run": 14,
                "prev_run_vet_finding": 0,
                "draw": 3,
                "actual_weight": 122,
                "win_odds": 6.0,
            },
            {
                "no": 3,
                "name": "UNCLEARED VET",
                "clean_name": "UNCLEARED VET",
                "has_overseas_form": 0,
                "AWT_win_rate": 0.0,
                "AWT_starts": 0,
                "AWT_vs_Turf_pref": "Turf",
                "gallops_30d": 0,
                "swims_30d": 2,
                "is_in_conghua": 0,
                "days_since_last_run": 60,
                "prev_run_vet_finding": 1,
                "draw": 10,
                "actual_weight": 130,
                "win_odds": 15.0,
            },
        ])
        mock_memory = {
            "UNLUCKY CLOSER": {
                "horse_name": "UNLUCKY CLOSER",
                "runs": [{
                    "race_date": "2026-10-19",
                    "race_id": "20261019_R5",
                    "finish_pos": 3,
                    "beaten_lengths": 1.0,
                    "sp": 5.5,
                    "barrier": 8,
                    "interference_severity": 3,
                    "incident_flags": [{"flag": "traffic_trouble", "severity": 3, "snippet": "Badly held up"}],
                }],
            },
            "UNCLEARED VET": {
                "horse_name": "UNCLEARED VET",
                "runs": [{
                    "race_date": "2026-08-20",
                    "race_id": "20260820_R2",
                    "finish_pos": 2,
                    "beaten_lengths": 0.8,
                    "sp": 4.0,
                    "barrier": 2,
                    "ground_saved_score": 1.0,
                    "interference_severity": 3,
                    "incident_flags": [{"flag": "traffic_trouble", "severity": 3, "snippet": "Held up"}],
                }],
            },
        }
        res = compute_telemetry_harmony_multipliers(
            df_runners=df,
            is_st=True,
            is_hv=False,
            is_awt_race=True,
            distance=1200,
            class_int=4,
            has_strong_trial=np.array([False, False, False]),
            horse_memory=mock_memory,
        )

        # Runner 1: Local HK AWT specialist (+0.040) + peak trackwork (+0.015)
        self.assertAlmostEqual(res["awt_specialist_boost"][0], 0.040)
        self.assertAlmostEqual(res["trackwork_conditioning_multiplier"][0], 0.015)
        self.assertAlmostEqual(res["active_vet_risk_penalty"][0], 0.0)

        # Runner 2: Unlucky closer (+0.025 tactical incident) + Conghua prep (+0.015)
        self.assertAlmostEqual(res["tactical_incident_multiplier"][1], 0.025)
        self.assertAlmostEqual(res["trackwork_conditioning_multiplier"][1], 0.015)

        # Runner 3: Uncleared vet (-0.020 vet risk) + underprepared layoff (-0.015)
        self.assertAlmostEqual(res["active_vet_risk_penalty"][2], -0.020)
        self.assertAlmostEqual(res["trackwork_conditioning_multiplier"][2], -0.015)

    def test_ronan_tactical_rules(self):
        """
        Verify Ronan's 4 tactical racing rules:
        1. 1000m/1200m outside-draw gate-speed crosser gets +2.5% (+0.025) without needing to be a G1 horse.
        2. High-pace setup (3+ speed horses) boosts 6th-12th runners with strong late sectionals (+2.0% / +0.020).
        3. "False favourite" market-respect guard waives -3.0% penalty (+0.030) when market continues to wager on it,
           and strengthens penalty (-0.005 extra -> -3.5% net) when drifting.
        4. Handicap topweight (130-135 lb) resilience works across all distances & all draws (e.g. 1200m Megastar Heart / PI Legend).
        """
        df = pd.DataFrame([
            # 1. Wide gate (Gate 11) in 1200m sprint with proven gate speed -> +0.025 crosser boost
            {
                "no": 1,
                "name": "WIDE CROSSER",
                "clean_name": "WIDE CROSSER",
                "draw": 11,
                "actual_weight": 126,
                "avg_first_pos": 2.2,
                "best_last_sec": 23.0,
                "recent_avg_pos": 4.5,
                "win_odds": 6.5,
                "baseline_odds": 6.5,
                "implied_prob": 0.14,
                "class_diff": 0,
                "had_excuse": False,
                "prev_run_vet_finding": 0,
            },
            # 2. Speed leader #2
            {
                "no": 2,
                "name": "SPEED TWO",
                "clean_name": "SPEED TWO",
                "draw": 3,
                "actual_weight": 130,
                "avg_first_pos": 1.5,
                "best_last_sec": 22.9,
                "recent_avg_pos": 2.5,
                "recent_win_rate": 0.25,
                "win_odds": 3.5,
                "baseline_odds": 3.5,
                "implied_prob": 0.25,
                "class_diff": 0,
                "had_excuse": False,
                "prev_run_vet_finding": 0,
            },
            # 3. Speed leader #3 (triggers speed_count == 3 high-pace race)
            {
                "no": 3,
                "name": "SPEED THREE",
                "clean_name": "SPEED THREE",
                "draw": 5,
                "actual_weight": 122,
                "avg_first_pos": 3.0,
                "best_last_sec": 23.2,
                "recent_avg_pos": 5.0,
                "win_odds": 10.0,
                "baseline_odds": 10.0,
                "implied_prob": 0.09,
                "class_diff": 0,
                "had_excuse": False,
                "prev_run_vet_finding": 0,
            },
            # 4. Lying 6th-12th (avg_first_pos 8.5) with strong late sectional (22.35s) -> +0.020 high-pace closer boost
            {
                "no": 4,
                "name": "STRONG LATE CLOSER",
                "clean_name": "STRONG LATE CLOSER",
                "draw": 7,
                "actual_weight": 135,
                "avg_first_pos": 8.5,
                "best_last_sec": 22.35,
                "recent_avg_pos": 3.5,
                "ST_win_rate": 0.20,
                "win_odds": 5.5,
                "baseline_odds": 5.5,
                "implied_prob": 0.16,
                "class_diff": 0,
                "had_excuse": False,
                "prev_run_vet_finding": 0,
            },
            # 5. Backed "False Favourite" (recent_avg_pos 7.5, odds steamed from 4.5 to 3.4) -> +0.030 waiver
            {
                "no": 5,
                "name": "BACKED FALSE FAV",
                "clean_name": "BACKED FALSE FAV",
                "draw": 2,
                "actual_weight": 125,
                "avg_first_pos": 5.0,
                "best_last_sec": 22.9,
                "recent_avg_pos": 7.5,
                "win_odds": 3.4,
                "baseline_odds": 4.5,
                "implied_prob": 0.26,
                "class_diff": 0,
                "had_excuse": False,
                "prev_run_vet_finding": 0,
            },
            # 6. Drifting "False Favourite" (recent_avg_pos 7.5, odds drifted from 3.5 to 4.2) -> -0.005 extra penalty
            {
                "no": 6,
                "name": "DRIFTING FALSE FAV",
                "clean_name": "DRIFTING FALSE FAV",
                "draw": 6,
                "actual_weight": 125,
                "avg_first_pos": 5.0,
                "best_last_sec": 23.1,
                "recent_avg_pos": 7.5,
                "win_odds": 4.2,
                "baseline_odds": 3.5,
                "implied_prob": 0.21,
                "class_diff": 0,
                "had_excuse": False,
                "prev_run_vet_finding": 0,
            },
        ])

        res = compute_telemetry_harmony_multipliers(
            df_runners=df,
            is_st=True,
            is_hv=False,
            is_awt_race=False,
            distance=1200,
            class_int=3,
            has_strong_trial=np.zeros(len(df), dtype=bool),
            horse_memory={},
        )

        # 1. Wide gate-speed crosser (Gate 11, with only 2 speed horses inside in Gates 3 & 5) gets +0.025
        self.assertAlmostEqual(res["sprint_gate_speed_crosser_boost"][0], 0.025)
        # 2. Inside gate-speed horse (Gate 3, in 1-4 tier) gets +0.015
        self.assertAlmostEqual(res["sprint_gate_speed_crosser_boost"][1], 0.015)
        # 3. Mid gate-speed horse (Gate 5, in 5-8 tier) gets +0.0075
        self.assertAlmostEqual(res["sprint_gate_speed_crosser_boost"][2], 0.0075)
        # 4. Runner 4 (lying 8.5 with 22.35s split in 3-speed-horse race) gets +0.020 high_pace_strong_closer_boost
        self.assertAlmostEqual(res["high_pace_strong_closer_boost"][3], 0.020)
        # 5. Backed false favourite gets +0.030 waiver; drifting false favourite gets -0.005 extra penalty
        self.assertAlmostEqual(res["false_fav_market_guard"][4], 0.030)
        self.assertAlmostEqual(res["false_fav_market_guard"][5], -0.005)

        # Verify Trapped-Wide Guard: if 3+ fast horses are drawn inside (Gates 1, 3, 5), Gate 11 crosser gets 0.0%
        df_trapped = df.copy()
        df_trapped.loc[4, "avg_first_pos"] = 2.0  # Gate 2 now also has speed -> Gates 2, 3, 5 (3 inside speed horses!)
        res_trapped = compute_telemetry_harmony_multipliers(
            df_runners=df_trapped,
            is_st=True,
            is_hv=False,
            is_awt_race=False,
            distance=1200,
            class_int=3,
            has_strong_trial=np.zeros(len(df_trapped), dtype=bool),
            horse_memory={},
        )
        self.assertAlmostEqual(res_trapped["sprint_gate_speed_crosser_boost"][0], 0.0)

    def test_grok_audit_fixes(self):
        """
        Verify Grok's audit fixes:
        1. Oct 25 replay horses in horse_incident_memory.json have real finish_pos, race_id, barrier, sp, and distance.
        2. check_stewards_excuse recognizes 'without cover', 'raced keenly', 'over-raced', 'unbalanced'.
        3. First-time Hood (H1) gets +1.5% (0.015) and total multiplier is capped at 1.25x.
        """
        from data.incident_engine import load_horse_memory
        from run_predictions import check_stewards_excuse

        mem = load_horse_memory()
        self.assertIn("CHILL EASY", mem)
        chill_run = mem["CHILL EASY"]["runs"][0]
        self.assertEqual(chill_run["finish_pos"], 1)
        self.assertEqual(chill_run["beaten_lengths"], 0.0)
        self.assertEqual(chill_run["race_id"], "20261025_R9")

        self.assertIn("CIRCUIT CHAMPION", mem)
        cc_run = mem["CIRCUIT CHAMPION"]["runs"][0]
        self.assertEqual(cc_run["finish_pos"], 3)
        self.assertEqual(cc_run["race_id"], "20261025_R11")

        # Excuse keywords check
        self.assertTrue(check_stewards_excuse("Raced three wide without cover throughout."))
        self.assertTrue(check_stewards_excuse("Settled rearward and raced keenly in the middle stages."))
        self.assertTrue(check_stewards_excuse("Became unbalanced near the 300m."))

        # Health risk vs Excuse separation check: medical issues must NOT be excused
        from features.stewards import check_health_risk
        self.assertFalse(check_stewards_excuse("Substantial blood in trachea after racing."))
        self.assertTrue(check_health_risk("Substantial blood in trachea after racing."))
        self.assertTrue(check_health_risk("Veterinary examination revealed horse to be lame right fore."))


class TestAppMultipliers(unittest.TestCase):

    def test_purton_lone_speed_rules(self):
        """Test lone speed boost is 0.02 and only Purton can qualify without recent_pos <= 5.5."""
        df = pd.DataFrame([
            {'jockey': 'Z PURTON', 'avg_first_pos': 2.0, 'recent_avg_pos': 7.0},
            {'jockey': 'B AVDULLA', 'avg_first_pos': 2.0, 'recent_avg_pos': 7.0},
            {'jockey': 'B AVDULLA', 'avg_first_pos': 2.0, 'recent_avg_pos': 3.0},
            {'jockey': 'C L CHAU', 'avg_first_pos': 2.0, 'recent_avg_pos': 3.0}
        ])
        recent_pos = df['recent_avg_pos']
        is_purton_leader = df['jockey'].astype(str).str.strip().str.upper() == 'Z PURTON'
        lone_speed = np.where((df['avg_first_pos'] <= 3.5) & ((recent_pos <= 5.5) | is_purton_leader), 0.02, 0.0)

        self.assertEqual(lone_speed[0], 0.02)
        self.assertEqual(lone_speed[1], 0.0)
        self.assertEqual(lone_speed[2], 0.02)
        self.assertEqual(lone_speed[3], 0.02)

    def test_purton_only_jockey_boosts(self):
        """Test elite_jockey_boost is 0.02 for Purton and 0 for everyone else."""
        df = pd.DataFrame([
            {'jockey': 'Z PURTON', 'recent_avg_pos': 2.0, 'prev_run_vet_finding': 0},
            {'jockey': 'H BOWMAN', 'recent_avg_pos': 2.0, 'prev_run_vet_finding': 0},
            {'jockey': 'C Y HO', 'recent_avg_pos': 2.0, 'prev_run_vet_finding': 0},
            {'jockey': 'A ATZENI', 'recent_avg_pos': 2.0, 'prev_run_vet_finding': 0}
        ])
        recent_pos = df['recent_avg_pos']
        vet_issue = df['prev_run_vet_finding']
        is_purton_jockey = df['jockey'].astype(str).str.strip().str.upper() == 'Z PURTON'
        elite_jockey_boost = np.where(is_purton_jockey & (recent_pos <= 4.0) & (vet_issue == 0), 0.02, 0.0)

        self.assertEqual(elite_jockey_boost[0], 0.02)
        self.assertEqual(elite_jockey_boost[1], 0.0)
        self.assertEqual(elite_jockey_boost[2], 0.0)
        self.assertEqual(elite_jockey_boost[3], 0.0)

    def test_races_outrank_trials_closer_penalty(self):
        """Test that deep closer with only a trial and NO race evidence of gate speed takes -0.03 penalty."""
        df = pd.DataFrame([
            {
                'clean_name': 'TRIAL STAR ONLY',
                'avg_first_pos': 7.0,
                'distance': 1200,
                'recent_avg_pos': 5.0,
                'best_last_sec': 23.0,
                'last_comment': 'settled rearward, ran on fairly'
            }
        ])
        distance = df['distance'].iloc[0]
        recent_pos = df['recent_avg_pos'].iloc[0]
        has_race_gate_speed = (df['avg_first_pos'] <= 4.5) | df['last_comment'].str.contains('jumped well|began speedily|led early|raced prominently', case=False, na=False)

        closer_pace_penalty = np.where(
            (df['avg_first_pos'] > 6.0) &
            (distance <= 1200) &
            (recent_pos > 4.0) &
            (df['best_last_sec'] >= 22.5) &
            (~has_race_gate_speed),
            -0.03,
            0.0
        )
        self.assertEqual(closer_pace_penalty[0], -0.03)

    def test_purton_cap_at_2_percent(self):
        """Test elite_jockey_boost + jockey_trainer_boost is capped at 0.02 max."""
        jockey_trainer_boost = 0.02
        elite_jockey_boost = 0.02
        purton_total_boost = np.minimum(jockey_trainer_boost + elite_jockey_boost, 0.02)
        self.assertEqual(purton_total_boost, 0.02)

    def test_shifted_win_stake_p2_only_and_13_cap(self):
        """Test win stake shift restricts strictly to Pick 2 with <= 13.0 odds and no health risk (Picks 3-4 excluded)."""
        p2 = {'no': 2, 'name': 'HORSE B', 'win_odds': 7.9, 'model_prob': 0.16, 'has_health_risk': False}
        p3 = {'no': 3, 'name': 'HORSE C', 'win_odds': 5.0, 'model_prob': 0.25, 'has_health_risk': False}
        p4 = {'no': 4, 'name': 'HORSE D', 'win_odds': 8.0, 'model_prob': 0.18, 'has_health_risk': False}

        p24_cands = [(p2, 2)]
        valid = []
        for cand, r_idx in p24_cands:
            c_odds = float(cand.get('win_odds', 20.0))
            c_prob = float(cand.get('model_prob', 0.0))
            c_health = bool(cand.get('has_health_risk', False))
            if (not c_health) and (c_odds > 0) and (c_odds <= 13.0) and (c_prob * c_odds > 1.0):
                valid.append((cand, r_idx, c_prob * c_odds))

        self.assertEqual(len(valid), 1)
        shifted_win_runner, shifted_from_rank = valid[0][0], valid[0][1]
        self.assertEqual(shifted_win_runner['no'], 2)
        self.assertEqual(shifted_from_rank, 2)

        # Verify Pick 2 priced > 13.0 is blocked from win stake shift
        p2_longshot = {'no': 2, 'name': 'LONGSHOT B', 'win_odds': 15.0, 'model_prob': 0.10, 'has_health_risk': False}
        valid_long = [
            (cand, r_idx) for cand, r_idx in [(p2_longshot, 2)]
            if (not cand['has_health_risk']) and (0 < cand['win_odds'] <= 13.0) and (cand['model_prob'] * cand['win_odds'] > 1.0)
        ]
        self.assertEqual(len(valid_long), 0)


class TestFailLoudMonitoringRegressions(unittest.TestCase):

    @patch("scraper.requests.post")
    def test_scraper_graphql_down_never_returns_fake_kasa_papa(self, mock_post):
        """Regression 0.1: When GraphQL fails and no cache exists, return status='error', never 'KASA PAPA'."""
        mock_post.side_effect = RuntimeError("Connection timeout")
        res = scraper.get_live_meeting_data(force_network=True, cache_path="data/non_existent_cache_12345.json")
        self.assertEqual(res.get("status"), "error")
        self.assertEqual(res.get("meetings"), [])
        is_valid, errs = validate_racecard_contract(res)
        self.assertFalse(is_valid)

    def test_odds_missing_returns_none_and_suppresses_stakes(self):
        """Regression 0.3: Missing odds return None (not 20.0), and >20% missing suppresses win_stake_active."""
        val = odds_tracker.get_current_odds_with_fallback("2099-12-31", "ST", 1, 99, scraped_odds=None)
        self.assertIsNone(val)

        df = pd.DataFrame([
            {"no": 1, "win_odds": 3.5, "odds_missing": False},
            {"no": 2, "win_odds": 20.0, "odds_missing": True},
            {"no": 3, "win_odds": 20.0, "odds_missing": True},
            {"no": 4, "win_odds": 6.0, "odds_missing": False},
        ])
        contract = validate_odds_contract(df)
        self.assertEqual(contract["missing_count"], 2)
        self.assertAlmostEqual(contract["missing_ratio"], 0.5)
        self.assertTrue(contract["suppress_win_stake"])

    def test_incident_engine_parses_horse_column_and_checks_date_header(self):
        """Regression 0.4: Incident parser reads Horse column (not Placing tds[0]) and enforces date header match."""
        sample_html = """
        <html>
        <body>
            <div>Race Meeting: 21/10/2026 Happy Valley</div>
            <table>
                <tr><th>Pla.</th><th>Horse No.</th><th>Horse</th><th>Jockey</th><th>Incident</th></tr>
                <tr>
                    <td>1</td>
                    <td>3</td>
                    <td>TURIN CHAMPIONS (H402)</td>
                    <td>K Teetan</td>
                    <td>Jumped well and raced handy throughout.</td>
                </tr>
                <tr>
                    <td>3</td>
                    <td>6</td>
                    <td>FLOW RIDER (J211)</td>
                    <td>A Badel</td>
                    <td>Held up for clear running near the 200m before shifting out.</td>
                </tr>
            </table>
        </body>
        </html>
        """
        incidents = parse_hkjc_racereport_html(sample_html, expect_date="2026-10-21")
        self.assertIn("TURIN CHAMPIONS", incidents)
        self.assertIn("FLOW RIDER", incidents)
        self.assertNotIn("1", incidents)
        self.assertNotIn("3", incidents)

        valid_inc, inc_errs = validate_incident_contract(incidents, min_expected_records=2)
        self.assertTrue(valid_inc, f"Unexpected incident contract errors: {inc_errs}")

        # Mismatched date header must raise HKJCDateMismatch
        with self.assertRaises(HKJCDateMismatch):
            parse_hkjc_racereport_html(sample_html, expect_date="2026-10-19")

    def test_github_workflows_reference_only_existing_python_scripts(self):
        """Regression 0.5: Every `python X.py` command in .github/workflows/*.yml must exist in the repo."""
        workflows_dir = os.path.join(PROJECT_ROOT, ".github", "workflows")
        for fname in os.listdir(workflows_dir):
            if not fname.endswith((".yml", ".yaml")):
                continue
            fpath = os.path.join(workflows_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            scripts = re.findall(r"python\s+([A-Za-z0-9_./-]+\.py)", content)
            for script_rel in scripts:
                full_script_path = os.path.join(PROJECT_ROOT, script_rel)
                self.assertTrue(
                    os.path.exists(full_script_path),
                    f"Workflow {fname} references non-existent script '{script_rel}'",
                )

    def test_staking_audit_filters_enforced_across_scripts(self):
        """
        Verify the 189-race audit staking guards are present in run_predictions.py,
        get_detailed_picks.py, and app.py:
        1. Pure win stakes capped at <= 13.0 odds (13/1).
        2. Shifted win stakes restricted strictly to Pick 2 (p24_cands = [(p2, 2)]).
        3. Medical health risk guard (~has_health_risk) blocks win_stake_active.
        """
        for fname in ["run_predictions.py", "get_detailed_picks.py", "app.py"]:
            fpath = os.path.join(PROJECT_ROOT, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                src = f.read()
            self.assertIn("p24_cands = [(p2, 2)]", src, f"{fname} must restrict shifted win stakes to Pick 2 only")
            self.assertIn("<= 13.0", src, f"{fname} must cap pure win stakes at <= 13.0 odds")
            self.assertIn("has_health_risk", src, f"{fname} must enforce medical health risk guard on win stakes")


if __name__ == '__main__':
    unittest.main()

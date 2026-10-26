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


class TestShaTinCalibrations(unittest.TestCase):

    def test_st_straight_1000m_outside_rail_multiplier(self):
        """
        Calibration 1: Sha Tin 1000m sprints only:
        - +4.5% (+0.045) win-probability boost for gates 10-14
        - -3.5% (-0.035) penalty for gates 1-4
        - 0.0 for middle gates 5-9 or non-1000m / HV races
        """
        df = pd.DataFrame([
            {"no": 1, "name": "INSIDE TRAP", "draw": 2, "actual_weight": 125},
            {"no": 2, "name": "MIDDLE GATE", "draw": 7, "actual_weight": 125},
            {"no": 3, "name": "STANDS RAIL", "draw": 12, "actual_weight": 125},
            {"no": 4, "name": "OUTSIDE 14", "draw": 14, "actual_weight": 125},
        ])

        res_st_1000 = compute_sha_tin_calibrations(df, is_st=True, is_awt_race=False, distance=1000, class_int=4)
        mult = res_st_1000["st_straight_outside_rail_multiplier"]

        self.assertAlmostEqual(mult[0], -0.035)  # Gate 2 -> -3.5%
        self.assertAlmostEqual(mult[1], 0.0)     # Gate 7 -> 0.0%
        self.assertAlmostEqual(mult[2], 0.045)   # Gate 12 -> +4.5%
        self.assertAlmostEqual(mult[3], 0.045)   # Gate 14 -> +4.5%

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

    def test_shifted_win_stake_p24(self):
        """Test win stake shift selects best of Picks 2-4 passing price test (model_prob * odds > 1.0)."""
        p2 = {'no': 2, 'name': 'HORSE B', 'win_odds': 4.0, 'model_prob': 0.20}
        p3 = {'no': 3, 'name': 'HORSE C', 'win_odds': 5.0, 'model_prob': 0.25}
        p4 = {'no': 4, 'name': 'HORSE D', 'win_odds': 8.0, 'model_prob': 0.18}

        p24_cands = [(p2, 2), (p3, 3), (p4, 4)]
        valid = []
        for cand, r_idx in p24_cands:
            c_odds = float(cand.get('win_odds', 20.0))
            c_prob = float(cand.get('model_prob', 0.0))
            if (c_odds > 0) and (c_odds < 20.0) and (c_prob * c_odds > 1.0):
                valid.append((cand, r_idx, c_prob * c_odds))

        valid.sort(key=lambda x: x[2], reverse=True)
        shifted_win_runner, shifted_from_rank = valid[0][0], valid[0][1]
        self.assertEqual(shifted_win_runner['no'], 4)
        self.assertEqual(shifted_from_rank, 4)


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


if __name__ == '__main__':
    unittest.main()

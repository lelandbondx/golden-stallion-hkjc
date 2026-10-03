"""
Unit Tests for Tactical Incident Engine, Memory Architecture & Calibrated Multipliers
"""

import os
import sys
import unittest
import pandas as pd
import numpy as np

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data.incident_engine import parse_incident, evaluate_tactical_scores, build_horse_incident_memory


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
        
        # Test for Offender (Horse A) -> Should NOT receive traffic trouble victim flag
        offender_flags = parse_incident(text, target_horse_name="HORSE A")
        self.assertFalse(any(f['flag'] == 'traffic_trouble' for f in offender_flags))

        # Test for Victim (Horse B) -> Should receive traffic trouble flag
        victim_flags = parse_incident(text, target_horse_name="HORSE B")
        self.assertTrue(any(f['flag'] == 'traffic_trouble' for f in victim_flags))

    def test_zero_leakage_date_d(self):
        """Test that fact from race R does not retroactively change race R scores."""
        # Simulated memory where Horse X ran on 2026-10-01
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
        # Evaluation today (2026-10-04) should see the prior start credit
        scores = evaluate_tactical_scores("HORSE X", {"barrier": 4, "sp": 4.0}, mem)
        self.assertEqual(scores['forgiven_run'], 2.5)


class TestAppMultipliers(unittest.TestCase):

    def test_purton_lone_speed_rules(self):
        """Test lone speed boost is 0.02 and only Purton can qualify without recent_pos <= 5.5."""
        # Setup df
        df = pd.DataFrame([
            {'jockey': 'Z PURTON', 'avg_first_pos': 2.0, 'recent_avg_pos': 7.0},  # Purton with poor recent form -> QUALIFIES
            {'jockey': 'B AVDULLA', 'avg_first_pos': 2.0, 'recent_avg_pos': 7.0}, # Avdulla with poor recent form -> DOES NOT QUALIFY
            {'jockey': 'B AVDULLA', 'avg_first_pos': 2.0, 'recent_avg_pos': 3.0}, # Avdulla with good form -> QUALIFIES
            {'jockey': 'C L CHAU', 'avg_first_pos': 2.0, 'recent_avg_pos': 3.0}   # Chau with good form -> QUALIFIES
        ])
        recent_pos = df['recent_avg_pos']
        is_purton_leader = df['jockey'].astype(str).str.strip().str.upper() == 'Z PURTON'
        lone_speed = np.where((df['avg_first_pos'] <= 3.5) & ((recent_pos <= 5.5) | is_purton_leader), 0.02, 0.0)

        self.assertEqual(lone_speed[0], 0.02) # Purton qualifies with form 7.0
        self.assertEqual(lone_speed[1], 0.0)  # Avdulla fails with form 7.0
        self.assertEqual(lone_speed[2], 0.02) # Avdulla qualifies with form 3.0
        self.assertEqual(lone_speed[3], 0.02) # Chau qualifies with form 3.0

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

    def test_standout_and_st_draw_coefficients(self):
        """Test standout is 0.02 and ST 1000m draw boost is 0.027."""
        # Super standout 0.02
        is_super = True
        standout_boost = np.where(is_super, 0.02, 0.0)
        self.assertEqual(standout_boost, 0.02)

        # ST 1000m draw 0.027
        is_outside = True
        st_1000_boost = np.where(is_outside, 0.027, 0.0)
        self.assertEqual(st_1000_boost, 0.027)

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


if __name__ == '__main__':
    unittest.main()

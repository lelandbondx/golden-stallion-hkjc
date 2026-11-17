"""
Unit & Integration Tests for Read-Only Multi-Bot Feeds Importer (`bot_feeds_import.py`)
and Trial Processing Bugfixes (`process_trials.py`).
Uses offline fixtures copied from `trial-data @ b144f26` under `tests/fixtures/bot_feeds/`.
Never writes into `data/`.
"""

import copy
import csv
import io
import json
import logging
import math
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import bot_feeds_import as bfi
import data.automated_feeds as automated_feeds
import process_trials

FIXTURE_ROOT = os.path.join(REPO_ROOT, "tests", "fixtures", "bot_feeds")


def make_fixture_transport(overrides=None, missing_paths=None):
    overrides = overrides or {}
    missing_paths = set(missing_paths or ())

    def _transport(folder: str, relpath: str) -> bytes:
        key = f"{folder}/{relpath}"
        if key in missing_paths:
            raise FileNotFoundError(key)
        if key in overrides:
            val = overrides[key]
            return val() if callable(val) else val
        path = os.path.join(FIXTURE_ROOT, folder, relpath)
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        with open(path, "rb") as f:
            return f.read()

    return _transport


class TestBotFeedsImport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache_dir = self.tmp.name
        bfi._MEM_MEETING_CACHE.clear()
        with open(os.path.join(FIXTURE_ROOT, "st_20261114_meeting_72f7759.json"), "r", encoding="utf-8") as f:
            self.st_meeting = json.load(f)
        self.st_runners = [
            {**rn, "race_no": rc["race_no"]}
            for rc in self.st_meeting["races"]
            for rn in rc["runners"]
        ]
        self._env_backup = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env_backup)
        bfi._MEM_MEETING_CACHE.clear()
        self.tmp.cleanup()

    def test_01_sha256_mismatch_rejects_and_keeps_cache(self):
        """sha256 mismatch retries once, logs health fail, and preserves last good cache."""
        transport_ok = make_fixture_transport()
        with patch.object(bfi, "record_health") as mock_hlth:
            parsed1, meta1 = bfi.fetch_bot_folder(
                "steward", cache_dir=self.cache_dir, transport_fn=transport_ok, retry_delay_s=0.0
            )
            self.assertIsNotNone(parsed1)
            self.assertEqual(meta1["status"], "ok")
            mock_hlth.assert_not_called()

            attempts = {"n": 0}

            def _bad_records():
                attempts["n"] += 1
                with open(os.path.join(FIXTURE_ROOT, "steward", "records.csv"), "rb") as f:
                    return f.read() + b"\n"

            transport_bad = make_fixture_transport(overrides={"steward/records.csv": _bad_records})
            parsed2, meta2 = bfi.fetch_bot_folder(
                "steward", cache_dir=self.cache_dir, transport_fn=transport_bad, retry_delay_s=0.0
            )
            self.assertEqual(attempts["n"], 2)  # initial + 1 retry
            self.assertEqual(meta2["status"], "stale_cache")
            self.assertIsNotNone(parsed2)
            self.assertEqual(len(parsed2["records_rows"]), 174)
            mock_hlth.assert_called()
            self.assertEqual(mock_hlth.call_args[0][0], "bot_feed_steward")
            self.assertEqual(mock_hlth.call_args[0][1], "fail")

    def test_02_row_count_mismatch_rejects_and_keeps_cache(self):
        """Row-count mismatch fails validation and preserves last good cache."""
        transport_ok = make_fixture_transport()
        bfi.fetch_bot_folder("replay", cache_dir=self.cache_dir, transport_fn=transport_ok, retry_delay_s=0.0)

        with open(os.path.join(FIXTURE_ROOT, "replay", "manifest.json"), "r", encoding="utf-8") as f:
            bad_manifest = json.load(f)
        bad_manifest["total_rows"] = 999

        transport_bad = make_fixture_transport(
            overrides={"replay/manifest.json": json.dumps(bad_manifest).encode("utf-8")}
        )
        with patch.object(bfi, "record_health") as mock_hlth:
            parsed, meta = bfi.fetch_bot_folder(
                "replay", cache_dir=self.cache_dir, transport_fn=transport_bad, retry_delay_s=0.0
            )
            self.assertEqual(meta["status"], "stale_cache")
            self.assertEqual(len(parsed["all_rows"]), 255)
            mock_hlth.assert_called_with("bot_feed_replay", "fail", metrics={"ref": "trial-data"}, error=unittest.mock.ANY)

    def test_03_absent_optional_manifest_files_warn_only(self):
        """trial_bot JSONs listed in manifest sha256 but absent produce a warning, not failure."""
        transport = make_fixture_transport()
        with patch.object(bfi, "record_health") as mock_hlth:
            parsed, meta = bfi.fetch_bot_folder(
                "trial_bot", cache_dir=self.cache_dir, transport_fn=transport, retry_delay_s=0.0
            )
            self.assertIsNotNone(parsed)
            self.assertEqual(meta["status"], "ok")
            mock_hlth.assert_not_called()
            warn_txt = " ".join(meta["warnings"])
            self.assertIn("declared_trials_latest.json", warn_txt)
            self.assertIn("meeting_2026-11-14_ST.json", warn_txt)

    def test_04_missing_required_column_fails_that_folder_only(self):
        """Missing required column rejects only that folder; other folders still load."""
        with open(os.path.join(FIXTURE_ROOT, "grok_rising", "manifest.json"), "r", encoding="utf-8") as f:
            gm = json.load(f)

        # Strip required `evidence` column from one grok_rising CSV while leaving grok_rising empty
        with open(os.path.join(FIXTURE_ROOT, "grok_rising", "2026-11-14_ST.csv"), "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
            cols = [c for c in rows[0].keys() if c != "evidence"]
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in cols})
        bad_bytes = buf.getvalue().encode("utf-8")
        gm["sha256"]["2026-11-14_ST.csv"] = bfi._sha256_bytes(bad_bytes)

        transport = make_fixture_transport(
            overrides={
                "grok_rising/2026-11-14_ST.csv": bad_bytes,
                "grok_rising/manifest.json": json.dumps(gm).encode("utf-8"),
            }
        )
        with patch.object(bfi, "record_health") as mock_hlth:
            feats, rep = bfi.load_bot_feeds(
                "2026-11-14",
                "ST",
                self.st_runners,
                cache_dir=self.cache_dir,
                transport_fn=transport,
                retry_delay_s=0.0,
            )
            self.assertEqual(rep["folders"]["grok_rising"]["status"], "fail")
            self.assertIn("evidence", rep["folders"]["grok_rising"]["error"])
            self.assertEqual(rep["folders"]["trial_bot"]["status"], "ok")
            self.assertEqual(rep["folders"]["trial_bot"]["matched_total"], 153)
            self.assertEqual(rep["gate_status"], "ok")
            mock_hlth.assert_called()

    def test_05_boolean_parsing(self):
        self.assertIs(bfi.parse_tri_bool("True"), True)
        self.assertIs(bfi.parse_tri_bool("true"), True)
        self.assertIs(bfi.parse_tri_bool("False"), False)
        self.assertIs(bfi.parse_tri_bool("false"), False)
        self.assertIsNone(bfi.parse_tri_bool("unknown"))
        self.assertIsNone(bfi.parse_tri_bool(""))
        self.assertIsNone(bfi.parse_tri_bool("missing"))

    def test_06_horse_name_normalization(self):
        self.assertEqual(bfi.normalize_horse_name("lady\u2019s love "), "LADY'S LOVE")
        self.assertEqual(bfi.normalize_horse_name("  glorious   st  paul\u2019s "), "GLORIOUS ST PAUL'S")

    def test_07_steward_meeting_id_parsing(self):
        self.assertEqual(bfi.parse_steward_meeting_id("HV-20261111"), ("2026-11-11", "HV"))
        self.assertEqual(bfi.parse_steward_meeting_id("ST-20261114-precheck"), ("2026-11-14", "ST"))

    def test_08_replay_finish_parsing(self):
        self.assertEqual(bfi.parse_replay_finish("7 DH"), (7, True))
        self.assertEqual(bfi.parse_replay_finish("1"), (1, False))
        self.assertEqual(bfi.parse_replay_finish(""), (None, False))

        # Check end-to-end replay feature extraction
        out_dh = bfi._extract_replay_features([{"meeting_date": "2026-11-11", "race_no": "3", "finish": "7 DH", "flags": "traffic", "traffic": "true", "wide_no_cover": "false", "slow_away": "false"}])
        self.assertEqual(out_dh["bot_replay_finish"], 7)
        self.assertIs(out_dh["bot_replay_dead_heat"], True)
        out_blank = bfi._extract_replay_features([{"meeting_date": "2026-11-11", "race_no": "3", "finish": "", "flags": "", "traffic": "", "wide_no_cover": "", "slow_away": ""}])
        self.assertNotIn("bot_replay_finish", out_blank)

    def test_09_join_by_code_and_logged_name_fallback(self):
        """Joins by horse_code first; falls back to normalized name & logs when code absent."""
        transport = make_fixture_transport()
        sample_runners = [
            {"race_no": 1, "no": 1, "name": "ALMIGHTY WARRIOR", "code": "L245"},
            {"race_no": 1, "no": 2, "name": "happy pegasus"},  # no code -> fallback
        ]
        with patch.object(bfi, "record_health"), self.assertLogs("bot_feeds_import", level="INFO") as cm:
            feats, rep = bfi.load_bot_feeds(
                "2026-11-14",
                "ST",
                sample_runners,
                cache_dir=self.cache_dir,
                transport_fn=transport,
                retry_delay_s=0.0,
            )
        tb = rep["folders"]["trial_bot"]
        self.assertEqual(tb["matched_by_code"], 1)
        self.assertEqual(tb["matched_by_name"], 1)
        self.assertIn("ALMIGHTY WARRIOR", feats)
        self.assertIn("HAPPY PEGASUS", feats)
        self.assertTrue(any("Bot Feeds Name Fallback" in msg and "HAPPY PEGASUS" in msg for msg in cm.output))

    def test_10_trial_bot_meeting_mismatch_fails_gate(self):
        """ST 14 Nov CSV with target HV 18 Nov produces no trial_bot features and fails gate."""
        transport = make_fixture_transport()
        hv_runners = [{"race_no": 1, "no": 1, "name": "ALMIGHTY WARRIOR", "code": "L245"}]
        with patch.object(bfi, "record_health") as mock_hlth:
            feats, rep = bfi.load_bot_feeds(
                "2026-11-18",
                "HV",
                hv_runners,
                cache_dir=self.cache_dir,
                transport_fn=transport,
                retry_delay_s=0.0,
            )
            self.assertEqual(rep["folders"]["trial_bot"]["matched_total"], 0)
            self.assertEqual(rep["folders"]["trial_bot"]["rows_for_target_meeting"], 0)
            self.assertEqual(rep["gate_status"], "fail")
            self.assertNotIn("bot_trial_pos", feats.get("ALMIGHTY WARRIOR", {}))
            mock_hlth.assert_called()

    def test_11_coverage_gate_and_strict_exception(self):
        """3 declared + 1 standby with 2 matched -> 66.7% fail, standby excluded, strict raises."""
        runners = [
            {"race_no": 1, "no": 1, "name": "H1", "code": "A001"},
            {"race_no": 1, "no": 2, "name": "H2", "code": "A002"},
            {"race_no": 1, "no": 3, "name": "H3", "code": "A003"},
            {"race_no": 1, "no": "", "name": "H4_SB", "code": "A004", "runner_status": "standby", "standby_order": "1"},
        ]
        feats = {"H1": {"bot_trial_pos": 1}, "H2": {"bot_trial_pos": 2}}
        match_stats = {
            "trial_bot": {
                "matched_by_code": 2,
                "matched_by_name": 0,
                "unmatched": ["R1-3 H3 (A003)"],
                "fresh": 2,
                "stale": 0,
                "missing_trial": 1,
                "rows_for_target_meeting": 2,
            }
        }
        with patch.object(bfi, "record_health") as mock_hlth:
            rep = bfi.check_bot_coverage(
                "2026-11-18", "HV", runners, feats, threshold=0.95, match_stats=match_stats, cache_dir=self.cache_dir
            )
            self.assertEqual(rep["declared_runners"], 3)
            self.assertEqual(rep["standby_runners"], 1)
            self.assertAlmostEqual(rep["folders"]["trial_bot"]["coverage_ratio"], 0.6667, places=3)
            self.assertEqual(rep["gate_status"], "fail")
            self.assertEqual(rep["folders"]["trial_bot"]["unmatched"], ["R1-3 H3 (A003)"])
            mock_hlth.assert_called()

            os.environ["BOT_COVERAGE_STRICT"] = "1"
            with self.assertRaises(RuntimeError):
                bfi.check_bot_coverage(
                    "2026-11-18", "HV", runners, feats, threshold=0.95, match_stats=match_stats, cache_dir=self.cache_dir
                )

    def test_12_real_fixture_153_declared_matched(self):
        """Real trial-data @ b144f26 fixture matches 153/153 declared runners for ST 14 Nov."""
        transport = make_fixture_transport()
        with patch.object(bfi, "record_health") as mock_hlth:
            feats, rep = bfi.load_bot_feeds(
                "2026-11-14",
                "ST",
                self.st_runners,
                cache_dir=self.cache_dir,
                transport_fn=transport,
                retry_delay_s=0.0,
            )
            self.assertEqual(rep["declared_runners"], 153)
            self.assertEqual(rep["folders"]["trial_bot"]["matched_total"], 153)
            self.assertEqual(rep["folders"]["trial_bot"]["coverage_ratio"], 1.0)
            self.assertEqual(rep["gate_status"], "ok")
            mock_hlth.assert_not_called()

    def test_13_empty_median_omits_speed_vs_median(self):
        """Runner with empty median_sec (BEAUTY WAVES H294) has no bot_trial_speed_vs_median_sec key."""
        transport = make_fixture_transport()
        with patch.object(bfi, "record_health"):
            feats, _ = bfi.load_bot_feeds(
                "2026-11-14",
                "ST",
                self.st_runners,
                cache_dir=self.cache_dir,
                transport_fn=transport,
                retry_delay_s=0.0,
            )
        self.assertIn("BEAUTY WAVES", feats)
        bw = feats["BEAUTY WAVES"]
        self.assertNotIn("bot_trial_speed_vs_median_sec", bw)
        self.assertNotIn("bot_flag_fast", bw)
        self.assertNotIn("bot_flag_slow", bw)
        self.assertEqual(bw.get("bot_trial_median_n"), 3)
        self.assertNotEqual(bw["bot_sources"]["trial_bot"], bw["bot_sources"]["steward"])

    def test_14_no_core_or_bot_key_ever_none(self):
        """Neither shadow nor live mode ever sets a core key or bot key to None or NaN."""
        transport = make_fixture_transport()
        os.environ["SILKS_BOT_FEEDS_CACHE"] = self.cache_dir
        for mode, live_trials in [("shadow", "0"), ("live", "1")]:
            os.environ["SILKS_BOT_FEEDS"] = mode
            os.environ["SILKS_BOT_LIVE_TRIALS"] = live_trials
            merged = bfi.merge_bot_features(
                {},
                self.st_meeting,
                self.st_runners,
                cache_dir=self.cache_dir,
                transport_fn=transport,
                retry_delay_s=0.0,
            )
            self.assertGreaterEqual(len(merged), 153)
            for hname, hdict in merged.items():
                for k, v in hdict.items():
                    self.assertIsNotNone(v, f"{mode}: {hname}.{k} must never be None")
                    if isinstance(v, float):
                        self.assertFalse(math.isnan(v), f"{mode}: {hname}.{k} must never be NaN")

    def test_15_load_trial_bot_feed_list_rejects_missing_position(self):
        """Regression guard: data/automated_feeds.py list branch rejects items missing position."""
        tmp_json = os.path.join(self.cache_dir, "bad_trial_list.json")
        payload = [
            {"horse": "BAD HORSE", "total_runners": 10, "speed_diff": 0.4},  # missing position
            {"horse": "GOOD HORSE", "position": 1, "total_runners": 10, "speed_diff": 0.6},
        ]
        with open(tmp_json, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        with patch.object(automated_feeds, "TRIAL_BOT_CANDIDATES", [tmp_json]):
            tf, meta = automated_feeds.load_trial_bot_feed()
        self.assertNotIn("BAD HORSE", tf)
        self.assertIn("GOOD HORSE", tf)
        self.assertEqual(meta["rejected_incomplete"], 1)

    def test_16_grok_bot_vs_rising_no_double_count_and_diff_logged(self):
        """grok_bot identical keys produce zero diff and no double-counting; diffs log warning."""
        transport = make_fixture_transport()
        hv_plus_runners = [{"race_no": 1, "no": 1, "name": "WINNING BEAUTY", "code": "K230"}]
        # On 2026-11-18, grok_rising has 2026-11-14 ST + 2026-11-11 HV rows.
        # Quick Check on any runner in grok_rising (CIRCUIT DUFFY J501 from ST 2026-11-14).
        test_runners = [{"race_no": 1, "no": 1, "name": "CIRCUIT DUFFY", "code": "J501"}]
        with patch.object(bfi, "record_health"):
            feats, rep = bfi.load_bot_feeds(
                "2026-11-18",
                "HV",
                test_runners,
                cache_dir=self.cache_dir,
                transport_fn=transport,
                retry_delay_s=0.0,
            )
        self.assertEqual(rep["folders"]["grok_bot_crosscheck"]["diff_count"], 0)
        # J501 has exactly 1 flag in 2026-11-14_ST.csv -> must NOT be doubled to 2
        self.assertEqual(len(feats["CIRCUIT DUFFY"]["bot_ev_flags"]), 1)

        # Now inject a differing priority in grok_bot/all_ev_records.csv
        with open(os.path.join(FIXTURE_ROOT, "grok_bot", "all_ev_records.csv"), "r", encoding="utf-8") as f:
            gb_rows = list(csv.DictReader(f))
            gb_cols = list(gb_rows[0].keys())
        gb_rows[0]["priority"] = "critical"
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=gb_cols)
        w.writeheader()
        w.writerows(gb_rows)

        transport_diff = make_fixture_transport(overrides={"grok_bot/all_ev_records.csv": buf.getvalue().encode("utf-8")})
        with patch.object(bfi, "record_health"), self.assertLogs("bot_feeds_import", level="WARNING") as cm:
            _, rep_diff = bfi.load_bot_feeds(
                "2026-11-18",
                "HV",
                test_runners,
                cache_dir=os.path.join(self.cache_dir, "diff_run"),
                transport_fn=transport_diff,
                retry_delay_s=0.0,
            )
        self.assertGreater(rep_diff["folders"]["grok_bot_crosscheck"]["diff_count"], 0)
        self.assertTrue(any("Grok Feed Crosscheck" in msg for msg in cm.output))

    def test_17_off_mode_returns_trial_features_unchanged(self):
        os.environ["SILKS_BOT_FEEDS"] = "off"
        base = {"MY HORSE": {"best_trial_pos_ratio": 0.25}}

        def _should_not_be_called(*args, **kwargs):
            raise AssertionError("Transport must not be called in off mode")

        res = bfi.merge_bot_features(base, self.st_meeting, self.st_runners, transport_fn=_should_not_be_called)
        self.assertIs(res, base)

    def test_18_shadow_mode_byte_identical_race_scoring(self):
        """off mode vs shadow mode produces byte-identical model_prob and gs_score on ST 14 Nov R1."""
        with open(os.path.join(FIXTURE_ROOT, "st_20261114_r1_72f7759.json"), "r", encoding="utf-8") as f:
            r1_frozen = json.load(f)
        with open(os.path.join(REPO_ROOT, "data", "engineered_trial_features.json"), "r", encoding="utf-8") as f:
            base_tf = json.load(f)

        from monitoring.contracts import (
            evaluate_debutant_relaxed_trial_waiver,
            evaluate_pick5_sleeper_candidates,
            compute_telemetry_harmony_multipliers,
        )
        transport = make_fixture_transport()
        os.environ["SILKS_BOT_FEEDS_CACHE"] = self.cache_dir

        def _score_race(mode: str):
            os.environ["SILKS_BOT_FEEDS"] = mode
            bfi._MEM_MEETING_CACHE.clear()
            tf = bfi.merge_bot_features(
                base_tf,
                self.st_meeting,
                self.st_runners,
                cache_dir=self.cache_dir,
                transport_fn=transport,
                retry_delay_s=0.0,
            )
            df = pd.DataFrame(copy.deepcopy(r1_frozen))
            df["clean_name"] = df["name"].astype(str).str.upper().str.strip()
            df["model_prob"] = pd.to_numeric(df["raw_model_prob"], errors="coerce")
            is_deb = np.ones(len(df), dtype=bool)
            has_strong = np.array(
                [
                    (
                        nm in tf
                        and tf[nm].get("best_trial_pos_ratio", 1.0) <= 0.35
                        and (bool(tf[nm].get("high_quality_trial", False)) or (int(tf[nm].get("recent_top2_trials", 0)) >= 1 and tf[nm].get("best_trial_speed_diff", 0.0) > 0.0))
                    )
                    for nm in df["clean_name"]
                ],
                dtype=bool,
            )
            waive = evaluate_debutant_relaxed_trial_waiver(df, is_deb, has_strong, tf, race_no=1)
            probs = np.where((df["win_odds"] >= 20.0) & (~waive), df["model_prob"] * 0.5, df["model_prob"])
            t_adj = np.array(
                [
                    (0.02 if (nm in tf and tf[nm].get("best_trial_speed_diff", 0.0) >= 0.5 and tf[nm].get("best_trial_pos_ratio", 1.0) <= 0.50) else 0.0)
                    + (0.02 if (nm in tf and tf[nm].get("high_quality_trial", False)) else 0.0)
                    for nm in df["clean_name"]
                ],
                dtype=float,
            )
            df, mem = bfi.apply_live_bot_runner_overlays(df, tf, None)
            th = compute_telemetry_harmony_multipliers(df, is_st=True, is_hv=False, is_awt_race=False, distance=1200, class_int=4, has_strong_trial=has_strong, horse_memory=mem)
            mult = np.clip(1.0 + t_adj + th["telemetry_harmony_multiplier"], 0.1, 1.25)
            adj = probs * mult
            final_probs = adj / adj.sum()
            gs = final_probs * 100.0
            df["gs_score"] = gs
            p5 = evaluate_pick5_sleeper_candidates(df, df.sort_values("gs_score", ascending=False)["no"].head(4).tolist(), tf, is_hv=False, race_no=1)
            return final_probs, gs, p5["selected_no"]

        with patch.object(bfi, "record_health"):
            p_off, g_off, p5_off = _score_race("off")
            p_shd, g_shd, p5_shd = _score_race("shadow")

        self.assertTrue(np.array_equal(p_off, p_shd))
        self.assertTrue(np.array_equal(g_off, g_shd))
        self.assertEqual(p5_off, p5_shd)

    def test_19_process_trials_bugfixes(self):
        """Dec/Jan rollover works, future trials rejected, winner-only total_time, missing speed_diff omitted."""
        with tempfile.TemporaryDirectory() as td:
            old_cwd = os.getcwd()
            os.chdir(td)
            try:
                os.makedirs("data", exist_ok=True)
                pd.DataFrame([
                    # Year rollover: 20/12 prior to 2026-01-10 -> 20 days ago, winner -> valid speed_diff
                    {"date": "20/12", "group": 1, "distance": 1200, "track": "SHA TIN AWT", "position": 1, "total_runners": 10, "jockey": "Z PURTON", "splits": "", "total_time": "1.09.50", "horse_name": "DEC ROLLOVER WINNER", "race_no": 1},
                    # Future trial relative to meeting_date 2026-01-10 -> rejected!
                    {"date": "15/01", "group": 2, "distance": 1200, "track": "SHA TIN AWT", "position": 1, "total_runners": 10, "jockey": "Z PURTON", "splits": "", "total_time": "1.09.00", "horse_name": "FUTURE ONLY HORSE", "race_no": 1},
                    # Position 4 with only batch winner's total_time -> must NOT assign speed_diff = 0.0 or use batch time
                    {"date": "02/01", "group": 3, "distance": 1200, "track": "SHA TIN AWT", "position": 4, "total_runners": 10, "jockey": "A ATZENI", "splits": "", "total_time": "1.09.50", "horse_name": "NON WINNER BATCH TIME", "race_no": 2},
                    # Winner at unmapped distance 1548 -> best_trial_speed_diff omitted (never 0.0)
                    {"date": "02/01", "group": 4, "distance": 1548, "track": "SHA TIN TURF", "position": 1, "total_runners": 10, "jockey": "Z PURTON", "splits": "", "total_time": "1.34.00", "horse_name": "UNMAPPED DIST HORSE", "race_no": 3},
                ]).to_csv("data/latest_trial_stats.csv", index=False)

                with patch("monitoring.health.record"):
                    out = process_trials.process_trials("2026-01-10")
            finally:
                os.chdir(old_cwd)

        self.assertIn("DEC ROLLOVER WINNER", out)
        self.assertAlmostEqual(out["DEC ROLLOVER WINNER"]["best_trial_speed_diff"], 1.0, places=2)
        self.assertNotIn("FUTURE ONLY HORSE", out)
        self.assertIn("NON WINNER BATCH TIME", out)
        self.assertNotIn("best_trial_speed_diff", out["NON WINNER BATCH TIME"])
        self.assertIn("UNMAPPED DIST HORSE", out)
        self.assertNotIn("best_trial_speed_diff", out["UNMAPPED DIST HORSE"])


if __name__ == "__main__":
    unittest.main()

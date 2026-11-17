"""
Silks.AI - Walk-Forward Dry-Run Backtest for Multi-Bot Feeds (`trial-data`)

Strict anti-look-ahead evaluation across November 2026 HKJC meetings using each
meeting's pre-race git data snapshot paired with current HEAD `run_predictions.py`
scoring logic (`SILKS_WET_PACE_TEST_MODE=0`).

Hard safety guarantees:
  - Strictly dry-run: intercepts `odds_tracker.save_frozen_predictions` in memory.
  - Runs each meeting in an isolated temporary directory so ZERO files under
    `REPO_ROOT/data/` or `data/frozen_predictions_*.json` are ever modified.
  - Compares A (`SILKS_BOT_FEEDS=off`) against B (`LIVE_TRIALS`, `LIVE_STEWARD`,
    `LIVE_REPLAY`, and `ALL_COMBINED`).

Usage:
  python backtests/bot_feeds_backtest.py
"""

from __future__ import annotations

import contextlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

MEETINGS = [
    ("2026-11-01", "Happy Valley", "20261101", "1e09b26", True),
    ("2026-11-04", "Happy Valley", "20261104", "ceb9070", True),
    ("2026-11-08", "Sha Tin", "20261108", "b2a2129", True),
    ("2026-11-11", "Happy Valley", "20261111", "2a48de2", True),
    ("2026-11-14", "Sha Tin", "20261114", "72f7759", False),
]

CONFIGS = [
    ("A_OFF", {"SILKS_BOT_FEEDS": "off", "SILKS_BOT_LIVE_TRIALS": "0", "SILKS_BOT_LIVE_STEWARD": "0", "SILKS_BOT_LIVE_REPLAY": "0"}),
    ("B_TRIALS", {"SILKS_BOT_FEEDS": "live", "SILKS_BOT_LIVE_TRIALS": "1", "SILKS_BOT_LIVE_STEWARD": "0", "SILKS_BOT_LIVE_REPLAY": "0"}),
    ("B_STEWARD", {"SILKS_BOT_FEEDS": "live", "SILKS_BOT_LIVE_TRIALS": "0", "SILKS_BOT_LIVE_STEWARD": "1", "SILKS_BOT_LIVE_REPLAY": "0"}),
    ("B_REPLAY", {"SILKS_BOT_FEEDS": "live", "SILKS_BOT_LIVE_TRIALS": "0", "SILKS_BOT_LIVE_STEWARD": "0", "SILKS_BOT_LIVE_REPLAY": "1"}),
    ("B_ALL", {"SILKS_BOT_FEEDS": "live", "SILKS_BOT_LIVE_TRIALS": "1", "SILKS_BOT_LIVE_STEWARD": "1", "SILKS_BOT_LIVE_REPLAY": "1"}),
]

NOV14_OFFICIAL_GOINGS = {
    1: "GOOD TO YIELDING",
    2: "GOOD TO YIELDING",
    3: "WET SLOW",
    4: "GOOD TO YIELDING",
    5: "GOOD TO YIELDING",
    6: "WET SLOW",
    7: "GOOD TO YIELDING",
    8: "GOOD",
    9: "GOOD",
    10: "WET SLOW",
    11: "GOOD",
}


def _copy_head_code_into_iso(iso_dir: str, dt_tag: str) -> None:
    """Overlays current HEAD Python modules and cached odds onto the pre-race data tree."""
    for entry in os.listdir(REPO_ROOT):
        if entry.endswith(".py") or entry == "model.joblib":
            shutil.copy2(os.path.join(REPO_ROOT, entry), os.path.join(iso_dir, entry))

    for sub in ("monitoring", "features"):
        src_sub = os.path.join(REPO_ROOT, sub)
        dst_sub = os.path.join(iso_dir, sub)
        if os.path.isdir(src_sub):
            shutil.copytree(src_sub, dst_sub, dirs_exist_ok=True)

    for data_py in ("automated_feeds.py", "incident_engine.py", "calculate_jvoe.py"):
        sp = os.path.join(REPO_ROOT, "data", data_py)
        if os.path.exists(sp):
            shutil.copy2(sp, os.path.join(iso_dir, "data", data_py))

    for odds_fn in (f"odds_cache_{dt_tag}.json", f"baseline_odds_{dt_tag}.json"):
        sp = os.path.join(REPO_ROOT, "data", odds_fn)
        if os.path.exists(sp):
            shutil.copy2(sp, os.path.join(iso_dir, "data", odds_fn))


def _parse_race_picks_from_stdout(stdout_text: str) -> dict[int, dict[str, int]]:
    picks_by_race: dict[int, dict[str, int]] = {}
    cur_race = None
    pat_num = re.compile(r"#(\d+)\b")
    for line in stdout_text.splitlines():
        s = line.strip()
        if s.startswith("--- RACE "):
            try:
                cur_race = int(s.split("RACE")[1].split(":")[0].strip())
                picks_by_race.setdefault(cur_race, {})
            except Exception:
                cur_race = None
        elif cur_race is not None:
            for idx, tag in enumerate(
                (
                    "PICK 1 (WINNING HORSE PICK):",
                    "PICK 2 (EXACTA/QUINELLA):",
                    "PICK 3 (TRIO PODIUM):",
                    "PICK 4 (TRIO 4TH LEG):",
                    "PICK 5 (DUAL-STAKE SLEEPER / HIGHEST EV):",
                ),
                start=1,
            ):
                if tag in s:
                    m = pat_num.search(s.split(tag, 1)[1])
                    if m:
                        picks_by_race[cur_race][f"p{idx}"] = int(m.group(1))
    return picks_by_race


def _run_meeting_child(
    m_date: str,
    venue: str,
    dt_tag: str,
    git_rev: str,
    hist_fallback: bool,
    cache_dir: str,
) -> dict:
    with tempfile.TemporaryDirectory() as iso_dir:
        tar_bytes = subprocess.check_output(["git", "archive", "--format=tar", git_rev], cwd=REPO_ROOT)
        with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as tf:
            tf.extractall(iso_dir)
        _copy_head_code_into_iso(iso_dir, dt_tag)

        # Ensure official Nov 14 race-by-race goings in isolated meeting JSON
        with open(os.path.join(iso_dir, "data", "last_scraped_meeting.json"), "r", encoding="utf-8") as f:
            m_payload = json.load(f)
        target_m = None
        for m in m_payload.get("meetings") or []:
            if m.get("date") == m_date:
                target_m = m
                break
        if target_m is None:
            target_m = (m_payload.get("meetings") or [{}])[0]
        if m_date == "2026-11-14":
            for rc in target_m.get("races") or []:
                rno = int(rc.get("race_no") or 0)
                if rno in NOV14_OFFICIAL_GOINGS:
                    rc["going"] = NOV14_OFFICIAL_GOINGS[rno]
        with open(os.path.join(iso_dir, "data", "last_scraped_meeting.json"), "w", encoding="utf-8") as f:
            json.dump({"status": "success", "source": "backtest", "meetings": [target_m]}, f)

        # Remove frozen predictions inside iso_dir so HEAD computes every race fresh
        iso_frozen = os.path.join(iso_dir, "data", f"frozen_predictions_{dt_tag}.json")
        if os.path.exists(iso_frozen):
            os.remove(iso_frozen)

        out_path = os.path.join(iso_dir, "_bt_out.json")
        child_script = f"""
import contextlib, io, json, os, sys
iso_dir = {iso_dir!r}
os.chdir(iso_dir)
sys.path.insert(0, iso_dir)
os.environ['SILKS_WET_PACE_TEST_MODE'] = '0'
os.environ['SILKS_BOT_FEEDS_CACHE'] = {cache_dir!r}
os.environ['SILKS_BOT_ALLOW_HISTORY_TRIAL_FALLBACK'] = {'1' if hist_fallback else '0'!r}

import bot_feeds_import
import hkjc_profile_scraper
import odds_tracker
import run_predictions

with open('data/last_scraped_meeting.json', 'r', encoding='utf-8') as f:
    payload = json.load(f)

captured = {{}}
def _dry_save(m_date, m_venue, race_no, records):
    clean_recs = []
    for r in records:
        clean_recs.append({{
            'no': int(r['no']) if r.get('no') is not None else 0,
            'name': str(r.get('name') or ''),
            'code': str(r.get('code') or r.get('horse_code') or ''),
            'model_prob': float(r.get('model_prob') or 0.0),
            'gs_score': float(r.get('gs_score') or 0.0),
            'win_odds': float(r.get('win_odds') or 20.0),
            'has_health_risk': bool(r.get('has_health_risk', False)),
            'had_excuse': bool(r.get('had_excuse', False)),
            'tactical_incident_multiplier': float(r.get('tactical_incident_multiplier') or 0.0),
            'active_vet_risk_penalty': float(r.get('active_vet_risk_penalty') or 0.0),
            'pick5_qualifier_reason': str(r.get('pick5_qualifier_reason') or ''),
        }})
    captured[int(race_no)] = clean_recs

hkjc_profile_scraper.ensure_meeting_profiles_synced = lambda m: None
odds_tracker.cache_live_odds = lambda *a, **kw: None
odds_tracker.get_frozen_predictions = lambda *a, **kw: None
odds_tracker.save_frozen_predictions = _dry_save
run_predictions.get_live_meeting_data = lambda: payload
run_predictions.select_active_meeting = lambda d: d['meetings'][0]

# Use existing disk cache in test runner for grok/trial/steward/replay after first fetch
all_results = {{}}
for cfg_name, env_map in {CONFIGS!r}:
    captured = {{}}
    bot_feeds_import._MEM_MEETING_CACHE.clear()
    for ek, ev in env_map.items():
        os.environ[ek] = ev
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        run_predictions.run()
    all_results[cfg_name] = {{'races': captured, 'stdout': buf.getvalue()}}

with open({out_path!r}, 'w', encoding='utf-8') as f:
    json.dump(all_results, f)
"""
        proc = subprocess.run(
            [sys.executable, "-c", child_script],
            cwd=iso_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"Backtest child failed for {m_date} {venue}:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        with open(out_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

    parsed_out = {}
    for cfg_name, payload in raw.items():
        picks = _parse_race_picks_from_stdout(payload["stdout"])
        # Extract debutant waiver log tags from stdout per race+horse
        waivers = set()
        for line in payload["stdout"].splitlines():
            m_w = re.search(r"\[Debutant Trial Waiver\]\s+Race\s+(\d+)\s+#(\d+)\b", line)
            if m_w:
                waivers.add((int(m_w.group(1)), int(m_w.group(2))))
        parsed_out[cfg_name] = {
            "races": {int(k): v for k, v in payload["races"].items()},
            "picks": picks,
            "waivers": waivers,
        }
    return parsed_out


def _parse_race_outcome(res_data: dict, rno: int, dt_tag: str) -> Optional[dict]:
    """
    Extracts winners (`set[int]`), podium (`set[int]`), finish_by_no (`dict[int, str]`),
    win_dividends_hk10 (`dict[int, float]`, HK$10 unit), and dividend_note (`str`).
    """
    entry = res_data.get(str(rno))
    if not entry:
        return None

    winners: set[int] = set()
    podium: set[int] = set()
    finish_by_no: dict[int, str] = {}
    win_divs_hk10: dict[int, float] = {}

    if isinstance(entry, dict):
        for rn in entry.get("runners") or []:
            try:
                no_i = int(str(rn.get("no")).strip())
            except Exception:
                continue
            plc_str = str(rn.get("plc") or "").strip().upper()
            finish_by_no[no_i] = plc_str
            m_plc = re.match(r"^0*(\d+)", plc_str)
            if m_plc:
                pos_i = int(m_plc.group(1))
                if pos_i == 1:
                    winners.add(no_i)
                if pos_i <= 3:
                    podium.add(no_i)
        divs = entry.get("dividends") or {}
        for item in divs.get("WIN") or []:
            comb = str(item.get("combination", item.get("comb", "")) or "").strip()
            div_raw = str(item.get("dividend", item.get("div", "")) or "").replace(",", "").strip()
            try:
                comb_i = int(comb)
                div_f = float(div_raw)
                win_divs_hk10[comb_i] = div_f
            except Exception:
                continue
        div_source = "official_dividends"
    elif isinstance(entry, list):
        for rn in entry:
            try:
                no_i = int(rn.get("no"))
                plc_i = int(rn.get("place"))
            except Exception:
                continue
            finish_by_no[no_i] = str(plc_i)
            if plc_i == 1:
                winners.add(no_i)
                try:
                    win_divs_hk10[no_i] = float(rn.get("odds", 0.0)) * 10.0
                except Exception:
                    pass
            if plc_i <= 3:
                podium.add(no_i)
        div_source = "sp_odds_x10"
    else:
        return None

    if not winners:
        return None
    return {
        "winners": winners,
        "podium": podium,
        "finish_by_no": finish_by_no,
        "win_divs_hk10": win_divs_hk10,
        "div_source": div_source,
    }


def _grade_config(meeting_runs: list[tuple], cfg_name: str) -> tuple[list[dict], dict]:
    per_meeting_rows = []
    tot_races = 0
    tot_p1_win = 0
    tot_top4_hit = 0
    tot_p5_win = 0
    tot_p1_place = 0
    tot_brier = 0.0
    tot_logloss = 0.0
    tot_staked = 0.0
    tot_returned = 0.0

    for m_date, venue, dt_tag, res_data, run_data in meeting_runs:
        cfg = run_data[cfg_name]
        races_cnt = 0
        p1_win = 0
        top4_hit = 0
        p5_win = 0
        p1_place = 0
        brier_sum = 0.0
        ll_sum = 0.0
        staked = 0.0
        returned = 0.0

        for rno in sorted(cfg["races"].keys()):
            outcome = _parse_race_outcome(res_data, rno, dt_tag)
            if outcome is None:
                continue
            runners = cfg["races"][rno]
            if not runners:
                continue
            picks = cfg["picks"].get(rno) or {}
            sorted_gs = sorted(runners, key=lambda x: x["gs_score"], reverse=True)
            top4_nos = {picks[k] for k in ("p1", "p2", "p3", "p4") if k in picks}
            if not top4_nos:
                top4_nos = {int(x["no"]) for x in sorted_gs[:4]}
            p1_no = picks.get("p1", int(sorted_gs[0]["no"]))
            p5_no = picks.get("p5", int(sorted_gs[4]["no"]) if len(sorted_gs) > 4 else int(sorted_gs[-1]["no"]))

            winners = outcome["winners"]
            podium = outcome["podium"]
            races_cnt += 1
            if p1_no in winners:
                p1_win += 1
            if top4_nos & winners:
                top4_hit += 1
            if p5_no in winners:
                p5_win += 1
            if p1_no in podium:
                p1_place += 1

            # Normalize probabilities just in case of tiny float rounding
            prob_sum = sum(max(0.0, r["model_prob"]) for r in runners) or 1.0
            race_brier = 0.0
            p_win = 0.0
            for r in runners:
                p = max(0.0, r["model_prob"]) / prob_sum
                y = 1.0 if int(r["no"]) in winners else 0.0
                race_brier += (p - y) ** 2
                if y == 1.0:
                    p_win = max(p_win, p)
            brier_sum += race_brier
            ll_sum += -math.log(max(p_win, 1e-6))

            staked += 10.0
            if p1_no in winners:
                returned += float(outcome["win_divs_hk10"].get(p1_no, 0.0))

        tot_races += races_cnt
        tot_p1_win += p1_win
        tot_top4_hit += top4_hit
        tot_p5_win += p5_win
        tot_p1_place += p1_place
        tot_brier += brier_sum
        tot_logloss += ll_sum
        tot_staked += staked
        tot_returned += returned

        per_meeting_rows.append(
            {
                "meeting": f"{m_date} {venue[:2].upper() if venue != 'Sha Tin' else 'ST'}",
                "races": races_cnt,
                "p1_win": p1_win,
                "top4_hit": top4_hit,
                "p5_win": p5_win,
                "p1_place": p1_place,
                "brier": round(brier_sum / races_cnt, 5) if races_cnt else 0.0,
                "logloss": round(ll_sum / races_cnt, 5) if races_cnt else 0.0,
                "roi_pct": round(((returned - staked) / staked) * 100.0, 2) if staked else 0.0,
                "returned": round(returned, 1),
                "staked": round(staked, 1),
            }
        )

    agg = {
        "meeting": "TOTAL",
        "races": tot_races,
        "p1_win": tot_p1_win,
        "top4_hit": tot_top4_hit,
        "p5_win": tot_p5_win,
        "p1_place": tot_p1_place,
        "brier": round(tot_brier / tot_races, 5) if tot_races else 0.0,
        "logloss": round(tot_logloss / tot_races, 5) if tot_races else 0.0,
        "roi_pct": round(((tot_returned - tot_staked) / tot_staked) * 100.0, 2) if tot_staked else 0.0,
        "returned": round(tot_returned, 1),
        "staked": round(tot_staked, 1),
    }
    return per_meeting_rows, agg


def _collect_changes(meeting_runs: list[tuple], target_cfg: str) -> list[dict]:
    diffs = []
    for m_date, venue, dt_tag, res_data, run_data in meeting_runs:
        base = run_data["A_OFF"]
        cand = run_data[target_cfg]
        v_short = "ST" if "SHA TIN" in venue.upper() else "HV"

        for rno in sorted(base["races"].keys()):
            outcome = _parse_race_outcome(res_data, rno, dt_tag)
            if outcome is None:
                continue
            b_picks = base["picks"].get(rno) or {}
            c_picks = cand["picks"].get(rno) or {}
            b_slot = {no: f"P{i}" for i in range(1, 6) if (no := b_picks.get(f"p{i}")) is not None}
            c_slot = {no: f"P{i}" for i in range(1, 6) if (no := c_picks.get(f"p{i}")) is not None}

            b_map = {int(r["no"]): r for r in base["races"][rno]}
            c_map = {int(r["no"]): r for r in cand["races"][rno]}

            for no_i, rb in sorted(b_map.items()):
                rc = c_map.get(no_i)
                if not rc:
                    continue
                bs = b_slot.get(no_i, "-")
                cs = c_slot.get(no_i, "-")
                bw = (rno, no_i) in base["waivers"]
                cw = (rno, no_i) in cand["waivers"]
                reasons = []
                if bs != cs:
                    reasons.append(f"slot {bs}->{cs}")
                if bw != cw:
                    reasons.append(f"deb_waiver {bw}->{cw}")
                if rb.get("pick5_qualifier_reason") != rc.get("pick5_qualifier_reason"):
                    reasons.append(f"p5_qual {rb.get('pick5_qualifier_reason')!r}->{rc.get('pick5_qualifier_reason')!r}")
                if rb.get("has_health_risk") != rc.get("has_health_risk"):
                    reasons.append(f"health_risk {rb.get('has_health_risk')}->{rc.get('has_health_risk')}")
                if rb.get("had_excuse") != rc.get("had_excuse"):
                    reasons.append(f"had_excuse {rb.get('had_excuse')}->{rc.get('had_excuse')}")
                if abs(float(rb.get("tactical_incident_multiplier", 0.0)) - float(rc.get("tactical_incident_multiplier", 0.0))) > 1e-6:
                    reasons.append(
                        f"tact_mult {rb.get('tactical_incident_multiplier'):+.3f}->{rc.get('tactical_incident_multiplier'):+.3f}"
                    )
                if reasons:
                    diffs.append(
                        {
                            "meeting": f"{m_date} {v_short}",
                            "race": rno,
                            "no": no_i,
                            "name": rb["name"],
                            "finish": outcome["finish_by_no"].get(no_i, "?"),
                            "gs_delta": f"{rb['gs_score']:.2f}->{rc['gs_score']:.2f}",
                            "changes": "; ".join(reasons),
                        }
                    )
    return diffs


def main() -> int:
    src_cache = os.path.join(REPO_ROOT, ".cache", "bot_feeds")
    with tempfile.TemporaryDirectory() as bt_cache_tmp:
        if os.path.isdir(src_cache):
            shutil.copytree(src_cache, bt_cache_tmp, dirs_exist_ok=True)
        cache_dir = bt_cache_tmp
        meeting_runs = []
        for m_date, venue, dt_tag, git_rev, hist_fb in MEETINGS:
            res_path = os.path.join(REPO_ROOT, "data", f"results_{dt_tag}.json")
            with open(res_path, "r", encoding="utf-8") as f:
                res_data = json.load(f)
            run_data = _run_meeting_child(m_date, venue, dt_tag, git_rev, hist_fb, cache_dir)
            meeting_runs.append((m_date, venue, dt_tag, res_data, run_data))

        return _print_report(meeting_runs)


def _print_report(meeting_runs: list[tuple]) -> int:

    print("========================================================================================")
    print("SILKS.AI BOT FEEDS DRY-RUN WALK-FORWARD BACKTEST (NO FROZEN FILE / NO data/ WRITES)")
    print("========================================================================================")
    print("Limitations:")
    print("  1. Pre-14-Nov cards (1, 4, 8, 11 Nov) lack declared_trials_latest snapshots on `trial-data`,")
    print("     so trial_bot features are rebuilt strictly from `trials_history.csv` (438 rows, 1 latest trial/horse).")
    print("  2. `grok_rising` starts 11 Nov HV (37 rows) and `replay` starts 8 Nov ST, so both mostly inform 14 Nov.")
    print("  3. `results_20261114.json` stores SP odds (flat $10 return approximated as 10 * odds),")
    print("     while 1/4/8/11 Nov use official HKJC WIN dividends.")
    print("  4. ~49 races is a small safety sample: passing means 'no regression', NOT proof of long-term lift.\n")

    summaries = {}
    for cfg_name, _ in CONFIGS:
        per_m, agg = _grade_config(meeting_runs, cfg_name)
        summaries[cfg_name] = (per_m, agg)

    header = f"{'Config':<11} | {'Meeting':<13} | {'R':<2} | {'P1_Win':<6} | {'Top4':<4} | {'P5_Win':<6} | {'P1_Plc':<6} | {'Brier':<7} | {'LogLoss':<7} | {'$10_ROI':<8}"
    print(header)
    print("-" * len(header))
    for cfg_name, _ in CONFIGS:
        per_m, agg = summaries[cfg_name]
        for row in per_m + [agg]:
            m_lbl = f"**{row['meeting']}**" if row["meeting"] == "TOTAL" else row["meeting"]
            print(
                f"{cfg_name:<11} | {m_lbl:<13} | {row['races']:<2} | {row['p1_win']:<6} | {row['top4_hit']:<4} | "
                f"{row['p5_win']:<6} | {row['p1_place']:<6} | {row['brier']:<7.5f} | {row['logloss']:<7.5f} | {row['roi_pct']:>+7.2f}%"
            )
        print("-" * len(header))

    base_agg = summaries["A_OFF"][1]
    print("\n=== DECISION RULE SUMMARY (§6: No worse than A on Winner-in-Picks-1-4 AND Brier Score) ===")
    for cfg_name, _ in CONFIGS[1:]:
        _, agg = summaries[cfg_name]
        t4_ok = agg["top4_hit"] >= base_agg["top4_hit"]
        brier_ok = agg["brier"] <= base_agg["brier"] + 1e-6
        verdict = "NO REGRESSION (ELIGIBLE FOR REVIEW)" if (t4_ok and brier_ok) else "REGRESSION / KEEP OFF"
        print(
            f"  {cfg_name:<10}: Top4 {agg['top4_hit']}/{agg['races']} vs {base_agg['top4_hit']}/{base_agg['races']} | "
            f"Brier {agg['brier']:.5f} vs {base_agg['brier']:.5f} | P1_ROI {agg['roi_pct']:+.2f}% vs {base_agg['roi_pct']:+.2f}% -> {verdict}"
        )

    for cfg_name in ("B_TRIALS", "B_STEWARD", "B_REPLAY", "B_ALL"):
        diffs = _collect_changes(meeting_runs, cfg_name)
        print(f"\n=== RUNNER CHANGES: A_OFF vs {cfg_name} ({len(diffs)} changed runners) ===")
        if not diffs:
            print("  (none)")
        for d in diffs:
            print(
                f"  {d['meeting']} R{d['race']:<2} #{d['no']:<2} {d['name']:<20} Fin={d['finish']:<3} GS={d['gs_delta']:<13} | {d['changes']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

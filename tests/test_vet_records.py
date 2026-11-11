import os
import sys
from datetime import date
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from vet_records import (
    BARRIER_TRIAL_UNPUBLISHED_TEXT,
    NO_VET_RECORDS_TEXT,
    VET_DATA_UNAVAILABLE_TEXT,
    build_horse_vet_record,
    extract_vet_attributes,
    format_radar_vet_item,
    format_vet_column_display,
    parse_hkjc_date,
    render_runner_vet_block_html,
    update_latest_horse_stats_csv,
)
from features.stewards import check_health_risk, get_health_risk_severity
from monitoring.contracts import compute_telemetry_harmony_multipliers


AS_OF = date(2026, 11, 11)


def test_hayday_latest_is_ddsp_active_requirement():
    """
    Hayday (HK_2022_H321): HKJC table lists oldest row 0 first (23/02/2023 humerus injury)
    and newest row last (12/07/2026 DDSP airway abnormality, Passed: -).
    Must surface 12/07/2026 as latest, category='airway', status='active_requirement'.
    """
    raw_rows = [
        {
            "date": "23/02/2023",
            "details": "Right fore humerus bone injury",
            "passed_on": "29/06/2023",
        },
        {
            "date": "12/07/2026",
            "details": "Airway abnormality (dorsal displacement of the soft palate) noted after racing",
            "passed_on": "-",
        },
    ]
    rec = build_horse_vet_record(
        horse_id="HK_2022_H321",
        horse_code="H321",
        horse_name="HAYDAY",
        raw_rows=raw_rows,
        source_url="https://racing.hkjc.com/en-us/local/information/ovehorse?horseid=HK_2022_H321",
        as_of=AS_OF,
    )
    assert len(rec["entries"]) == 2
    latest = rec["entries"][0]
    assert latest["date"] == "12/07/2026"
    assert latest["category"] == "airway"
    assert latest["procedure"] == "DDSP (soft palate displacement)"
    assert latest["status"] == "active_requirement"
    assert latest["passed_on"] is None
    assert latest["is_material"] is True
    assert rec["prev_run_vet_finding"] == 1


def test_viva_taste_latest_surgery_cleared_and_roarer_preserved():
    """
    Viva Taste (HK_2024_K415):
    Row 0: 15/11/2025 Diagnosed to be a "roarer" (Passed: -)
    Row 1: 03/07/2026 Throat surgery to correct an airway abnormality (tieback and hobday) (Passed: 21/09/2026)
    Latest must be surgery, cleared 21/09/2026, prev_run_vet_finding == 0, and roarer stays in entries.
    """
    raw_rows = [
        {
            "date": "15/11/2025",
            "details": 'Diagnosed to be a "roarer"',
            "passed_on": "-",
        },
        {
            "date": "03/07/2026",
            "details": "Throat surgery to correct an airway abnormality (tieback and hobday)",
            "passed_on": "21/09/2026",
        },
    ]
    rec = build_horse_vet_record(
        horse_id="HK_2024_K415",
        horse_code="K415",
        horse_name="VIVA TASTE",
        raw_rows=raw_rows,
        source_url="https://racing.hkjc.com/en-us/local/information/ovehorse?horseid=HK_2024_K415",
        as_of=AS_OF,
    )
    assert len(rec["entries"]) == 2
    latest = rec["entries"][0]
    assert latest["date"] == "03/07/2026"
    assert latest["category"] == "surgery"
    assert latest["status"] == "cleared"
    assert latest["passed_on"] == "21/09/2026"
    assert rec["prev_run_vet_finding"] == 0
    assert rec["has_surgery_history"] == 1
    assert rec["last_material_date"] == "03/07/2026"
    assert rec["days_since_material_clearance"] == (AS_OF - date(2026, 9, 21)).days
    # Ensure historical roarer entry remains in entries
    older = rec["entries"][1]
    assert older["date"] == "15/11/2025"
    assert "roarer" in older["details"].lower()


def test_kansas_castration_is_no_requirement_and_tracheal_blood_is_active():
    """
    Kansas (HK_2025_L305):
    Row 0: 15/01/2026 Castration (Passed: -) -> administrative, no_requirement, is_material=False
    Row 1: 08/11/2026 Substantial blood in trachea noted on post-race scoping (Passed: -) -> tracheal_blood, active_requirement
    """
    raw_rows = [
        {
            "date": "15/01/2026",
            "details": "Castration",
            "passed_on": "-",
        },
        {
            "date": "08/11/2026",
            "details": "Substantial blood in trachea noted on post-race scoping",
            "passed_on": "-",
        },
    ]
    rec = build_horse_vet_record(
        horse_id="HK_2025_L305",
        horse_code="L305",
        horse_name="KANSAS",
        raw_rows=raw_rows,
        source_url="https://racing.hkjc.com/en-us/local/information/ovehorse?horseid=HK_2025_L305",
        as_of=AS_OF,
    )
    castration_entry = rec["entries"][1]
    assert castration_entry["date"] == "15/01/2026"
    assert castration_entry["category"] == "administrative"
    assert castration_entry["status"] == "no_requirement"
    assert castration_entry["is_material"] is False

    latest = rec["entries"][0]
    assert latest["date"] == "08/11/2026"
    assert latest["category"] == "tracheal_blood"
    assert latest["status"] == "active_requirement"
    assert latest["is_material"] is True
    assert rec["prev_run_vet_finding"] == 1

    # Radar tag must map tracheal blood to TRACHEAL BLOOD (never RESPIRATORY CLEAR)
    radar = format_radar_vet_item(rec, "#1 KANSAS")
    assert radar is not None
    assert "TRACHEAL BLOOD" in radar["type"]
    assert "RESPIRATORY CLEAR" not in radar["type"]

    # A horse with ONLY Castration must have prev_run_vet_finding == 0 and never say "Clear Record"
    castration_only = build_horse_vet_record(
        horse_id="HK_2025_L999",
        horse_code="L999",
        horse_name="GELDING TEST",
        raw_rows=[{"date": "15/01/2026", "details": "Castration", "passed_on": "-"}],
        source_url="https://racing.hkjc.com/en-us/local/information/ovehorse?horseid=HK_2025_L999",
        as_of=AS_OF,
    )
    assert castration_only["prev_run_vet_finding"] == 0
    disp_castration = format_vet_column_display(castration_only)
    assert disp_castration != "✅ Clear Record"
    assert "Clear Record" not in disp_castration
    assert "No material entry" in disp_castration
    assert "15/01/2026" in disp_castration
    assert format_radar_vet_item(castration_only, "#2 GELDING TEST") is None


def test_aeris_nova_five_entries_latest_failed_vet_exam_cleared():
    """
    Aeris Nova (HK_2023_J534): 5 entries on HKJC ovehorse.
    Latest (15/05/2026) is failed_vet_exam, cleared 24/08/2026.
    """
    raw_rows = [
        {"date": "30/07/2025", "details": "Castration", "passed_on": "-"},
        {"date": "20/01/2026", "details": "Bled from both nostrils", "passed_on": "15/05/2026"},
        {"date": "10/04/2026", "details": "Failed vet exam: Lame left fore", "passed_on": "24/04/2026"},
        {"date": "27/04/2026", "details": "Failed vet exam: Substantial blood on scope", "passed_on": "15/05/2026"},
        {"date": "15/05/2026", "details": "Failed vet exam: Substantial blood on scope", "passed_on": "24/08/2026"},
    ]
    rec = build_horse_vet_record(
        horse_id="HK_2023_J534",
        horse_code="J534",
        horse_name="AERIS NOVA",
        raw_rows=raw_rows,
        source_url="https://racing.hkjc.com/en-us/local/information/ovehorse?horseid=HK_2023_J534",
        as_of=AS_OF,
    )
    assert len(rec["entries"]) == 5
    latest = rec["entries"][0]
    assert latest["date"] == "15/05/2026"
    assert latest["category"] == "failed_vet_exam"
    assert latest["status"] == "cleared"
    assert latest["passed_on"] == "24/08/2026"
    assert rec["prev_run_vet_finding"] == 0
    assert rec["nostril_bleed_count_12m"] == 1
    assert rec["tracheal_bleed_count_12m"] == 2
    assert rec["bleed_count_12m"] == 3


def test_sea_chariot_update_clause_promotes_category_to_surgery():
    """
    Sea Chariot (HK_2024_K358):
    '16/03/2026 Lame left front leg on the day after racing. Update: Arthroscopic surgery to left fore fetlock (bone fragment removal).'
    Must take the more specific category from the Update clause -> category == 'surgery'.
    """
    details = (
        "Lame left front leg on the day after racing. "
        "Update: Arthroscopic surgery to left fore fetlock (bone fragment removal)."
    )
    attrs = extract_vet_attributes(details, "11/09/2026")
    assert attrs["category"] == "surgery"
    assert attrs["status"] == "cleared"
    assert attrs["passed_on"] == "11/09/2026"
    assert attrs["body_part"] == "fetlock"
    assert attrs["side"] == "left fore"
    assert "arthroscopic surgery" in (attrs["procedure"] or "")
    assert attrs["is_material"] is True


def test_name_collision_isolation_by_horse_code_and_horse_id(tmp_path):
    """
    Two horses with the exact same name ('SUPER STAR') but different horse_id / horse_code
    must never merge or overwrite each other in vet_records or latest_horse_stats.csv.
    """
    rec_old = build_horse_vet_record(
        horse_id="HK_2020_E111",
        horse_code="E111",
        horse_name="SUPER STAR",
        raw_rows=[{"date": "10/01/2022", "details": "Bled from both nostrils", "passed_on": "10/05/2022"}],
        source_url="https://racing.hkjc.com/en-us/local/information/ovehorse?horseid=HK_2020_E111",
        as_of=AS_OF,
    )
    rec_new = build_horse_vet_record(
        horse_id="HK_2024_K999",
        horse_code="K999",
        horse_name="SUPER STAR",
        raw_rows=[],
        source_url="https://racing.hkjc.com/en-us/local/information/ovehorse?horseid=HK_2024_K999",
        as_of=AS_OF,
    )
    store = {
        "scraped_at": "2026-11-11T00:00:00Z",
        "horses": {
            "HK_2020_E111": rec_old,
            "HK_2024_K999": rec_new,
        },
    }
    stats_csv = tmp_path / "latest_horse_stats.csv"
    initial_df = pd.DataFrame(
        [
            {"clean_name": "SUPER STAR", "horse_code": "E111", "prev_run_vet_finding": 1, "latest_vet_note": "Old"},
            {"clean_name": "SUPER STAR", "horse_code": "K999", "prev_run_vet_finding": 0, "latest_vet_note": "No Findings"},
        ]
    )
    initial_df.to_csv(stats_csv, index=False)

    update_latest_horse_stats_csv(store, stats_path=str(stats_csv))
    updated = pd.read_csv(stats_csv).set_index("horse_code")

    assert len(updated) == 2
    assert "Bled from both nostrils" in str(updated.loc["E111", "latest_vet_note"])
    assert str(updated.loc["K999", "latest_vet_note"]) == NO_VET_RECORDS_TEXT


def test_winning_machine_and_race6_picks_fixture(tmp_path):
    """
    Worked acceptance fixture (Section 3 & Section 4):
    - WINNING MACHINE (K239, HK_2024_K239): 4 rows on HKJC ovehorse, newest-first:
      14/07/2026 (surgery, Passed 12/10/2026), 01/07/2026 (bleeding_nostrils, Passed 12/10/2026),
      31/03/2025 (injury, Passed 05/06/2025), 20/01/2025 (administrative, Passed 27/01/2025).
    - Summary must be: '14/07/2026 — Arthroscopic surgery to both knees (bone fragment removal). Cleared 12/10/2026'
    - Stewards' requirement must quote the Sha Tin 01/07/2026 Race 3 report, show Passed 12/10/2026 for the official
      veterinary examination, and show 'Barrier trial completion date not published' when no trial date is published.
    - Race 6 picks FLOW RIDER (M012) & MR INVINCIBLE (L448) with 0 entries must say 'No HKJC veterinary records'
      (never '✅ Clear Record'), and failed fetches must say 'Vet data unavailable'.
    - ALGARVE (historical recycled K239) must not inherit WINNING MACHINE's horse_id or vet fields in latest_horse_stats.csv.
    """
    raw_rows = [
        {
            "date": "20/01/2025",
            "details": "Fractious in the barriers. Withdrawn from barrier trial.",
            "passed_on": "27/01/2025",
        },
        {
            "date": "31/03/2025",
            "details": "Lame right hind leg on the day after racing. Update: Right pelvis injury.",
            "passed_on": "05/06/2025",
        },
        {
            "date": "01/07/2026",
            "details": "Bled from both nostrils after racing.",
            "passed_on": "12/10/2026",
        },
        {
            "date": "14/07/2026",
            "details": "Arthroscopic surgery to both knees (bone fragment removal).",
            "passed_on": "12/10/2026",
        },
    ]
    st_quote = (
        "A veterinary inspection immediately following the race found that horse to have bled from both nostrils. "
        "Before being allowed to race again, WINNING MACHINE will be required to perform satisfactorily in a barrier trial "
        "and be subjected to an official veterinary examination."
    )
    wm_rec = build_horse_vet_record(
        horse_id="HK_2024_K239",
        horse_code="K239",
        horse_name="WINNING MACHINE",
        raw_rows=raw_rows,
        source_url="https://racing.hkjc.com/en-us/local/information/ovehorse?horseid=HK_2024_K239",
        as_of=AS_OF,
        scraped_at="2026-11-11T01:19:59Z",
        stewards_reports={"01/07/2026": {"date": "01/07/2026", "report": st_quote, "quote": st_quote}},
        official_trials=None,
        last_stewards_comment=st_quote,
    )

    assert len(wm_rec["entries"]) == 4
    assert [e["date"] for e in wm_rec["entries"]] == [
        "14/07/2026",
        "01/07/2026",
        "31/03/2025",
        "20/01/2025",
    ]
    assert [e["category"] for e in wm_rec["entries"]] == [
        "surgery",
        "bleeding_nostrils",
        "injury",
        "administrative",
    ]
    assert wm_rec["entries"][0]["passed_on"] == "12/10/2026"
    assert wm_rec["entries"][1]["passed_on"] == "12/10/2026"
    assert wm_rec["prev_run_vet_finding"] == 0

    summary = format_vet_column_display(wm_rec)
    assert summary == "14/07/2026 — Arthroscopic surgery to both knees (bone fragment removal). Cleared 12/10/2026"
    assert summary != "✅ Clear Record"

    block_html = render_runner_vet_block_html({"no": 11, "name": "WINNING MACHINE", "code": "K239"}, wm_rec)
    assert "14/07/2026 — Arthroscopic surgery to both knees (bone fragment removal). Cleared 12/10/2026" in block_html
    assert st_quote in block_html
    assert "Passed 12/10/2026" in block_html
    assert BARRIER_TRIAL_UNPUBLISHED_TEXT in block_html
    assert "https://racing.hkjc.com/en-us/local/information/ovehorse?horseid=HK_2024_K239" in block_html
    assert "2026-11-11T01:19:59Z" in block_html

    # Race 6 picks with 0 entries (Flow Rider M012, Mr Invincible L448) and failed fetches
    flow_rider = build_horse_vet_record(
        horse_id="HK_2025_M012",
        horse_code="M012",
        horse_name="FLOW RIDER",
        raw_rows=[],
        source_url="https://racing.hkjc.com/en-us/local/information/ovehorse?horseid=HK_2025_M012",
        as_of=AS_OF,
    )
    assert format_vet_column_display(flow_rider) == NO_VET_RECORDS_TEXT
    assert "Clear Record" not in format_vet_column_display(flow_rider)
    assert format_vet_column_display(None) == VET_DATA_UNAVAILABLE_TEXT

    # ALGARVE vs WINNING MACHINE brand-code collision check in latest_horse_stats.csv
    stats_csv = tmp_path / "latest_horse_stats.csv"
    pd.DataFrame(
        [
            {
                "clean_name": "ALGARVE",
                "horse_code": "K239",
                "horse_id": "HK_2024_K239",
                "latest_vet_note": "14/07/2026: Arthroscopic surgery",
                "prev_run_vet_finding": 0,
            },
            {
                "clean_name": "WINNING MACHINE",
                "horse_code": "K239",
                "horse_id": "HK_2024_K239",
                "latest_vet_note": "No Findings",
                "prev_run_vet_finding": 0,
            },
        ]
    ).to_csv(stats_csv, index=False)
    update_latest_horse_stats_csv({"HK_2024_K239": wm_rec}, stats_path=str(stats_csv))
    df_out = pd.read_csv(stats_csv).set_index("clean_name")
    assert pd.isna(df_out.loc["ALGARVE", "horse_id"]) or str(df_out.loc["ALGARVE", "horse_id"]) == ""
    assert "Arthroscopic surgery" not in str(df_out.loc["ALGARVE", "latest_vet_note"])
    assert str(df_out.loc["WINNING MACHINE", "horse_id"]) == "HK_2024_K239"
    assert "Arthroscopic surgery" in str(df_out.loc["WINNING MACHINE", "latest_vet_note"])


def test_dd_mm_yyyy_parsing_and_cleared_penalty_immunity():
    """
    03/07/2026 must parse as 3 July 2026 (never 7 March 2026).
    Also verify get_health_risk_severity matches 'bled from both nostrils' and cleared entries
    do not trigger the -2% active_vet_risk_penalty in monitoring/contracts.py.
    """
    parsed = parse_hkjc_date("03/07/2026")
    assert parsed is not None
    assert (parsed.year, parsed.month, parsed.day) == (2026, 7, 3)
    assert parsed.month == 7 and parsed.day == 3

    # Severity matching for 'Bled from both nostrils' when active vs cleared
    assert get_health_risk_severity(latest_vet_note="20/01/2026: Bled from both nostrils (Passed: -)") == 3
    assert get_health_risk_severity(latest_vet_note="20/01/2026: Bled from both nostrils (Passed: 15/05/2026)") == 0
    assert check_health_risk(latest_vet_note="03/07/2026: Throat surgery (Passed: 21/09/2026)") is False

    # Cleared entries must NEVER trigger the -2% active_vet_risk_penalty in monitoring/contracts.py
    df_runners = pd.DataFrame(
        [
            {
                "name": "CIRCUIT CENTURY",
                "prev_run_vet_finding": 0,
                "latest_vet_note": "01/10/2026: Substantial blood in trachea (Passed: 03/11/2026)",
                "vet_status": "cleared",
                "draw": 4,
                "actual_weight": 135,
                "win_odds": 5.0,
            },
            {
                "name": "KANSAS UNCLEARED",
                "prev_run_vet_finding": 1,
                "latest_vet_note": "08/11/2026: Substantial blood in trachea noted on post-race scoping (Passed: -)",
                "vet_status": "active_requirement",
                "draw": 5,
                "actual_weight": 125,
                "win_odds": 8.0,
            },
        ]
    )
    res = compute_telemetry_harmony_multipliers(
        df_runners, is_awt_race=False, is_hv=True, is_st=False, distance=1650, class_int=3
    )
    penalties = res["active_vet_risk_penalty"]
    assert penalties[0] == 0.0
    assert penalties[1] == -0.020


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    test_hayday_latest_is_ddsp_active_requirement()
    print("[PASS] test_hayday_latest_is_ddsp_active_requirement")
    test_viva_taste_latest_surgery_cleared_and_roarer_preserved()
    print("[PASS] test_viva_taste_latest_surgery_cleared_and_roarer_preserved")
    test_kansas_castration_is_no_requirement_and_tracheal_blood_is_active()
    print("[PASS] test_kansas_castration_is_no_requirement_and_tracheal_blood_is_active")
    test_aeris_nova_five_entries_latest_failed_vet_exam_cleared()
    print("[PASS] test_aeris_nova_five_entries_latest_failed_vet_exam_cleared")
    test_sea_chariot_update_clause_promotes_category_to_surgery()
    print("[PASS] test_sea_chariot_update_clause_promotes_category_to_surgery")
    with tempfile.TemporaryDirectory() as td:
        test_name_collision_isolation_by_horse_code_and_horse_id(Path(td))
        test_winning_machine_and_race6_picks_fixture(Path(td))
    print("[PASS] test_name_collision_isolation_by_horse_code_and_horse_id")
    print("[PASS] test_winning_machine_and_race6_picks_fixture")
    test_dd_mm_yyyy_parsing_and_cleared_penalty_immunity()
    print("[PASS] test_dd_mm_yyyy_parsing_and_cleared_penalty_immunity")
    print("ALL 8 VET RECORD TESTS PASSED.")


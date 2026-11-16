# Silks feed schema (schema_version 1.0)

Produced by the saved routine "Daily HKJC declared runners trial review". Files in this folder:

| File | Content |
|---|---|
| declared_trials_latest.csv / .json | One row per declared or standby (reserve) runner of every HV/ST meeting in the 48h window of the latest run |
| meeting_<YYYY-MM-DD>_<HV\|ST>.csv / .json | Same rows restricted to one meeting |
| trials_history.csv | Append-only trial extracts. Dedup key = horse_code + trial_date + trial_batch + trial_distance_m. Existing rows are never edited; new keys are appended. Seeded on first creation from archives/review_*.csv (legacy: finish position/field size per the legacy method, field size may have included withdrawn horses; result text not captured; seed_source says so) |
| manifest.json | Written LAST: run id, timestamps, meetings, row counts, coverage, completeness, flag counts, source failures, sha256 of every other feed file. If manifest is older than the data files, treat the feed as incomplete. |

All files are written temp-file-then-rename. On validation failure the previous feed is kept and the failure recorded in ../status_<date>.txt (no manifest update).

## JSON conventions
Missing values are `null`. Tri-state flags are `true` / `false` / `null` (null = unknown). In CSV, flags are the strings `true` / `false` / `unknown`; missing values are empty strings. The JSON file is `{schema_version, run_id, ..., row_count, rows:[...]}`.

## Identity columns
- schema_version, run_id (e.g. `2026-11-13_0600HKT_ST_20261114`), retrieved_at_hkt / retrieved_at_utc (racecard retrieval time; later fetches of btresult and horse pages are in `_raw_runs/<date>_HKT/fetch_log.tsv`).
- meeting_date (ISO), venue (`ST`/`HV`), race_no, race_name.
- horse_no: declared saddle-cloth number; EMPTY for standby/reserve runners, whose standby_order holds the HKJC stand-by list number.
- horse_name (UPPERCASE), horse_code (permanent HKJC brand no., e.g. L245), horse_id (HKJC id, e.g. HK_2025_L245).
- runner_status: `declared` | `standby` (reserve). `withdrawn` is used if the card lists a withdrawal (none seen in this run).
- declared_gear: gear on the race card for this race (separate from trial gear). declared_gear_note explains blank.

## Trial columns (latest published barrier trial found before retrieval)
trial_date (ISO), trial_track (Sha Tin/Conghua/Happy Valley), trial_surface (`Turf`/`AWT`), trial_going, trial_distance_m, trial_batch, trial_finish_pos (row order among starters; the HKJC page has no explicit position column), trial_field_size (starters only, Withdrawn rows excluded), trial_lbw_raw (as published; blank for the winner), trial_lbw_lengths, trial_time_raw (horse's own published time, M.SS.hh), trial_time_sec, trial_sectionals (batch-leader/batch sectionals as published), trial_sectionals_type (`batch_leader` = not the horse's own splits; `individual` would be used only if HKJC publishes per-horse splits, which it currently does not), trial_comment (exact), trial_result_text (exact Result column, e.g. Passed), trial_gear (trial gear; separate from declared_gear), trial_gear_differs_from_declared, trial_jockey, trial_running_position, days_since_trial (meeting date minus trial date).
If several trials exist the latest date, then highest batch number, is used.

### trial_lbw_lengths
N / Nose = 0.05; SH = 0.1; HD / Head = 0.2; Neck / NK = 0.3; fractions e.g. `3-1/2`, `3 1/2L` = 3.5; plain numbers as is; blank on the winner row = 0. Unrecognised codes (e.g. `ML`, `DH`, `H`) are NOT guessed: lengths empty and noted in data_quality_notes.

### trial_time_sec
M.SS.hh converted to seconds (1.11.33 = 71.33).

## Opposition
- opposition_names: other starters in the same batch.
- opposition_ratings: `NAME (code)=rating` — the opponent's CURRENT HKJC rating from its HKJC horse page, plus any Group/Griffin win in that page's form record in brackets. `rating unavailable` if the page had no rating.
- opposition_rating_date: date those ratings were read (retrieval date). It is NOT the trial date; HKJC publishes no as-of-trial ratings.
- opposition_qualifying: opponents meeting the quality rule.

## Flags (each has a `_reason` column)
| Flag | Rule |
|---|---|
| flag_speed_outlier_fast | horse's own time vs median of ALL timed starters with same trial date + track + surface + distance (across batches; min 6 horses else unknown). true if >= 1.00 s quicker than median |
| flag_speed_outlier_slow | same median; true if >= 1.50 s slower |
| flag_quality_opposition | true only if some batch opponent has a published current HKJC rating >= 80 or a Group (G1/G2/G3) or Griffin win in its horse-page record (last 3 seasons shown on that page). false if every opponent has a rating and none qualify. unknown if none qualifies but some opponent's data was unavailable, or no opponents/trial |
| flag_poor_finish | true if finish position in the bottom third of starters (pos > 2/3 of field) or beaten > 5.0 L; false if neither and the margin is known; unknown if margin unparseable and not bottom third |
| flag_stale_trial | true if trial is more than 90 days before the meeting date; unknown if no trial |

Median and flags do not adjust for going or batch differences (as specified). No video was watched; all values are text facts from HKJC pages.

## Other columns
trial_same_surface_distance_median_sec / _n_timed (inputs of the speed flags); source_url_racecard, source_url_trial (btresult page for the trial date), source_url_horse; completeness (`complete` | `missing_trial`); data_quality_notes.

# HKJC trip notes — column schema

Replay-bot structured post-meeting trip notes for Hong Kong Jockey Club (HKJC) meetings. One row per reviewer trip note, enriched with official HKJC results, stewards' reports and sectional times.

This folder is the `data/replay/` feed on the `trial-data` branch of `lelandbondx/golden-stallion-hkjc`. Canonical type definitions for the original 34 columns are in `schema.json` (`schema_version` 2). This document describes every column in the files published here, the join keys, and the rules that must not change.

## Files

- `YYYY-MM-DD_VENUE.csv` — one meeting (VENUE = `ST` Sha Tin, `HV` Happy Valley). 34 original columns plus 5 appended alias/timestamp columns (see below).
- `YYYY-MM-DD_VENUE.json` — the same rows, typed, plus a `meeting` block (`generated_at`, `source_fetched_at`, `source_fetched_at_by_race`, course, going, races reviewed, limitations, sources). Meeting JSON files are copied from the validated build without modification, so their row objects have the original 34 fields only.
- `all_trip_notes.csv` — every meeting concatenated, deduplicated on `date`+`venue`+`race`+`horse`, with the same 5 appended columns.
- `latest.json` — pointer to the newest meeting.
- `schema.json` — machine-readable definition of the original 34 columns.
- `manifest.json` — run time, row counts, completeness and validation status (written in its own final commit).

## Row keys

Rows are uniquely keyed by:

- `date` / `meeting_date` — meeting date, ISO `YYYY-MM-DD` (Hong Kong local)
- `venue` — `ST` or `HV`
- `race` / `race_no` — race number on the card
- `horse` / `horse_name` — official horse name, uppercase, trimmed
- `horse_code` — HKJC brand number (e.g. `L165`). Preferred join key when present; may be blank (unknown).

`source` URLs (`results_url`, `stewards_url`, `replay_url`) are also on each row when known.

## Rule: blank means unknown

In CSV, an empty cell means unknown or not applicable. In JSON it is `null`. It never means `0` or `false`.

Booleans (`traffic`, `wide_no_cover`, `slow_away`, `sampled`): `false` means not flagged in the review. It does not prove a clean trip. Read CSVs with `keep_default_na=False` and convert explicitly, or use the JSON files.

A missing horse (no row) means nothing notable was recorded for it, not that it had a confirmed clean run. Only horses with a trip note get a row.

## Replay observations vs official stewards findings

These must be kept distinct:

- **Official findings** — `stewards_excuse`, `vet_finding` and `clearance_required` are copied verbatim from the official HKJC stewards' report (`RaceReportFull`). Do not paraphrase or infer a diagnosis.
- **Replay observations** — the reviewer's `note` and `flags` may include things seen on the official replay that are not in the stewards' report (for example a `wide_no_cover` or `strong_closer` flag). `source` tells you the evidence:
  - `replay` — reviewer's own observation only; not an official finding
  - `stewards` — official report only (for example a withdrawn horse, or an incident that could not be confirmed on video)
  - `replay+stewards` — both
- `verification` records per-row provenance and limitations (sectional source, replay-angle limits, out-of-vocabulary flags, conflicts).
- `pace_role` is derived only from the first official running position, not from the video.

Never claim a video was watched unless it actually was. Never invent values; leave them blank.

## Append-only column policy

Column names of the original 34 fields are stable. New columns may be **appended at the end** only. Existing columns must never be renamed or dropped. Schema versions increment when columns are added (`schema.json` changelog: v1 = 33 columns; v2 added `generated_at` as the last original column).

The CSV copies in this folder append five lossless alias/timestamp columns after `generated_at`. They do not replace or rename the originals:

| Appended column | Equals / source |
| --- | --- |
| `meeting_date` | `date` |
| `race_no` | `race` |
| `horse_name` | `horse`, uppercased and trimmed |
| `retrieved_at_hkt` | that race's `source_fetched_at_by_race` (`R01`…`R11`) from the meeting JSON; else meeting-level `source_fetched_at`. ISO 8601 with `+08:00` (HKT). Blank if unknown. |
| `retrieved_at_utc` | the same instant as `retrieved_at_hkt`, expressed in UTC with a `Z` suffix. Blank if `retrieved_at_hkt` is blank. |

These five columns are **not** present in the meeting JSON files or in `schema.json`, which remain exact copies of the validated build.

## Original columns (schema_version 2)

Order below is the CSV header order.

### Race and horse context

1. **schema_version** (integer, required) — schema version of this row. Currently `2` (v1 columns plus `generated_at`).
2. **date** (string `YYYY-MM-DD`, required) — meeting date (Hong Kong local).
3. **venue** (string, required) — `ST` = Sha Tin, `HV` = Happy Valley.
4. **race** (integer, required) — race number on the card.
5. **race_index** (integer, nullable) — HKJC season race index (e.g. 178) from LocalResults.
6. **class** (string, nullable) — official race class string, e.g. `Class 3`, `Group Three`.
7. **distance_m** (integer, required) — race distance in metres.
8. **course** (string, nullable) — track/course from official results, normalised: `Turf B`, `Turf C+3`, `All Weather Track`.
9. **going** (string, nullable) — official going for that track on the day, uppercase (e.g. `GOOD`).
10. **horse** (string, required) — official horse name exactly as in HKJC results (uppercase). Join key with `horse_code`.
11. **horse_code** (string, nullable) — HKJC brand code, e.g. `L165`. Most reliable join key.
12. **draw** (integer, nullable) — barrier draw. Blank for withdrawn horses.
13. **jockey** (string, nullable) — jockey as printed on official results (may include apprentice claim, e.g. `(-2)`).
14. **finish** (string, nullable) — official placing as a string; keeps dead heats (`7 DH`). Blank = withdrawn / no placing.
15. **win_odds** (number, nullable) — official final win odds (decimal dividend per $1, HKJC style). Blank if withdrawn.

### Flags

16. **flags** (CSV: semicolon-separated string; JSON: array of strings; nullable) — trip-note flags from the reviewer. Blank = no flags. Allowed values and meanings:

    - `blocked` — held up / no run
    - `checked` — steadied or checked
    - `hampered` — hampered by another runner
    - `bumped` — physical contact
    - `wide_no_cover` — raced wide without cover
    - `slow_away` — slow/awkward start or lost ground at the start
    - `strong_closer` — made strong late ground
    - `more_in_hand` — won/ran with more in hand than the margin
    - `faded_after_leading` — led or raced prominently then weakened
    - `soft_lead` — led at a soft/moderate pace
    - `led_throughout` — led all the way
    - `keen` — raced keenly / over-raced
    - `green` — raced green/inexperienced
    - `favourite_beaten` — beaten favourite
    - `vet_blocked` — official vet issue / clearance required before racing again
    - `stewards_flag` — notable stewards action or explanation
    - `roarer` — noted making a respiratory noise
    - `possible_issue` — something looked wrong, not officially confirmed
    - `crowded` — crowded for room

    Legacy exception: `wide` appears once in the 2026-11-08 data (R7 MONARCH COUNTY) and is kept verbatim. It means raced wide; cover status is not encoded in that flag, and `wide_no_cover` is left blank (unknown).

17. **traffic** (boolean, nullable) — `true` if `flags` contain any of `blocked`, `checked`, `hampered`, `bumped`, `crowded`. `false` = none of those flagged by the review (not proof of a clean trip).
18. **wide_no_cover** (boolean, nullable) — `true` if `flags` contain `wide_no_cover`. `false` = not flagged. Blank = unknown (legacy `wide` flag without cover info).
19. **slow_away** (boolean, nullable) — `true` if `flags` contain `slow_away`. `false` = not flagged.

### Official text

20. **stewards_excuse** (string, nullable) — verbatim official stewards' racing-incident text for this horse (`RaceReportFull`). Blank if the report said `No report.` or only `Sent for sampling post-race.` When present it is the full verbatim text, which may include the sampling sentence.
21. **sampled** (boolean, nullable) — `true` if the stewards' text includes `Sent for sampling post-race` (routine drug test). Blank if no stewards entry exists.

### Pace

22. **pace_role** (string, nullable) — derived ONLY from the first official running position (LocalResults `Running Position`, first call) and field size N (runners with positions): `1` = `led`; `2`–`3` = `on_pace`; `4`..`ceil(2N/3)` = `midfield`; `> ceil(2N/3)` = `back`. Blank if no official positions (e.g. withdrawn). Allowed: `led`, `on_pace`, `midfield`, `back`.
23. **pace_note** (string, nullable) — official running-positions string plus any pace-related review flags (`led_throughout`, `soft_lead`, `faded_after_leading`, `keen`, `strong_closer`). No free-text inference.

### Vet and clearance

24. **vet_finding** (string, nullable) — verbatim official sentences from the stewards' text about veterinary findings (inspection results, blood in trachea, lameness, heart rhythm, vet checks pre-race, vet withdrawals). Official text only; blank if none. Do not confuse blood in the trachea with bleeding from both nostrils.
25. **clearance_required** (string, nullable) — verbatim official sentence(s) beginning `Before being allowed to race again...` (official veterinary examination, stalls test, barrier trial). Blank if none.

### Sectionals

26. **horse_last_400m_sec** (number, nullable) — this horse's official final sectional (last 400m) in seconds, from HKJC DisplaySectionalTime. Blank if unavailable (e.g. withdrawn).
27. **race_last_400m_sec** (number, nullable) — race's official final sectional (leader's last 400m split) in seconds, from LocalResults `Sectional Time`, cross-checked against the DisplaySectionalTime header.

### Notes, sources, timestamps

28. **note** (string, nullable) — reviewer's trip note, copied verbatim from the legacy `trip_notes.csv`.
29. **source** (string, required) — evidence behind the flags/note: `replay`, `stewards`, or `replay+stewards`.
30. **results_url** (string, nullable) — official LocalResults URL for the race.
31. **stewards_url** (string, nullable) — official RaceReportFull URL for the meeting.
32. **replay_url** (string, nullable) — official HKJC replay-full video URL for the race (only for rows whose `source` includes `replay`).
33. **verification** (string, nullable) — per-row provenance and limitations (where the sectional came from, replay angle limits, replay-only rows, out-of-vocabulary flags, gaps).
34. **generated_at** (string, required) — build time of the file this row was written in (same for every row of one build). ISO 8601 with `+08:00` (HKT) offset. Added in `schema_version` 2.

### Appended columns (CSV copies in this folder only)

35. **meeting_date** — alias of `date`.
36. **race_no** — alias of `race`.
37. **horse_name** — alias of `horse`, uppercased and trimmed.
38. **retrieved_at_hkt** — source-fetch time in HKT, as described above.
39. **retrieved_at_utc** — the same instant in UTC (`Z`).

## Pre-race cross-reference files (`prerace/`)

This section documents a separate, append-only add-on. It does **not** rename, drop, or alter any of the 39 columns described above, and it is **not** part of `all_trip_notes.csv` or `manifest.json`.

Location: `data/replay/prerace/`. One upcoming meeting at a time, named `YYYY-MM-DD_VENUE.csv` and `YYYY-MM-DD_VENUE.json` (VENUE = `ST` or `HV`).

These files join the official HKJC racecard for an upcoming meeting to the most recent stored trip-note row (if any) for each horse. They are a pre-race helper for Silks AI / Antigravity. They are not post-meeting trip notes and must not be concatenated into `all_trip_notes.csv`.

### Row keys

- `meeting_date` — upcoming meeting date, ISO `YYYY-MM-DD` (Hong Kong local)
- `venue` — `ST` or `HV`
- `race_no` — race number on the upcoming card
- `horse_no` — saddlecloth / standby number as printed on the racecard
- `horse_name` — official name, uppercase, trimmed
- `horse_code` — HKJC brand number (preferred join key)

Rows include declared runners and any stand-by starters printed on the card (`runner_status` = `declared` or `standby`). Scratchings are recorded when the card shows them.

### Join rules

Match stored trip notes in `all_trip_notes.csv` first by `horse_code`, else by uppercase trimmed `horse_name`. `match_method` is `horse_code`, `horse_name`, or `unmatched`. For a match, the copied trip-note fields come from the **most recent** stored row (`source_meeting`, `source_venue`, `source_race_no`). `prior_note_count` is how many stored rows exist for that horse. Blank cells mean unknown, never `0` or `false`.

Copied trip-note fields (same meaning as above; blank if unmatched): `traffic`, `wide_no_cover`, `slow_away`, `stewards_excuse`, `vet_finding`, `clearance_required`, `pace_role`, `horse_last_400m_sec`, `race_last_400m_sec`, `flags`, `note`, `source`.

`stewards_excuse`, `vet_finding` and `clearance_required` remain official stewards text. `note`, `flags`, `traffic`, `wide_no_cover` and `slow_away` remain replay-review observations unless `source` includes `stewards`.

### Clearance flags

If any stored row for that horse has a non-blank `clearance_required`, `clearance_in_prior_notes` is `true` and the latest such text is copied to `clearance_text` with `clearance_source_meeting` / `clearance_source_race_no`. Being declared or a standby on the upcoming official card is **not** treated as proof that the official veterinary examination, barrier trial, or stalls test has been passed. Those cases are flagged `clearance_status=unverified`. Horses with a stored clearance that are not on the card appear only in the JSON `clearance_flags` list (`clearance_status=not_declared`).

### JSON wrapper

The JSON file has a meeting header (`races_published`, `last_race_no`, `last_race_post_time_hkt`, advertised course/going, row counts, `sources`, `limitations`, `clearance_flags`) plus a `rows` array that matches the CSV. Timestamps: `generated_at_hkt` (ISO 8601 with `+08:00`) and `generated_at_utc` (`Z`).

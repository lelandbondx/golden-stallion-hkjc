# grok_rising EV flag feed schema (schema_version 1.0)

Produced by Grok Rising after each HKJC meeting cycle, from Trial Bot, Replay Bot, and Steward Bot outputs. This folder holds structured EV-relevant trial, replay, and medical flags for Silks.AI import and team review.

This feed contains facts only. It does not include probabilities, rankings, or stakes, and it does not change them.

## Files

| File | Content |
|---|---|
| `<YYYY-MM-DD>_<HV\|ST>.csv` / `.json` | One row per horse flag for that meeting |
| `<YYYY-MM-DD>_<HV\|ST>.md` | Human-readable team-review summary for that meeting (copied from the source summary) |
| `schema.md` | Column descriptions, row key, allowed values, and column policy |
| `manifest.json` | Written last, in its own commit: run timestamps (HKT and UTC), files, row counts, completeness, source paths, checksums (`sha256`) and byte sizes (`size_bytes`, added 2026-11-25). If the manifest is older than the data files, treat the feed as incomplete. |

JSON meeting files have the shape `{"rows":[...]}`. Missing numeric `race_no` is `null` in JSON and an empty cell in CSV. Missing or inapplicable strings are empty (`""` / empty CSV cell). Booleans are JSON `true` / `false` and CSV `true` / `false`. Unknown values are left empty; placeholders are never invented.

## Row key

Identity fields specified for import: `meeting_date`, `venue`, `race_no`, `horse_name` (UPPERCASE, trimmed), `horse_code` (HKJC brand number).

A horse may have more than one flag, so the unique row key is:

`meeting_date` + `venue` + `race_no` + `horse_name` + `horse_code` + `flag_type`

`race_no` may be empty when the source record has no race number (for example a clearance or eligibility flag that is not tied to a race in that meeting).

## Columns

Columns are listed in file order. This is an append-only schema: new columns may be appended at the end; existing columns are never renamed or dropped.

| Column | Type | Description |
|---|---|---|
| meeting_date | string, ISO `YYYY-MM-DD` | Meeting date |
| venue | string | `HV` (Happy Valley) or `ST` (Sha Tin) |
| race_no | integer or empty | Race number on the card, if the source record has one |
| horse_name | string | Horse name, UPPERCASE, trimmed |
| horse_code | string | Permanent HKJC brand number (for example `K308`) |
| flag_type | string | Kind of flag. Allowed: `trial`, `trip_excuse`, `medical`, `regulatory`, `gear` |
| direction | string | How the flag reads for later cards. Allowed: `upgrade_candidate`, `caution`, `neutral` |
| priority | string | Review priority. Allowed: `high`, `normal` |
| clearance_required | boolean | `true` if official clearance (trial and/or vet exam) is required before the horse races again |
| verified | boolean | `true` if the flag was verified against its cited source |
| evidence | string | Source evidence text, facts only. Copied from the source record with trimming only; not rewritten |
| source_url | string | HTTP/HTTPS URL taken from the source field when one is present; otherwise empty |
| source_ref | string | Original source path or text, trimmed only. May be a URL, a local path, or both |
| generated_at | string, ISO 8601 | Timestamp on the source summary record when that flag was generated |
| retrieved_at_hkt | string, ISO 8601 with `+08:00` | Time these feed files were built, Hong Kong Time |
| retrieved_at_utc | string, ISO 8601 with `+00:00` | The same build time in UTC |

## Column policy

Append-only. Do not rename or drop columns. If a new field is needed, append it after `retrieved_at_utc` and document it in this file. Older rows leave new columns empty.

## Out of scope

No `model_prob`, `raw_model_prob`, `implied_prob`, `win_odds`, `gs_rank`, `card_rank`, `win_stake_active`, `kelly_stake`, or any other probability, ranking, or stake field is stored in this feed.

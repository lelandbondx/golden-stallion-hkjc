# Steward medical and integrity ledger (schema version 1)

Produced by the steward bot medical/integrity routine. Files in this folder
(`data/steward/` on branch `trial-data` only):

| File | Content |
|---|---|
| records.jsonl | Append-only ledger. One JSON object per line, one record per finding, clearance, requirement, suspension or integrity notice. Copied as-is from the steward source ledger. |
| records.csv | The same records as a single table, one row per record, with `retrieved_at` split into HKT and UTC. This is the machine-readable feed for Silks AI. |
| horses_latest.json | Snapshot keyed by HKJC `horse_id`. Latest status, open requirements and pointer into `records.jsonl` for each horse that has a ledger row. Rebuilt after each run. |
| meetings/<meeting_id>.json | Per-meeting review summary (status, record counts, open items, sources checked, source gaps). Includes pre-meet status files when present (filename contains `-precheck`). |
| schema.md | This file. Describes every column and JSON field. |
| manifest.json | Written LAST, in its own commit: run time (HKT and UTC), row counts, meetings covered, completeness and pending gaps. If manifest is older than the data files, treat the feed as incomplete. |

Column names on `records.csv` are stable. New columns may be appended. Existing columns are never renamed or dropped. Missing or unknown values are empty strings in CSV and `null` in JSON. Never placeholders such as `N/A`, `unknown`, or `TBD`.

Join horses on `horse_id` (HKJC identifier, e.g. `HK_2024_K239`). Never join on name alone. `horse_code` is the HKJC brand number (e.g. `K239`).

# records.csv columns

- `meeting_date`: ISO date `YYYY-MM-DD` of the HKJC meeting where the event arose. Empty for history-only vet-page rows that are not tied to a reviewed meeting.
- `venue`: `HV` (Happy Valley) or `ST` (Sha Tin). Empty when the row is not tied to a meeting.
- `race_no`: Race number on that card (integer as text). Empty when not applicable.
- `horse_name`: Horse name, UPPERCASE, trimmed, as on HKJC.
- `horse_code`: HKJC brand number (e.g. `L009`). Empty if not known.
- `horse_id`: HKJC horse identifier (e.g. `HK_2025_L009`). Primary key for joins.
- `record_id`: SHA1 of `horse_id|event_date|record_type|category|finding_verbatim`. Deduplication key.
- `record_type`: `flag` | `clearance` | `requirement` | `requirement_met` | `suspension` | `integrity`.
- `category`: `surgery` | `injury` | `lameness` | `bleeding_nostrils` | `tracheal_blood` | `cardiac` | `airway` | `heat_stress` | `failed_vet_exam` | `stalls_test` | `racing_manners` | `riding_offence` | `sampling` | `administrative` | `other`.
- `is_material`: `true` or `false`. `false` for castration, routine sampling, and official "no significant findings". Empty if unknown.
- `finding_verbatim`: Official HKJC wording of the finding.
- `requirement`: Official requirement text (e.g. barrier trial, official vet exam). Empty if none.
- `status`: `active_requirement` | `cleared` | `no_requirement` | `pending`.
- `event_date`: ISO date `YYYY-MM-DD` of the finding or event.
- `passed_on`: ISO date from the HKJC vet record when the horse passed / was cleared. Empty if not published.
- `suspension_from`: ISO start date of a riding suspension. Empty if not a suspension.
- `suspension_to`: ISO end date of a riding suspension. Empty if not a suspension.
- `jockey`: Jockey name for suspensions or riding matters. Empty otherwise.
- `finish_pos`: Official finishing position (integer as text). Empty if not applicable or not known.
- `source_name`: `stewards_report` | `vet_record_horse` | `vet_record_race` | `ove_database` | `changes` | `results` | `barrier_trial`.
- `source_url`: Exact official HKJC URL for the source page.
- `retrieved_at_hkt`: ISO 8601 timestamp with offset `+08:00` (Asia/Hong_Kong), converted from the source `retrieved_at`.
- `retrieved_at_utc`: ISO 8601 timestamp with offset `+00:00`, converted from the source `retrieved_at`.
- `checked_by`: Who recorded the row (currently `steward bot`).
- `supersedes`: `record_id` of an earlier row this updates (for example a clearance of a prior flag). Empty if none.
- `notes`: Short factual notes. Empty if none.

# records.jsonl fields

One JSON object per line. Field names match the steward source schema (version 1) and are also stable (append only).

- `record_id`, `record_type`, `meeting_id`, `meeting_date`, `venue`, `race_no`, `finish_pos`, `horse_name`, `horse_code`, `horse_id`, `jockey`, `category`, `is_material`, `finding_verbatim`, `requirement`, `status`, `event_date`, `passed_on`, `suspension_from`, `suspension_to`, `source_name`, `source_url`, `retrieved_at`, `checked_by`, `supersedes`, `notes`.

Differences from the CSV: `meeting_id` is present (e.g. `HV-20261111`; `null` for history-only rows); timestamps are a single `retrieved_at` field in ISO 8601 with the original offset; JSON uses `null` rather than empty strings; `is_material` is a boolean; `race_no` and `finish_pos` are numbers or `null`.

`meeting_id` format is `<venue>-<YYYYMMDD>`.

# horses_latest.json

A JSON object keyed by `horse_id`. Each value has:

- `horse_id`: HKJC identifier (same as the key).
- `horse_code`: HKJC brand number.
- `horse_name`: UPPERCASE name.
- `status`: Latest status for the horse (`active_requirement` | `cleared` | `no_requirement` | `pending`).
- `latest_entry`: Object with `record_id`, `record_type`, `category`, `event_date`, `meeting_id`, `finding_verbatim`, `source_url` of the most recent material or latest row.
- `passed_on`: Latest published Passed On date, or `null`.
- `open_requirements`: List of still-open requirement strings.
- `history_pointer`: Text pointer to the matching rows in `records.jsonl`.
- `last_checked`: ISO 8601 timestamp of the last check of this horse.
- `vet_page`: Official HKJC ovehorse URL for this `horse_id`.

# meetings/<meeting_id>.json

One file per reviewed meeting or pre-meet check. Typical fields on a post-meeting review:

- `meeting_id`, `meeting_date`, `venue`, `description`, `status` (e.g. `FLAGGED`), `reviewed_at`, `records_count`, `horses_with_records`, `summary`, `open_items`, `sources_checked`, `source_gaps`, `replay_bot_coverage`, `replay_bot_agent_id`, `notes`.

Pre-meet files may use `type` (e.g. `pre_meet_status`), `checked_at`, `official_sources_checked`, and runner/scratching fields instead of a post-race `status`.

# manifest.json

Written in a separate final commit after the data files. Typical fields:

- `schema_version`, `status`, `run_time_hkt`, `run_time_utc`, `source_last_run`, `row_counts`, `meetings_covered`, `reviewed_meeting_ids`, `meeting_status`, `completeness`, `pending_gaps`, `open_items`, `sha256`, `git` (commit SHAs when a push was completed).

Pending gaps are copied from the steward `state.json` and from each meeting file's `source_gaps`. They are not an all-clear.

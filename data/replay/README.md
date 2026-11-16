# HKJC trip notes for Silks AI ingestion

Structured post-meeting trip notes (one row per reviewer note) for Hong Kong Jockey Club meetings, enriched with official HKJC results, stewards' reports and sectional times. Column definitions, types and allowed values are in `schema.json` (schema_version 2: the v1 columns plus `generated_at` as the last column, an ISO 8601 build time in HKT, +08:00).

## Files
- `YYYY-MM-DD_VENUE.csv` — one meeting (VENUE = ST Sha Tin, HV Happy Valley).
- `YYYY-MM-DD_VENUE.json` — the same rows, typed, plus a `meeting` block (generated_at, source_fetched_at, course, going, races reviewed, limitations, sources).
- `all_trip_notes.csv` — every meeting, deduplicated on date+venue+race+horse.
- `latest.json` — points to the newest meeting (currently `2026-11-11_HV`), with its generated_at and source_fetched_at.
- `raw/` — raw HKJC DisplaySectionalTime HTML and `fetch_log.tsv`.
- `tools/` — the build and validation scripts.

## USAGE (build one meeting)
```bash
cd /workspace/silks_ingest/hkjc_trip_notes
python3 tools/build.py    --date 2026-11-14 --venue ST --workdir /workspace/replays/2026-11-14
python3 tools/validate.py --date 2026-11-14 --venue ST --workdir /workspace/replays/2026-11-14   # exit 0 = pass
```
- The workdir needs `trip_notes.csv` (legacy format), `official_results.json` and `official_stewards.json`. Optionally add `limitations.json` (`{"limitations": [...]}` or a list) or `limitations.txt` (one item per line). These files are only read, never modified.
- `build.py` downloads that meeting's HKJC DisplaySectionalTime pages into `raw/`, unless a valid copy is already there. Use `--refetch` to download again or `--no-fetch` to work offline. Every attempt is logged in `raw/fetch_log.tsv`.
- `build.py` writes `<date>_<venue>.csv` and `.json`. It replaces that meeting's rows in `all_trip_notes.csv` and moves the `latest.json` pointer only when this meeting is the newest one. Re-running for the same meeting is safe.
- Automatic limitation notes are added for withdrawn horses, out-of-vocabulary legacy flags and any sectional that could not be fetched (left blank).
- The legacy flag `wide` is kept as it is, and `wide_no_cover` is left blank (unknown).
- `--outdir DIR` writes somewhere else, for testing.

## Rule: blank means unknown
In CSV, an empty cell means unknown or not applicable. In JSON it is `null`. It never means 0 or false. Read CSVs with `keep_default_na=False` and convert explicitly, or use the JSON files.
Booleans (`traffic`, `wide_no_cover`, `slow_away`, `sampled`): `false` means not flagged in the review. It does not prove a clean trip.

## Load
```python
import pandas as pd, json
df = pd.read_csv("all_trip_notes.csv", dtype=str, keep_default_na=False)
df = df.replace("", pd.NA)
for c in ["traffic", "wide_no_cover", "slow_away", "sampled"]:
    df[c] = df[c].map({"true": True, "false": False})          # NA stays NA (unknown)
for c in ["race", "race_index", "distance_m", "draw"]:
    df[c] = pd.to_numeric(df[c]).astype("Int64")
for c in ["win_odds", "horse_last_400m_sec", "race_last_400m_sec"]:
    df[c] = pd.to_numeric(df[c])
df["flags"] = df["flags"].fillna("").str.split(";").apply(lambda l: [f for f in l if f])

latest = json.load(open("latest.json"))
meet = json.load(open(latest["json"]))
rows = pd.DataFrame(meet["rows"])          # already typed; None = unknown
print(meet["meeting"]["limitations"])
```
Join to runners on `horse_code` (preferred) or on `date`+`venue`+`race`+`horse`. `horse` is the official uppercase name.

## Provenance
- `source` tells you whether a note comes from the replay, the stewards or both. Rows marked `replay` alone are the reviewer's own observations and are not official findings.
- `stewards_excuse`, `vet_finding` and `clearance_required` are copied verbatim from official HKJC text.
- `pace_role` is derived only from the first official running position (see schema).
- Only horses with a trip note get a row. A missing horse means nothing notable was recorded for it, not that it had a confirmed clean run.

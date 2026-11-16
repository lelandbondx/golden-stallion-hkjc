# data/grok_bot schema (v1)

Grok Bot's per-horse EV flag summaries for Silks AI, one JSON + Markdown pair per meeting, plus `all_ev_records.csv` combining every meeting.

Each JSON file: `{meeting_date, venue, generated_at, records: [...]}`. Each record / CSV row:

| column | type | meaning |
|---|---|---|
| meeting_date | YYYY-MM-DD | HK meeting date |
| venue | ST or HV | racecourse |
| race_no | int or blank | race number; blank when the note is about eligibility, not a specific race |
| horse_name | upper-case string | horse name |
| horse_code | string | HKJC brand code, e.g. J501 |
| flag_type | string | medical, trial, steward, replay, etc. |
| direction | positive / caution / neutral | how the flag should move the horse's rating |
| priority | high / normal | importance |
| clearance_required | bool | horse needs a vet or trial clearance before running |
| evidence | string | what was found |
| source | string | where the evidence came from |
| verified | bool | evidence confirmed against an official source |
| generated_at | ISO 8601 with offset (America/New_York) | when the record was built |

Join key for the app: (meeting_date, venue, race_no, horse_code), falling back to horse_name.

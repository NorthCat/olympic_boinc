# Podium finisher score validation

From the repository root:

```bash
uv run --locked python scripts/data_checks/check_scores.py
```

The connection is taken from `OLYMPIC_DATABASE_URL` in the environment or `.env`, as
in the application. The script only reads saved data and does not contact BoincStats.

Checks strictly decreasing scores: **1st place > 2nd place > 3rd place**.
Equal scores at different places are considered a violation. With multiple teams
at one place, all combinations of teams at adjacent places are checked; teams at
one place are not compared with each other. Missing places and unknown/invalid
scores are reported as incomplete data for which validation cannot be completed.

For each problematic challenge, the output includes its ID, name, type, end date,
link, reasons, and teams with places and scores. This is followed by the total
number of checked and problematic challenges.

Exit codes: `0` — no problems (including an empty database), `1` — violations
or incomplete data found, `2` — execution/connection error.

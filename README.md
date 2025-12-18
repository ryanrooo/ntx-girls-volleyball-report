# North Texas Girls Volleyball Reporting

This repository provides a lightweight script to turn weekend tournament results from VSTAR (or any CSV export) into:

- A weekend snapshot that shows which clubs played and how they performed.
- A season-to-date ranking of all clubs based on win percentage, total wins, and average finish.

## Preparing data

1. Sign in to VSTAR and open the tournament results you want to capture.
2. Export or copy the results into a CSV file with **one row per club per tournament** using the following columns:
   - `date` (YYYY-MM-DD)
   - `club`
   - `tournament`
   - `finish` (numeric place; leave blank if unknown)
   - `wins`
   - `losses`
3. Save the file anywhere (default path: `data/tournaments.csv`). A sample file is included at `data/sample_tournaments.csv` for quick testing.

## Generating reports

Run the script directly with Python 3.11+:

```bash
python report.py --data data/sample_tournaments.csv --output reports/sample_report.md
```

Key options:

- `--weekend-start` / `--weekend-end`: specify a weekend window (inclusive). If omitted, the most recent Saturday/Sunday window in the data is used.
- `--season-start`: limit the season ranking to results on/after this date (YYYY-MM-DD). Defaults to the entire dataset.
- `--output`: save the Markdown report to a file in addition to printing it.

The generated report contains Markdown tables for both the selected weekend and the cumulative season ranking. You can upload the Markdown file to your preferred dashboard or share it directly.

# North Texas Girls Volleyball Reporting

This repository provides a lightweight script to turn weekend tournament results from VSTAR (or any CSV export) into:

- A weekend snapshot that shows which clubs played and how they performed.
- A season-to-date ranking of all clubs based on win percentage, total wins, and average finish.

## Preparing data

### Option A: Scrape VSTAR directly (no login)

Pass one or more public VSTAR pages that show tournament results. The scraper will find HTML tables, convert them to the expected CSV layout, and cache them locally:

```bash
python report.py --vstar-scrape "https://vstarvolleyball.com/?page_id=409&scope=current,https://vstarvolleyball.com/?page_id=409&scope=past" --data data/tournaments.csv

# Multiple pages can be supplied by repeating the flag or using commas
python report.py --vstar-scrape https://vstarvolleyball.com/?page_id=409&scope=current --vstar-scrape https://vstarvolleyball.com/?page_id=409&scope=past

# Use the built-in defaults for the current and past result pages
python report.py --vstar-scrape default --data data/tournaments.csv
```

Notes:

- No authentication is required. A friendly User-Agent is sent, and the scraped CSV is written to `--data` for reuse.
- The scraper looks for headers such as Date, Club/Team, Tournament/Event, Finish/Rank, Wins/Losses, or a combined Record column. Missing values default to zeros so reports can still be generated.

### Option B: Pull a downloadable CSV from VSTAR

If you have a CSV export link, the script can download it before running the report:

```bash
python report.py --vstar-url "https://<vstar-download-url>" --data data/tournaments.csv
```

Notes:

- If the export requires authentication, capture the `Cookie` header from your logged-in browser session and pass it with `--vstar-cookie "name=value; another=value"` or set it once via `export VSTAR_COOKIE="name=value; another=value"`.
- The CSV will be saved to the `--data` path so you keep a local copy even after VSTAR rotates history.

### Option C: Manual CSV

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
- `--vstar-scrape`: scrape one or more public VSTAR pages for HTML tables and build the CSV automatically.
- `--vstar-url`: download a CSV export from VSTAR into `--data` before generating the report (useful because VSTAR prunes history).
- `--vstar-cookie`: optional cookie header for authenticated downloads (or set `VSTAR_COOKIE`).

The generated report contains Markdown tables for both the selected weekend and the cumulative season ranking. You can upload the Markdown file to your preferred dashboard or share it directly.

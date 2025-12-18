#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import os
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from statistics import mean
from typing import Iterable, List, Optional
from urllib import error, request


@dataclass
class TournamentResult:
    date: dt.date
    club: str
    tournament: str
    finish: Optional[int]
    wins: int
    losses: int

    @property
    def games_played(self) -> int:
        return self.wins + self.losses


@dataclass
class ClubSummary:
    club: str
    tournaments: int
    wins: int
    losses: int
    finishes: List[int]

    @property
    def win_pct(self) -> float:
        games = self.wins + self.losses
        return self.wins / games if games else 0.0

    @property
    def best_finish(self) -> Optional[int]:
        return min(self.finishes) if self.finishes else None

    @property
    def average_finish(self) -> Optional[float]:
        return mean(self.finishes) if self.finishes else None


class ReportGenerator:
    def __init__(self, results: Iterable[TournamentResult]):
        self.results = list(results)
        if not self.results:
            raise ValueError("No tournament results found.")

    def determine_weekend(self, start: Optional[dt.date], end: Optional[dt.date]) -> tuple[dt.date, dt.date]:
        if start and not end:
            end = start + dt.timedelta(days=1)
        if start and end:
            return start, end

        latest = max(result.date for result in self.results)
        days_since_saturday = (latest.weekday() - 5) % 7
        saturday = latest - dt.timedelta(days=days_since_saturday)
        sunday = saturday + dt.timedelta(days=1)
        return saturday, sunday

    def _filter_results(self, start: dt.date, end: dt.date) -> List[TournamentResult]:
        return [result for result in self.results if start <= result.date <= end]

    def _summarize(self, records: Iterable[TournamentResult]) -> List[ClubSummary]:
        totals: dict[str, ClubSummary] = {}
        for result in records:
            summary = totals.setdefault(
                result.club,
                ClubSummary(club=result.club, tournaments=0, wins=0, losses=0, finishes=[]),
            )
            summary.tournaments += 1
            summary.wins += result.wins
            summary.losses += result.losses
            if result.finish is not None:
                summary.finishes.append(result.finish)
        return list(totals.values())

    def weekend_report(self, start: dt.date, end: dt.date) -> list[ClubSummary]:
        return self._summarize(self._filter_results(start, end))

    def season_report(self, season_start: Optional[dt.date] = None) -> list[ClubSummary]:
        records = self.results
        if season_start:
            records = [result for result in records if result.date >= season_start]
        return self._summarize(records)

    @staticmethod
    def rank_clubs(clubs: list[ClubSummary]) -> list[ClubSummary]:
        def sort_key(summary: ClubSummary):
            avg_finish = summary.average_finish if summary.average_finish is not None else float("inf")
            return (-summary.win_pct, -summary.wins, avg_finish, summary.club)

        return sorted(clubs, key=sort_key)


def parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date '{value}'. Use YYYY-MM-DD.") from exc


def load_results(path: Path) -> list[TournamentResult]:
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    results: list[TournamentResult] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required_columns = {"date", "club", "tournament", "finish", "wins", "losses"}
        missing = required_columns - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing columns in CSV: {', '.join(sorted(missing))}")

        for row in reader:
            date = parse_date(row["date"])
            finish_value = row.get("finish")
            finish = int(finish_value) if finish_value else None
            results.append(
                TournamentResult(
                    date=date,
                    club=row["club"].strip(),
                    tournament=row["tournament"].strip(),
                    finish=finish,
                    wins=int(row["wins"]),
                    losses=int(row["losses"]),
                )
            )
    return results


class SimpleTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._current_table: list[list[str]] = []
        self._current_row: list[str] = []
        self._current_cell: list[str] = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False

    def handle_starttag(self, tag, attrs):  # noqa: D401 - HTMLParser API
        if tag == "table":
            self._in_table = True
            self._current_table = []
        elif tag == "tr" and self._in_table:
            self._in_row = True
            self._current_row = []
        elif tag in {"th", "td"} and self._in_row:
            self._in_cell = True
            self._current_cell = []

    def handle_data(self, data):  # noqa: D401 - HTMLParser API
        if self._in_cell:
            text = data.strip()
            if text:
                self._current_cell.append(text)

    def handle_endtag(self, tag):  # noqa: D401 - HTMLParser API
        if tag in {"th", "td"} and self._in_cell:
            cell_text = " ".join(self._current_cell).strip()
            self._current_row.append(cell_text)
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if any(self._current_row):
                self._current_table.append(self._current_row)
            self._in_row = False
        elif tag == "table" and self._in_table:
            if any(self._current_table):
                self.tables.append(self._current_table)
            self._in_table = False


def parse_html_tables(html: str) -> list[tuple[list[str], list[list[str]]]]:
    parser = SimpleTableParser()
    parser.feed(html)

    parsed_tables: list[tuple[list[str], list[list[str]]]] = []
    for table in parser.tables:
        if not table:
            continue

        headers = table[0]
        rows = table[1:] if len(table) > 1 else []
        parsed_tables.append((headers, rows))

    return parsed_tables


def format_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    header_line = "| " + " | ".join(headers) + " |"
    separator_line = "| " + " | ".join(["---"] * len(headers)) + " |"
    row_lines = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header_line, separator_line, *row_lines])


def render_club_summary(clubs: list[ClubSummary], include_rank: bool = False) -> str:
    headers = ["Club", "Tournaments", "Wins", "Losses", "Win %", "Best Finish", "Avg Finish"]
    rows: list[list[str]] = []
    for idx, club in enumerate(clubs, start=1):
        cells = [
            club.club,
            str(club.tournaments),
            str(club.wins),
            str(club.losses),
            f"{club.win_pct:.3f}",
            "-" if club.best_finish is None else str(club.best_finish),
            "-" if club.average_finish is None else f"{club.average_finish:.2f}",
        ]
        if include_rank:
            cells.insert(0, f"#{idx}")
        rows.append(cells)

    if include_rank:
        headers = ["Rank", *headers]
    return format_markdown_table(headers, rows)


def generate_report(
    results: list[TournamentResult],
    weekend_start: Optional[dt.date],
    weekend_end: Optional[dt.date],
    season_start: Optional[dt.date],
) -> str:
    generator = ReportGenerator(results)
    weekend_start, weekend_end = generator.determine_weekend(weekend_start, weekend_end)

    weekend_clubs = generator.weekend_report(weekend_start, weekend_end)
    ranked_weekend = ReportGenerator.rank_clubs(weekend_clubs)

    season_clubs = generator.season_report(season_start)
    ranked_season = ReportGenerator.rank_clubs(season_clubs)

    lines = [
        "# North Texas Club Performance Report",
        "",
        f"Weekend window: {weekend_start} to {weekend_end}",
        f"Season start: {season_start or 'full dataset'}",
        "",
        "## Weekend Snapshot",
        "Performance of all clubs that played during the selected weekend.",
        render_club_summary(ranked_weekend, include_rank=True),
        "",
        "## Season-to-Date Rankings",
        "Ranking is by win percentage, then total wins, with average finish used as a tiebreaker.",
        render_club_summary(ranked_season, include_rank=True),
    ]
    return "\n".join(lines)


def fetch_vstar_csv(url: str, destination: Path, cookie: Optional[str] = None) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)

    headers = {"User-Agent": "ntx-volleyball-reporter/1.0"}
    if cookie:
        headers["Cookie"] = cookie

    req = request.Request(url, headers=headers)
    try:
        with request.urlopen(req, timeout=30) as resp:
            destination.write_bytes(resp.read())
    except error.HTTPError as exc:
        raise RuntimeError(f"HTTP error {exc.code} while downloading VSTAR data") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Failed to reach VSTAR: {exc.reason}") from exc

    return destination


def _index_for(headers: list[str], candidates: list[str]) -> Optional[int]:
    for idx, header in enumerate(headers):
        header_lower = header.lower()
        if any(candidate in header_lower for candidate in candidates):
            return idx
    return None


def _parse_int(value: str) -> Optional[int]:
    digits = re.findall(r"\d+", value)
    return int(digits[0]) if digits else None


def _parse_record(value: str) -> Optional[tuple[int, int]]:
    match = re.search(r"(\d+)\s*[-/]\s*(\d+)", value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def extract_results_from_tables(
    tables: list[tuple[list[str], list[list[str]]]], fallback_tournament: str
) -> list[TournamentResult]:
    collected: list[TournamentResult] = []

    for headers, rows in tables:
        if not headers or not rows:
            continue

        date_idx = _index_for(headers, ["date"])
        club_idx = _index_for(headers, ["club", "team"])
        tournament_idx = _index_for(headers, ["tournament", "event", "division"])
        finish_idx = _index_for(headers, ["finish", "place", "rank"])
        wins_idx = _index_for(headers, ["wins", "win", "w"])
        losses_idx = _index_for(headers, ["losses", "loss", "l"])
        record_idx = _index_for(headers, ["record", "win-loss", "w-l"])

        if date_idx is None or club_idx is None:
            continue

        for row in rows:
            if len(row) < len(headers):
                continue

            try:
                date = parse_date(row[date_idx])
            except argparse.ArgumentTypeError:
                continue

            club = row[club_idx].strip()
            if not club:
                continue

            tournament_name = fallback_tournament
            if tournament_idx is not None:
                maybe_tournament = row[tournament_idx].strip()
                if maybe_tournament:
                    tournament_name = maybe_tournament

            finish = _parse_int(row[finish_idx]) if finish_idx is not None else None

            wins = _parse_int(row[wins_idx]) if wins_idx is not None else None
            losses = _parse_int(row[losses_idx]) if losses_idx is not None else None

            if (wins is None or losses is None) and record_idx is not None:
                parsed_record = _parse_record(row[record_idx])
                if parsed_record:
                    wins, losses = parsed_record

            wins = wins if wins is not None else 0
            losses = losses if losses is not None else 0

            collected.append(
                TournamentResult(
                    date=date,
                    club=club,
                    tournament=tournament_name,
                    finish=finish,
                    wins=wins,
                    losses=losses,
                )
            )

    return collected


def scrape_vstar_pages(urls: list[str], destination: Path) -> list[TournamentResult]:
    if not urls:
        raise ValueError("No VSTAR URLs provided to scrape.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "ntx-volleyball-reporter/1.0"}

    all_results: list[TournamentResult] = []

    for url in urls:
        req = request.Request(url, headers=headers)
        try:
            with request.urlopen(req, timeout=30) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
        except error.HTTPError as exc:
            raise RuntimeError(f"HTTP error {exc.code} while scraping {url}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Failed to reach VSTAR ({url}): {exc.reason}") from exc

        title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        page_title = title_match.group(1).strip() if title_match else url

        parsed_tables = parse_html_tables(html)
        page_results = extract_results_from_tables(parsed_tables, fallback_tournament=page_title)

        if not page_results:
            raise RuntimeError(f"No recognizable results tables found on {url}")

        all_results.extend(page_results)

    # Persist the scrape so reports can be regenerated without re-hitting the site
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "club", "tournament", "finish", "wins", "losses"])
        for result in all_results:
            writer.writerow(
                [
                    result.date.isoformat(),
                    result.club,
                    result.tournament,
                    result.finish if result.finish is not None else "",
                    result.wins,
                    result.losses,
                ]
            )

    return all_results


def main():
    parser = argparse.ArgumentParser(description="Generate weekend and season reports from tournament CSV data.")
    parser.add_argument("--data", type=Path, default=Path("data/tournaments.csv"), help="Path to tournament CSV data.")

    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument("--vstar-url", help="VSTAR CSV export URL to download before generating the report.")
    source_group.add_argument(
        "--vstar-scrape",
        action="append",
        metavar="URL",
        help="One or more VSTAR pages to scrape for results (comma-separated or repeated).",
    )

    parser.add_argument(
        "--vstar-cookie",
        help="Cookie header for authenticated VSTAR downloads. Falls back to the VSTAR_COOKIE environment variable.",
    )
    parser.add_argument("--weekend-start", type=parse_date, help="Weekend start date (YYYY-MM-DD). Defaults to the most recent Saturday in the data.")
    parser.add_argument("--weekend-end", type=parse_date, help="Weekend end date (YYYY-MM-DD). Defaults to the Saturday+1 day window.")
    parser.add_argument("--season-start", type=parse_date, help="First date to include in season ranking (YYYY-MM-DD). Defaults to all data.")
    parser.add_argument("--output", type=Path, help="Optional path to save the markdown report.")

    args = parser.parse_args()

    if args.vstar_scrape:
        scrape_urls: list[str] = []
        for entry in args.vstar_scrape:
            scrape_urls.extend(url.strip() for url in entry.split(",") if url.strip())

        try:
            results = scrape_vstar_pages(scrape_urls, args.data)
            print(f"Scraped {len(results)} rows from VSTAR and saved to {args.data}")
        except Exception as exc:  # noqa: BLE001
            parser.error(f"Unable to scrape VSTAR: {exc}")
    elif args.vstar_url:
        cookie = args.vstar_cookie or os.environ.get("VSTAR_COOKIE")
        try:
            fetch_vstar_csv(args.vstar_url, args.data, cookie)
            print(f"Downloaded VSTAR data to {args.data}")
        except Exception as exc:  # noqa: BLE001
            parser.error(f"Unable to download VSTAR data: {exc}")
        results = load_results(args.data)
    else:
        results = load_results(args.data)

    report_body = generate_report(results, args.weekend_start, args.weekend_end, args.season_start)

    print(report_body)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report_body, encoding="utf-8")
        print(f"\nReport saved to {args.output}")


if __name__ == "__main__":
    main()

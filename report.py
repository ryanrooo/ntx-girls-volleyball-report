#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Iterable, List, Optional


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


def main():
    parser = argparse.ArgumentParser(description="Generate weekend and season reports from tournament CSV data.")
    parser.add_argument("--data", type=Path, default=Path("data/tournaments.csv"), help="Path to tournament CSV data.")
    parser.add_argument("--weekend-start", type=parse_date, help="Weekend start date (YYYY-MM-DD). Defaults to the most recent Saturday in the data.")
    parser.add_argument("--weekend-end", type=parse_date, help="Weekend end date (YYYY-MM-DD). Defaults to the Saturday+1 day window.")
    parser.add_argument("--season-start", type=parse_date, help="First date to include in season ranking (YYYY-MM-DD). Defaults to all data.")
    parser.add_argument("--output", type=Path, help="Optional path to save the markdown report.")

    args = parser.parse_args()

    results = load_results(args.data)
    report_body = generate_report(results, args.weekend_start, args.weekend_end, args.season_start)

    print(report_body)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report_body, encoding="utf-8")
        print(f"\nReport saved to {args.output}")


if __name__ == "__main__":
    main()

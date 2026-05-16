from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from src.pipeline.common import (
    default_metadata_path,
    normalize_conference,
    project_path,
    read_table,
    resolve_source,
    write_table,
)


def fetch_papers(args: argparse.Namespace) -> Path:
    conference = normalize_conference(args.conference)
    year = str(args.year)
    source = resolve_source(conference, args.source)
    output_path = project_path(args.output, default_metadata_path(conference, year))
    output_path = output_path if output_path.suffix else output_path.with_suffix(".xlsx")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if source == "openreview":
        return fetch_from_openreview(args, conference, year, output_path)
    if source == "openaccess":
        return fetch_from_openaccess(args, conference, year, output_path)
    raise ValueError(f"Unsupported fetch source: {source}")


def fetch_from_openreview(args: argparse.Namespace, conference: str, year: str, output_path: Path) -> Path:
    from src.paper_fetch.openreview_scraper import OpenReviewScraper

    venue = args.venue or f"{conference}.cc/{year}/Conference"
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "openreview_metadata.csv"
        scraper = OpenReviewScraper(venue=venue, output_csv=str(csv_path), baseurl=args.baseurl)
        scraper.run()
        df = read_table(csv_path)
    write_table(df, output_path)
    print(f"Fetched {len(df)} papers to: {output_path}")
    return output_path


def fetch_from_openaccess(args: argparse.Namespace, conference: str, year: str, output_path: Path) -> Path:
    from src.paper_fetch.paper_scraper import build_conference_url, export_papers_metadata

    url = args.url or build_conference_url(conference, year)
    patterns = args.patterns or []
    if output_path.suffix.lower() == ".csv":
        export_papers_metadata(conference, year, url, str(output_path), patterns=patterns)
        return output_path

    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "metadata.csv"
        export_papers_metadata(conference, year, url, str(csv_path), patterns=patterns)
        df = read_table(csv_path)
    write_table(df, output_path)
    print(f"Converted metadata to: {output_path}")
    return output_path

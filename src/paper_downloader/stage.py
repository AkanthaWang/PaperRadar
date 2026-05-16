from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from src.pipeline.common import PDFS_DIR, ensure_status_columns, infer_conference_year, normalize_conference, project_path, read_table, write_table


def download_papers(args: argparse.Namespace) -> Path:
    input_path = project_path(args.input)
    output_dir = project_path(args.output_dir, PDFS_DIR)
    conference = normalize_conference(args.conference) if args.conference else None
    year = str(args.year) if args.year else None
    if conference is None or year is None:
        inferred_conference, inferred_year = infer_conference_year(input_path)
        conference = conference or inferred_conference
        year = year or inferred_year

    from src.paper_downloader.paper_download import paper_download

    if input_path.suffix.lower() == ".csv":
        paper_download(str(input_path), str(output_dir), conference, year, max_workers=args.workers)
        update_download_status(input_path, output_dir, conference, year)
        return output_dir

    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "download_input.csv"
        read_table(input_path).to_csv(csv_path, index=False, encoding="utf-8-sig")
        paper_download(str(csv_path), str(output_dir), conference, year, max_workers=args.workers)
    update_download_status(input_path, output_dir, conference, year)
    return output_dir


def update_download_status(table_path: Path, output_dir: Path, conference: str, year: str) -> None:
    from src.paper_downloader.paper_download import sanitize_filename

    if not table_path.exists():
        return
    df = ensure_status_columns(read_table(table_path))
    if "title" not in df.columns:
        return
    for index, row in df.iterrows():
        title = str(row.get("title", "unknown_title"))
        filename = f"{year}_{conference}_{sanitize_filename(title)}.pdf"
        pdf_path = output_dir / filename
        df.at[index, "pdf_path"] = str(pdf_path)
        df.at[index, "download_status"] = "downloaded" if pdf_path.exists() else "missing"
    write_table(df, table_path)
    print(f"Updated download status table: {table_path}")

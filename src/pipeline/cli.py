from __future__ import annotations

import argparse
from pathlib import Path

from src.mineru_parser.stage import parse_pdfs
from src.paper_downloader.stage import download_papers
from src.paper_fetch.stage import fetch_papers
from src.paper_filter.stage import filter_papers
from src.paper_summarizer.stage import summarize_pdfs
from src.pipeline.runner import run_pipeline


def add_fetch_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--conference", required=True, help="Conference name, e.g. CVPR, ICCV, ICLR.")
    parser.add_argument("--year", required=True, help="Conference year, e.g. 2026.")
    parser.add_argument("--source", choices=["auto", "openaccess", "openreview"], default="auto")
    parser.add_argument("--output", help="Metadata output table path, .xlsx or .csv.")
    parser.add_argument("--url", help="Override conference listing URL for openaccess scraping.")
    parser.add_argument("--venue", help="Override OpenReview venue, e.g. ICLR.cc/2026/Conference.")
    parser.add_argument("--baseurl", default="https://api2.openreview.net", help="OpenReview API base URL.")
    parser.add_argument("--patterns", nargs="*", default=[], help="Optional regex patterns recorded during fetch.")


def add_filter_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input", required=True, help="Input metadata table, .xlsx or .csv.")
    parser.add_argument("--output", help="Filtered output table, .xlsx or .csv.")
    parser.add_argument("--keywords", nargs="+", required=True, help="Keywords or regex patterns.")
    parser.add_argument("--columns", nargs="+", default=None, help="Default: existing title/abstract/keywords columns.")
    parser.add_argument("--match-all", action="store_true", help="Require all keywords to match.")
    parser.add_argument("--regex", action="store_true", help="Treat keywords as regex patterns.")
    parser.add_argument("--case-sensitive", action="store_true")
    parser.add_argument("--types", help="Optional accepted paper types, comma-separated.")
    parser.add_argument("--type-column", default="type")


def add_download_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input", required=True, help="Filtered paper table, .xlsx or .csv.")
    parser.add_argument("--output-dir", default=None, help="PDF download directory. Default: data/pdfs.")
    parser.add_argument("--conference", help="Conference name. Inferred from input filename if omitted.")
    parser.add_argument("--year", help="Conference year. Inferred from input filename if omitted.")
    parser.add_argument("--workers", type=int, default=5)


def add_analyzer_args(parser: argparse.ArgumentParser, include_llm: bool) -> None:
    parser.add_argument("--pdf", help="Analyze one PDF path or URL.")
    parser.add_argument("--pdf-dir", "--downloads-dir", dest="pdf_dir", default=None, help="PDF directory. Default: data/pdfs.")
    parser.add_argument("--outputs-dir", "--parsed-dir", dest="outputs_dir", default=None, help="Parsed output directory. Default: data/parsed.")
    parser.add_argument("--assets-dir", default=None)
    parser.add_argument("--cache-dir", default=None)
    parser.add_argument("--status-table", default=None, help="Filtered status table. Default: data/filtered_papers/filtered_papers.xlsx.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--mineru-token", default=None, help="Override MinerU token from the repository .env file.")
    parser.add_argument("--mineru-model-version", default=None, help="Override MinerU model version from .env.")
    parser.add_argument("--max-images", type=int, default=None)
    parser.add_argument("--max-chars", type=int, default=None)
    parser.add_argument("--summary-max-chars", type=int, default=None)
    parser.add_argument("--summary-chunk-chars", type=int, default=None)
    if include_llm:
        parser.add_argument("--reports-dir", default=None, help="Report output directory. Default: data/reports.")
        parser.add_argument("--llm-provider", choices=["vivo", "ecnu"], default=None, help="LLM provider. Defaults to .env settings.")
        parser.add_argument("--ecnu-api-key", default=None, help="Override ECNU API key from the repository .env file.")
        parser.add_argument("--ecnu-base-url", default=None)
        parser.add_argument("--ecnu-model", default=None)
        parser.add_argument("--ecnu-thinking-type", default=None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the refactored five-stage PaperRadar pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="Fetch paper metadata and save it as Excel/CSV.")
    add_fetch_args(fetch_parser)
    fetch_parser.set_defaults(func=fetch_papers)

    filter_parser = subparsers.add_parser("filter", help="Filter metadata by keywords.")
    add_filter_args(filter_parser)
    filter_parser.set_defaults(func=filter_papers)

    download_parser = subparsers.add_parser("download", help="Download filtered papers as PDFs.")
    add_download_args(download_parser)
    download_parser.set_defaults(func=download_papers)

    parse_parser = subparsers.add_parser("parse", help="Parse PDFs with MinerU and write raw Markdown/JSON.")
    add_analyzer_args(parse_parser, include_llm=False)
    parse_parser.set_defaults(func=parse_pdfs)

    summarize_parser = subparsers.add_parser("summarize", help="Summarize MinerU Markdown with an LLM.")
    add_analyzer_args(summarize_parser, include_llm=True)
    summarize_parser.add_argument("--parse-missing", action="store_true", help="Call MinerU when raw Markdown is missing.")
    summarize_parser.set_defaults(func=summarize_pdfs)

    run_parser = subparsers.add_parser("run", help="Run fetch, filter, download, parse, and summarize.")
    add_fetch_args(run_parser)
    run_parser.add_argument("--keywords", nargs="+", required=True)
    run_parser.add_argument("--columns", nargs="+", default=None, help="Default: existing title/abstract/keywords columns.")
    run_parser.add_argument("--match-all", action="store_true")
    run_parser.add_argument("--regex", action="store_true")
    run_parser.add_argument("--case-sensitive", action="store_true")
    run_parser.add_argument("--types", help="Optional accepted paper types, comma-separated.")
    run_parser.add_argument("--type-column", default="type")
    run_parser.add_argument("--metadata-output", help="Stage 1 output table.")
    run_parser.add_argument("--filtered-output", help="Stage 2 output table.")
    run_parser.add_argument("--download-dir", default=None, help="PDF download directory. Default: data/pdfs.")
    run_parser.add_argument("--workers", type=int, default=5)
    run_parser.add_argument("--outputs-dir", default=None)
    run_parser.add_argument("--assets-dir", default=None)
    run_parser.add_argument("--cache-dir", default=None)
    run_parser.add_argument("--reports-dir", default=None)
    run_parser.add_argument("--status-table", default=None)
    run_parser.add_argument("--limit", type=int, default=None)
    run_parser.add_argument("--overwrite", action="store_true")
    run_parser.add_argument("--mineru-token", default=None, help="Override MinerU token from the repository .env file.")
    run_parser.add_argument("--mineru-model-version", default=None, help="Override MinerU model version from .env.")
    run_parser.add_argument("--max-images", type=int, default=None)
    run_parser.add_argument("--max-chars", type=int, default=None)
    run_parser.add_argument("--summary-max-chars", type=int, default=None)
    run_parser.add_argument("--summary-chunk-chars", type=int, default=None)
    run_parser.add_argument("--llm-provider", choices=["vivo", "ecnu"], default=None, help="LLM provider. Defaults to .env settings.")
    run_parser.add_argument("--ecnu-api-key", default=None, help="Override ECNU API key from the repository .env file.")
    run_parser.add_argument("--ecnu-base-url", default=None)
    run_parser.add_argument("--ecnu-model", default=None)
    run_parser.add_argument("--ecnu-thinking-type", default=None)
    run_parser.set_defaults(func=run_pipeline)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    result = args.func(args)
    if isinstance(result, Path):
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

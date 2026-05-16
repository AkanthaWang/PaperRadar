from __future__ import annotations

import argparse
from pathlib import Path

from src.mineru_parser.stage import parse_pdfs
from src.paper_downloader.stage import download_papers
from src.paper_fetch.stage import fetch_papers
from src.paper_filter.stage import filter_papers
from src.paper_summarizer.stage import summarize_pdfs
from src.pipeline.common import DEFAULT_FILTERED_PAPERS_TABLE, PDFS_DIR, default_filtered_path, default_metadata_path, normalize_conference, project_path


def run_pipeline(args: argparse.Namespace) -> None:
    conference = normalize_conference(args.conference)
    year = str(args.year)
    keywords = args.keywords or []

    metadata_path = project_path(args.metadata_output or args.output, default_metadata_path(conference, year))
    filtered_path = project_path(args.filtered_output, default_filtered_path(metadata_path, keywords))
    download_dir = project_path(args.download_dir, PDFS_DIR)
    status_table = project_path(args.status_table, DEFAULT_FILTERED_PAPERS_TABLE)

    fetched = fetch_papers(
        argparse.Namespace(
            conference=conference,
            year=year,
            source=args.source,
            output=str(metadata_path),
            url=args.url,
            venue=args.venue,
            baseurl=args.baseurl,
            patterns=args.patterns,
        )
    )
    filtered = filter_papers(
        argparse.Namespace(
            input=str(fetched),
            output=str(filtered_path),
            keywords=keywords,
            columns=args.columns,
            match_all=args.match_all,
            regex=args.regex,
            case_sensitive=args.case_sensitive,
            types=args.types,
            type_column=args.type_column,
        )
    )
    download_papers(
        argparse.Namespace(
            input=str(filtered),
            output_dir=str(download_dir),
            conference=conference,
            year=year,
            workers=args.workers,
        )
    )
    parse_pdfs(
        argparse.Namespace(
            pdf=None,
            pdf_dir=str(download_dir),
            downloads_dir=None,
            outputs_dir=args.outputs_dir,
            assets_dir=args.assets_dir,
            cache_dir=args.cache_dir,
            status_table=str(status_table),
            limit=args.limit,
            overwrite=args.overwrite,
            mineru_token=args.mineru_token,
            mineru_model_version=args.mineru_model_version,
            max_images=args.max_images,
            max_chars=args.max_chars,
            summary_max_chars=args.summary_max_chars,
            summary_chunk_chars=args.summary_chunk_chars,
            llm_provider=None,
            ecnu_api_key=None,
            ecnu_base_url=None,
            ecnu_model=None,
            ecnu_thinking_type=None,
        )
    )
    summarize_pdfs(
        argparse.Namespace(
            pdf=None,
            pdf_dir=str(download_dir),
            downloads_dir=None,
            outputs_dir=args.outputs_dir,
            assets_dir=args.assets_dir,
            cache_dir=args.cache_dir,
            reports_dir=args.reports_dir,
            status_table=str(status_table),
            limit=args.limit,
            overwrite=args.overwrite,
            parse_missing=False,
            mineru_token=args.mineru_token,
            mineru_model_version=args.mineru_model_version,
            max_images=args.max_images,
            max_chars=args.max_chars,
            summary_max_chars=args.summary_max_chars,
            summary_chunk_chars=args.summary_chunk_chars,
            llm_provider=args.llm_provider,
            ecnu_api_key=args.ecnu_api_key,
            ecnu_base_url=args.ecnu_base_url,
            ecnu_model=args.ecnu_model,
            ecnu_thinking_type=args.ecnu_thinking_type,
        )
    )

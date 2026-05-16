from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.mineru_parser.mineru_client import MinerUClient
from src.mineru_parser.mineru_context import load_visual_items
from src.paper_summarizer.analysis_core import cache_stem_for_source, iter_progress, safe_stem_for_source
from src.pipeline.common import analyzer_settings_from_args, collect_stage_pdfs, ensure_status_columns, read_table, status_table_path_from_args, write_table


def parse_pdfs(args: argparse.Namespace) -> list[Path]:
    settings = analyzer_settings_from_args(args)
    pdfs = collect_stage_pdfs(settings, args)
    if not pdfs:
        raise FileNotFoundError(f"No PDFs found in {settings.downloads_dir}")

    mineru_client = None
    outputs: list[Path] = []
    failures = 0
    for pdf_path in iter_progress(pdfs, "MinerU parsing"):
        try:
            raw_path = raw_markdown_path(settings, pdf_path)
            if raw_path.exists() and not args.overwrite:
                print(f"Skip existing MinerU Markdown: {raw_path}")
                outputs.append(raw_path)
                continue
            if mineru_client is None:
                mineru_client = MinerUClient.from_settings(settings)
            parsed_path = parse_one_pdf(pdf_path, settings, mineru_client, overwrite=args.overwrite)
            update_parse_status(args, pdf_path, parsed_path)
            outputs.append(parsed_path)
        except Exception as exc:
            failures += 1
            print(f"Failed to parse {pdf_path}: {exc}")
    if failures:
        raise RuntimeError(f"MinerU parsing completed with {failures} failure(s).")
    return outputs


def parse_one_pdf(pdf_path, settings, mineru_client: MinerUClient, overwrite: bool = False) -> Path:
    source_stem = safe_stem_for_source(pdf_path)
    stem = cache_stem_for_source(pdf_path)
    parsed_dir = parsed_paper_dir(settings, pdf_path)
    output_dir = parsed_dir / "extract"
    raw_path = parsed_dir / f"{stem}.mineru.md"
    visuals_path = parsed_dir / f"{stem}.mineru.visuals.json"

    print(f"Parse PDF with MinerU: {pdf_path}")
    result = mineru_client.parse_pdf(pdf_path, output_dir, overwrite=overwrite)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(result.markdown, encoding="utf-8")

    visual_items = load_visual_items(result.output_dir, raw_path.parent)
    visuals_path.write_text(
        json.dumps([item.to_dict() for item in visual_items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_parse_cache_metadata(parsed_dir, source_stem, stem, pdf_path, raw_path, visuals_path)
    print(f"Wrote MinerU raw Markdown: {raw_path}")
    print(f"Wrote MinerU visual JSON: {visuals_path}")
    return raw_path


def raw_markdown_path(settings, pdf_path) -> Path:
    stem = cache_stem_for_source(pdf_path)
    return parsed_paper_dir(settings, pdf_path) / f"{stem}.mineru.md"


def parsed_paper_dir(settings, pdf_path) -> Path:
    stem = cache_stem_for_source(pdf_path)
    return settings.outputs_dir / stem


def write_parse_cache_metadata(
    parsed_dir: Path,
    source_stem: str,
    cache_stem: str,
    pdf_path,
    raw_path: Path,
    visuals_path: Path,
) -> None:
    metadata_path = parsed_dir / "_parse_cache.json"
    metadata_path.write_text(
        json.dumps(
            {
                "source_stem": source_stem,
                "cache_stem": cache_stem,
                "pdf_path": str(pdf_path),
                "raw_markdown_path": str(raw_path),
                "visuals_path": str(visuals_path),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def update_parse_status(args: argparse.Namespace, pdf_path, raw_path: Path) -> None:
    table_path = status_table_path_from_args(args)
    if table_path is None or not table_path.exists():
        return
    df = ensure_status_columns(read_table(table_path))
    pdf_value = str(Path(pdf_path).resolve()) if isinstance(pdf_path, Path) else str(pdf_path)
    matched = False
    for index, row in df.iterrows():
        row_pdf = str(row.get("pdf_path", ""))
        if row_pdf and Path(row_pdf).name == Path(pdf_value).name:
            df.at[index, "parse_status"] = "parsed"
            df.at[index, "parsed_dir"] = str(raw_path.parent)
            matched = True
    if matched:
        write_table(df, table_path)
        print(f"Updated parse status table: {table_path}")

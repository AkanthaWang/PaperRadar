from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Iterable

import pandas as pd

from src.config import AnalyzerSettings, PROJECT_ROOT, resolve_path


EXCEL_SUFFIXES = {".xlsx", ".xls"}
CSV_SUFFIXES = {".csv"}
OPENREVIEW_CONFERENCES = {"ICLR", "ICML", "NEURIPS"}
DATA_ROOT = PROJECT_ROOT / "data"
ALL_PAPERS_DIR = DATA_ROOT / "all_papers"
FILTERED_PAPERS_DIR = DATA_ROOT / "filtered_papers"
PDFS_DIR = DATA_ROOT / "pdfs"
PARSED_DIR = DATA_ROOT / "parsed"
REPORTS_DIR = DATA_ROOT / "reports"
DEFAULT_ALL_PAPERS_TABLE = ALL_PAPERS_DIR / "all_papers.xlsx"
DEFAULT_FILTERED_PAPERS_TABLE = FILTERED_PAPERS_DIR / "filtered_papers.xlsx"
DEFAULT_STATUS_COLUMNS = {
    "download_status": "pending",
    "pdf_path": "",
    "parse_status": "pending",
    "parsed_dir": "",
    "report_status": "pending",
    "report_path": "",
}


def project_path(value: str | Path | None, default: Path | None = None) -> Path:
    if value in (None, ""):
        if default is None:
            raise ValueError("Missing path value.")
        return default
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def normalize_conference(value: str) -> str:
    return value.strip().upper()


def keyword_slug(keywords: Iterable[str]) -> str:
    cleaned = [re.sub(r"[^A-Za-z0-9_.-]+", "_", item.strip()).strip("_") for item in keywords]
    slug = "_".join(item for item in cleaned if item)
    return slug[:80] or "keywords"


def default_metadata_path(conference: str, year: str) -> Path:
    return DEFAULT_ALL_PAPERS_TABLE


def default_filtered_path(input_path: Path, keywords: list[str]) -> Path:
    return DEFAULT_FILTERED_PAPERS_TABLE


def read_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in EXCEL_SUFFIXES:
        return pd.read_excel(path)
    if suffix in CSV_SUFFIXES:
        return pd.read_csv(path)
    raise ValueError(f"Unsupported table format: {path}. Use .xlsx, .xls, or .csv.")


def write_table(df: pd.DataFrame, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix in EXCEL_SUFFIXES:
        df.to_excel(path, index=False)
    elif suffix in CSV_SUFFIXES:
        df.to_csv(path, index=False, encoding="utf-8-sig")
    else:
        raise ValueError(f"Unsupported table format: {path}. Use .xlsx, .xls, or .csv.")
    return path


def ensure_status_columns(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    for column, default in DEFAULT_STATUS_COLUMNS.items():
        if column not in result.columns:
            result[column] = default
    return result


def status_table_path_from_args(args) -> Path | None:
    value = getattr(args, "status_table", None)
    if value:
        return project_path(value)
    if DEFAULT_FILTERED_PAPERS_TABLE.exists():
        return DEFAULT_FILTERED_PAPERS_TABLE
    return None


def reports_dir_from_args(args) -> Path:
    value = getattr(args, "reports_dir", None)
    reports_dir = project_path(value, REPORTS_DIR)
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir


def infer_conference_year(path: Path) -> tuple[str, str]:
    match = re.search(r"([A-Za-z]+)[_\- ]?(\d{4})", path.stem)
    if not match:
        raise ValueError(
            f"Cannot infer conference/year from {path.name}. "
            "Pass --conference and --year explicitly."
        )
    return match.group(1).upper(), match.group(2)


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def resolve_source(conference: str, source: str) -> str:
    if source != "auto":
        return source
    return "openreview" if conference in OPENREVIEW_CONFERENCES else "openaccess"


def analyzer_settings_from_args(args) -> AnalyzerSettings:
    settings = AnalyzerSettings.from_env(PROJECT_ROOT)
    overrides = {}

    downloads_value = getattr(args, "pdf_dir", None) or getattr(args, "downloads_dir", None)
    parsed_value = getattr(args, "outputs_dir", None) or getattr(args, "parsed_dir", None)
    assets_value = getattr(args, "assets_dir", None)
    cache_value = getattr(args, "cache_dir", None)
    overrides["downloads_dir"] = resolve_path(downloads_value, settings.project_root) if downloads_value else PDFS_DIR
    overrides["outputs_dir"] = resolve_path(parsed_value, settings.project_root) if parsed_value else PARSED_DIR
    overrides["assets_dir"] = resolve_path(assets_value, settings.project_root) if assets_value else PARSED_DIR
    overrides["cache_dir"] = resolve_path(cache_value, settings.project_root) if cache_value else PARSED_DIR / "_cache"

    scalar_fields = [
        ("max_images", "max_images"),
        ("max_chars", "max_chars"),
        ("summary_max_chars", "summary_max_chars"),
        ("summary_chunk_chars", "summary_chunk_chars"),
        ("mineru_token", "mineru_token"),
        ("mineru_model_version", "mineru_model_version"),
        ("llm_provider", "llm_provider"),
        ("ecnu_api_key", "ecnu_api_key"),
        ("ecnu_base_url", "ecnu_base_url"),
        ("ecnu_model", "ecnu_model"),
        ("ecnu_thinking_type", "ecnu_thinking_type"),
    ]
    for arg_name, field_name in scalar_fields:
        if hasattr(args, arg_name):
            value = getattr(args, arg_name)
            if value is not None:
                overrides[field_name] = value

    overrides["parser"] = "mineru"
    if overrides:
        settings = replace(settings, **overrides)
    settings.ensure_dirs()
    return settings


def collect_stage_pdfs(settings: AnalyzerSettings, args):
    from src.paper_summarizer.analysis_core import collect_pdfs

    return collect_pdfs(settings, getattr(args, "pdf", None), getattr(args, "limit", None))

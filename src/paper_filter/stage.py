from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

from src.pipeline.common import default_filtered_path, ensure_status_columns, project_path, read_table, split_csv, write_table


def filter_dataframe(
    df: pd.DataFrame,
    keywords: list[str],
    columns: list[str],
    match_all: bool = False,
    regex: bool = False,
    case_sensitive: bool = False,
    allowed_types: list[str] | None = None,
    type_column: str = "type",
) -> pd.DataFrame:
    if not keywords:
        raise ValueError("At least one keyword is required.")

    missing_columns = [column for column in columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing filter columns: {', '.join(missing_columns)}")

    flags = 0 if case_sensitive else re.IGNORECASE
    matched_keywords: list[str] = []
    keep_mask: list[bool] = []

    for _, row in df.iterrows():
        text = "\n".join(str(row.get(column, "")) for column in columns)
        row_matches: list[str] = []
        for keyword in keywords:
            if regex:
                is_match = re.search(keyword, text, flags=flags) is not None
            elif case_sensitive:
                is_match = keyword in text
            else:
                is_match = keyword.lower() in text.lower()
            if is_match:
                row_matches.append(keyword)

        keep = len(row_matches) == len(keywords) if match_all else bool(row_matches)
        keep_mask.append(keep)
        matched_keywords.append(", ".join(row_matches))

    result = df.loc[keep_mask].copy()
    result["matched_keywords"] = [value for value, keep in zip(matched_keywords, keep_mask) if keep]

    if allowed_types is not None:
        if type_column not in result.columns:
            raise ValueError(f"Cannot apply type filter; missing column: {type_column}")
        allowed = {item.strip().lower() for item in allowed_types if item.strip()}
        result = result[result[type_column].astype(str).str.strip().str.lower().isin(allowed)].copy()

    return result


def filter_papers(args: argparse.Namespace) -> Path:
    input_path = project_path(args.input)
    keywords = args.keywords or []
    output_path = project_path(args.output, default_filtered_path(input_path, keywords))
    output_path = output_path if output_path.suffix else output_path.with_suffix(".xlsx")
    allowed_types = split_csv(args.types) if args.types else None

    df = read_table(input_path)
    columns = args.columns
    if columns is None:
        columns = [column for column in ["title", "abstract", "keywords"] if column in df.columns]
    if not columns:
        raise ValueError("No filter columns found. Expected at least one of: title, abstract, keywords.")

    result = filter_dataframe(
        df,
        keywords=keywords,
        columns=columns,
        match_all=args.match_all,
        regex=args.regex,
        case_sensitive=args.case_sensitive,
        allowed_types=allowed_types,
        type_column=args.type_column,
    )
    result = ensure_status_columns(result)
    write_table(result, output_path)
    print(f"Matched {len(result)} / {len(df)} papers.")
    print(f"Filtered table saved to: {output_path}")
    return output_path

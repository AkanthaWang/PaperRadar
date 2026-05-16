from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from src.paper_summarizer.analysis_core import (
    build_fallback_summary,
    cache_stem_for_source,
    extract_markdown_title,
    extract_named_section,
    generate_markdown_summary_with_llm,
    iter_progress,
    safe_stem_for_source,
)
from src.paper_summarizer.pdf_parser import infer_metadata_from_filename
from src.mineru_parser.mineru_client import MinerUClient
from src.mineru_parser.mineru_context import (
    MinerUVisualItem,
    insert_visuals_into_summary,
    load_visual_items,
    render_visual_context,
)
from src.mineru_parser.stage import parse_one_pdf
from src.pipeline.common import analyzer_settings_from_args, collect_stage_pdfs, ensure_status_columns, read_table, reports_dir_from_args, status_table_path_from_args, write_table
from src.utils.llm_client import create_llm_client


@dataclass(frozen=True)
class ReportLayout:
    root: Path
    blog_dir: Path
    data_dir: Path
    img_dir: Path
    blog_path: Path
    data_path: Path


def summarize_pdfs(args: argparse.Namespace) -> list[Path]:
    settings = analyzer_settings_from_args(args)
    pdfs = collect_stage_pdfs(settings, args)
    if not pdfs:
        raise FileNotFoundError(f"No PDFs found in {settings.downloads_dir}")

    client = create_llm_client(settings)
    mineru_client = None
    outputs: list[Path] = []
    failures = 0
    for pdf_path in iter_progress(pdfs, "Summarizing"):
        try:
            raw_path = raw_markdown_path(settings, pdf_path)
            if not raw_path.exists():
                if not args.parse_missing:
                    raise FileNotFoundError(f"Missing MinerU Markdown: {raw_path}")
                if mineru_client is None:
                    mineru_client = MinerUClient.from_settings(settings)
                parse_one_pdf(pdf_path, settings, mineru_client, overwrite=args.overwrite)
            report_path = summarize_one_pdf(pdf_path, settings, client, args, overwrite=args.overwrite)
            update_report_status(args, pdf_path, report_path)
            outputs.append(report_path)
        except Exception as exc:
            failures += 1
            print(f"Failed to summarize {pdf_path}: {exc}")
    if failures:
        raise RuntimeError(f"Summarization completed with {failures} failure(s).")
    return outputs


def summarize_one_pdf(pdf_path, settings, client, args: argparse.Namespace, overwrite: bool = False) -> Path:
    source_stem = safe_stem_for_source(pdf_path)
    stem = cache_stem_for_source(pdf_path)
    parsed_dir = parsed_paper_dir(settings, pdf_path)
    raw_path = parsed_dir / f"{stem}.mineru.md"
    visuals_path = parsed_dir / f"{stem}.mineru.visuals.json"
    raw_path, visuals_path, parsed_dir = resolve_parsed_artifacts(settings, pdf_path, raw_path, visuals_path, parsed_dir)
    reports_root = reports_dir_from_args(args)

    markdown = raw_path.read_text(encoding="utf-8")
    status_row = find_status_row(args, pdf_path)
    metadata = build_report_metadata(pdf_path, source_stem, markdown, status_row)
    layout = build_report_layout(reports_root, metadata["id"])
    if layout.blog_path.exists() and not overwrite:
        if not layout.data_path.exists():
            write_report_metadata(layout.data_path, metadata)
        print(f"Skip existing summary: {layout.blog_path}")
        return layout.blog_path

    visual_items = load_visual_items_for_source(settings, pdf_path, visuals_path)
    report_visual_items, image_path_map = copy_visuals_for_blog(settings, parsed_dir, visual_items, layout)
    visual_context = render_visual_context(report_visual_items)

    print("Summarize MinerU Markdown with LLM")
    llm_error = ""
    try:
        summary_markdown = generate_markdown_summary_with_llm(
            stem,
            markdown,
            visual_context,
            client,
            settings,
        )
    except Exception as exc:
        llm_error = str(exc)
        print(f"LLM summary failed; writing fallback Markdown: {llm_error}")
        summary_markdown = build_fallback_summary(stem, markdown, raw_path, visuals_path, llm_error)

    summary_markdown = insert_visuals_into_summary(summary_markdown, report_visual_items)
    summary_markdown = rewrite_markdown_image_paths(summary_markdown, image_path_map)
    summary_markdown = copy_referenced_markdown_images(settings, parsed_dir, summary_markdown, layout)
    layout.blog_path.parent.mkdir(parents=True, exist_ok=True)
    layout.blog_path.write_text(summary_markdown, encoding="utf-8")
    write_report_metadata(layout.data_path, metadata)
    write_summary_cache(
        settings,
        stem,
        layout.blog_path,
        raw_path,
        visuals_path,
        report_visual_items,
        llm_error,
        layout.data_path,
        layout.img_dir,
    )
    print(f"Wrote summary Markdown: {layout.blog_path}")
    print(f"Wrote report metadata JSON: {layout.data_path}")
    return layout.blog_path


def raw_markdown_path(settings, pdf_path) -> Path:
    stem = cache_stem_for_source(pdf_path)
    raw_path = parsed_paper_dir(settings, pdf_path) / f"{stem}.mineru.md"
    if raw_path.exists():
        return raw_path

    legacy_stem = safe_stem_for_source(pdf_path)
    legacy_raw_path = settings.outputs_dir / legacy_stem / f"{legacy_stem}.mineru.md"
    return legacy_raw_path if legacy_raw_path.exists() else raw_path


def build_report_layout(reports_root: Path, paper_id: str) -> ReportLayout:
    blog_dir = reports_root / "blog"
    data_dir = reports_root / "data"
    img_dir = reports_root / "img" / paper_id
    return ReportLayout(
        root=reports_root,
        blog_dir=blog_dir,
        data_dir=data_dir,
        img_dir=img_dir,
        blog_path=blog_dir / f"{paper_id}.md",
        data_path=data_dir / f"{paper_id}.json",
    )


def copy_visuals_for_blog(
    settings,
    parsed_dir: Path,
    items: list[MinerUVisualItem],
    layout: ReportLayout,
) -> tuple[list[MinerUVisualItem], dict[str, str]]:
    if not items:
        return [], {}

    layout.img_dir.mkdir(parents=True, exist_ok=True)
    copied_items: list[MinerUVisualItem] = []
    image_path_map: dict[str, str] = {}
    used_names: set[str] = set()

    for item in items:
        if not item.path:
            copied_items.append(item)
            continue

        source = resolve_visual_source(settings, parsed_dir, item.path)
        if source is None:
            copied_items.append(item)
            continue

        target_name = unique_image_name(source.name, used_names)
        target = layout.img_dir / target_name
        if not target.exists() or source.stat().st_size != target.stat().st_size:
            shutil.copy2(source, target)

        blog_relative_path = os.path.relpath(target, layout.blog_dir).replace("\\", "/")
        image_path_map[item.path] = blog_relative_path
        copied_items.append(replace(item, path=blog_relative_path))

    return copied_items, image_path_map


def resolve_visual_source(settings, parsed_dir: Path, item_path: str) -> Path | None:
    raw_path = Path(item_path)
    candidates = []
    if raw_path.is_absolute():
        candidates.append(raw_path)
    else:
        candidates.extend([settings.outputs_dir / raw_path, parsed_dir / raw_path])

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def unique_image_name(filename: str, used_names: set[str]) -> str:
    stem = sanitize_slug(Path(filename).stem, max_length=80) or "image"
    suffix = Path(filename).suffix.lower() or ".png"
    candidate = f"{stem}{suffix}"
    counter = 2
    while candidate.lower() in used_names:
        candidate = f"{stem}-{counter}{suffix}"
        counter += 1
    used_names.add(candidate.lower())
    return candidate


def rewrite_markdown_image_paths(markdown: str, path_map: dict[str, str]) -> str:
    if not path_map:
        return markdown

    def replace_match(match: re.Match[str]) -> str:
        alt_text = match.group(1)
        raw_path = match.group(2).strip()
        normalized = raw_path.replace("\\", "/")
        replacement = path_map.get(raw_path) or path_map.get(normalized)
        if replacement is None:
            return match.group(0)
        return f"![{alt_text}]({replacement})"

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", replace_match, markdown)


def copy_referenced_markdown_images(settings, parsed_dir: Path, markdown: str, layout: ReportLayout) -> str:
    used_names = {path.name.lower() for path in layout.img_dir.glob("*") if path.is_file()} if layout.img_dir.exists() else set()

    def replace_match(match: re.Match[str]) -> str:
        alt_text = match.group(1)
        raw_path = match.group(2).strip()
        if is_external_or_report_image(raw_path):
            return match.group(0)

        source = resolve_visual_source(settings, parsed_dir, raw_path)
        if source is None:
            return match.group(0)

        layout.img_dir.mkdir(parents=True, exist_ok=True)
        target_name = unique_image_name(source.name, used_names)
        target = layout.img_dir / target_name
        shutil.copy2(source, target)
        blog_relative_path = os.path.relpath(target, layout.blog_dir).replace("\\", "/")
        return f"![{alt_text}]({blog_relative_path})"

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", replace_match, markdown)


def is_external_or_report_image(path: str) -> bool:
    normalized = path.replace("\\", "/").strip()
    return (
        normalized.startswith(("http://", "https://", "data:", "#"))
        or normalized.startswith("../img/")
        or normalized.startswith("/img/")
    )


def write_report_metadata(path: Path, metadata: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_report_metadata(
    pdf_path,
    stem: str,
    markdown: str,
    status_row: dict[str, object] | None,
) -> dict[str, object]:
    filename_year, filename_venue, filename_title = infer_source_metadata(pdf_path, stem)
    row = status_row or {}
    full_title = first_nonempty(row, "title", "full_title", "fullTitle") or extract_markdown_title(markdown) or filename_title
    explicit_short_title = first_nonempty(row, "title_short", "short_title", "acronym", "abbr")
    short_title = explicit_short_title or infer_short_title(full_title, stem)
    paper_id_source = first_nonempty(row, "id", "paper_id", "slug")
    if not paper_id_source:
        has_acronym = bool(explicit_short_title or extract_leading_acronym(clean_title(full_title)) or extract_leading_acronym(stem))
        paper_id_source = short_title if has_acronym else full_title
    paper_id = sanitize_slug(normalize_id_source(paper_id_source)) or sanitize_slug(stem)
    year = infer_year(first_nonempty(row, "year", "conference_year") or filename_year)
    venue = first_nonempty(row, "venue", "conference", "source") or filename_venue
    category = first_nonempty(row, "category") or "Emotion"
    paper_type = first_nonempty(row, "paper_type", "paperType") or "Method"
    modality = infer_modality(row, markdown)
    tags = infer_tags(row, modality)
    introduction = first_nonempty(row, "introduction", "abstract") or extract_named_section(markdown, "abstract", max_chars=500)

    return {
        "id": paper_id,
        "title": short_title,
        "fullTitle": full_title,
        "year": year,
        "category": category,
        "type": paper_type,
        "modality": modality,
        "tags": tags,
        "introduction": introduction,
        "blog": {
            "enabled": True,
            "slug": f"/blog/{paper_id}",
        },
        "venue": venue,
    }


def infer_source_metadata(pdf_path, stem: str) -> tuple[str, str, str]:
    if isinstance(pdf_path, Path):
        return infer_metadata_from_filename(pdf_path)
    filename = Path(str(pdf_path).rstrip("/").split("/")[-1].split("?")[0] or stem)
    if filename.suffix:
        return infer_metadata_from_filename(filename)
    return "", "", stem


def find_status_row(args: argparse.Namespace, pdf_path) -> dict[str, object] | None:
    table_path = status_table_path_from_args(args)
    if table_path is None or not table_path.exists():
        return None
    try:
        df = read_table(table_path)
    except Exception:
        return None

    pdf_name = Path(str(pdf_path)).name
    for _, row in df.iterrows():
        row_pdf = str(row.get("pdf_path", ""))
        if row_pdf and Path(row_pdf).name == pdf_name:
            return {key: value for key, value in row.to_dict().items() if not is_empty_value(value)}
    return None


def first_nonempty(row: dict[str, object], *keys: str) -> str:
    lowered = {key.lower(): value for key, value in row.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if not is_empty_value(value):
            return str(value).strip()
    return ""


def is_empty_value(value: object) -> bool:
    if value is None:
        return True
    try:
        import pandas as pd

        if pd.isna(value):
            return True
    except Exception:
        pass
    return str(value).strip() == ""


def infer_short_title(full_title: str, stem: str) -> str:
    title = clean_title(full_title)
    acronym = extract_leading_acronym(title)
    if acronym:
        return acronym
    stem_acronym = extract_leading_acronym(stem)
    if stem_acronym:
        return stem_acronym
    words = re.findall(r"[A-Za-z0-9]+", title)
    if 2 <= len(words) <= 5:
        return " ".join(words)
    return " ".join(words[:4]) if words else stem


def extract_leading_acronym(value: str) -> str:
    match = re.match(r"^\s*([A-Za-z][A-Za-z0-9-]{1,20})\s*[:：-]\s+", value)
    if not match:
        return ""
    candidate = match.group(1).strip("-")
    if any(char.isupper() for char in candidate) or len(candidate) <= 8:
        return candidate
    return ""


def clean_title(value: str) -> str:
    title = re.sub(r"^\s*20\d{2}[_\s-]+[A-Za-z]+[_\s-]+", "", value)
    title = title.replace("_", " ")
    title = re.sub(r"\s+", " ", title).strip(" .")
    return title or value


def infer_year(value: str) -> int:
    match = re.search(r"20\d{2}", str(value))
    return int(match.group(0)) if match else 2026


def infer_modality(row: dict[str, object], markdown: str) -> str:
    explicit = first_nonempty(row, "modality")
    if explicit:
        return explicit
    text = " ".join(
        [
            first_nonempty(row, "title", "keywords", "abstract"),
            markdown[:4000],
        ]
    ).lower()
    modality_keywords = [
        ("video", ["video", "audiovisual", "audio-visual"]),
        ("audio", ["audio", "speech", "prosody", "voice"]),
        ("text", ["text", "language", "llm", "dialogue", "conversation"]),
        ("image", ["image", "vision", "visual", "facial", "face"]),
    ]
    matched = [label for label, keywords in modality_keywords if any(keyword in text for keyword in keywords)]
    if len(matched) > 1:
        return "multimodal"
    return matched[0] if matched else "image"


def infer_tags(row: dict[str, object], modality: str) -> list[str]:
    raw = first_nonempty(row, "tags", "matched_keywords", "keywords")
    tags = split_tags(raw)
    if "emotion" not in {tag.lower() for tag in tags}:
        tags.insert(0, "Emotion")
    modality_tag = modality.capitalize()
    if modality_tag and modality_tag.lower() not in {tag.lower() for tag in tags}:
        tags.append(modality_tag)
    return tags[:8]


def split_tags(value: str) -> list[str]:
    if not value:
        return []
    tags = [item.strip() for item in re.split(r"[,;|/]+", value) if item.strip()]
    return dedupe_preserve_order(tags)


def dedupe_preserve_order(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def sanitize_slug(value: str, max_length: int = 80) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().lower())
    slug = slug.strip("-")
    return slug[:max_length].strip("-")


def normalize_id_source(value: str) -> str:
    value = str(value).strip()
    value = re.sub(r"^/blog/", "", value, flags=re.IGNORECASE)
    return value.strip("/")


def resolve_parsed_artifacts(
    settings,
    pdf_path,
    raw_path: Path,
    visuals_path: Path,
    parsed_dir: Path,
) -> tuple[Path, Path, Path]:
    if raw_path.exists():
        return raw_path, visuals_path, parsed_dir

    legacy_stem = safe_stem_for_source(pdf_path)
    legacy_dir = settings.outputs_dir / legacy_stem
    legacy_raw_path = legacy_dir / f"{legacy_stem}.mineru.md"
    legacy_visuals_path = legacy_dir / f"{legacy_stem}.mineru.visuals.json"
    if legacy_raw_path.exists():
        return legacy_raw_path, legacy_visuals_path, legacy_dir
    return raw_path, visuals_path, parsed_dir


def load_visual_items_for_source(settings, pdf_path, visuals_path: Path) -> list[MinerUVisualItem]:
    mineru_output_root = parsed_paper_dir(settings, pdf_path) / "extract"
    if not mineru_output_root.exists() and visuals_path.exists():
        mineru_output_root = visuals_path.parent / "extract"
    extract_dir = latest_extract_dir(mineru_output_root)
    if extract_dir is not None:
        visual_items = load_visual_items(extract_dir, settings.outputs_dir)
        visuals_path.write_text(
            json.dumps([item.to_dict() for item in visual_items], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return visual_items
    if visuals_path.exists():
        return load_visual_items_from_json(visuals_path)
    return []


def parsed_paper_dir(settings, pdf_path) -> Path:
    stem = cache_stem_for_source(pdf_path)
    return settings.outputs_dir / stem


def latest_extract_dir(root: Path) -> Path | None:
    if not root.exists():
        return None
    dirs = sorted(
        [path for path in root.iterdir() if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return dirs[0] if dirs else None


def update_report_status(args: argparse.Namespace, pdf_path, report_path: Path) -> None:
    table_path = status_table_path_from_args(args)
    if table_path is None or not table_path.exists():
        return
    df = ensure_status_columns(read_table(table_path))
    pdf_value = str(Path(pdf_path).resolve()) if isinstance(pdf_path, Path) else str(pdf_path)
    matched = False
    for index, row in df.iterrows():
        row_pdf = str(row.get("pdf_path", ""))
        if row_pdf and Path(row_pdf).name == Path(pdf_value).name:
            df.at[index, "report_status"] = "reported"
            df.at[index, "report_path"] = str(report_path)
            matched = True
    if matched:
        write_table(df, table_path)
        print(f"Updated report status table: {table_path}")


def load_visual_items_from_json(path: Path) -> list[MinerUVisualItem]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items: list[MinerUVisualItem] = []
    if not isinstance(payload, list):
        return items
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            items.append(MinerUVisualItem(**item))
        except TypeError:
            continue
    return items


def write_summary_cache(
    settings,
    stem: str,
    output_path: Path,
    raw_path: Path,
    visuals_path: Path,
    visual_items: list[MinerUVisualItem],
    llm_error: str,
    metadata_path: Path | None = None,
    image_dir: Path | None = None,
) -> None:
    cache_path = settings.cache_dir / f"{stem}.summary.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "status": "fallback" if llm_error else "ok",
                "summary_error": llm_error,
                "output_path": str(output_path),
                "metadata_path": str(metadata_path) if metadata_path is not None else "",
                "image_dir": str(image_dir) if image_dir is not None else "",
                "raw_markdown_path": str(raw_path),
                "visuals_path": str(visuals_path),
                "visual_count": len(visual_items),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

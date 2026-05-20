from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from datetime import datetime
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


MAX_REPORT_TAGS = 5


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
    auto_parse_missing = bool(getattr(args, "parse_missing", False) or getattr(args, "pdf", None))
    for pdf_path in iter_progress(pdfs, "Summarizing"):
        try:
            raw_path = raw_markdown_path(settings, pdf_path)
            if not raw_path.exists():
                if not auto_parse_missing:
                    raise FileNotFoundError(f"Missing MinerU Markdown: {raw_path}")
                if mineru_client is None:
                    mineru_client = MinerUClient.from_settings(settings)
                parse_one_pdf(pdf_path, settings, mineru_client, overwrite=args.overwrite)
                raw_path = raw_markdown_path(settings, pdf_path)
            report_path = summarize_one_pdf(pdf_path, settings, client, args, overwrite=args.overwrite)
            update_report_status(args, pdf_path, report_path)
            outputs.append(report_path)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[INFO] {now} 成功生成摘要: {Path(pdf_path).name}")
        except Exception as exc:
            failures += 1
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[INFO] {now} 无法生成摘要: {Path(pdf_path).name} 错误: {exc}")
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
        existing_summary = layout.blog_path.read_text(encoding="utf-8")
        existing_metadata = read_report_metadata(layout.data_path)
        generated_tags = metadata.get("tags", [])
        metadata = merge_report_metadata(metadata, existing_metadata)
        metadata["tags"] = merge_report_tags(generated_tags, existing_metadata.get("tags"))
        metadata = ensure_chinese_introduction(metadata, existing_summary)
        if (
            not existing_metadata
            or existing_metadata.get("introduction") != metadata.get("introduction")
            or existing_metadata.get("tags") != metadata.get("tags")
        ):
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
    metadata = ensure_chinese_introduction(metadata, summary_markdown)
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


def read_report_metadata(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def merge_report_metadata(metadata: dict[str, object], existing: dict[str, object]) -> dict[str, object]:
    if not existing:
        return metadata
    merged = dict(metadata)
    merged.update(existing)
    return merged


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
    tags = infer_tags(row, modality, markdown, full_title)
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


def ensure_chinese_introduction(metadata: dict[str, object], summary_markdown: str) -> dict[str, object]:
    result = dict(metadata)
    current = str(result.get("introduction") or "").strip()
    if has_chinese(current):
        result["introduction"] = normalize_intro_text(current)
        return result

    summary_intro = extract_chinese_introduction_from_summary(summary_markdown)
    if summary_intro:
        result["introduction"] = summary_intro
        return result

    result["introduction"] = build_generic_chinese_introduction(result)
    return result


def extract_chinese_introduction_from_summary(markdown: str) -> str:
    core = first_intro_sentence_from_section(markdown, ["核心问题"])
    method = first_intro_sentence_from_section(markdown, ["方法介绍", "方法概述"])
    motivation = first_intro_sentence_from_section(markdown, ["动机和思想"])
    task = extract_basic_info_field(markdown, "研究任务")

    pieces: list[str] = []
    for value in [core, method, motivation, task]:
        value = normalize_intro_text(value)
        if not is_good_chinese_intro(value):
            continue
        if value not in pieces:
            pieces.append(value)
        if len(" ".join(pieces)) >= 220:
            break

    return truncate_intro(" ".join(pieces), max_chars=320)


def first_intro_sentence_from_section(markdown: str, titles: list[str]) -> str:
    section = extract_summary_section(markdown, titles, max_chars=1200)
    if not section:
        return ""
    text = normalize_intro_text(section)
    for sentence in split_intro_sentences(text):
        if is_good_chinese_intro(sentence):
            return sentence
    return text if is_good_chinese_intro(text) else ""


def extract_summary_section(markdown: str, titles: list[str], max_chars: int) -> str:
    wanted = {normalize_summary_heading(title) for title in titles}
    lines = markdown.splitlines()
    start = None
    level = 0
    for index, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line.strip())
        if not match:
            continue
        title = normalize_summary_heading(match.group(2))
        if title in wanted:
            start = index + 1
            level = len(match.group(1))
            break
    if start is None:
        return ""

    collected: list[str] = []
    for line in lines[start:]:
        match = re.match(r"^(#{1,6})\s+\S+", line.strip())
        if match and len(match.group(1)) <= level:
            break
        collected.append(line)
        if len("\n".join(collected)) >= max_chars:
            break
    return "\n".join(collected).strip()


def extract_basic_info_field(markdown: str, field: str) -> str:
    section = extract_summary_section(markdown, ["基本信息"], max_chars=1000)
    if not section:
        return ""
    for line in section.splitlines():
        clean = re.sub(r"^[>\-\*\s]+", "", line).strip()
        match = re.match(rf"^{re.escape(field)}\s*[:：]\s*(.+)$", clean)
        if match:
            return normalize_intro_text(match.group(1))
    return ""


def normalize_summary_heading(value: str) -> str:
    value = re.sub(r"[#`*_~>\s]+", "", value)
    value = re.sub(r"[：:，,。.!！?？（）()\[\]【】]+", "", value)
    return value.lower()


def normalize_intro_text(value: str) -> str:
    value = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", value)
    value = re.sub(r"\[[^\]]+\]\([^)]+\)", lambda match: match.group(0).split("](", 1)[0].lstrip("["), value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"^[#>\-\*\d\.\s]+", "", value, flags=re.MULTILINE)
    value = re.sub(r"[`*_~]+", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" \t\r\n-，,；;：:")


def split_intro_sentences(text: str) -> list[str]:
    text = normalize_intro_text(text)
    if not text:
        return []
    matches = re.findall(r"[^。！？!?；;]+[。！？!?；;]?", text)
    return [sentence.strip() for sentence in matches if sentence.strip()]


def is_good_chinese_intro(value: str) -> bool:
    if not value or not has_chinese(value):
        return False
    lowered = value.lower()
    bad_markers = ["llm 总结失败", "请修复", "mineru markdown", "mineru visual json"]
    if any(marker in lowered for marker in bad_markers):
        return False
    return len(value) >= 12


def has_chinese(value: str) -> bool:
    return re.search(r"[\u3400-\u9fff]", value) is not None


def truncate_intro(text: str, max_chars: int) -> str:
    text = normalize_intro_text(text)
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rstrip()
    for punctuation in ["。", "！", "？", "；"]:
        index = cut.rfind(punctuation)
        if index >= 80:
            return cut[: index + 1]
    return cut.rstrip("，,；;：:、 ") + "。"


def build_generic_chinese_introduction(metadata: dict[str, object]) -> str:
    title = str(metadata.get("fullTitle") or metadata.get("title") or "该论文").strip()
    return f"本文围绕《{title}》展开研究，主要内容包括问题背景、方法设计、实验结果和可借鉴点，详见对应博客总结。"


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


TAG_ALIASES = {
    "affect": "Affective Computing",
    "affective computing": "Affective Computing",
    "audio": "Audio",
    "audio driven": "Audio-Driven",
    "audio-driven": "Audio-Driven",
    "au": "Action Unit",
    "action unit": "Action Unit",
    "action units": "Action Unit",
    "face": "Face",
    "facial": "Face",
    "facial expression": "Facial Expression Recognition",
    "facial expression recognition": "Facial Expression Recognition",
    "fer": "Facial Expression Recognition",
    "emotion": "Emotion",
    "emotion recognition": "Emotion Recognition",
    "visual emotion": "Visual Emotion Recognition",
    "visual emotion recognition": "Visual Emotion Recognition",
    "ver": "Visual Emotion Recognition",
    "image": "Image",
    "vision": "Computer Vision",
    "video": "Video",
    "text": "Text",
    "language": "Language",
    "multimodal": "Multimodal",
    "multi modal": "Multimodal",
    "multi-modal": "Multimodal",
    "cross domain": "Cross-Domain",
    "cross-domain": "Cross-Domain",
    "domain adaptation": "Domain Adaptation",
    "unsupervised": "Unsupervised Learning",
    "supervised": "Supervised Learning",
    "diffusion": "Diffusion",
    "generative": "Generative Model",
    "generation": "Generation",
    "talking head": "Talking Head Generation",
    "lip sync": "Lip Synchronization",
    "lip-sync": "Lip Synchronization",
    "clip": "CLIP",
    "vlm": "VLM",
    "llm": "LLM",
    "lora": "LoRA",
    "moe": "MoE",
    "transformer": "Transformer",
    "attention": "Attention",
    "contrastive learning": "Contrastive Learning",
    "prompt learning": "Prompt Learning",
    "knowledge distillation": "Knowledge Distillation",
    "knowledge graph": "Knowledge Graph",
    "benchmark": "Benchmark",
    "dataset": "Dataset",
    "ablation": "Ablation Study",
    "classification": "Classification",
    "recognition": "Recognition",
    "情感": "Emotion",
    "情感识别": "Emotion Recognition",
    "视觉情感": "Visual Emotion Recognition",
    "表情识别": "Facial Expression Recognition",
    "面部表情": "Facial Expression Recognition",
    "动作单元": "Action Unit",
    "跨域": "Cross-Domain",
    "领域自适应": "Domain Adaptation",
    "无监督": "Unsupervised Learning",
    "扩散": "Diffusion",
    "多模态": "Multimodal",
    "图像": "Image",
    "视频": "Video",
    "音频": "Audio",
    "文本": "Text",
}


TAG_RULES = [
    ("Facial Expression Recognition", [r"\bfer\b", r"facial expression"]),
    ("Visual Emotion Recognition", [r"\bver\b", r"visual emotion"]),
    ("Emotion Recognition", [r"emotion recognition", r"affect recognition"]),
    ("Affective Computing", [r"affective computing", r"emotion analysis"]),
    ("Cross-Domain", [r"cross[-\s]?domain", r"domain shift"]),
    ("Domain Adaptation", [r"domain adaptation", r"\bda\b"]),
    ("Unsupervised Learning", [r"unsupervised", r"without target labels"]),
    ("Universal Cross-Domain", [r"universal cross[-\s]?domain", r"\bucd?ver\b"]),
    ("Diffusion", [r"diffusion", r"denois"]),
    ("Counterfactual Learning", [r"counterfactual"]),
    ("Knowledge Alignment", [r"knowledge[-\s]?aligned", r"knowledge alignment"]),
    ("CLIP", [r"\bclip\b"]),
    ("VLM", [r"\bvlm\b", r"vision[-\s]?language model"]),
    ("LLM", [r"\bllm\b", r"large language model"]),
    ("LoRA", [r"\blora\b"]),
    ("MoE", [r"\bmoe\b", r"mixture of experts"]),
    ("Transformer", [r"transformer"]),
    ("Attention", [r"attention"]),
    ("Contrastive Learning", [r"contrastive"]),
    ("Prompt Learning", [r"prompt"]),
    ("Knowledge Distillation", [r"distillation"]),
    ("Knowledge Graph", [r"knowledge graph", r"triplet"]),
    ("Action Unit", [r"\bau\b", r"action unit"]),
    ("Talking Head Generation", [r"talking head"]),
    ("Lip Synchronization", [r"lip[-\s]?sync"]),
    ("Audio-Driven", [r"audio[-\s]?driven", r"speech[-\s]?driven"]),
    ("Generation", [r"generation", r"generate"]),
    ("Classification", [r"classification", r"classifier"]),
    ("Benchmark", [r"benchmark", r"state[-\s]?of[-\s]?the[-\s]?art", r"\bsota\b"]),
    ("Dataset", [r"dataset", r"emoset", r"ser30k", r"emo8"]),
]


MODALITY_TAGS = {
    "image": ["Image"],
    "video": ["Video"],
    "audio": ["Audio"],
    "text": ["Text", "Language"],
    "multimodal": ["Multimodal"],
}


def infer_tags(row: dict[str, object], modality: str, markdown: str, full_title: str) -> list[str]:
    tags: list[str] = []
    add_tag(tags, "Emotion")

    text = tag_source_text(row, markdown, full_title)
    for tag, patterns in TAG_RULES:
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
            add_tag(tags, tag)

    for tag in modality_tags(modality):
        add_tag(tags, tag)

    raw_values = [
        first_nonempty(row, "tags"),
        first_nonempty(row, "matched_keywords"),
        first_nonempty(row, "keywords"),
        first_nonempty(row, "category"),
    ]
    for raw in raw_values:
        for tag in split_tags(raw):
            add_tag(tags, tag)

    return tags[:MAX_REPORT_TAGS]


def merge_report_tags(generated_tags: object, existing_tags: object) -> list[str]:
    tags: list[str] = []
    for value in [generated_tags, existing_tags]:
        for tag in split_tag_value(value):
            add_tag(tags, tag)
    return tags[:MAX_REPORT_TAGS]


def add_tag(tags: list[str], raw_tag: str) -> None:
    tag = normalize_english_tag(raw_tag)
    if not tag:
        return
    if tag.lower() in {existing.lower() for existing in tags}:
        return
    tags.append(tag)


def normalize_english_tag(value: str) -> str:
    tag = re.sub(r"[`*_#]+", " ", str(value or ""))
    tag = re.sub(r"\s+", " ", tag).strip(" \t\r\n,;|/、，；")
    if not tag:
        return ""

    alias_key = tag_alias_key(tag)
    if alias_key in TAG_ALIASES:
        return TAG_ALIASES[alias_key]
    for key, canonical in TAG_ALIASES.items():
        if has_chinese(key) and key in tag:
            return canonical

    if has_chinese(tag):
        return ""
    if not re.search(r"[A-Za-z]", tag):
        return ""
    return format_english_tag(tag)


def tag_alias_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def format_english_tag(value: str) -> str:
    value = re.sub(r"[_-]+", " ", value.strip())
    value = re.sub(r"\s+", " ", value).strip()
    acronyms = {"ai", "au", "clip", "fer", "gan", "llm", "moe", "nlp", "uc", "vae", "ver", "vlm"}
    special = {"lora": "LoRA"}
    words = []
    for word in value.split(" "):
        key = word.lower()
        if key in special:
            words.append(special[key])
        elif key in acronyms:
            words.append(key.upper())
        elif len(word) > 1 and word.isupper():
            words.append(word)
        else:
            words.append(word[:1].upper() + word[1:].lower())
    return " ".join(words)


def modality_tags(modality: str) -> list[str]:
    normalized = tag_alias_key(modality)
    if normalized in MODALITY_TAGS:
        return MODALITY_TAGS[normalized]
    return [format_english_tag(modality)] if modality else []


def tag_source_text(row: dict[str, object], markdown: str, full_title: str) -> str:
    values = [
        full_title,
        first_nonempty(row, "title"),
        first_nonempty(row, "keywords"),
        first_nonempty(row, "abstract"),
        first_nonempty(row, "matched_keywords"),
        first_nonempty(row, "tags"),
        markdown[:10000],
    ]
    return " ".join(value for value in values if value).lower()


def split_tags(value: str) -> list[str]:
    return split_tag_value(value)


def split_tag_value(value: object) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [item.strip() for item in re.split(r"[,;|/、，；]+", text) if item.strip()]


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

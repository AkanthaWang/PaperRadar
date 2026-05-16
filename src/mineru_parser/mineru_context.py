from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from html import unescape
from pathlib import Path
from typing import Any


@dataclass
class MinerUVisualItem:
    index: int
    kind: str
    page: int
    path: str
    caption: str
    footnote: str
    section: str
    before: str
    after: str
    table_body: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SummaryHeading:
    level: int
    title: str
    position: int = -1


def load_visual_items(extract_dir: str | Path, markdown_dir: str | Path, max_items: int = 12) -> list[MinerUVisualItem]:
    extract_dir = Path(extract_dir)
    markdown_dir = Path(markdown_dir)
    content_list_path = find_content_list_file(extract_dir)
    if content_list_path is None:
        return []

    try:
        blocks = json.loads(content_list_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(blocks, list):
        return []

    items: list[MinerUVisualItem] = []
    seen_paths: set[str] = set()
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        kind = str(block.get("type", "")).strip().lower()
        if kind not in {"image", "table"}:
            continue

        image_path = str(block.get("img_path") or block.get("image_path") or "").strip()
        resolved_path = resolve_asset_path(extract_dir, image_path)
        relative_path = ""
        if resolved_path is not None:
            key = str(resolved_path.resolve()).lower()
            if key in seen_paths:
                continue
            seen_paths.add(key)
            relative_path = os.path.relpath(resolved_path, markdown_dir).replace("\\", "/")

        caption = join_text_list(
            block.get("image_caption")
            or block.get("table_caption")
            or block.get("caption")
            or []
        )
        footnote = join_text_list(
            block.get("image_footnote")
            or block.get("table_footnote")
            or block.get("footnote")
            or []
        )
        before = nearby_text(blocks, index, -1)
        after = nearby_text(blocks, index, 1)
        section = nearest_section(blocks, index)
        table_body = strip_html(str(block.get("table_body") or "")) if kind == "table" else ""

        if not any([relative_path, caption, table_body]):
            continue

        items.append(
            MinerUVisualItem(
                index=len(items) + 1,
                kind=kind,
                page=int(block.get("page_idx", -1)) + 1 if isinstance(block.get("page_idx"), int) else 0,
                path=relative_path,
                caption=caption,
                footnote=footnote,
                section=section,
                before=before,
                after=after,
                table_body=truncate(table_body, 1200),
            )
        )
        if len(items) >= max_items:
            break

    return items


def render_visual_context(items: list[MinerUVisualItem], max_items: int = 6) -> str:
    if not items:
        return "MinerU JSON 未提取到可用图表信息。"

    items = choose_visual_items(items, max_items=max_items)
    lines = ["## MinerU JSON 图表与上下文", ""]
    for item in items:
        label = "Table" if item.kind == "table" else "Figure"
        lines.append(f"### {label} {item.index}")
        lines.append(f"- 类型：{item.kind}")
        lines.append(f"- 页码：{item.page or '未知'}")
        if item.path:
            lines.append(f"- Markdown 图片路径：`{item.path}`")
        if item.section:
            lines.append(f"- 所在章节：{item.section}")
        if item.caption:
            lines.append(f"- Caption：{item.caption}")
        if item.footnote:
            lines.append(f"- Footnote：{item.footnote}")
        if item.before:
            lines.append(f"- 前文上下文：{truncate(item.before, 160)}")
        if item.after:
            lines.append(f"- 后文上下文：{truncate(item.after, 160)}")
        if item.table_body:
            lines.append(f"- 表格内容摘录：{truncate(item.table_body, 220)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def insert_visuals_into_summary(markdown: str, items: list[MinerUVisualItem], max_items: int = 8) -> str:
    if not items:
        return markdown

    existing_paths = extract_existing_image_paths(markdown)
    grouped: dict[SummaryHeading, list[MinerUVisualItem]] = {}
    for item in choose_visual_items(items, max_items=max_items):
        if not item.path or item.path in existing_paths:
            continue
        for target_heading in choose_summary_headings_for_visual(markdown, item):
            grouped.setdefault(target_heading, []).append(item)

    result = markdown.rstrip()
    for heading, section_items in sorted(grouped.items(), key=lambda pair: pair[0].position, reverse=True):
        block = render_visual_markdown(section_items, heading)
        result = insert_block_under_existing_heading(result, heading, block)
    return remove_related_visual_headings(result) + "\n"


def find_content_list_file(extract_dir: Path) -> Path | None:
    exact = sorted(extract_dir.rglob("*_content_list.json"))
    if exact:
        return exact[0]
    versioned = sorted(extract_dir.rglob("*_content_list_v2.json"))
    if versioned:
        return versioned[0]
    return None


def resolve_asset_path(extract_dir: Path, image_path: str) -> Path | None:
    if not image_path:
        return None
    candidate = extract_dir / image_path
    if candidate.exists():
        return candidate
    name = Path(image_path).name
    if not name:
        return None
    found = next((path for path in extract_dir.rglob(name) if path.is_file()), None)
    return found


def join_text_list(value: Any) -> str:
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, list):
        return clean_text(" ".join(str(item) for item in value if item not in (None, "")))
    return ""


def clean_text(value: str) -> str:
    value = unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def strip_html(value: str) -> str:
    value = re.sub(r"<\s*/\s*(tr|p|div|table)\s*>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<\s*/\s*(td|th)\s*>", " | ", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", " ", value)
    return clean_text(value)


def nearby_text(blocks: list[Any], index: int, direction: int, max_blocks: int = 3) -> str:
    texts: list[str] = []
    cursor = index + direction
    while 0 <= cursor < len(blocks) and len(texts) < max_blocks:
        block = blocks[cursor]
        if isinstance(block, dict) and block.get("type") == "text":
            text = clean_text(str(block.get("text") or ""))
            if len(text) >= 30:
                if direction < 0:
                    texts.insert(0, text)
                else:
                    texts.append(text)
        cursor += direction
    return clean_text(" ".join(texts))


def nearest_section(blocks: list[Any], index: int) -> str:
    for cursor in range(index - 1, -1, -1):
        block = blocks[cursor]
        if not isinstance(block, dict):
            continue
        if block.get("type") != "text":
            continue
        text = clean_text(str(block.get("text") or ""))
        level = block.get("text_level")
        if level == 1 or re.match(r"^\d+(?:\.\d+)*\s+\S+", text):
            return text
    return ""


def choose_visual_items(items: list[MinerUVisualItem], max_items: int) -> list[MinerUVisualItem]:
    scored = sorted(items, key=visual_score, reverse=True)
    return sorted(scored[:max_items], key=lambda item: item.index)


def visual_score(item: MinerUVisualItem) -> tuple[int, int, int]:
    text = f"{item.caption} {item.before} {item.after}".lower()
    score = 0
    if item.caption:
        score += 5
    if item.kind == "table":
        score += 4
    if re.search(r"\b(fig\.|figure|table)\s*\d+", text):
        score += 3
    if re.search(r"result|experiment|comparison|ablation|performance|accuracy|flow|curve|dataset|method|model", text):
        score += 2
    return (score, 1 if item.path else 0, -item.index)


def classify_visual_section(item: MinerUVisualItem) -> str:
    text = f"{item.caption} {item.section} {item.before} {item.after}".lower()
    if re.search(r"limitation|future work|failure|poor|weakness", text):
        return "局限与不足"
    if item.kind == "table" or re.search(
        r"result|experiment|comparison|ablation|performance|accuracy|dataset|percentile|curve|reduction|score|benchmark",
        text,
    ):
        return "关键实验与结果"
    if re.search(r"method|model|framework|architecture|pipeline|algorithm|module|overview|approach", text):
        return "核心方法"
    if re.search(r"motivation|problem|challenge|introduction|background", text):
        return "研究问题"
    return "关键实验与结果"


SECTION_ALIASES = {
    "研究问题": [
        "核心问题",
        "研究问题",
        "动机和思想",
        "基本信息",
    ],
    "核心方法": [
        "方法概述",
        "核心方法",
        "方法",
        "模型结构",
        "实验设置",
    ],
    "关键实验与结果": [
        "主要结果",
        "实验设置",
        "关键实验与结果",
        "实验结果",
        "结果分析",
        "贡献展示",
        "贡献",
    ],
    "局限与不足": [
        "局限与风险",
        "局限与不足",
        "局限",
        "不足",
        "未来工作",
    ],
}


SECTION_KEYWORDS = {
    "基本信息": ["title", "venue", "conference", "year", "paper", "作者", "标题", "会议", "年份"],
    "核心问题": [
        "problem",
        "challenge",
        "motivation",
        "background",
        "limitation of existing",
        "问题",
        "挑战",
        "动机",
        "背景",
    ],
    "动机和思想": ["motivation", "idea", "insight", "intuition", "思想", "动机", "直觉", "启发"],
    "方法概述": [
        "method",
        "model",
        "framework",
        "architecture",
        "pipeline",
        "algorithm",
        "module",
        "overview",
        "approach",
        "training",
        "inference",
        "prompt",
        "loss",
        "方法",
        "模型",
        "框架",
        "结构",
        "流程",
        "算法",
        "模块",
        "训练",
        "推理",
    ],
    "实验设置": [
        "dataset",
        "benchmark",
        "metric",
        "baseline",
        "setting",
        "protocol",
        "implementation",
        "数据集",
        "基准",
        "指标",
        "基线",
        "设置",
        "协议",
        "实现",
    ],
    "主要结果": [
        "result",
        "experiment",
        "comparison",
        "performance",
        "accuracy",
        "f1",
        "score",
        "benchmark",
        "ablation",
        "generalization",
        "结果",
        "实验",
        "性能",
        "准确率",
        "对比",
        "消融",
        "泛化",
    ],
    "贡献展示": ["contribution", "贡献", "propose", "introduce", "提出", "构建"],
    "局限与风险": [
        "limitation",
        "failure",
        "risk",
        "weakness",
        "future work",
        "局限",
        "不足",
        "风险",
        "失败",
        "未来",
    ],
    "可借鉴点": ["takeaway", "lesson", "insight", "future", "借鉴", "启示", "参考"],
}


def render_visual_markdown(items: list[MinerUVisualItem], heading: SummaryHeading | None = None) -> str:
    lines = [""]
    for item in items:
        label, number = display_visual_label(item, heading)
        alt = f"{label} {number}" if number else f"{label} {item.index}"
        caption = render_chinese_caption(item, label, number)
        lines.append('<p align="center">')
        lines.append(f'  <img src="{item.path}" alt="{alt}" />')
        lines.append("</p>")
        if caption:
            lines.append(f'<p align="center"><em>{caption}</em></p>')
        lines.append("")
    return "\n".join(lines).rstrip()


def display_visual_label(item: MinerUVisualItem, heading: SummaryHeading | None = None) -> tuple[str, str]:
    if heading is not None:
        heading_ref = extract_visual_ref_from_heading(heading.title)
        if heading_ref is not None:
            kind, number = heading_ref
            return ("Table" if kind == "table" else "Figure", number)
    label = "Table" if item.kind == "table" else "Figure"
    number = extract_visual_number(item.caption, label.lower()) or str(item.index)
    return label, number


def render_chinese_caption(item: MinerUVisualItem, label: str, number: str = "") -> str:
    prefix = "表" if label == "Table" else "图"
    number = number or extract_visual_number(item.caption, label.lower()) or str(item.index)
    caption = translate_caption_to_chinese(item.caption)
    parts = [f"{prefix} {number}"]
    if item.page:
        parts.append(f"第 {item.page} 页")
    if caption:
        parts.append(caption)
    return "，".join(parts)


def extract_visual_ref_from_heading(heading: str) -> tuple[str, str] | None:
    normalized = normalize_heading(heading)
    match = re.search(r"(表|table)([0-9]+)", normalized, flags=re.IGNORECASE)
    if match:
        return ("table", match.group(2))
    match = re.search(r"(图|figure|fig)([0-9]+)", normalized, flags=re.IGNORECASE)
    if match:
        return ("figure", match.group(2))
    return None


def translate_caption_to_chinese(caption: str) -> str:
    caption = clean_text(caption)
    caption = re.sub(r"^(table|figure|fig\.?)\s*\d+\s*[:.]\s*", "", caption, flags=re.IGNORECASE)
    replacements = [
        (r"Experimental results of (.+?) on (.+?) in terms of emotion classification accuracy", r"\1 在 \2 上的情绪分类准确率实验结果"),
        (r"Experimental results of (.+?) setting on multiple datasets in terms of emotion classification accuracy", r"\1 设置下多个数据集的情绪分类准确率实验结果"),
        (r"Ablation results of (.+?) and comparison with the vanilla CLIP", r"\1 的消融结果，以及与原始 CLIP 的对比"),
        (r"Ablation study of (.+?) setting in (.+?) task", r"\1 设置下 \2 任务的消融研究"),
        (r"Effectiveness of different fine-tuning strategies on the (.+?) task", r"不同微调策略在 \1 任务上的效果"),
        (r"Visualization results of (.+)", r"\1 的可视化结果"),
        (r"Overview of (.+)", r"\1 的整体框架"),
        (r"Comparison with (.+)", r"与 \1 的对比"),
    ]
    for pattern, replacement in replacements:
        new_caption = re.sub(pattern, replacement, caption, flags=re.IGNORECASE)
        if new_caption != caption:
            caption = new_caption
            break
    caption = caption.replace("DA", "领域自适应")
    caption = caption.replace("UC", "通用跨域")
    caption = caption.replace("UCDVER", "无监督跨域视觉情感识别")
    caption = caption.replace("state-of-the-art", "当前最优")
    caption = caption.replace("SOTA", "当前最优")
    caption = caption.replace("source domain", "源域")
    caption = caption.replace("target domain", "目标域")
    caption = caption.replace("classification accuracy", "分类准确率")
    caption = caption.replace("fine-tuning", "微调")
    caption = caption.replace("features-based", "基于特征")
    caption = caption.replace("prompt-based", "基于提示")
    return caption.strip()


def extract_existing_image_paths(markdown: str) -> set[str]:
    paths = set()
    for raw_path in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", markdown):
        paths.add(raw_path)
        paths.add(raw_path.replace("\\", "/"))
    return paths


def remove_related_visual_headings(markdown: str) -> str:
    return re.sub(r"^#{3,4}\s+相关图表\s*\n+", "", markdown, flags=re.MULTILINE)


def choose_summary_headings_for_visual(markdown: str, item: MinerUVisualItem) -> list[SummaryHeading]:
    numbered_headings = find_numbered_visual_headings(markdown, item)
    if numbered_headings:
        return numbered_headings

    headings = list_summary_headings(markdown)
    if not headings:
        return [SummaryHeading(2, classify_visual_section(item))]

    visual_text = visual_description_text(item)
    classified_section = classify_visual_section(item)
    best_heading = SummaryHeading(2, "", -1)
    best_score = -1
    for heading in headings:
        score = score_visual_section_match(visual_text, item, heading.title, classified_section)
        if score > best_score:
            best_score = score
            best_heading = heading

    if best_score > 0:
        return [best_heading]
    return [find_best_summary_heading(markdown, classified_section)]


def choose_summary_heading_for_visual(markdown: str, item: MinerUVisualItem) -> SummaryHeading:
    return choose_summary_headings_for_visual(markdown, item)[0]


def choose_summary_section_for_visual(markdown: str, item: MinerUVisualItem) -> str:
    return choose_summary_heading_for_visual(markdown, item).title


def find_numbered_visual_headings(markdown: str, item: MinerUVisualItem) -> list[SummaryHeading]:
    refs = visual_number_refs(item)
    if not refs:
        return []
    headings = list_summary_headings(markdown, min_level=2, max_level=4)
    matches: list[SummaryHeading] = []
    seen: set[tuple[int, str]] = set()
    for heading in headings:
        title = normalize_heading(heading.title)
        for kind, number in refs:
            if visual_ref_matches_heading(title, kind, number):
                key = (heading.level, heading.title)
                if key not in seen:
                    seen.add(key)
                    matches.append(heading)
    return matches


def find_numbered_visual_heading(markdown: str, item: MinerUVisualItem) -> SummaryHeading | None:
    headings = find_numbered_visual_headings(markdown, item)
    return headings[0] if headings else None


def visual_number_refs(item: MinerUVisualItem) -> list[tuple[str, str]]:
    text = item.caption or ""
    refs: list[tuple[str, str]] = []
    for match in re.finditer(r"\b(table|figure|fig\.?)\s*([0-9]+)\b", text, flags=re.IGNORECASE):
        kind = "table" if match.group(1).lower().startswith("table") else "figure"
        refs.append((kind, match.group(2)))
    seen: set[tuple[str, str]] = set()
    result = []
    for ref in refs:
        if ref in seen:
            continue
        seen.add(ref)
        result.append(ref)
    return result


def extract_visual_number(caption: str, expected_kind: str) -> str:
    kind_pattern = "table" if expected_kind == "table" else r"figure|fig\\.?"
    match = re.search(rf"\b(?:{kind_pattern})\s*([0-9]+)\b", caption or "", flags=re.IGNORECASE)
    return match.group(1) if match else ""


def visual_ref_matches_heading(normalized_heading: str, kind: str, number: str) -> bool:
    if kind == "table":
        patterns = [f"表{number}", f"table{number}"]
    else:
        patterns = [f"图{number}", f"figure{number}", f"fig{number}"]
    return any(pattern in normalized_heading for pattern in patterns)


def visual_description_text(item: MinerUVisualItem) -> str:
    return clean_text(
        " ".join(
            part
            for part in [
                item.caption,
                item.section,
                item.before,
                item.after,
                item.table_body,
                item.kind,
            ]
            if part
        )
    ).lower()


def score_visual_section_match(
    visual_text: str,
    item: MinerUVisualItem,
    heading: str,
    classified_section: str,
) -> int:
    normalized_heading = normalize_heading(heading)
    score = 0

    if headings_match_alias(heading, classified_section):
        score += 4

    if item.section and heading_text_overlaps(item.section, heading):
        score += 5

    for canonical, keywords in SECTION_KEYWORDS.items():
        if not headings_match_alias(heading, canonical):
            continue
        hits = sum(1 for keyword in keywords if keyword.lower() in visual_text)
        score += min(hits, 5) * 2

    if item.kind == "table" and headings_match_alias(heading, "主要结果"):
        score += 2
    if re.search(r"\b(table|benchmark|dataset|metric|baseline)\b|表|数据集|基准|指标|基线", visual_text) and headings_match_alias(heading, "实验设置"):
        score += 3
    if re.search(r"\b(ablation|result|performance|accuracy|f1|score|comparison)\b|消融|结果|性能|对比", visual_text) and headings_match_alias(heading, "主要结果"):
        score += 4
    if re.search(r"\b(method|framework|architecture|pipeline|module|algorithm)\b|方法|框架|结构|流程|模块", visual_text) and headings_match_alias(heading, "方法概述"):
        score += 4
    if re.search(r"\b(limitation|failure|future work|weakness|risk)\b|局限|不足|失败|未来|风险", visual_text) and headings_match_alias(heading, "局限与风险"):
        score += 4

    heading_terms = extract_heading_terms(heading)
    score += min(sum(1 for term in heading_terms if term and term in visual_text), 3)

    if normalized_heading in {"基本信息", "可借鉴点"} and score <= 2:
        score -= 2
    return score


def headings_match_alias(heading: str, canonical: str) -> bool:
    normalized_heading = normalize_heading(heading)
    aliases = SECTION_ALIASES.get(canonical, [canonical])
    aliases = aliases + [canonical]
    for alias in aliases:
        normalized_alias = normalize_heading(alias)
        if normalized_heading == normalized_alias or normalized_alias in normalized_heading or normalized_heading in normalized_alias:
            return True
    return False


def heading_text_overlaps(source_heading: str, summary_heading: str) -> bool:
    source_terms = set(extract_heading_terms(source_heading))
    summary_terms = set(extract_heading_terms(summary_heading))
    return bool(source_terms and summary_terms and source_terms & summary_terms)


def extract_heading_terms(value: str) -> list[str]:
    normalized = normalize_heading(value)
    terms = re.findall(r"[a-zA-Z]{4,}|[\u4e00-\u9fff]{2,}", normalized)
    return [term.lower() for term in terms]


def find_best_summary_heading(markdown: str, target_section: str) -> SummaryHeading:
    headings = list_summary_headings(markdown)
    if not headings:
        return SummaryHeading(2, target_section, -1)

    aliases = SECTION_ALIASES.get(target_section, [target_section])
    normalized_aliases = [normalize_heading(alias) for alias in aliases]
    for alias in normalized_aliases:
        for heading in headings:
            normalized_heading = normalize_heading(heading.title)
            if normalized_heading == alias or alias in normalized_heading or normalized_heading in alias:
                return heading

    return headings[-1]


def find_best_summary_section(markdown: str, target_section: str) -> str:
    return find_best_summary_heading(markdown, target_section).title


def list_summary_headings(markdown: str, min_level: int = 2, max_level: int = 2) -> list[SummaryHeading]:
    headings: list[SummaryHeading] = []
    for match in re.finditer(r"^(#{2,4})\s+(.+?)\s*$", markdown, flags=re.MULTILINE):
        level = len(match.group(1))
        if level < min_level or level > max_level:
            continue
        heading = match.group(1).strip()
        heading = match.group(2).strip()
        if heading and normalize_heading(heading) != "相关图表":
            headings.append(SummaryHeading(level, heading, match.start()))
    return headings


def normalize_heading(value: str) -> str:
    value = re.sub(r"^[#\s]+", "", value)
    value = re.sub(r"^\d+(?:\.\d+)*\.?\s*", "", value)
    value = re.sub(r"[：:()\[\]【】\-—_\s]+", "", value)
    return value.strip().lower()


def insert_block_under_existing_heading(markdown: str, heading: SummaryHeading, block: str) -> str:
    marker = "#" * heading.level
    pattern = re.compile(rf"(^{re.escape(marker)}\s+{re.escape(heading.title)}\s*$)", flags=re.MULTILINE)
    match = pattern.search(markdown)
    if not match:
        fallback_heading = find_best_summary_heading(markdown, heading.title)
        if fallback_heading.title != heading.title or fallback_heading.level != heading.level:
            return insert_block_under_existing_heading(markdown, fallback_heading, block)
        return markdown.rstrip() + f"\n\n## {heading.title}\n{block}\n"

    insert_at = match.end()
    return markdown[:insert_at].rstrip() + "\n" + block + "\n\n" + markdown[insert_at:].lstrip()


def insert_block_under_existing_section(markdown: str, section: str, block: str) -> str:
    return insert_block_under_existing_heading(markdown, SummaryHeading(2, section, -1), block)


def truncate(text: str, max_chars: int) -> str:
    text = clean_text(text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."

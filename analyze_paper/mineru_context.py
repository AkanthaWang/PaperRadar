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

    existing_paths = set(re.findall(r"!\[[^\]]*\]\(([^)]+)\)", markdown))
    grouped: dict[str, list[MinerUVisualItem]] = {}
    for item in choose_visual_items(items, max_items=max_items):
        if not item.path or item.path in existing_paths:
            continue
        grouped.setdefault(classify_visual_section(item), []).append(item)

    result = markdown.rstrip()
    for section, section_items in grouped.items():
        block = render_visual_markdown(section_items)
        result = insert_block_under_section(result, section, block)
    return result + "\n"


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


def render_visual_markdown(items: list[MinerUVisualItem]) -> str:
    lines = ["", "### 相关图表", ""]
    for item in items:
        label = "Table" if item.kind == "table" else "Figure"
        alt = f"{label} {item.index}"
        lines.append(f"![{alt}]({item.path})")
        detail_parts = [f"{label} {item.index}"]
        if item.page:
            detail_parts.append(f"page {item.page}")
        if item.caption:
            detail_parts.append(item.caption)
        lines.append(f"*{'，'.join(detail_parts)}*")
        lines.append("")
    return "\n".join(lines).rstrip()


def insert_block_under_section(markdown: str, section: str, block: str) -> str:
    pattern = re.compile(rf"(^##\s+{re.escape(section)}\s*$)", flags=re.MULTILINE)
    match = pattern.search(markdown)
    if not match:
        return markdown.rstrip() + f"\n\n## {section}\n{block}\n"

    next_match = re.search(r"^##\s+", markdown[match.end() :], flags=re.MULTILINE)
    insert_at = len(markdown) if next_match is None else match.end() + next_match.start()
    return markdown[:insert_at].rstrip() + "\n" + block + "\n\n" + markdown[insert_at:].lstrip()


def truncate(text: str, max_chars: int) -> str:
    text = clean_text(text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from src.paper_summarizer.pdf_parser import safe_stem_for_path
from src.paper_summarizer.prompts import (
    MARKDOWN_SYSTEM_PROMPT,
    build_markdown_chunk_prompt,
    build_markdown_reduce_prompt,
    build_markdown_summary_prompt,
)


CACHE_STEM_MAX_CHARS = 72
MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s+\S+")
PLAIN_SECTION_HEADING_RE = re.compile(
    r"^(?:"
    r"abstract|references|acknowledg(?:e)?ments?|appendix(?:\s+[A-Z0-9.]+)?|"
    r"\d+(?:\.\d+)*\.?\s+[A-Z][^\n]{0,120}"
    r")$",
    flags=re.IGNORECASE,
)


def is_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def iter_progress(items, label: str):
    try:
        from tqdm import tqdm
    except ImportError:
        return items
    return tqdm(items, desc=label, unit="paper")


def collect_pdfs(settings, pdf: str | None, limit: int | None) -> list[Path | str]:
    if pdf:
        if is_url(pdf):
            return [pdf]
        path = Path(pdf)
        if not path.is_absolute():
            path = settings.project_root / path
        pdfs: list[Path | str] = [path.resolve()]
    else:
        pdfs = sorted(settings.downloads_dir.glob("*.pdf"))

    pdfs = [path for path in pdfs if isinstance(path, str) or (path.exists() and path.suffix.lower() == ".pdf")]
    if limit is not None:
        pdfs = pdfs[:limit]
    return pdfs


def safe_stem_for_source(source: Path | str) -> str:
    if isinstance(source, Path):
        return safe_stem_for_path(source)
    name = source.rstrip("/").split("/")[-1].split("?")[0] or "paper"
    return safe_stem_for_path(Path(name))


def cache_stem_for_source(source: Path | str, max_chars: int = CACHE_STEM_MAX_CHARS) -> str:
    return shorten_cache_stem(safe_stem_for_source(source), max_chars=max_chars)


def shorten_cache_stem(stem: str, max_chars: int = CACHE_STEM_MAX_CHARS) -> str:
    stem = re.sub(r'[\\/:*?"<>|]+', "_", stem)
    stem = re.sub(r"\s+", "_", stem).strip("._- ")
    stem = stem or "paper"
    if len(stem) <= max_chars:
        return stem

    digest = hashlib.sha1(stem.encode("utf-8")).hexdigest()[:10]
    budget = max(12, max_chars - len(digest) - 1)
    prefix_match = re.match(r"^(20\d{2}_[^_]+_)(.+)$", stem)
    if prefix_match and len(prefix_match.group(1)) < budget:
        prefix = prefix_match.group(1)
        body_budget = budget - len(prefix)
        short = prefix + prefix_match.group(2)[:body_budget].rstrip("._- ")
    else:
        short = stem[:budget].rstrip("._- ")
    return f"{short}-{digest}"


def split_text(text: str, chunk_chars: int, max_chunks: int) -> list[str]:
    chunk_chars = max(1000, chunk_chars)
    max_chunks = max(1, max_chunks)
    sections = split_markdown_sections(text)

    chunks: list[str] = []
    current = ""
    for section in sections:
        section_parts = split_long_section(section, chunk_chars)
        for part in section_parts:
            if not current:
                current = part
                continue
            candidate = f"{current.rstrip()}\n\n{part.lstrip()}"
            if len(candidate) <= chunk_chars:
                current = candidate
            else:
                chunks.append(current)
                current = part

    if current:
        chunks.append(current)

    return limit_chunks(chunks, max_chunks)


def split_markdown_sections(text: str) -> list[str]:
    lines = text.splitlines()
    if not lines:
        return []

    sections: list[list[str]] = []
    current: list[str] = []
    skip_current = False
    in_fence = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence

        prev_blank = index == 0 or not lines[index - 1].strip()
        is_heading = not in_fence and is_section_heading_line(line, prev_blank)
        if is_heading and current:
            if not skip_current:
                sections.append(current)
            current = [line]
            skip_current = is_skippable_section_heading(line)
        else:
            current.append(line)
            if index == 0 and is_heading:
                skip_current = is_skippable_section_heading(line)

    if current and not skip_current:
        sections.append(current)

    return [normalize_section_lines(section) for section in sections if normalize_section_lines(section)]


def is_section_heading_line(line: str, prev_blank: bool) -> bool:
    stripped = line.strip()
    if MARKDOWN_HEADING_RE.match(stripped):
        return True
    if not prev_blank:
        return False
    if len(stripped) > 140:
        return False
    return PLAIN_SECTION_HEADING_RE.match(stripped) is not None


def is_skippable_section_heading(line: str) -> bool:
    text = line.strip().lstrip("#").strip().lower()
    text = re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", text)
    return text in {"references", "bibliography"}


def normalize_section_lines(lines: list[str]) -> str:
    return "\n".join(lines).strip()


def split_long_section(section: str, chunk_chars: int) -> list[str]:
    if len(section) <= chunk_chars:
        return [section]

    heading, body = extract_section_heading(section)
    prefix = f"{heading}\n\n" if heading else ""
    continued_prefix = f"{heading}\n\n[Section continued]\n\n" if heading else ""
    first_budget = max(500, chunk_chars - len(prefix))
    continued_budget = max(500, chunk_chars - len(continued_prefix))

    parts: list[str] = []
    current = ""
    budget = first_budget
    for paragraph in split_paragraphs(body or section):
        candidate = paragraph if not current else f"{current.rstrip()}\n\n{paragraph.lstrip()}"
        if len(candidate) <= budget:
            current = candidate
            continue

        if current:
            parts.append(current)
            current = ""
            budget = continued_budget

        if len(paragraph) > budget:
            hard_parts = hard_split_text(paragraph, budget, continued_budget)
            parts.extend(hard_parts[:-1])
            current = hard_parts[-1] if hard_parts else ""
            budget = continued_budget
        else:
            current = paragraph

    if current:
        parts.append(current)

    result: list[str] = []
    for index, part in enumerate(parts):
        part_prefix = prefix if index == 0 else continued_prefix
        result.append(f"{part_prefix}{part}".strip())
    return result


def extract_section_heading(section: str) -> tuple[str, str]:
    lines = section.splitlines()
    if not lines:
        return "", ""
    first = lines[0].strip()
    if is_section_heading_line(first, prev_blank=True):
        return first, "\n".join(lines[1:]).strip()
    return "", section


def split_paragraphs(text: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    return paragraphs or ([text.strip()] if text.strip() else [])


def hard_split_text(text: str, first_max_chars: int, next_max_chars: int | None = None) -> list[str]:
    chunks: list[str] = []
    start = 0
    next_max_chars = next_max_chars or first_max_chars
    while start < len(text):
        max_chars = first_max_chars if not chunks else next_max_chars
        overlap = min(600, max_chars // 12)
        end = min(start + max_chars, len(text))
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return [chunk for chunk in chunks if chunk]


def limit_chunks(chunks: list[str], max_chunks: int) -> list[str]:
    chunks = [chunk for chunk in chunks if chunk.strip()]
    if len(chunks) <= max_chunks:
        return chunks
    return chunks[:max_chunks]


def generate_markdown_summary_with_llm(source_name: str, markdown: str, visual_context: str, client, settings) -> str:
    summary_max_chars = min(settings.max_chars, settings.summary_max_chars)
    effective_length = len(markdown) + len(visual_context)
    if effective_length <= summary_max_chars:
        prompt = build_markdown_summary_prompt(source_name, markdown, summary_max_chars, visual_context)
        return client.complete(prompt, MARKDOWN_SYSTEM_PROMPT)

    chunks = split_text(markdown, settings.summary_chunk_chars, settings.max_chunks)
    chunk_summaries: list[str] = []
    total = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        prompt = build_markdown_chunk_prompt(source_name, chunk, index, total)
        chunk_summaries.append(client.complete(prompt, MARKDOWN_SYSTEM_PROMPT))
    return client.complete(build_markdown_reduce_prompt(source_name, chunk_summaries), MARKDOWN_SYSTEM_PROMPT)


def build_fallback_summary(source_name: str, markdown: str, raw_markdown_path: Path, visuals_path: Path, error: str) -> str:
    title = extract_markdown_title(markdown) or source_name
    abstract = extract_named_section(markdown, "abstract", max_chars=1400)
    headings = extract_markdown_headings(markdown, max_items=24)
    first_lines = extract_leading_text(markdown, max_chars=1000)

    heading_lines = "\n".join(f"- {heading}" for heading in headings) if headings else "- 未识别到明显章节标题"
    abstract_text = abstract or first_lines or "LLM 总结失败，当前文件仅保留 MinerU 原始解析线索。"
    return f"""# 论文总结

> LLM 总结失败，已生成 fallback 报告：`{error}`
>
> MinerU Markdown：`{raw_markdown_path}`
>
> MinerU visual JSON：`{visuals_path}`

## 基本信息
- 标题：{title}
- 状态：请修复模型额度或 token 限制后，使用 `--overwrite` 重新生成总结。

## 摘要线索
{abstract_text}

## MinerU 章节线索
{heading_lines}
"""


def extract_markdown_title(markdown: str) -> str:
    for line in markdown.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line.lstrip("#").strip()
    return ""


def extract_markdown_headings(markdown: str, max_items: int) -> list[str]:
    headings: list[str] = []
    for line in markdown.splitlines():
        line = line.strip()
        if re.match(r"^#{1,4}\s+\S+", line):
            headings.append(line)
        if len(headings) >= max_items:
            break
    return headings


def extract_named_section(markdown: str, name: str, max_chars: int) -> str:
    lines = markdown.splitlines()
    start = None
    for index, line in enumerate(lines):
        clean = line.strip().strip("#").strip().lower()
        if clean == name.lower():
            start = index + 1
            break
    if start is None:
        return ""

    collected: list[str] = []
    for line in lines[start:]:
        if line.startswith("#") and collected:
            break
        stripped = line.strip()
        if stripped:
            collected.append(stripped)
        if len(" ".join(collected)) >= max_chars:
            break
    return truncate_plain_text(" ".join(collected), max_chars)


def extract_leading_text(markdown: str, max_chars: int) -> str:
    parts: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("!") or stripped.startswith("<"):
            continue
        parts.append(stripped)
        if len(" ".join(parts)) >= max_chars:
            break
    return truncate_plain_text(" ".join(parts), max_chars)


def truncate_plain_text(text: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."

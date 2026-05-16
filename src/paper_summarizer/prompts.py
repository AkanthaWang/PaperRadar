from __future__ import annotations

from src.config import PROJECT_ROOT


PROMPT_DIR = PROJECT_ROOT / "config" / "prompts"


def load_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8").strip()


MARKDOWN_SYSTEM_PROMPT = load_prompt("markdown_system_prompt.md")
SYSTEM_PROMPT = load_prompt("system_prompt.md")


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    head = int(max_chars * 0.68)
    tail = max_chars - head
    return text[:head] + "\n\n[...中间内容已截断...]\n\n" + text[-tail:]


def build_markdown_summary_prompt(source_name: str, markdown: str, max_chars: int, visual_context: str = "") -> str:
    return load_prompt("markdown_summary_prompt.md").format(
        source_name=source_name,
        content=truncate_text(markdown, max_chars),
        visual_context=visual_context or "无额外图表上下文。",
    )


def build_markdown_chunk_prompt(source_name: str, chunk: str, index: int, total: int) -> str:
    return load_prompt("markdown_chunk_prompt.md").format(
        source_name=source_name,
        chunk=chunk,
        index=index,
        total=total,
    )


def build_markdown_reduce_prompt(source_name: str, chunk_summaries: list[str]) -> str:
    merged = "\n\n".join(
        f"### 分片 {index}\n{summary}" for index, summary in enumerate(chunk_summaries, start=1)
    )
    return load_prompt("markdown_reduce_prompt.md").format(source_name=source_name, merged=merged)

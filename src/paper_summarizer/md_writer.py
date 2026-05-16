from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from src.paper_summarizer.pdf_parser import FigureInfo, ParsedPaper


def strip_leading_h1(markdown: str) -> str:
    lines = markdown.strip().splitlines()
    if lines and lines[0].startswith("# "):
        return "\n".join(lines[1:]).lstrip()
    return markdown.strip()


def rel_path(target: str | Path, base_dir: str | Path) -> str:
    return Path(os.path.relpath(Path(target), Path(base_dir))).as_posix()


def render_figures(figures: list[FigureInfo], output_path: Path) -> str:
    if not figures:
        return "## 论文原图\n\n未抽取到可用原图。\n"

    lines = ["## 论文原图", ""]
    for index, figure in enumerate(figures, start=1):
        relative = rel_path(figure.path, output_path.parent)
        lines.append(f"![Figure {index}]({relative})")
        lines.append("")
        detail = f"页码：{figure.page}，尺寸：{figure.width}x{figure.height}"
        if figure.caption:
            detail += f"。上下文：{figure.caption}"
        lines.append(detail)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_report(parsed: ParsedPaper, llm_markdown: str, output_path: Path) -> str:
    title = parsed.title or Path(parsed.pdf_path).stem
    venue_year = " ".join(part for part in [parsed.venue, parsed.year] if part) or "未知"
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = strip_leading_h1(llm_markdown)

    header = f"""# {title}

> 文件：`{parsed.pdf_path}`  
> 会议/年份：{venue_year}  
> 页数：{parsed.page_count}  
> 生成时间：{generated_at}

"""
    figures = render_figures(parsed.figures, output_path)
    return header + body.rstrip() + "\n\n" + figures


def write_report(parsed: ParsedPaper, llm_markdown: str, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_report(parsed, llm_markdown, output_path), encoding="utf-8")
    return output_path


def render_no_api_report(parsed: ParsedPaper) -> str:
    sample = parsed.full_text[:1200].replace("\n", " ")
    return f"""## 一句话总结

未调用 API；这里只生成 PDF 解析验证版报告。

## 核心问题

未调用 API，暂未生成。

## 核心动机

未调用 API，暂未生成。

## 数据集

未调用 API，暂未生成。

## 方法

未调用 API，暂未生成。

## 实验

未调用 API，暂未生成。

## 主要贡献

未调用 API，暂未生成。

## 适合引用的观点

未调用 API，暂未生成。

## 可能的局限

未调用 API，暂未生成。

## 后续可关注问题

未调用 API，暂未生成。

## 解析预览

{sample}
"""

from __future__ import annotations

from typing import Iterable

from .pdf_parser import FigureInfo, ParsedPaper


SYSTEM_PROMPT = """你是严谨的论文阅读助手。你的任务是基于论文内容生成中文结构化总结。
只能使用输入材料中能支持的信息；不要编造论文没有出现的结论、实验结果或数值。
输出必须是中文 Markdown，不要用代码块包裹最终答案。"""


MARKDOWN_SYSTEM_PROMPT = """你是严谨的论文阅读助手。你的任务是基于 MinerU 从 PDF 解析出的 Markdown 生成中文论文总结。
只能使用输入 Markdown 中能支持的信息；不要编造论文没有出现的结论、实验结果或数值。
输出必须是中文 Markdown，不要用代码块包裹最终答案。"""


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    head = int(max_chars * 0.68)
    tail = max_chars - head
    return text[:head] + "\n\n[...中间内容已截断...]\n\n" + text[-tail:]


def figure_notes(figures: Iterable[FigureInfo]) -> str:
    lines: list[str] = []
    for index, figure in enumerate(figures, start=1):
        note = figure.caption or figure.context or "无可用说明"
        lines.append(
            f"- Figure {index}: page={figure.page}, size={figure.width}x{figure.height}, context={note}"
        )
    return "\n".join(lines) if lines else "未提取到图片。"


def build_paper_context(parsed: ParsedPaper, max_chars: int) -> str:
    text = truncate_text(parsed.full_text, max_chars)
    venue_year = " ".join(part for part in [parsed.venue, parsed.year] if part) or "未知"
    return f"""论文文件：{parsed.pdf_path}
标题：{parsed.title}
会议/年份：{venue_year}
页数：{parsed.page_count}

图片信息：
{figure_notes(parsed.figures)}

论文文本：
{text}
"""


def build_final_prompt(parsed: ParsedPaper, max_chars: int) -> str:
    context = build_paper_context(parsed, max_chars)
    return f"""{context}

请基于以上论文内容生成结构化中文 Markdown。

请按以下结构输出：

# 论文总结

## 基本信息
- 标题：
- 作者/机构：
- 会议或年份：

## 一句话概括

## 研究问题

## 核心方法

## 关键实验与结果

## 主要贡献

## 局限与不足

## 可复现信息

## 适合引用的结论

要求：
- 保留关键英文术语、方法名、数据集名和指标名。
- 结果中如果有具体数值，请优先列出；没有则写“原文未明确给出”。
- 不要复述整篇论文，重点总结创新点、方法逻辑和实验结论。
- 如果某一项在论文文本中找不到可靠信息，请写“原文未明确给出”。
"""


def split_text(text: str, chunk_chars: int, max_chunks: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    overlap = min(1200, chunk_chars // 10)
    while start < len(text) and len(chunks) < max_chunks:
        end = min(start + chunk_chars, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def build_chunk_prompt(parsed: ParsedPaper, chunk: str, index: int, total: int) -> str:
    return f"""下面是论文《{parsed.title}》的文本片段 {index}/{total}。
请把这个片段整理成中文阅读笔记，供后续合并成完整论文总结。

请提取：
- 论文主题、问题定义或动机
- 方法模块、模型结构、训练或推理流程
- 数据集、实验设置、指标和关键结果
- 消融实验、对比实验和作者结论
- 局限、不足或未来工作

只总结本片段明确出现的信息，不要补全或猜测。

文本片段：

{chunk}
"""


def build_reduce_prompt(parsed: ParsedPaper, chunk_summaries: list[str]) -> str:
    merged = "\n\n".join(
        f"### 片段 {index}\n{summary}" for index, summary in enumerate(chunk_summaries, start=1)
    )
    return f"""下面是论文《{parsed.title}》按片段得到的中文阅读笔记。请合并为最终结构化中文 Markdown 总结。

请按以下结构输出：

# 论文总结

## 基本信息
- 标题：
- 作者/机构：
- 会议或年份：

## 一句话概括

## 研究问题

## 核心方法

## 关键实验与结果

## 主要贡献

## 局限与不足

## 可复现信息

## 适合引用的结论

要求：
- 去重合并，不要按片段机械罗列。
- 保留关键英文术语、方法名、数据集名和指标名。
- 结果中如果有具体数值，请优先列出；没有则写“原文未明确给出”。
- 只使用阅读笔记中能支持的信息，不要补编。

阅读笔记：

{merged}
"""


def build_markdown_summary_prompt(source_name: str, markdown: str, max_chars: int) -> str:
    content = truncate_text(markdown, max_chars)
    return f"""下面是论文 `{source_name}` 经过 MinerU 解析得到的 Markdown。请基于这些内容生成结构化中文总结。

请按以下结构输出：

# 论文总结

## 基本信息
- 标题：
- 作者/机构：
- 会议或年份：

## 一句话概括

## 研究问题

## 核心方法

## 关键实验与结果

## 主要贡献

## 局限与不足

## 可复现信息

## 适合引用的结论

要求：
- 保留关键英文术语、方法名、数据集名和指标名。
- 结果中如果有具体数值，请优先列出；没有则写“原文未明确给出”。
- 不要复述整篇论文，重点总结创新点、方法逻辑和实验结论。
- 如果某一项在 Markdown 中找不到可靠信息，请写“原文未明确给出”。

MinerU Markdown：

{content}
"""


def build_markdown_chunk_prompt(source_name: str, chunk: str, index: int, total: int) -> str:
    return f"""下面是论文 `{source_name}` 的 MinerU Markdown 片段 {index}/{total}。
请把这个片段整理成中文阅读笔记，供后续合并成完整论文总结。

请提取：
- 论文主题、问题定义或动机
- 方法模块、模型结构、训练或推理流程
- 数据集、实验设置、指标和关键结果
- 消融实验、对比实验和作者结论
- 局限、不足或未来工作

只总结本片段明确出现的信息，不要补全或猜测。

Markdown 片段：

{chunk}
"""


def build_markdown_reduce_prompt(source_name: str, chunk_summaries: list[str]) -> str:
    merged = "\n\n".join(
        f"### 片段 {index}\n{summary}" for index, summary in enumerate(chunk_summaries, start=1)
    )
    return f"""下面是论文 `{source_name}` 按 MinerU Markdown 片段得到的中文阅读笔记。请合并为最终结构化中文 Markdown 总结。

请按以下结构输出：

# 论文总结

## 基本信息
- 标题：
- 作者/机构：
- 会议或年份：

## 一句话概括

## 研究问题

## 核心方法

## 关键实验与结果

## 主要贡献

## 局限与不足

## 可复现信息

## 适合引用的结论

要求：
- 去重合并，不要按片段机械罗列。
- 保留关键英文术语、方法名、数据集名和指标名。
- 结果中如果有具体数值，请优先列出；没有则写“原文未明确给出”。
- 只使用阅读笔记中能支持的信息，不要补编。

阅读笔记：

{merged}
"""

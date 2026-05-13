from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from analyze_paper.config import AnalyzerSettings, PROJECT_ROOT, resolve_path
from analyze_paper.llm_client import ECNULMClient, LLMClient, create_llm_client
from analyze_paper.mineru_context import (
    insert_visuals_into_summary,
    load_visual_items,
    render_visual_context,
)
from analyze_paper.mineru_client import MinerUClient
from analyze_paper.md_writer import render_no_api_report, write_report
from analyze_paper.pdf_parser import ParsedPaper, parse_pdf, safe_stem_for_path
from analyze_paper.prompts import (
    MARKDOWN_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_markdown_chunk_prompt,
    build_markdown_reduce_prompt,
    build_markdown_summary_prompt,
    build_chunk_prompt,
    build_final_prompt,
    build_reduce_prompt,
    split_text,
)


def is_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def iter_progress(items: list[Path], label: str):
    try:
        from tqdm import tqdm
    except ImportError:
        return items
    return tqdm(items, desc=label, unit="paper")


def collect_pdfs(settings: AnalyzerSettings, pdf: str | None, limit: int | None) -> list[Path | str]:
    if pdf:
        if is_url(pdf):
            return [pdf]
        path = Path(pdf)
        if not path.is_absolute():
            path = settings.project_root / path
        pdfs = [path.resolve()]
    else:
        pdfs = sorted(settings.downloads_dir.glob("*.pdf"))

    pdfs = [path for path in pdfs if path.exists() and path.suffix.lower() == ".pdf"]
    if limit is not None:
        pdfs = pdfs[:limit]
    return pdfs


def safe_stem_for_source(source: Path | str) -> str:
    if isinstance(source, Path):
        return safe_stem_for_path(source)
    name = source.rstrip("/").split("/")[-1].split("?")[0] or "paper"
    return safe_stem_for_path(Path(name))


def short_asset_dir_for_source(settings: AnalyzerSettings, source: Path | str, stem: str) -> Path:
    digest = hashlib.sha1(str(source).encode("utf-8")).hexdigest()[:10]
    prefix = stem[:60].strip(" ._") or "paper"
    return settings.assets_dir / f"{prefix}_{digest}"


def write_cache(cache_path: Path, parsed: ParsedPaper, output_path: Path, status: str, error: str | None = None) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "error": error,
        "output_path": str(output_path),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "paper": parsed.to_dict(),
    }
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def generate_with_llm(
    parsed: ParsedPaper,
    client: LLMClient,
    settings: AnalyzerSettings,
) -> str:
    if len(parsed.full_text) <= settings.max_chars:
        return client.complete(build_final_prompt(parsed, settings.max_chars), SYSTEM_PROMPT)

    chunks = split_text(parsed.full_text, settings.chunk_chars, settings.max_chunks)
    chunk_summaries: list[str] = []
    total = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        prompt = build_chunk_prompt(parsed, chunk, index, total)
        chunk_summaries.append(client.complete(prompt, SYSTEM_PROMPT))
    return client.complete(build_reduce_prompt(parsed, chunk_summaries), SYSTEM_PROMPT)


def generate_markdown_summary_with_llm(
    source_name: str,
    markdown: str,
    visual_context: str,
    client: LLMClient,
    settings: AnalyzerSettings,
) -> str:
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
    reduce_prompt = build_markdown_reduce_prompt(source_name, chunk_summaries)
    return client.complete(reduce_prompt, MARKDOWN_SYSTEM_PROMPT)


def build_fallback_summary(
    source_name: str,
    markdown: str,
    raw_markdown_path: Path,
    visuals_path: Path,
    error: str,
) -> str:
    title = extract_markdown_title(markdown) or source_name
    abstract = extract_named_section(markdown, "abstract", max_chars=1400)
    headings = extract_markdown_headings(markdown, max_items=24)
    first_lines = extract_leading_text(markdown, max_chars=1000)

    heading_lines = "\n".join(f"- {heading}" for heading in headings) if headings else "- 原文未明确提取到章节标题"
    abstract_text = abstract or first_lines or "原文未明确给出"

    return f"""# 论文总结

> 自动降级生成：MinerU 解析已成功，但大模型总结失败。失败原因：`{error}`
>  
> 原始解析 Markdown：`{raw_markdown_path}`
>  
> MinerU 图表 JSON：`{visuals_path}`

## 基本信息
- 标题：{title}
- 总结状态：LLM 总结失败，当前文件由本地 fallback 逻辑生成。
- 建议：额度或 token 限制恢复后，使用 `--reuse-mineru --overwrite` 重新生成精总结。

## 一句话概括
{abstract_text}

## 研究问题
原文相关内容请优先查看 MinerU 原始 Markdown 的 Abstract、Introduction 和 Problem/Background 相关章节。

## 核心方法
当前未调用大模型抽取方法细节。请参考下方“MinerU 章节概览”和原始 Markdown 中 Method、Approach、Framework、Experiment 等章节。

## 关键实验与结果
当前未调用大模型抽取实验结论。程序会根据 MinerU JSON 将关键图表插入本节，便于先定位实验表格、结果曲线和对比图。

## 主要贡献
当前未调用大模型抽取贡献点。可在原始 Markdown 中检索 `contribution`、`we propose`、`in summary`、`experiment` 等关键词。

## 局限与不足
当前未调用大模型抽取局限。可在原始 Markdown 中检索 `limitation`、`future work`、`fail`、`weakness` 等关键词。

## 可复现信息
当前未调用大模型抽取复现细节。可先检查原始 Markdown 中是否包含数据集、代码链接、实验设置、超参数和评测指标。

## 适合引用的结论
当前未调用大模型生成引用结论。请以原始 Markdown 和论文原文为准。

## MinerU 章节概览
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


def analyze_one(
    pdf_path: Path | str,
    settings: AnalyzerSettings,
    client: LLMClient | None,
    mineru_client: MinerUClient | None,
    overwrite: bool,
    no_api: bool,
    parser_name: str,
    reuse_mineru: bool = False,
) -> Path | None:
    stem = safe_stem_for_source(pdf_path)
    output_path = settings.outputs_dir / f"{stem}.md"
    raw_markdown_path = settings.outputs_dir / f"{stem}.mineru.md"
    visuals_path = settings.outputs_dir / f"{stem}.mineru.visuals.json"
    cache_path = settings.cache_dir / f"{stem}.json"
    mineru_output_dir = short_asset_dir_for_source(settings, pdf_path, stem)

    if output_path.exists() and not overwrite:
        print(f"Skip existing report: {output_path}")
        return output_path

    if parser_name == "mineru":
        if mineru_client is None:
            raise RuntimeError("MinerU client is not initialized.")
        if reuse_mineru and raw_markdown_path.exists():
            existing_dirs = sorted(
                [path for path in mineru_output_dir.iterdir() if path.is_dir()],
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            ) if mineru_output_dir.exists() else []
            if not existing_dirs:
                raise RuntimeError(f"Cannot reuse MinerU result; no extracted output found under {mineru_output_dir}")
            print(f"Reuse MinerU Markdown: {raw_markdown_path}")
            result_markdown = raw_markdown_path.read_text(encoding="utf-8")
            result_output_dir = existing_dirs[0]
            result_task_id = result_output_dir.name
            result_raw = {"reused": True, "task_id": result_task_id}
        else:
            print(f"Parse PDF with MinerU: {pdf_path}")
            result = mineru_client.parse_pdf(pdf_path, mineru_output_dir, overwrite=overwrite)
            result_markdown = result.markdown
            result_output_dir = result.output_dir
            result_task_id = result.task_id
            result_raw = result.raw_result
        raw_markdown_path.parent.mkdir(parents=True, exist_ok=True)
        raw_markdown_path.write_text(result_markdown, encoding="utf-8")
        visual_items = load_visual_items(result_output_dir, raw_markdown_path.parent)
        visual_context = render_visual_context(visual_items)
        visuals_path.write_text(
            json.dumps([item.to_dict() for item in visual_items], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        summary_status = "skipped"
        if no_api:
            output_for_cache = raw_markdown_path
            print(f"Wrote MinerU raw Markdown: {raw_markdown_path}")
        else:
            if client is None:
                raise RuntimeError("LLM client is not initialized.")
            print("Summarize MinerU Markdown with LLM")
            llm_error = ""
            try:
                summary_markdown = generate_markdown_summary_with_llm(
                    stem,
                    result_markdown,
                    visual_context,
                    client,
                    settings,
                )
            except Exception as exc:
                llm_error = str(exc)
                print(f"LLM summary failed; writing fallback Markdown: {llm_error}")
                summary_markdown = build_fallback_summary(
                    stem,
                    result_markdown,
                    raw_markdown_path,
                    visuals_path,
                    llm_error,
                )
            summary_markdown = insert_visuals_into_summary(summary_markdown, visual_items)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(summary_markdown, encoding="utf-8")
            output_for_cache = output_path
            summary_status = "fallback" if llm_error else "ok"
            print(f"Wrote summary Markdown: {output_path}")

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {
                    "status": "ok",
                    "parser": "mineru",
                    "summary_status": summary_status,
                    "summary_error": llm_error if summary_status == "fallback" else "",
                    "task_id": result_task_id,
                    "output_path": str(output_for_cache),
                    "summary_output_path": str(output_path) if summary_status == "ok" else "",
                    "raw_markdown_path": str(raw_markdown_path),
                    "visuals_path": str(visuals_path),
                    "visual_count": len(visual_items),
                    "mineru_output_dir": str(result_output_dir),
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                    "result": result_raw,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return output_for_cache

    if not isinstance(pdf_path, Path):
        raise RuntimeError("Local parser only supports local PDF files. Use --parser mineru for URL input.")

    print(f"Parse PDF: {pdf_path.name}")
    parsed = parse_pdf(pdf_path, settings.assets_dir, max_images=settings.max_images)

    try:
        if no_api:
            markdown = render_no_api_report(parsed)
        else:
            if client is None:
                raise RuntimeError("LLM client is not initialized.")
            markdown = generate_with_llm(parsed, client, settings)

        write_report(parsed, markdown, output_path)
        write_cache(cache_path, parsed, output_path, "ok")
        print(f"Wrote report: {output_path}")
        return output_path
    except Exception as exc:
        write_cache(cache_path, parsed, output_path, "error", str(exc))
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze downloaded paper PDFs and write Markdown reports.")
    parser.add_argument("--pdf", help="Analyze one PDF path or URL. Relative paths are resolved from project root.")
    parser.add_argument("--downloads-dir", default=None, help="Directory that contains downloaded PDFs.")
    parser.add_argument("--outputs-dir", default=None, help="Directory for generated Markdown reports.")
    parser.add_argument("--assets-dir", default=None, help="Directory for extracted paper figures.")
    parser.add_argument("--cache-dir", default=None, help="Directory for parser and run cache.")
    parser.add_argument("--limit", type=int, default=None, help="Analyze at most N PDFs.")
    parser.add_argument("--overwrite", action="store_true", help="Regenerate reports that already exist.")
    parser.add_argument("--no-api", "--skip-api", action="store_true", dest="no_api", help="Only parse PDFs and write a draft report.")
    parser.add_argument("--max-images", type=int, default=None, help="Maximum figures to extract per paper.")
    parser.add_argument("--max-chars", type=int, default=None, help="Maximum characters sent in one final prompt.")
    parser.add_argument(
        "--parser",
        choices=["local", "mineru"],
        default=None,
        help="PDF parser backend. local uses PyMuPDF; mineru calls MinerU VLM parsing API.",
    )
    parser.add_argument("--mineru-token", default=None, help="MinerU API token. Overrides MINERU_API_TOKEN/MINERU_API_KEY.")
    parser.add_argument("--mineru-model-version", default=None, help="MinerU model version, for example vlm.")
    parser.add_argument("--llm-provider", choices=["vivo", "ecnu"], default=None, help="LLM provider for summaries.")
    parser.add_argument("--ecnu-api-key", default=None, help="ECNU API key. Overrides ECNU_API_KEY.")
    parser.add_argument("--ecnu-base-url", default=None, help="ECNU API base URL.")
    parser.add_argument("--ecnu-model", default=None, help="ECNU model name, for example ecnu-max or ecnu-reasoner.")
    parser.add_argument("--ecnu-thinking-type", default=None, help="ECNU thinking type, for example disabled.")
    parser.add_argument("--list-ecnu-models", action="store_true", help="List ECNU models and exit.")
    parser.add_argument(
        "--reuse-mineru",
        action="store_true",
        help="Reuse existing .mineru.md and extracted MinerU assets when available; skip a new MinerU API parse.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = AnalyzerSettings.from_env(PROJECT_ROOT)

    overrides = {}
    for cli_name, field_name in [
        ("downloads_dir", "downloads_dir"),
        ("outputs_dir", "outputs_dir"),
        ("assets_dir", "assets_dir"),
        ("cache_dir", "cache_dir"),
    ]:
        value = getattr(args, cli_name)
        if value:
            overrides[field_name] = resolve_path(value, settings.project_root)
    if args.max_images is not None:
        overrides["max_images"] = args.max_images
    if args.max_chars is not None:
        overrides["max_chars"] = args.max_chars
    if args.parser is not None:
        overrides["parser"] = args.parser
    if args.mineru_token is not None:
        overrides["mineru_token"] = args.mineru_token
    if args.mineru_model_version is not None:
        overrides["mineru_model_version"] = args.mineru_model_version
    if args.llm_provider is not None:
        overrides["llm_provider"] = args.llm_provider
    if args.ecnu_api_key is not None:
        overrides["ecnu_api_key"] = args.ecnu_api_key
    if args.ecnu_base_url is not None:
        overrides["ecnu_base_url"] = args.ecnu_base_url
    if args.ecnu_model is not None:
        overrides["ecnu_model"] = args.ecnu_model
    if args.ecnu_thinking_type is not None:
        overrides["ecnu_thinking_type"] = args.ecnu_thinking_type
    if overrides:
        settings = replace(settings, **overrides)

    if args.list_ecnu_models:
        settings = replace(settings, llm_provider="ecnu")
        models = ECNULMClient.from_settings(settings).list_models()
        print(json.dumps(models, ensure_ascii=False, indent=2))
        return 0

    settings.ensure_dirs()
    print(f"Using settings: {settings}")
    pdfs = collect_pdfs(settings, args.pdf, args.limit)
    if not pdfs:
        print(f"No PDFs found in {settings.downloads_dir}")
        return 1
    print(f"Found {len(pdfs)} PDF(s) to analyze.")
    parser_name = settings.parser.strip().lower()
    if parser_name not in {"local", "mineru"}:
        raise RuntimeError(f"Unsupported parser: {settings.parser}")
    mineru_client = MinerUClient.from_settings(settings) if parser_name == "mineru" else None
    client = None if args.no_api else create_llm_client(settings)
    failures = 0
    for pdf_path in iter_progress(pdfs, "Analyzing"):
        try:
            analyze_one(
                pdf_path,
                settings,
                client,
                mineru_client,
                args.overwrite,
                args.no_api,
                parser_name,
                args.reuse_mineru,
            )
        except Exception as exc:
            failures += 1
            print(f"Failed: {pdf_path} -> {exc}")

    if failures:
        print(f"Completed with {failures} failure(s).")
        return 1
    print("All done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from analyze_paper.config import AnalyzerSettings, PROJECT_ROOT, resolve_path
from analyze_paper.llm_client import VivoBlueLMClient
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
    client: VivoBlueLMClient,
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
    client: VivoBlueLMClient,
    settings: AnalyzerSettings,
) -> str:
    if len(markdown) <= settings.max_chars:
        prompt = build_markdown_summary_prompt(source_name, markdown, settings.max_chars)
        return client.complete(prompt, MARKDOWN_SYSTEM_PROMPT)

    chunks = split_text(markdown, settings.chunk_chars, settings.max_chunks)
    chunk_summaries: list[str] = []
    total = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        prompt = build_markdown_chunk_prompt(source_name, chunk, index, total)
        chunk_summaries.append(client.complete(prompt, MARKDOWN_SYSTEM_PROMPT))
    reduce_prompt = build_markdown_reduce_prompt(source_name, chunk_summaries)
    return client.complete(reduce_prompt, MARKDOWN_SYSTEM_PROMPT)


def analyze_one(
    pdf_path: Path | str,
    settings: AnalyzerSettings,
    client: VivoBlueLMClient | None,
    mineru_client: MinerUClient | None,
    overwrite: bool,
    no_api: bool,
    parser_name: str,
) -> Path | None:
    stem = safe_stem_for_source(pdf_path)
    output_path = settings.outputs_dir / f"{stem}.md"
    raw_markdown_path = settings.outputs_dir / f"{stem}.mineru.md"
    cache_path = settings.cache_dir / f"{stem}.json"
    mineru_output_dir = short_asset_dir_for_source(settings, pdf_path, stem)

    if output_path.exists() and not overwrite:
        print(f"Skip existing report: {output_path}")
        return output_path

    if parser_name == "mineru":
        if mineru_client is None:
            raise RuntimeError("MinerU client is not initialized.")
        print(f"Parse PDF with MinerU: {pdf_path}")
        result = mineru_client.parse_pdf(pdf_path, mineru_output_dir, overwrite=overwrite)
        raw_markdown_path.parent.mkdir(parents=True, exist_ok=True)
        raw_markdown_path.write_text(result.markdown, encoding="utf-8")

        summary_status = "skipped"
        if no_api:
            output_for_cache = raw_markdown_path
            print(f"Wrote MinerU raw Markdown: {raw_markdown_path}")
        else:
            if client is None:
                raise RuntimeError("LLM client is not initialized.")
            print("Summarize MinerU Markdown with LLM")
            summary_markdown = generate_markdown_summary_with_llm(stem, result.markdown, client, settings)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(summary_markdown, encoding="utf-8")
            output_for_cache = output_path
            summary_status = "ok"
            print(f"Wrote summary Markdown: {output_path}")

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {
                    "status": "ok",
                    "parser": "mineru",
                    "summary_status": summary_status,
                    "task_id": result.task_id,
                    "output_path": str(output_for_cache),
                    "summary_output_path": str(output_path) if summary_status == "ok" else "",
                    "raw_markdown_path": str(raw_markdown_path),
                    "mineru_output_dir": str(result.output_dir),
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                    "result": result.raw_result,
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
    if overrides:
        settings = replace(settings, **overrides)

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
    client = None if args.no_api else VivoBlueLMClient.from_settings(settings)
    failures = 0
    for pdf_path in iter_progress(pdfs, "Analyzing"):
        try:
            analyze_one(pdf_path, settings, client, mineru_client, args.overwrite, args.no_api, parser_name)
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

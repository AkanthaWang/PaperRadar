#!/usr/bin/env python3
"""Combine per-paper JSON files in data/reports/data into a single JSON array.

By default excludes a file named `paper.json`.

Usage:
  python scripts/combine_reports.py
  python scripts/combine_reports.py --input data/reports/data --output data/reports/all_reports.json --exclude paper.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def combine(input_dir: str = "data/reports/data", output: str = "data/reports/all_reports.json", exclude_name: str = "paper.json") -> int:
    src = Path(input_dir)
    if not src.exists() or not src.is_dir():
        print(f"输入目录不存在: {src}", file=sys.stderr)
        return 2

    items = []
    files = sorted(src.glob("*.json"))
    for fp in files:
        if fp.name == exclude_name:
            continue
        try:
            text = fp.read_text(encoding="utf-8")
            data = json.loads(text)
            items.append(data)
        except Exception as exc:
            print(f"跳过无法解析的文件 {fp}: {exc}", file=sys.stderr)

    outp = Path(output)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已写入 {len(items)} 个条目到: {outp}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Combine per-paper JSON files into one array JSON.")
    parser.add_argument("--input", "-i", default="data/reports/data", help="input directory containing per-paper JSON files")
    parser.add_argument("--output", "-o", default="data/reports/all_reports.json", help="output combined JSON path")
    parser.add_argument("--exclude", "-e", default="paper.json", help="filename to exclude from combining")
    args = parser.parse_args()
    raise SystemExit(combine(args.input, args.output, args.exclude))

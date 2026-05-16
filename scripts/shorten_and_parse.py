#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
缩短 PDF 文件名并解析
"""

import sys
from pathlib import Path
import shutil

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.pipeline.cli import main


def main():
    print("=" * 60)
    print("PaperRadar - 缩短文件名并解析")
    print("=" * 60)
    print()

    # 原 PDF 路径
    original_pdf = Path(r"D:\Github\PaperRadar\data\pdfs\2026_arXiv_Modeling Multi-Dimensional Cognitive States in Large Language Models under Cognitive Crowding.pdf")
    
    # 新的短文件名
    short_name = "2026_arXiv_Cognitive_States_LLM.pdf"
    short_pdf = original_pdf.parent / short_name

    if not original_pdf.exists():
        print(f"❌ 找不到原文件: {original_pdf}")
        return

    print(f"原文件名: {original_pdf.name}")
    print(f"新文件名: {short_name}")
    print()

    # 复制到短文件名
    if not short_pdf.exists():
        print("正在复制文件...")
        shutil.copy2(original_pdf, short_pdf)
        print(f"✓ 已复制到: {short_pdf}")
    else:
        print(f"✓ 文件已存在: {short_pdf}")

    print()
    print("=" * 60)
    print("现在开始解析 PDF...")
    print("=" * 60)
    print()

    # 运行解析
    sys.argv = [
        "python",
        "parse",
        "--pdf",
        str(short_pdf)
    ]
    main()


if __name__ == "__main__":
    main()

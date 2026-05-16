#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PDF 解析脚本 - 使用 MinerU 解析单个或多个 PDF 文件

使用方法:
    python scripts/parse_pdf.py --pdf "path/to/your.pdf"
    python scripts/parse_pdf.py --pdf-dir "data/pdfs/"
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.pipeline.cli import main

if __name__ == "__main__":
    # 如果没有提供参数，使用默认值
    if len(sys.argv) == 1:
        print("使用示例:")
        print("  1. 解析单个 PDF:")
        print(r'     python scripts/parse_pdf.py --pdf "D:\Github\PaperRadar\data\pdfs\2026_arXiv_Modeling Multi-Dimensional Cognitive States in Large Language Models under Cognitive Crowding.pdf"')
        print("\n  2. 解析整个目录下的所有 PDF:")
        print(r'     python scripts/parse_pdf.py --pdf-dir "data/pdfs/"')
        print("\n  3. 覆盖已存在的解析结果:")
        print(r'     python scripts/parse_pdf.py --pdf "path/to/your.pdf" --overwrite')
        sys.exit(0)
    
    # 插入 parse 命令
    sys.argv.insert(1, "parse")
    main()

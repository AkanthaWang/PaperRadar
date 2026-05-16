#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PDF 总结脚本 - 使用 LLM 生成论文总结报告

使用方法:
    python scripts/summarize_pdf.py --pdf "path/to/your.pdf"
    python scripts/summarize_pdf.py --pdf-dir "data/pdfs/"
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
        print("  1. 生成单个 PDF 总结:")
        print(r'     python scripts/summarize_pdf.py --pdf "D:\Github\PaperRadar\data\pdfs\2026_arXiv_Modeling Multi-Dimensional Cognitive States in Large Language Models under Cognitive Crowding.pdf" --llm-provider ecnu --ecnu-model ecnu-max')
        print("\n  2. 生成整个目录下所有 PDF 的总结:")
        print(r'     python scripts/summarize_pdf.py --pdf-dir "data/pdfs/" --llm-provider ecnu --ecnu-model ecnu-max')
        print("\n  3. 如果缺少解析结果，自动先解析:")
        print(r'     python scripts/summarize_pdf.py --pdf "path/to/your.pdf" --parse-missing --llm-provider ecnu --ecnu-model ecnu-max')
        print("\n  4. 覆盖已存在的总结:")
        print(r'     python scripts/summarize_pdf.py --pdf "path/to/your.pdf" --overwrite --llm-provider ecnu --ecnu-model ecnu-max')
        sys.exit(0)
    
    # 插入 summarize 命令
    sys.argv.insert(1, "summarize")
    main()

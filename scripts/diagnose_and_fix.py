#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
诊断和修复 PDF 解析问题
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import shutil


def main():
    print("=" * 60)
    print("PaperRadar - PDF 解析问题诊断")
    print("=" * 60)
    print()

    # 检查预期的 PDF 路径
    expected_pdf = Path(r"D:\Github\PaperRadar\data\pdfs\2026_arXiv_Modeling Multi-Dimensional Cognitive States in Large Language Models under Cognitive Crowding.pdf")
    print(f"[1] 检查 PDF 文件: {expected_pdf}")
    print(f"    文件存在: {expected_pdf.exists()}")
    
    if not expected_pdf.exists():
        print()
        print("❌ PDF 文件不存在！请检查：")
        print("   1. PDF 文件是否在正确的位置？")
        print("   2. 文件名是否正确？")
        print()
        
        # 查找项目中的所有 PDF 文件
        print("搜索项目中的 PDF 文件...")
        pdf_files = list(project_root.rglob("*.pdf"))
        if pdf_files:
            print(f"\n找到 {len(pdf_files)} 个 PDF 文件:")
            for i, pdf in enumerate(pdf_files[:10], 1):
                print(f"  {i}. {pdf}")
            if len(pdf_files) > 10:
                print(f"  ... 还有 {len(pdf_files) - 10} 个")
        else:
            print("未找到任何 PDF 文件")
        
        print()
        print("💡 建议：")
        print("   - 将您的 PDF 放到 data/pdfs/ 目录下")
        print("   - 或者使用较短的文件名")
        return
    
    print()
    print("[2] 检查 data 目录结构...")
    data_dir = project_root / "data"
    data_dir.mkdir(exist_ok=True)
    
    for subdir in ["pdfs", "parsed", "reports"]:
        (data_dir / subdir).mkdir(exist_ok=True)
        print(f"    ✓ {data_dir / subdir}")
    
    print()
    print("[3] 建议重命名 PDF（缩短文件名）...")
    
    # 建议的新文件名
    new_name = "2026_arXiv_Cognitive_States_LLM.pdf"
    new_path = expected_pdf.parent / new_name
    
    print(f"    原文件名: {expected_pdf.name}")
    print(f"    建议改为: {new_name}")
    
    if not new_path.exists():
        confirm = input("\n是否自动重命名？(y/n): ").strip().lower()
        if confirm == "y":
            shutil.copy2(expected_pdf, new_path)
            print(f"\n✓ 已复制到: {new_path}")
            print("\n现在您可以使用新文件名运行解析：")
            print(f'  python scripts/parse_pdf.py --pdf "{new_path}"')
    else:
        print(f"\n文件已存在: {new_path}")
        print("\n您可以直接使用新文件名运行解析：")
        print(f'  python scripts/parse_pdf.py --pdf "{new_path}"')


if __name__ == "__main__":
    main()

@echo off
chcp 65001 >nul
echo ========================================
echo PaperRadar - PDF 解析与总结流水线
echo ========================================
echo.

REM 设置默认 PDF 文件路径（可修改此处）
set DEFAULT_PDF=D:\Github\PaperRadar\data\pdfs\2026_arXiv_Cognitive_States_LLM.pdf

REM 如果命令行参数为空，使用默认值
if "%~1"=="" (
    set PDF_PATH=%DEFAULT_PDF%
) else (
    set PDF_PATH=%~1
)

echo [1/2] 正在解析 PDF: %PDF_PATH%
python scripts/parse_pdf.py --pdf "%PDF_PATH%"
if errorlevel 1 (
    echo.
    echo ❌ PDF 解析失败！
    pause
    exit /b 1
)

echo.
echo [2/2] 正在生成论文总结...
python scripts/summarize_pdf.py --pdf "%PDF_PATH%" --llm-provider ecnu --ecnu-model ecnu-max --parse-missing
if errorlevel 1 (
    echo.
    echo ❌ 总结生成失败！
    pause
    exit /b 1
)

echo.
echo ========================================
echo ✅ 全部完成！
echo ========================================
echo 解析结果位置: data\parsed\
echo 总结报告位置: data\reports\
echo.
pause

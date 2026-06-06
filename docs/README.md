# PaperRadar 快速启动

PaperRadar 是一个论文发现与分析工具，支持抓取顶会论文元数据、按关键词筛选、批量下载 PDF、调用 MinerU 解析论文，并使用 LLM 生成中文结构化报告。前端提供本地 Web 控制台，可浏览已生成报告，也可以选择 PDF 文件或目录触发解析与总结任务。

## 1. 配置 Conda 环境

在项目根目录执行：

```powershell
conda create -n paperradar python=3.10 -y
conda activate paperradar

pip install pandas requests beautifulsoup4 selenium openreview-py lxml python-dotenv tqdm openpyxl
```

如果需要使用 `src/utils/bertopic_analyzer.py` 的主题建模功能，再额外安装：

```powershell
pip install bertopic scikit-learn wordcloud sentence-transformers matplotlib
```

## 2. 配置环境变量

复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

然后编辑 `.env`，至少配置 MinerU 和一个 LLM 服务：

```dotenv
MINERU_API_TOKEN=your_mineru_token
MINERU_MODEL_VERSION=vlm
MINERU_ENABLE_FORMULA=true
MINERU_ENABLE_TABLE=true

PAPER_ANALYZER_LLM_PROVIDER=ecnu
ECNU_API_KEY=your_ecnu_key
ECNU_BASE_URL=https://chat.ecnu.edu.cn/open/api/v1
ECNU_MODEL=ecnu-max
```

如需抓取 OpenReview 登录相关数据，可继续配置：

```dotenv
OPENREVIEW_USERNAME=your_openreview_username
OPENREVIEW_PASSWORD=your_openreview_password
```

## 3. 启动后端

后端通过 Python CLI 运行，先确认命令可用：

```powershell
python -m src.pipeline.cli --help
```

常用完整流程：

```powershell
python -m src.pipeline.cli run --conference ICLR --year 2026 --source openreview --keywords emotion preference --llm-provider ecnu --ecnu-model ecnu-max
```

也可以分阶段执行：

```powershell
python -m src.pipeline.cli fetch --conference ICLR --year 2026 --source openreview
python -m src.pipeline.cli filter --input data/all_papers/all_papers.xlsx --keywords emotion preference
python -m src.pipeline.cli download --input data/filtered_papers/filtered_papers.xlsx --conference ICLR --year 2026
python -m src.pipeline.cli parse --pdf-dir data/pdfs --outputs-dir data/parsed
python -m src.pipeline.cli summarize --pdf-dir data/pdfs --outputs-dir data/parsed --reports-dir data/reports --parse-missing --llm-provider ecnu --ecnu-model ecnu-max
```

单篇 PDF 快速解析和总结：

```powershell
python -m src.pipeline.cli summarize --pdf "data/pdfs/your_paper.pdf" --parse-missing --llm-provider ecnu --ecnu-model ecnu-max
```

## 4. 启动前端

前端依赖本机 Node.js，项目当前不需要额外安装 npm 包。

项目根目录执行：

```powershell
npm run dev
```

如果 PowerShell 拦截 `npm.ps1`，使用：

```powershell
npm.cmd run dev
```

默认访问：

```text
http://127.0.0.1:5173/
```

如果 5173 端口被占用，服务会自动尝试后续端口，例如 `http://127.0.0.1:5174/`。前端运行任务时会调用本机 Python；如果需要指定 conda 环境里的 Python，可先设置：

```powershell
$env:PAPERRADAR_PYTHON = "C:\Users\Administrator\miniconda3\envs\paperradar\python.exe"
npm run dev
```

## 5. 主要功能

- 抓取 OpenReview、CVF/ECVA、DBLP 等来源的会议论文元数据。
- 按关键词、正则和投稿类型筛选论文。
- 批量下载筛选后的论文 PDF，并回写下载状态。
- 调用 MinerU 将 PDF 解析为 Markdown、图表 JSON 和图片资源。
- 调用 LLM 生成中文论文总结报告。
- 在本地 Web 前端浏览 `data/reports` 下的报告，并可提交 PDF 解析与总结任务。

更多细节可查看 `docs/README_fetch.md`、`docs/README_filter.md`、`docs/README_download.md`、`docs/README_parse.md`、`docs/README_summarize.md` 和 `docs/README_pipeline.md`。

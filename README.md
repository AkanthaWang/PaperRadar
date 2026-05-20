# PaperRadar 🚀

PaperRadar 是一个面向科研论文跟踪的自动化工具，帮助研究人员从 CVPR、ICCV、ECCV、NeurIPS、ICLR、ICML、AAAI 等会议获取论文元数据，按研究主题筛选论文，批量下载 PDF，并结合 MinerU 与 LLM 生成结构化中文论文报告。

## ✨ 主要功能

PaperRadar 面向论文发现、筛选、下载、解析和总结的完整研究工作流，核心能力包括：

- **会议论文元数据抓取**：支持从 OpenReview、CVF/OpenAccess、ECVA 和 DBLP 等来源抓取顶会论文信息，统一整理为 Excel/CSV 表格。
- **论文信息结构化**：自动保留论文 ID、标题、投稿类型、关键词、摘要、PDF 链接等字段，作为后续筛选和下载的基础数据。
- **关键词与类型筛选**：可在标题、摘要、关键词等字段中按关键词或正则表达式筛选，也支持按 `oral`、`spotlight`、`poster` 等类型进一步过滤。
- **PDF 批量下载**：根据筛选后的论文表批量下载 PDF，并回写下载状态和本地文件路径，便于中断后继续处理。
- **MinerU 论文解析**：调用 MinerU 将 PDF 解析为 Markdown、图表 JSON 和图片资源，为后续高质量总结提供结构化上下文。
- **LLM 中文报告生成**：基于解析后的正文、章节和图表上下文生成中文论文总结，并输出 Markdown、JSON 和图片资源包。
- **五阶段流水线**：提供统一 CLI，可分阶段运行 `fetch -> filter -> download -> parse -> summarize`，也可以通过 `run` 一键执行完整流程。

## 📊 支持的会议列表

| 来源平台 | 支持会议 | 抓取脚本 |
| :--- | :--- | :--- |
| **OpenReview** | NeurIPS, ICLR, ICML | `src/paper_fetch/openreview_scraper.py` |
| **CVF / ECVA** | CVPR, ICCV, ECCV | `src/paper_fetch/paper_scraper.py` |
| **DBLP** | AAAI, ACMMM | `src/paper_fetch/paper_scraper.py` |

## 📂 项目结构

```text
PaperRadar/
├── config/
│   └── prompts/              # LLM 总结使用的系统 prompt、分块 prompt 和合并 prompt
├── data/
│   ├── all_papers/           # fetch 阶段输出的全量论文元数据表
│   ├── filtered_papers/      # filter 阶段输出的筛选结果和状态表
│   ├── pdfs/                 # download 阶段保存的论文 PDF
│   ├── parsed/               # parse 阶段生成的 MinerU Markdown、图表 JSON 和图片资产
│   └── reports/              # summarize 阶段生成的 Markdown/JSON/图片报告包
├── docs/                     # 各阶段的详细说明文档
├── scripts/                  # 便捷脚本，如 parse_pdf.py、summarize_pdf.py、combine_reports.py
├── src/
│   ├── pipeline/             # 统一 CLI、阶段编排和公共路径/表格工具
│   ├── paper_fetch/          # OpenReview、CVF/ECVA、DBLP 等来源的论文元数据抓取
│   ├── paper_filter/         # 关键词、正则和投稿类型过滤
│   ├── paper_downloader/     # PDF 批量下载、URL 适配和文件名清洗
│   ├── mineru_parser/        # MinerU API 调用、解析缓存和图表上下文提取
│   ├── paper_summarizer/     # 论文分块、LLM 总结、报告 Markdown/JSON 生成
│   └── utils/                # LLM 客户端、鉴权、标题提取等通用工具
├── test/                     # 测试和实验脚本
├── .env.example              # 环境变量模板
├── README_PACKET.md          # 技术路线交付说明
└── README.md
```

## 🛠️ 安装步骤

1. **克隆仓库**：
   ```bash
   git clone https://github.com/your-username/PaperRadar.git
   cd PaperRadar
   ```

2. **安装依赖**：
   本项目依赖 Python 3.8+ 及以下库：
   ```bash
   pip install pandas requests beautifulsoup4 selenium openreview-py lxml python-dotenv tqdm openpyxl
   ```

3. **浏览器驱动**（仅针对 CVF/ECVA/DBLP 等网页抓取）：
   当前网页抓取实现会调用 Selenium Edge WebDriver，请确保本机 Edge 浏览器和对应 WebDriver 可用。

## 🚀 使用指南

PaperRadar 推荐使用统一 CLI 运行。所有命令都在项目根目录执行：

```bash
python -m src.pipeline.cli --help
```

### 1. 配置环境

复制 `.env.example` 为 `.env`，并按需要填写 MinerU 和 LLM 服务密钥：

```dotenv
MINERU_API_TOKEN=your_mineru_token
PAPER_ANALYZER_LLM_PROVIDER=ecnu
ECNU_API_KEY=your_ecnu_key
ECNU_MODEL=ecnu-max
```

如果使用 OpenReview 登录能力，可补充：

```dotenv
OPENREVIEW_USERNAME=your_openreview_username
OPENREVIEW_PASSWORD=your_openreview_password
```

### 2. 分阶段运行

1) Fetch — 抓取会议元数据（`src/paper_fetch`）
```bash
python -m src.pipeline.cli fetch --conference ICLR --year 2026 --source openreview
```
默认输出：`data/all_papers/all_papers.xlsx`。可用 `--output` 指定 `.xlsx` 或 `.csv` 路径。

2) Filter — 按关键词筛选（`src/paper_filter`）
```bash
python -m src.pipeline.cli filter --input data/all_papers/all_papers.xlsx --keywords emotion preference
```
默认输出：`data/filtered_papers/filtered_papers.xlsx`。该表会新增 `matched_keywords` 以及下载、解析、报告状态列。

3) Download — 批量下载 PDF（`src/paper_downloader`）
```bash
python -m src.pipeline.cli download --input data/filtered_papers/filtered_papers.xlsx --conference ICLR --year 2026 --workers 6
```
默认输出：`data/pdfs/`。文件名会被清洗为 `{year}_{conference}_{title}.pdf` 样式，并回写 `download_status` 和 `pdf_path`。

4) Parse — 调用 MinerU 解析 PDF（`src/mineru_parser`）
```bash
python -m src.pipeline.cli parse --pdf-dir data/pdfs --outputs-dir data/parsed
```
输出：`data/parsed/[cache_stem]/`（含 `.mineru.md`、`.mineru.visuals.json`、`_parse_cache.json`）。

5) Summarize — 基于解析产物生成中文报告（`src/paper_summarizer`）
```bash
python -m src.pipeline.cli summarize --pdf-dir data/pdfs --llm-provider ecnu --ecnu-model ecnu-max --reports-dir data/reports
```
常用选项：`--parse-missing`（缺少解析时先自动 parse）、`--overwrite`、`--llm-provider`/`--ecnu-model`。

### 3. 一键运行完整流程

Run 会顺序执行 `fetch -> filter -> download -> parse -> summarize`：

```bash
python -m src.pipeline.cli run --conference ICLR --year 2026 --source openreview --keywords emotion preference --llm-provider ecnu --ecnu-model ecnu-max
```
该命令会在内部按阶段调用各子包，并可通过 `--outputs-dir` / `--reports-dir` / `--status-table` 等参数定制路径。

### 4. 单篇 PDF 快速处理

如果已经有本地 PDF，可以直接解析和总结：

```bash
python scripts/parse_pdf.py --pdf "data/pdfs/your_paper.pdf"
python scripts/summarize_pdf.py --pdf "data/pdfs/your_paper.pdf" --llm-provider ecnu --ecnu-model ecnu-max
```

也可以直接使用 pipeline CLI：

```bash
python -m src.pipeline.cli parse --pdf "data/pdfs/your_paper.pdf"
python -m src.pipeline.cli summarize --pdf "data/pdfs/your_paper.pdf" --llm-provider ecnu --ecnu-model ecnu-max
```

更多细节可查看 `docs/README_fetch.md`、`docs/README_filter.md`、`docs/README_download.md`、`docs/README_parse.md`、`docs/README_summarize.md` 和 `docs/README_pipeline.md`。

## 📅 人工智能方向会议时间

| 会议名称 | CCF 分级 | 年次 | 时间 | 会议类型 |
| :--- | :--- | :--- | :--- | :--- |
| IJCAI | CCF B | 一年一次 | 一月中旬 | CV |
| ICML | CCF A | 一年一次 | 一月下旬 | 机器学习 |
| ACL | CCF A | 一年一次 | 二月中旬 | NLP |
| ECCV | CCF B | 两年一次(偶数) | 三月上旬 | CV |
| ICCV | CCF A | 一次(奇数) | 三月中上旬 | CV |
| ACMMM | CCF A | 一年一次 | 三月下旬或者四月初 | 多模态 |
| NeurIPS | CCF A | 一年一次 | 五月中下旬 | 多模态 |
| EMNLP | CCF B | 一年一次 | 六月下旬 | NLP |
| AAAI | CCF A | 一年一次 | 九月上旬 | 多模态 |
| CHI | CCF A | 一年一次 | 九月中旬 | 人机交互 |
| ICLR | CCF A | 一年一次 | 10月上旬 | CV |
| COLING | CCF B | 两年一次 | 10月下旬 | CV |
| CVPR | CCF A | 一年一次 | 11月中旬 | CV |
| ICME | CCF B | 一年一次 | 12月下旬 | CV|

## 📝 注意事项

- **API 限制**：抓取 OpenReview 数据时，建议配置环境变量 `OPENREVIEW_USERNAME` 和 `OPENREVIEW_PASSWORD`。
- **网络环境**：抓取部分海外学术网站（如 CVF）可能需要稳定的网络环境。
- **合法合规**：请在遵守各大学术平台 Robots 协议的前提下使用本工具，仅限科研学术用途。

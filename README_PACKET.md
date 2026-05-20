# README_PACKET：PaperRadar 技术路径交付包

本文档基于当前代码结构与已有阶段文档，给出 PaperRadar 从“论文发现”到“结构化中文报告”的完整技术路径。它不是替代 `README.md`，而是作为交付包入口，帮助使用者理解系统为什么这样拆分、每一层产出什么、如何运行，以及后续如何扩展。

## 1. 项目定位

PaperRadar 面向情感计算、多模态情绪理解、视觉情感识别、情绪对话、情感生成等研究方向，目标是把“找论文、筛论文、下载 PDF、解析结构、生成可阅读报告”串成一条可复用流水线。

当前系统已从早期的单脚本工具演进为五阶段 pipeline：

```text
会议/论文源
  -> fetch 元数据抓取
  -> filter 研究主题筛选
  -> download PDF 下载
  -> parse MinerU 结构化解析
  -> summarize LLM 中文报告生成
```

最终产物包括：

- 论文元数据总表：`data/all_papers/all_papers.xlsx`
- 筛选与状态总表：`data/filtered_papers/filtered_papers.xlsx`
- 本地 PDF：`data/pdfs/`
- MinerU 解析资产：`data/parsed/`
- 可发布的 Markdown/JSON/图片报告包：`data/reports/`

## 2. 核心理念

### 2.1 Research Radar，而不是一次性爬虫

PaperRadar 的重点不是只抓一次会议列表，而是持续维护一个研究方向雷达。`Awesome of Emotion Research.md` 已经体现了这一理念：按年份、会议和主题沉淀情感研究论文，帮助研究者快速看到方向演进。

因此技术路径采用状态化表格和分阶段输出：同一批论文可以多次筛选、补下载、重解析、重生成报告。

### 2.2 先结构化，再生成

论文 PDF 不直接丢给 LLM 总结，而是先通过 MinerU 解析成 Markdown、图表 JSON 和图片资产。这样做有三个好处：

- 正文、章节、图表、caption、页码和上下文可以独立检查。
- 长论文可以按章节分块，避免上下文被 References 占满。
- 最终报告能把真实图表插入到对应章节，而不是只生成纯文本摘要。

### 2.3 表格作为流程契约

流水线用 Excel/CSV 作为阶段间契约。`filtered_papers.xlsx` 不只是筛选结果，也承担任务状态表职责：

```text
download_status, pdf_path, parse_status, parsed_dir, report_status, report_path
```

这让流程可以中断后继续，也便于人工修正 URL、标题、标签、简介等字段。

### 2.4 人机协作的研究整理

LLM 负责把 MinerU Markdown、图表上下文和论文内容整理成中文报告；人工可以通过状态表补充 `id`、`title_short`、`category`、`paper_type`、`modality`、`tags`、`introduction`、`venue` 等字段，控制最终前端或博客展示效果。

## 3. 代码地图

```text
src/
  pipeline/
    cli.py                 # 统一 CLI 入口
    runner.py              # 五阶段一键运行
    common.py              # 路径、表格、状态列、settings 组装

  paper_fetch/
    stage.py               # fetch 阶段入口
    openreview_scraper.py  # OpenReview 元数据抓取
    paper_scraper.py       # CVF/ECVA/DBLP 元数据抓取

  paper_filter/
    stage.py               # filter 阶段入口
    keyword_filter.py      # 旧版关键词筛选能力

  paper_downloader/
    stage.py               # download 阶段入口
    paper_download.py      # PDF 下载和文件名清洗

  mineru_parser/
    stage.py               # parse 阶段入口
    mineru_client.py       # MinerU API 客户端
    mineru_context.py      # 图表上下文提取与报告插图

  paper_summarizer/
    stage.py               # summarize 阶段入口
    analysis_core.py       # 分块、fallback、LLM 调用编排
    prompts.py             # prompt 加载
    pdf_parser.py          # 文件名元数据推断

  utils/
    llm_client.py          # ECNU/vivo LLM 适配
    vivo_auth.py           # vivo HMAC 鉴权
```

阶段说明文档位于：

```text
docs/README_fetch.md
docs/README_filter.md
docs/README_download.md
docs/README_parse.md
docs/README_summarize.md
docs/README_pipeline.md
```

## 4. 环境准备

推荐 Python 3.8+。基础依赖包括：

```powershell
pip install pandas requests beautifulsoup4 selenium openreview-py lxml python-dotenv tqdm openpyxl
```

抓取 CVF/ECVA/DBLP 等 openaccess 页面时，当前实现会使用浏览器驱动，需保证本机 Edge/Chrome WebDriver 可用。

在项目根目录配置 `.env`：

```dotenv
# MinerU parser
MINERU_API_TOKEN=your_mineru_token
MINERU_MODEL_VERSION=vlm
MINERU_ENABLE_FORMULA=true
MINERU_ENABLE_TABLE=true

# LLM provider: ecnu or vivo
PAPER_ANALYZER_LLM_PROVIDER=ecnu
PAPER_ANALYZER_TIMEOUT=120
PAPER_ANALYZER_TEMPERATURE=0.2
PAPER_ANALYZER_MAX_RETRIES=2

# ECNU LLM
ECNU_API_KEY=your_ecnu_key
ECNU_BASE_URL=https://chat.ecnu.edu.cn/open/api/v1
ECNU_MODEL=ecnu-max
ECNU_THINKING_TYPE=disabled
```

如果使用 OpenReview 私有或需要登录的数据源，可补充：

```dotenv
OPENREVIEW_USERNAME=your_openreview_username
OPENREVIEW_PASSWORD=your_openreview_password
```

## 5. 最短可运行路径

### 5.1 一键运行五阶段

```powershell
python -m src.pipeline.cli run `
  --conference ICLR `
  --year 2026 `
  --source openreview `
  --keywords emotion preference `
  --llm-provider ecnu `
  --ecnu-model ecnu-max
```

适合从会议列表开始完整跑通：

```text
fetch -> filter -> download -> parse -> summarize
```

### 5.2 单篇 PDF 快速解析与总结

如果已经有 PDF，可以直接走后两阶段：

```powershell
python -m src.pipeline.cli parse `
  --pdf "D:\Github\PaperRadar\data\pdfs\2026_ICLR_Example Paper.pdf"
```

```powershell
python -m src.pipeline.cli summarize `
  --pdf "D:\Github\PaperRadar\data\pdfs\2026_ICLR_Example Paper.pdf" `
  --llm-provider ecnu `
  --ecnu-model ecnu-max
```

传入 `--pdf` 时，当前 summarize 实现会允许在缺少 MinerU Markdown 时自动先 parse。批量总结时若想自动补解析，可显式加：

```powershell
--parse-missing
```

## 6. 分阶段技术路径

### 6.1 Fetch：论文元数据获取

入口：

```text
src/paper_fetch/stage.py
```

支持来源：

- `openreview`：ICLR、ICML、NeurIPS 等 OpenReview 会议。
- `openaccess`：CVPR、ICCV、ECCV、AAAI、ACMMM 等公开页面或 DBLP 页面。
- `auto`：根据会议名自动选择，`ICLR`、`ICML`、`NEURIPS` 默认走 OpenReview，其余默认走 openaccess。

命令：

```powershell
python -m src.pipeline.cli fetch `
  --conference ICLR `
  --year 2026 `
  --source openreview
```

默认输出：

```text
data/all_papers/all_papers.xlsx
```

核心字段：

```text
paper_id, title, type, keywords, abstract, url
```

### 6.2 Filter：研究主题筛选

入口：

```text
src/paper_filter/stage.py
```

默认在 `title`、`abstract`、`keywords` 中匹配关键词。支持：

- 任一关键词命中。
- `--match-all` 要求全部关键词命中。
- `--regex` 使用正则。
- `--case-sensitive` 区分大小写。
- `--types` 按 oral、spotlight、poster 等类型筛选。

命令：

```powershell
python -m src.pipeline.cli filter `
  --input data/all_papers/all_papers.xlsx `
  --keywords emotion affect preference
```

默认输出：

```text
data/filtered_papers/filtered_papers.xlsx
```

新增字段：

```text
matched_keywords
download_status, pdf_path
parse_status, parsed_dir
report_status, report_path
```

### 6.3 Download：PDF 批量下载

入口：

```text
src/paper_downloader/stage.py
```

输入表需要包含 `url`，建议包含 `title`。下载文件名格式：

```text
{year}_{conference}_{sanitized_title}.pdf
```

命令：

```powershell
python -m src.pipeline.cli download `
  --input data/filtered_papers/filtered_papers.xlsx `
  --conference ICLR `
  --year 2026 `
  --workers 5
```

默认输出：

```text
data/pdfs/
```

阶段完成后会回写：

```text
download_status = downloaded | missing
pdf_path = 本地 PDF 路径
```

### 6.4 Parse：MinerU 结构化解析

入口：

```text
src/mineru_parser/stage.py
```

能力：

- 上传本地 PDF 或处理 PDF URL。
- 调用 MinerU API。
- 保存原始 Markdown。
- 从 MinerU content list 中提取图像、表格、caption、页码、章节、前后文。
- 对长文件名做上传名缩短和本地 cache stem 缩短，避免 Windows 深层路径过长。
- 成功后回写状态表。

命令：

```powershell
python -m src.pipeline.cli parse `
  --pdf-dir data/pdfs `
  --status-table data/filtered_papers/filtered_papers.xlsx
```

单篇：

```powershell
python -m src.pipeline.cli parse `
  --pdf "data/pdfs/2026_ICLR_Example Paper.pdf"
```

默认输出：

```text
data/parsed/[cache_stem]/
  [cache_stem].mineru.md
  [cache_stem].mineru.visuals.json
  _parse_cache.json
  extract/
```

状态表回写：

```text
parse_status = parsed
parsed_dir = data/parsed/[cache_stem]
```

解析失败时，当前实现会尝试把失败 PDF 移到：

```text
data/pdfs/error/
```

### 6.5 Summarize：中文报告生成

入口：

```text
src/paper_summarizer/stage.py
```

能力：

- 读取 MinerU Markdown。
- 读取或重新生成 MinerU visual JSON。
- 将图表上下文交给 LLM 参与总结。
- 对超长 Markdown 按章节分块，跳过 References/Bibliography。
- 使用 ECNU 或 vivo LLM 生成中文报告。
- 将真实图像复制到 report img 目录，并按 caption/章节/编号插入对应小节。
- 生成 blog Markdown 和前端友好的 JSON 元数据。
- LLM 失败时生成 fallback 报告，保留修复线索。

命令：

```powershell
python -m src.pipeline.cli summarize `
  --pdf-dir data/pdfs `
  --llm-provider ecnu `
  --ecnu-model ecnu-max
```

默认输出：

```text
data/reports/
  blog/
    [paper_id].md
  data/
    [paper_id].json
  img/
    [paper_id]/
      [images used by blog]
```

报告 Markdown 目标结构：

```text
# 论文总结

## 基本信息
## 核心问题
## 动机和思想
## 方法介绍
## 实验设置
## 主要结果
## 贡献展示
## 局限与风险
## 可借鉴点
```

状态表回写：

```text
report_status = reported
report_path = data/reports/blog/[paper_id].md
```

## 7. 数据契约

### 7.1 元数据表

`fetch` 输出的最小可用字段：

```text
title, url
```

推荐字段：

```text
paper_id, title, type, keywords, abstract, url
```

### 7.2 筛选与状态表

`filter` 会保证状态列存在：

```text
matched_keywords
download_status
pdf_path
parse_status
parsed_dir
report_status
report_path
```

可人工补充的展示字段：

```text
id
title_short
category
paper_type
modality
tags
introduction
venue
```

这些字段会在 `summarize` 阶段优先进入最终 JSON。

### 7.3 Report JSON

最终 JSON 结构：

```json
{
  "id": "paper-slug",
  "title": "Short Title",
  "fullTitle": "Full Paper Title",
  "year": 2026,
  "category": "Emotion",
  "type": "Method",
  "modality": "image",
  "tags": ["Emotion", "Visual Emotion Recognition", "Image"],
  "introduction": "中文简介。",
  "blog": {
    "enabled": true,
    "slug": "/blog/paper-slug"
  },
  "venue": "ICLR"
}
```

## 8. Prompt 与生成策略

Prompt 位于：

```text
config/prompts/
  markdown_system_prompt.md
  markdown_summary_prompt.md
  markdown_chunk_prompt.md
  markdown_reduce_prompt.md
```

生成策略：

- 内容较短时，直接使用 `markdown_summary_prompt.md`。
- 内容过长时，先按章节切分，用 `markdown_chunk_prompt.md` 分块总结。
- 多个分块总结再由 `markdown_reduce_prompt.md` 合并。
- `markdown_system_prompt.md` 控制总体写作风格和约束。

关键参数：

```dotenv
PAPER_ANALYZER_MAX_CHARS=60000
PAPER_ANALYZER_SUMMARY_MAX_CHARS=32000
PAPER_ANALYZER_SUMMARY_CHUNK_CHARS=12000
PAPER_ANALYZER_MAX_CHUNKS=8
```

## 9. 验收标准

一次完整交付应能满足：

- `python -m src.pipeline.cli --help` 可显示 CLI。
- `fetch` 能生成 `data/all_papers/all_papers.xlsx`。
- `filter` 能生成 `data/filtered_papers/filtered_papers.xlsx`，并包含状态列。
- `download` 后 PDF 出现在 `data/pdfs/`，状态表写入 `download_status` 和 `pdf_path`。
- `parse` 后每篇论文有 `.mineru.md`、`.mineru.visuals.json` 和 `_parse_cache.json`。
- `summarize` 后有 `data/reports/blog/[paper_id].md` 与 `data/reports/data/[paper_id].json`。
- 报告正文为中文，包含固定章节，图表尽量出现在相关章节中。
- 失败时有明确错误信息或 fallback 报告，不静默丢失论文。

## 10. 常用命令清单

查看 CLI：

```powershell
python -m src.pipeline.cli --help
```

抓取：

```powershell
python -m src.pipeline.cli fetch --conference ICLR --year 2026 --source openreview
```

筛选：

```powershell
python -m src.pipeline.cli filter --input data/all_papers/all_papers.xlsx --keywords emotion preference
```

下载：

```powershell
python -m src.pipeline.cli download --input data/filtered_papers/filtered_papers.xlsx --conference ICLR --year 2026
```

解析：

```powershell
python -m src.pipeline.cli parse
```

总结：

```powershell
python -m src.pipeline.cli summarize --llm-provider ecnu --ecnu-model ecnu-max
```

覆盖已有结果：

```powershell
python -m src.pipeline.cli summarize --pdf "data/pdfs/example.pdf" --overwrite --llm-provider ecnu
```

限制处理数量：

```powershell
python -m src.pipeline.cli summarize --limit 3 --llm-provider ecnu
```

## 11. 后续技术路线

### 11.1 稳定性增强

- 为 `fetch/filter/download/parse/summarize` 增加轻量单元测试和端到端 smoke test。
- 对 openaccess 抓取增加更多站点适配和失败重试。
- 对下载失败 URL 生成诊断列，例如 HTTP 状态、最终跳转 URL、错误原因。

### 11.2 研究知识库增强

- 将 `Awesome of Emotion Research.md` 与 `data/reports/data/*.json` 打通，自动生成年度/会议索引。
- 增加主题聚类能力，例如 BERTopic 方向聚类、标签归一、研究趋势统计。
- 支持人工标注“必读、相关、跳过、待复查”等研究状态。

### 11.3 报告质量增强

- 引入图表重要性评分，减少无关图片进入报告。
- 对报告 JSON 增加 citation、authors、project、code、dataset 等字段。
- 对 Markdown 报告增加引用片段校验，降低模型编造风险。

### 11.4 产品化增强

- 提供一个本地 Web UI，用于查看状态表、打开 PDF、预览 MinerU Markdown、重跑单篇总结。
- 把 `data/reports` 直接发布到博客或前端站点。
- 增加任务队列，使下载、解析、总结可以后台增量运行。

## 12. 当前推荐工作流

对于情感研究方向的日常使用，推荐：

1. 用 `fetch` 拉取目标会议年度论文。
2. 用 `filter` 以 `emotion affect facial multimodal preference empathy` 等关键词初筛。
3. 人工检查 `filtered_papers.xlsx`，补充重点论文的展示字段。
4. 用 `download` 下载 PDF。
5. 用 `parse --limit` 先抽样验证 MinerU 解析效果。
6. 用 `summarize --limit` 先抽样验证报告质量。
7. 批量运行 `parse` 和 `summarize`。
8. 将 `data/reports/blog` 与 `data/reports/data` 作为最终研究报告资产。

这条路径保留了自动化效率，也给人工研究判断留下了可介入的位置。

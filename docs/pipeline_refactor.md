# PaperRadar Pipeline Refactor

当前框架按五个阶段拆分到 `src`：

1. `src/paper_fetch`：论文元数据获取，保存全量表。
2. `src/paper_filter`：按关键词筛选论文，生成兼状态表。
3. `src/paper_downloader`：下载筛选后的论文 PDF。
4. `src/mineru_parser`：调用 MinerU 解析 PDF，输出 Markdown/JSON/图片资产。
5. `src/paper_summarizer`：结合 MinerU Markdown、JSON 和图片上下文，调用大模型生成最终总结报告。

Prompt 统一放在 `config/prompts`，其中 `markdown_reduce_prompt.md` 用于长文分块总结后的合并。

## Data Layout

```text
data/
  all_papers/
    all_papers.xlsx
  filtered_papers/
    filtered_papers.xlsx
  pdfs/
    [PDF files]
  parsed/
    [paper_stem]/
      [paper_stem].mineru.md
      [paper_stem].mineru.visuals.json
      extract/
  reports/
    blog/
      [paper_id].md
    data/
      [paper_id].json
    img/
      [paper_id]/
        [blog images]
```

`summarize` 阶段的最终输出统一放在 `data/reports` 下：

- `blog/`：最终总结 Markdown。
- `data/`：每篇论文一个 JSON 元数据文件，包含 `id`、`title`、`fullTitle`、`year`、`category`、`type`、`modality`、`tags`、`introduction`、`blog`、`venue`。
- `img/`：供 blog Markdown 引用的图像资源，Markdown 内使用相对链接 `../img/[paper_id]/...`。
- 图表插入会根据 MinerU visual JSON 的 caption、原论文章节、前后文和表格内容匹配最终总结中的已有章节；若报告小节标题包含 `表1`、`图4` 等编号，会优先插入对应小节。图片会放在匹配小节标题之后、正文描述之前，不再额外添加 `相关图表` 标题，使用居中 HTML 图片和居中中文图注。

`parse` 阶段调用 MinerU 上传本地 PDF 时，会自动判断上传文件名的 UTF-8 字节长度。文件名过长时，只在 MinerU API 请求中使用带 hash 后缀的短文件名；本地 PDF 文件名和 `data/parsed/[paper_stem]` 输出目录仍保持原逻辑。

对于长标题 PDF，`parse` 阶段还会使用短 cache stem 写入 `data/parsed/[short_stem]`，并在该目录下保存 `_parse_cache.json` 记录原始 stem、短 stem 和 PDF 路径。这可以避免 Windows 下 MinerU 解压后的深层图片路径过长。`summarize` 会优先读取短 cache 路径，同时兼容旧版长目录解析结果。

`summarize` 阶段处理超长 MinerU Markdown 时，会按章节优先分片：

- 优先识别 Markdown 标题和常见论文编号标题，把正文组织为章节。
- 短章节会自动合并到同一分片。
- 单个章节超过 `summary_chunk_chars` 时，会在章节内部按段落拆分，必要时再按字符兜底。
- `References/Bibliography` 章节会跳过，避免占用总结上下文。
- `max_chunks` 仍控制最多分片数；论文过长时可通过 `PAPER_ANALYZER_MAX_CHUNKS` 或 `--limit`/单篇处理策略调整。

`filtered_papers.xlsx` 会作为状态总表继续追加这些列：

```text
download_status, pdf_path, parse_status, parsed_dir, report_status, report_path
```

## Environment

密钥默认从项目根目录 `.env` 读取，命令行里不需要传 token。

```dotenv
MINERU_API_TOKEN=your_mineru_token
PAPER_ANALYZER_LLM_PROVIDER=ecnu
ECNU_API_KEY=your_ecnu_key
ECNU_MODEL=ecnu-max
ECNU_BASE_URL=https://chat.ecnu.edu.cn/open/api/v1
ECNU_THINKING_TYPE=disabled
```

如果要继续使用 vivo，把 `PAPER_ANALYZER_LLM_PROVIDER` 改成 `vivo`，并配置 vivo 对应的 `PAPER_ANALYZER_APP_ID`、`PAPER_ANALYZER_APP_KEY`、`PAPER_ANALYZER_DOMAIN`、`PAPER_ANALYZER_URI`、`PAPER_ANALYZER_MODEL`。

## Commands

分阶段运行：

```powershell
python -m src.pipeline.cli fetch --conference ICLR --year 2026 --source openreview
python -m src.pipeline.cli filter --input data/all_papers/all_papers.xlsx --keywords emotion preference
python -m src.pipeline.cli download --input data/filtered_papers/filtered_papers.xlsx --conference ICLR --year 2026
python -m src.pipeline.cli parse
python -m src.pipeline.cli summarize --llm-provider ecnu --ecnu-model ecnu-max
```

一键运行五阶段：

```powershell
python -m src.pipeline.cli run --conference ICLR --year 2026 --source openreview --keywords emotion preference --llm-provider ecnu --ecnu-model ecnu-max
```

`--mineru-token` 和 `--ecnu-api-key` 仍然保留为临时覆盖参数，但常规运行建议直接使用 `.env`。


python -m src.pipeline.cli parse --pdf "D:\Github\PaperRadar\data\pdfs\2026_ACL_Learning How and What to Memorize.pdf"

python -m src.pipeline.cli summarize --llm-provider ecnu --ecnu-model ecnu-max --pdf "D:\Github\PaperRadar\data\pdfs\2026_ACL_Learning How and What to Memorize.pdf"



python -m src.pipeline.cli summarize --llm-provider ecnu --ecnu-model ecnu-max --pdf "D:\Github\PaperRadar\data\pdfs\2026_arXiv_Cognitive_States_LLM.pdf"

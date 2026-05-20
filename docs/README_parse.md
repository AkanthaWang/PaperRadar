# Parse 阶段说明

`parse` 阶段负责调用 MinerU 将 PDF 解析为 Markdown、图表 JSON 和图片资产。它是 `summarize` 阶段的前置步骤。

对应代码：

- 阶段入口：`src/mineru_parser/stage.py`
- MinerU API 客户端：`src/mineru_parser/mineru_client.py`
- 图表上下文提取：`src/mineru_parser/mineru_context.py`
- PDF 收集和 cache stem：`src/paper_summarizer/analysis_core.py`
- 快捷脚本：`scripts/parse_pdf.py`

## 基本命令

解析默认 PDF 目录下的所有文件：

```powershell
python -m src.pipeline.cli parse
```

默认 PDF 目录：

```text
data/pdfs/
```

解析单个 PDF：

```powershell
python -m src.pipeline.cli parse `
  --pdf "D:\Github\PaperRadar\data\pdfs\2026_ICLR_Example Paper.pdf"
```

使用快捷脚本：

```powershell
python scripts/parse_pdf.py --pdf "data/pdfs/2026_ICLR_Example Paper.pdf"
```

## 环境变量

MinerU token 默认从项目根目录 `.env` 读取：

```dotenv
MINERU_API_TOKEN=your_mineru_token
MINERU_MODEL_VERSION=vlm
MINERU_ENABLE_FORMULA=true
MINERU_ENABLE_TABLE=true
MINERU_LANGUAGE=
MINERU_TIMEOUT=900
MINERU_POLL_INTERVAL=5
```

也兼容：

```dotenv
MINERU_API_KEY=...
PAPER_ANALYZER_MINERU_TOKEN=...
MINERU_API_BASE_URL=https://mineru.net
MINERU_USER_TOKEN=...
```

命令行可以临时覆盖：

```powershell
python -m src.pipeline.cli parse `
  --mineru-token "your_token" `
  --mineru-model-version vlm
```

## 输出结构

默认输出根目录：

```text
data/parsed/
```

单篇论文输出：

```text
data/parsed/[cache_stem]/
  [cache_stem].mineru.md
  [cache_stem].mineru.visuals.json
  _parse_cache.json
  extract/
    [MinerU task or batch id]/
      mineru_output.zip
      ...
      images/
```

文件说明：

| 文件 | 说明 |
| --- | --- |
| `[cache_stem].mineru.md` | MinerU 解析出的原始 Markdown，图片路径已重写为相对解析目录的路径。 |
| `[cache_stem].mineru.visuals.json` | 从 MinerU content list 中提取的图像、表格、caption、页码和上下文。 |
| `_parse_cache.json` | 记录原始文件名 stem、短 cache stem、PDF 路径、Markdown 路径和 visual JSON 路径。 |
| `extract/` | MinerU 下载并解压后的原始结果目录。 |

`visuals.json` 中每个元素包含：

```json
{
  "index": 1,
  "kind": "image",
  "page": 4,
  "path": "relative/path/to/image.jpg",
  "caption": "Figure 2. ...",
  "footnote": "",
  "section": "Method",
  "before": "图表前文上下文",
  "after": "图表后文上下文",
  "table_body": ""
}
```

表格会使用 `kind: "table"`，并尽量保留 `table_body` 摘录。

## 长文件名处理

`parse` 阶段有两层长文件名保护。

第一层是 MinerU 上传文件名缩短。部分 PDF 标题很长时，直接把完整文件名传给 MinerU API 可能失败。现在上传到 MinerU 时会判断 UTF-8 字节长度，超过限制会生成短文件名：

```text
原文件名 -> 截断后的标题前缀-hash.pdf
```

这只影响 MinerU API 请求中的文件名，不修改本地 PDF。

第二层是本地解析缓存目录缩短。长标题 PDF 在 Windows 下解压 MinerU 图片时容易触发路径过长问题，因此解析输出目录使用 `cache_stem`：

```text
data/parsed/[short_cache_stem]/
```

默认 cache stem 最大长度为 72 个字符，并带 hash 后缀避免冲突。

`_parse_cache.json` 会记录：

```json
{
  "source_stem": "原始 PDF stem",
  "cache_stem": "短 cache stem",
  "pdf_path": "PDF 路径",
  "raw_markdown_path": "MinerU Markdown 路径",
  "visuals_path": "visual JSON 路径"
}
```

`summarize` 会优先读取短 cache 路径，并兼容旧版长目录解析结果。

## 状态表更新

如果存在状态表，默认路径为：

```text
data/filtered_papers/filtered_papers.xlsx
```

解析成功后会根据 PDF 文件名匹配状态表中的 `pdf_path`，并更新：

```text
parse_status = parsed
parsed_dir = data/parsed/[cache_stem]
```

也可以显式指定状态表：

```powershell
python -m src.pipeline.cli parse `
  --status-table data/filtered_papers/emotion.xlsx
```

## 参数说明

| 参数 | 说明 |
| --- | --- |
| `--pdf` | 解析单个 PDF 路径或 URL。 |
| `--pdf-dir` | 批量解析目录，默认 `data/pdfs`。 |
| `--outputs-dir` | 解析输出目录，默认 `data/parsed`。 |
| `--cache-dir` | 缓存目录，默认 `data/parsed/_cache`。 |
| `--status-table` | 需要回写状态的表格。 |
| `--limit` | 只处理前 N 个 PDF。 |
| `--overwrite` | 覆盖已有解析结果。 |
| `--mineru-token` | 临时覆盖 MinerU token。 |
| `--mineru-model-version` | 临时覆盖 MinerU 模型版本。 |
| `--max-images` | 读取到 settings 中，当前 MinerU visual JSON 默认最多提取 12 个候选项。 |
| `--max-chars` | 读取到 settings 中，主要供后续总结阶段使用。 |
| `--summary-max-chars` | 读取到 settings 中，主要供后续总结阶段使用。 |
| `--summary-chunk-chars` | 读取到 settings 中，主要供后续总结阶段使用。 |

## 覆盖策略

如果目标 Markdown 已存在且未传 `--overwrite`，阶段会跳过该论文：

```text
Skip existing MinerU Markdown: ...
```

如需重新调用 MinerU：

```powershell
python -m src.pipeline.cli parse --pdf "data/pdfs/example.pdf" --overwrite
```

## 常见问题

如果报错缺少 MinerU token，检查 `.env`：

```dotenv
MINERU_API_TOKEN=...
```

如果出现 `No PDFs found`，检查：

- `data/pdfs` 下是否存在 `.pdf` 文件。
- 是否传错了 `--pdf-dir`。
- `--pdf` 是否为真实文件或 http/https URL。

如果 MinerU 返回失败，通常需要检查：

- token 是否有效。
- PDF 是否损坏或加密。
- 网络是否能访问 MinerU。
- `MINERU_TIMEOUT` 是否过短。

如果是长标题 PDF 导致路径问题，应使用当前 parse 逻辑重新解析；旧的长目录可以保留，新的短 cache 目录会自动避免深层图片路径过长。

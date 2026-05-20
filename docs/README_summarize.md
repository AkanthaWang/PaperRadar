# Summarize 阶段说明

`summarize` 阶段负责读取 MinerU 解析结果，调用大模型生成中文论文总结，并把最终 blog Markdown、元数据 JSON 和图像资源整理到 `data/reports`。

对应代码：

- 阶段入口：`src/paper_summarizer/stage.py`
- 长文分片和 LLM 总结：`src/paper_summarizer/analysis_core.py`
- Prompt 加载：`src/paper_summarizer/prompts.py`
- LLM 客户端：`src/utils/llm_client.py`
- MinerU 图表插入：`src/mineru_parser/mineru_context.py`
- 快捷脚本：`scripts/summarize_pdf.py`

## 基本命令

总结默认 PDF 目录中的所有论文：

```powershell
python -m src.pipeline.cli summarize --llm-provider ecnu --ecnu-model ecnu-max
```

总结单个 PDF：

```powershell
python -m src.pipeline.cli summarize `
  --pdf "D:\Github\PaperRadar\data\pdfs\2026_ICLR_Example Paper.pdf" `
  --llm-provider ecnu `
  --ecnu-model ecnu-max
```

使用快捷脚本：

```powershell
python scripts/summarize_pdf.py `
  --pdf "data/pdfs/2026_ICLR_Example Paper.pdf" `
  --llm-provider ecnu `
  --ecnu-model ecnu-max
```

如果缺少 MinerU 解析结果，可以自动先解析：

```powershell
python -m src.pipeline.cli summarize `
  --pdf "data/pdfs/2026_ICLR_Example Paper.pdf" `
  --parse-missing `
  --llm-provider ecnu `
  --ecnu-model ecnu-max
```

当前实现中，传入 `--pdf` 时也会自动允许缺失解析结果先 parse。

## 环境变量

默认从项目根目录 `.env` 读取。

ECNU 配置：

```dotenv
PAPER_ANALYZER_LLM_PROVIDER=ecnu
ECNU_API_KEY=your_ecnu_key
ECNU_BASE_URL=https://chat.ecnu.edu.cn/open/api/v1
ECNU_MODEL=ecnu-max
ECNU_THINKING_TYPE=disabled
```

vivo 配置：

```dotenv
PAPER_ANALYZER_LLM_PROVIDER=vivo
PAPER_ANALYZER_APP_ID=your_vivo_app_id
PAPER_ANALYZER_APP_KEY=your_vivo_app_key
PAPER_ANALYZER_DOMAIN=https://api-ai.vivo.com.cn/v1
PAPER_ANALYZER_URI=/chat/completions
PAPER_ANALYZER_MODEL=qwen3.5-plus
```

通用生成参数：

```dotenv
PAPER_ANALYZER_TIMEOUT=120
PAPER_ANALYZER_TEMPERATURE=0.2
PAPER_ANALYZER_MAX_RETRIES=2
PAPER_ANALYZER_MAX_CHARS=60000
PAPER_ANALYZER_SUMMARY_MAX_CHARS=32000
PAPER_ANALYZER_SUMMARY_CHUNK_CHARS=12000
PAPER_ANALYZER_MAX_CHUNKS=8
```

## 输入依赖

`summarize` 需要每篇 PDF 对应的 MinerU 解析结果：

```text
data/parsed/[cache_stem]/
  [cache_stem].mineru.md
  [cache_stem].mineru.visuals.json
  extract/
```

如果当前短 cache 路径不存在，代码会兼容旧版长目录：

```text
data/parsed/[source_stem]/
  [source_stem].mineru.md
```

单篇总结会根据 PDF 路径推断 cache stem，因此建议 `parse` 和 `summarize` 使用同一个 PDF 文件路径。

## 输出结构

默认输出根目录：

```text
data/reports/
```

单篇输出：

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

其中：

- `blog/[paper_id].md`：最终中文论文总结。
- `data/[paper_id].json`：站点或前端使用的论文元数据。
- `img/[paper_id]/`：blog 中引用的图像资源。

Markdown 中图片路径会写成：

```text
../img/[paper_id]/image.jpg
```

## 元数据 JSON

每篇论文会生成一个 JSON：

```json
{
  "id": "new-paper",
  "title": "New Paper",
  "fullTitle": "New Paper Full Title",
  "year": 2026,
  "category": "Emotion",
  "type": "Method",
  "modality": "image",
  "tags": ["Emotion", "Visual Emotion Recognition", "Cross-Domain", "Diffusion", "Image"],
  "introduction": "论文简介。",
  "blog": {
    "enabled": true,
    "slug": "/blog/new-paper"
  },
  "venue": "CVPR"
}
```

字段来源优先级：

| 字段 | 推断逻辑 |
| --- | --- |
| `id` | 优先状态表中的 `id`、`paper_id`、`slug`；否则优先短标题/缩写；再退化为完整标题 slug。 |
| `title` | 优先 `title_short`、`short_title`、`acronym`、`abbr`；否则从完整标题推断短标题。 |
| `fullTitle` | 优先状态表中的 `title`、`full_title`、`fullTitle`；否则从 MinerU Markdown 一级标题或文件名推断。 |
| `year` | 从状态表、文件名或默认值推断。 |
| `venue` | 从状态表 `venue`、`conference`、`source` 或文件名推断。 |
| `category` | 状态表 `category`，缺省为 `Emotion`。 |
| `type` | 状态表 `paper_type`、`paperType`，缺省为 `Method`。 |
| `modality` | 状态表 `modality` 优先；否则根据标题、关键词、摘要和 Markdown 前文关键词推断。 |
| `tags` | 输出英文规范标签，一般控制在 5 个左右。会基于标题、关键词、摘要和正文自动补充任务、方法、模态标签，例如 `Emotion`、`Visual Emotion Recognition`、`Cross-Domain`、`Diffusion`、`Image`。 |
| `introduction` | 必须输出中文。若状态表 `introduction` 已是中文则保留；否则优先从最终中文总结的 `核心问题`、`方法介绍/方法概述`、`动机和思想` 或 `基本信息/研究任务` 中提取。若仍无法提取中文，再写入中文兜底简介。 |

如果希望控制最终前端展示，建议在 `filtered_papers.xlsx` 中补充：

```text
id, title_short, category, paper_type, modality, tags, introduction, venue
```

## Markdown 结构

Prompt 要求最终总结包含：

```text
# 论文总结

## 基本信息
## 核心问题
## 动机和思想
## 方法介绍 / 方法概述
## 实验设置
## 主要结果
## 贡献展示 / 贡献
## 局限与风险
## 可借鉴点
```

不同 prompt 路径中可能出现 `方法介绍` 和 `方法概述`、`贡献展示` 和 `贡献` 的差异。图表插入逻辑会通过标题别名和关键词匹配尽量对齐。

Prompt 文件位于：

```text
config/prompts/
  markdown_system_prompt.md
  markdown_summary_prompt.md
  markdown_chunk_prompt.md
  markdown_reduce_prompt.md
```

## 长文分片逻辑

当 MinerU Markdown 和图表上下文总长度不超过 `summary_max_chars` 时，会一次性总结。

当内容过长时，会进入分片流程：

1. 按章节优先切分，识别 Markdown 标题和常见论文编号标题。
2. 短章节会合并到同一分片。
3. 单个章节超过 `summary_chunk_chars` 时，会在章节内部按段落拆分。
4. 如果段落仍过长，再按字符硬切，并保留少量重叠。
5. `References` 和 `Bibliography` 章节会跳过。
6. 每个分片先单独总结，再用 reduce prompt 合并为最终报告。

相关参数：

```powershell
python -m src.pipeline.cli summarize `
  --summary-max-chars 32000 `
  --summary-chunk-chars 12000 `
  --max-chars 60000
```

`PAPER_ANALYZER_MAX_CHUNKS` 目前通过环境变量控制。

## 图表插入逻辑

`parse` 阶段会从 MinerU content list 中提取图表项，包括：

- 类型：image/table
- 页码
- 图片路径
- caption
- footnote
- 所在章节
- 前后文
- 表格内容摘录

`summarize` 阶段会先把这些图表上下文交给 LLM，帮助模型在对应章节中描述图表。随后代码会再次根据图表描述把真实图片插入 Markdown。

插入规则：

1. 如果图表 caption 中出现 `Figure 2`、`Table 4` 等编号，会优先匹配报告中包含 `图2`、`表4`、`Figure 2`、`Table 4` 的小节标题。
2. 如果编号无法匹配，会根据 caption、原论文章节、前后文、表格内容和总结标题关键词进行匹配。
3. 图像会插入到匹配小节标题之后、正文文本之前。
4. 不再新增 `相关图表` 标题。
5. 图片使用居中 HTML。
6. 图注使用居中 `<em>`，并尽量把常见英文 caption 片段翻译为中文。

生成格式示例：

```md
## 方法概述

<p align="center">
  <img src="../img/auhead/figure-2.jpg" alt="Figure 2" />
</p>
<p align="center"><em>图 2，第 4 页，AUHead 两阶段框架的整体流程。</em></p>

提出**AUHead**两阶段框架...
```

如果同一个 caption 同时包含图和表，例如 `Figure 4 ... Table 4 ...`，会尝试插入到对应的多个编号小节中。

## 覆盖和 fallback

如果最终 blog Markdown 已存在且未传 `--overwrite`，阶段会跳过：

```text
Skip existing summary: ...
```

重新生成：

```powershell
python -m src.pipeline.cli summarize `
  --pdf "data/pdfs/example.pdf" `
  --overwrite `
  --llm-provider ecnu `
  --ecnu-model ecnu-max
```

如果 LLM 调用失败，代码会写入 fallback Markdown，包含：

- 错误信息。
- MinerU Markdown 路径。
- MinerU visual JSON 路径。
- 摘要线索。
- 章节线索。

同时缓存文件会标记：

```json
{
  "status": "fallback",
  "summary_error": "..."
}
```

## 状态表更新

如果存在状态表，默认路径为：

```text
data/filtered_papers/filtered_papers.xlsx
```

总结成功后会根据 PDF 文件名匹配 `pdf_path`，并更新：

```text
report_status = reported
report_path = data/reports/blog/[paper_id].md
```

也可以显式传入：

```powershell
python -m src.pipeline.cli summarize `
  --status-table data/filtered_papers/emotion.xlsx `
  --llm-provider ecnu
```

## 参数说明

| 参数 | 说明 |
| --- | --- |
| `--pdf` | 总结单个 PDF 路径或 URL。 |
| `--pdf-dir` | 批量总结目录，默认 `data/pdfs`。 |
| `--outputs-dir` | MinerU 解析输出目录，默认 `data/parsed`。 |
| `--reports-dir` | 总结输出目录，默认 `data/reports`。 |
| `--cache-dir` | 总结缓存目录，默认 `data/parsed/_cache`。 |
| `--status-table` | 需要回写状态的表格。 |
| `--limit` | 只处理前 N 个 PDF。 |
| `--overwrite` | 覆盖已有总结。 |
| `--parse-missing` | 缺少 MinerU Markdown 时自动调用 MinerU。 |
| `--llm-provider` | `ecnu` 或 `vivo`。 |
| `--ecnu-api-key` | 临时覆盖 ECNU API key。 |
| `--ecnu-base-url` | 临时覆盖 ECNU base URL。 |
| `--ecnu-model` | 临时覆盖 ECNU 模型名。 |
| `--ecnu-thinking-type` | 临时覆盖 ECNU thinking 配置。 |
| `--mineru-token` | 自动 parse 缺失文件时使用。 |
| `--mineru-model-version` | 自动 parse 缺失文件时使用。 |
| `--max-images` | settings 参数；当前图表插入默认最多选择 8 个图表。 |
| `--max-chars` | 总输入上限之一。 |
| `--summary-max-chars` | 单次总结阈值。 |
| `--summary-chunk-chars` | 分片目标长度。 |

## 常见问题

如果报错缺少 LLM key，检查 `.env` 中的 provider 和对应密钥。

如果报错缺少 MinerU Markdown，先运行：

```powershell
python -m src.pipeline.cli parse --pdf "data/pdfs/example.pdf"
```

或在总结时添加：

```powershell
--parse-missing
```

如果旧报告中的图表仍堆在后面，需要用当前逻辑重新生成：

```powershell
python -m src.pipeline.cli summarize --pdf "data/pdfs/example.pdf" --overwrite
```

如果图表插入位置不理想，优先检查 `data/parsed/[cache_stem]/[cache_stem].mineru.visuals.json` 中的 caption、section、before、after 是否足够准确。插入逻辑主要依赖这些文本线索。

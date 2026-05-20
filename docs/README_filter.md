# Filter 阶段说明

`filter` 阶段负责从全量论文元数据表中筛选目标论文，并生成后续流水线使用的状态表。它不仅输出匹配结果，还会补齐下载、解析、总结所需的状态列。

对应代码：

- 阶段入口：`src/paper_filter/stage.py`
- 旧版标题过滤脚本：`src/paper_filter/keyword_filter.py`
- 表格读写和状态列：`src/pipeline/common.py`

## 基本命令

```powershell
python -m src.pipeline.cli filter `
  --input data/all_papers/all_papers.xlsx `
  --keywords emotion preference
```

默认输出：

```text
data/filtered_papers/filtered_papers.xlsx
```

指定输出路径：

```powershell
python -m src.pipeline.cli filter `
  --input data/all_papers/all_papers.xlsx `
  --output data/filtered_papers/emotion.xlsx `
  --keywords emotion affect facial
```

## 输入表格

输入支持：

```text
.xlsx, .xls, .csv
```

默认会在以下列中搜索关键词：

```text
title, abstract, keywords
```

代码会自动使用表格中实际存在的列。如果三列都不存在，会报错。

可以用 `--columns` 指定筛选列：

```powershell
python -m src.pipeline.cli filter `
  --input data/all_papers/all_papers.xlsx `
  --keywords emotion `
  --columns title abstract
```

## 匹配逻辑

默认逻辑是“任意关键词命中即可保留”，且不区分大小写。

例如：

```powershell
python -m src.pipeline.cli filter `
  --input data/all_papers/all_papers.xlsx `
  --keywords emotion affect
```

只要 `emotion` 或 `affect` 任意一个出现在目标列中，就会保留该论文。

如果要求所有关键词都命中：

```powershell
python -m src.pipeline.cli filter `
  --input data/all_papers/all_papers.xlsx `
  --keywords emotion facial `
  --match-all
```

如果要启用正则：

```powershell
python -m src.pipeline.cli filter `
  --input data/all_papers/all_papers.xlsx `
  --keywords "emotion(al)?" "affect(ive)?" `
  --regex
```

如果要区分大小写：

```powershell
python -m src.pipeline.cli filter `
  --input data/all_papers/all_papers.xlsx `
  --keywords FER `
  --case-sensitive
```

## 类型过滤

对于 OpenReview 来源，`type` 通常会包含：

```text
oral, spotlight, poster
```

可以用 `--types` 进一步限制投稿类型：

```powershell
python -m src.pipeline.cli filter `
  --input data/all_papers/all_papers.xlsx `
  --keywords emotion `
  --types oral,spotlight
```

默认类型列为 `type`。如果输入表使用其他列名：

```powershell
python -m src.pipeline.cli filter `
  --input data/all_papers/all_papers.xlsx `
  --keywords emotion `
  --types oral,poster `
  --type-column paper_type
```

类型匹配会去除首尾空格并转小写。

## 输出字段

输出表会保留原始输入列，并新增：

```text
matched_keywords
download_status
pdf_path
parse_status
parsed_dir
report_status
report_path
```

字段含义：

| 字段 | 说明 |
| --- | --- |
| `matched_keywords` | 当前论文实际命中的关键词，多个关键词用逗号分隔。 |
| `download_status` | PDF 下载状态，初始为 `pending`，下载后更新为 `downloaded` 或 `missing`。 |
| `pdf_path` | 下载阶段推断或写入的本地 PDF 路径。 |
| `parse_status` | MinerU 解析状态，初始为 `pending`，解析成功后为 `parsed`。 |
| `parsed_dir` | 当前论文 MinerU 解析结果目录。 |
| `report_status` | 总结状态，初始为 `pending`，总结成功后为 `reported`。 |
| `report_path` | 最终 blog Markdown 路径。 |

这些状态列由 `ensure_status_columns` 统一补齐，是后续 `download`、`parse`、`summarize` 更新状态的依据。

## 参数说明

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--input` | 是 | 输入元数据表，支持 Excel/CSV。 |
| `--output` | 否 | 输出筛选表。默认 `data/filtered_papers/filtered_papers.xlsx`。 |
| `--keywords` | 是 | 一个或多个关键词或正则模式。 |
| `--columns` | 否 | 指定搜索列。默认从 `title`、`abstract`、`keywords` 中选择存在的列。 |
| `--match-all` | 否 | 要求所有关键词都命中。 |
| `--regex` | 否 | 将关键词当作正则表达式。 |
| `--case-sensitive` | 否 | 区分大小写。 |
| `--types` | 否 | 允许的论文类型，逗号分隔。 |
| `--type-column` | 否 | 类型列名，默认 `type`。 |

## 旧版标题过滤脚本

`src/paper_filter/keyword_filter.py` 是旧版脚本，只在 CSV 文件标题中搜索单个关键词，并按会议年份匹配文件名。

示例：

```powershell
python src/paper_filter/keyword_filter.py `
  --input-dir data `
  --output-dir filtered_data `
  --keyword emotion `
  --conference-name ICLR `
  --conference-year 2026
```

新流水线建议优先使用：

```powershell
python -m src.pipeline.cli filter ...
```

原因是新阶段支持 Excel、跨列匹配、多关键词、正则、状态列和类型过滤。

## 常见问题

如果报错 `No filter columns found`，说明输入表中没有 `title`、`abstract`、`keywords`，需要用 `--columns` 指定实际列名。

如果报错 `Missing filter columns`，说明 `--columns` 指定了不存在的列，检查表头拼写。

如果使用 `--regex`，关键词会直接传给 Python `re.search`。复杂模式建议先小范围验证，避免误匹配过多论文。

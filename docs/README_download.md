# Download 阶段说明

`download` 阶段负责读取筛选后的论文表，根据 `url` 字段批量下载 PDF，并回写下载状态。它通常接在 `filter` 阶段之后运行。

对应代码：

- 阶段入口：`src/paper_downloader/stage.py`
- 下载实现：`src/paper_downloader/paper_download.py`
- 状态列维护：`src/pipeline/common.py`

## 基本命令

```powershell
python -m src.pipeline.cli download `
  --input data/filtered_papers/filtered_papers.xlsx `
  --conference ICLR `
  --year 2026
```

默认下载目录：

```text
data/pdfs/
```

指定下载目录：

```powershell
python -m src.pipeline.cli download `
  --input data/filtered_papers/filtered_papers.xlsx `
  --output-dir data/pdfs `
  --conference ICLR `
  --year 2026
```

## 输入表格

输入支持：

```text
.xlsx, .xls, .csv
```

必须包含：

```text
url
```

建议包含：

```text
title
```

`title` 用于生成 PDF 文件名。如果缺失，会退化为 `unknown_title`。

## 文件命名规则

下载后的 PDF 文件名格式：

```text
{year}_{conference}_{sanitized_title}.pdf
```

示例：

```text
2026_ICLR_AUHead_AU-Guided_Talking_Head_Generation.pdf
```

文件名清洗规则：

- 替换 Windows 不支持的字符：`\ / : * ? " < > |`
- 去掉末尾空格和句点。
- 标题最长保留 200 个字符。

这部分由 `sanitize_filename` 实现。

## URL 处理

下载前会对部分平台链接做适配：

- OpenReview forum 链接会转换为 PDF 链接：`forum` -> `pdf`。
- AAAI/OJS 的 `article/view` 链接会尝试转换为 `article/download`。

请求会携带常见浏览器请求头，以减少 403 问题。

## 并发下载

默认并发数为 5：

```powershell
python -m src.pipeline.cli download `
  --input data/filtered_papers/filtered_papers.xlsx `
  --conference ICLR `
  --year 2026 `
  --workers 5
```

网络不稳定或目标站点限流时，可以降低：

```powershell
python -m src.pipeline.cli download `
  --input data/filtered_papers/filtered_papers.xlsx `
  --conference ICLR `
  --year 2026 `
  --workers 2
```

## 会议和年份推断

`download` 需要会议名和年份来生成文件名。

推荐显式传入：

```powershell
--conference ICLR --year 2026
```

如果省略，代码会尝试从输入文件名中推断，匹配模式类似：

```text
iclr2026_metadata.xlsx
ICLR_2026.xlsx
```

如果无法推断，会提示显式传入 `--conference` 和 `--year`。

## 状态表回写

下载完成后，阶段会更新输入表中的这些列：

```text
download_status, pdf_path
```

状态值：

| 值 | 说明 |
| --- | --- |
| `downloaded` | 目标 PDF 文件存在。 |
| `missing` | 按命名规则未找到目标 PDF，通常表示下载失败或 URL 缺失。 |

`pdf_path` 会写入按文件名规则推断出的本地路径。后续 `parse` 和 `summarize` 阶段会用 PDF 文件名与状态表行进行匹配。

## 参数说明

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--input` | 是 | 筛选后的论文表，支持 Excel/CSV。 |
| `--output-dir` | 否 | PDF 下载目录，默认 `data/pdfs`。 |
| `--conference` | 否 | 会议名。建议显式传入。 |
| `--year` | 否 | 会议年份。建议显式传入。 |
| `--workers` | 否 | 并发下载线程数，默认 5。 |

## 旧版下载脚本

仍可以直接使用下载实现脚本：

```powershell
python src/paper_downloader/paper_download.py `
  --csv-path data/filtered_papers/example.csv `
  --output-dir data/pdfs `
  --workers 5
```

旧版脚本只支持 CSV，并从文件名中推断会议和年份。新流水线建议使用：

```powershell
python -m src.pipeline.cli download ...
```

因为新阶段支持 Excel 输入，并会回写状态表。

## 常见问题

如果报错缺少 `url` 列，说明输入表不是标准 fetch/filter 输出，需要补充 PDF 链接列。

如果部分论文下载失败，优先检查：

- `url` 是否为可直接访问的 PDF。
- 目标网站是否需要登录或验证码。
- 是否被限流，必要时降低 `--workers`。

如果 PDF 已存在，下载函数会直接跳过并视为成功。

# Fetch 阶段说明

`fetch` 阶段负责从会议官网或 OpenReview 抓取论文元数据，并写入统一的表格文件。它是后续关键词筛选、PDF 下载、解析和总结的起点。

对应代码：

- 阶段入口：`src/paper_fetch/stage.py`
- OpenReview 抓取：`src/paper_fetch/openreview_scraper.py`
- OpenAccess/DBLP/ECVA 抓取：`src/paper_fetch/paper_scraper.py`
- CLI 入口：`src/pipeline/cli.py`

## 基本命令

```powershell
python -m src.pipeline.cli fetch --conference ICLR --year 2026 --source openreview
```

也可以让系统按会议自动选择来源：

```powershell
python -m src.pipeline.cli fetch --conference CVPR --year 2025 --source auto
```

默认输出：

```text
data/all_papers/all_papers.xlsx
```

如果需要指定输出位置：

```powershell
python -m src.pipeline.cli fetch `
  --conference ICLR `
  --year 2026 `
  --source openreview `
  --output data/all_papers/iclr2026.xlsx
```

## 数据来源选择

`--source` 支持三个值：

- `auto`：默认策略。`ICLR`、`ICML`、`NEURIPS` 使用 OpenReview，其余会议使用 openaccess 抓取逻辑。
- `openreview`：使用 OpenReview API，适合 ICLR、ICML、NeurIPS 等会议。
- `openaccess`：使用网页抓取逻辑，覆盖 CVPR、ICCV、ECCV、AAAI、ACMMM 等来源。

自动来源判断在 `src/pipeline/common.py` 的 `resolve_source` 中实现，目前 OpenReview 会议集合为：

```text
ICLR, ICML, NEURIPS
```

## OpenReview 抓取

OpenReview 抓取需要 `.env` 中配置账号：

```dotenv
OPENREVIEW_USERNAME=your_openreview_username
OPENREVIEW_PASSWORD=your_openreview_password
```

默认 venue 规则：

```text
{CONFERENCE}.cc/{YEAR}/Conference
```

例如：

```text
ICLR.cc/2026/Conference
```

如果会议 venue 不符合默认规则，可以显式传入：

```powershell
python -m src.pipeline.cli fetch `
  --conference ICLR `
  --year 2026 `
  --source openreview `
  --venue ICLR.cc/2026/Conference
```

OpenReview API 默认地址为：

```text
https://api2.openreview.net
```

可以用 `--baseurl` 覆盖。

OpenReview 输出字段：

```text
paper_id, title, type, keywords, abstract, url
```

其中：

- `paper_id`：OpenReview note id。
- `title`：论文标题。
- `type`：根据 venue 字段归一化为 `oral`、`spotlight`、`poster` 或其他原始类型。
- `keywords`：OpenReview keywords 列表合并后的字符串。
- `abstract`：摘要。
- `url`：OpenReview PDF 链接，格式为 `https://openreview.net/pdf?id=...`。

## OpenAccess/DBLP/ECVA 抓取

`openaccess` 来源通过 Selenium 打开会议页面，然后解析论文标题和 PDF 链接。当前实现使用 `webdriver.Edge()`，因此本机需要可用的 Edge 浏览器和对应 WebDriver。

当前 URL 构造规则：

| 会议 | 默认 URL |
| --- | --- |
| `CVPR` | `https://openaccess.thecvf.com/CVPR{year}?day=all` |
| `ICCV` | `https://openaccess.thecvf.com/ICCV{year}?day=all` |
| `ECCV` | `https://www.ecva.net/papers.php` |
| `AAAI` | `https://dblp.uni-trier.de/db/conf/aaai/aaai{year}.html` |
| `ACMMM` | `https://dblp.uni-trier.de/db/conf/mm/mm{year}.html` |

如果默认 URL 失效，可以用 `--url` 覆盖：

```powershell
python -m src.pipeline.cli fetch `
  --conference CVPR `
  --year 2025 `
  --source openaccess `
  --url "https://openaccess.thecvf.com/CVPR2025?day=all"
```

OpenAccess 输出字段同样为：

```text
paper_id, title, type, keywords, abstract, url
```

当前实现中：

- `paper_id`：按抓取顺序生成。
- `type`：默认写入会议名。
- `keywords`：来自 `--patterns` 对标题的正则匹配结果，只做记录，不做过滤。
- `abstract`：网页抓取路径通常为空。
- `url`：PDF 链接。

## 参数说明

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--conference` | 是 | 会议名，会转为大写，例如 `ICLR`、`CVPR`。 |
| `--year` | 是 | 会议年份，例如 `2026`。 |
| `--source` | 否 | `auto`、`openreview` 或 `openaccess`，默认 `auto`。 |
| `--output` | 否 | 输出表格路径，支持 `.xlsx`、`.csv`。不带后缀时自动补 `.xlsx`。 |
| `--url` | 否 | 覆盖 openaccess 抓取页面 URL。 |
| `--venue` | 否 | 覆盖 OpenReview venue。 |
| `--baseurl` | 否 | 覆盖 OpenReview API base URL。 |
| `--patterns` | 否 | 一个或多个正则表达式，只用于记录标题命中的关键词。 |

## 与后续阶段的关系

`fetch` 的输出会作为 `filter` 阶段的输入。后续阶段默认使用这些字段：

- `title`：关键词过滤、PDF 文件命名、报告元数据标题推断。
- `abstract`：关键词过滤、报告简介推断。
- `keywords`：关键词过滤、报告标签推断。
- `type`：投稿类型过滤。
- `url`：PDF 下载。

如果自定义抓取结果，至少应保留：

```text
title, url
```

建议保留：

```text
paper_id, title, type, keywords, abstract, url
```

## 常见问题

OpenReview 报错缺少账号时，检查 `.env`：

```dotenv
OPENREVIEW_USERNAME=...
OPENREVIEW_PASSWORD=...
```

网页抓取失败时，优先检查：

- 本机是否安装可用的 Edge 浏览器和 WebDriver。
- 默认会议 URL 是否已经变更。
- 目标页面是否需要登录、验证码或网络代理。

AAAI/ACMMM 通过 DBLP 链接进一步寻找 PDF。遇到 ACM 反爬或 OJS 页面结构变化时，可能抓不到部分 PDF，需要用 `--url` 或手工补充 `url` 字段。

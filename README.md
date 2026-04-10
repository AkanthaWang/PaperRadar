# PaperRadar 🚀

PaperRadar 是一个轻量级工具，旨在帮助研究人员高效地从各大顶级学术会议（如 CVPR, ICCV, ECCV, NeurIPS, ICLR, ICML, AAAI 等）抓取论文元数据，并根据关键词进行快速过滤。

## ✨ 主要功能

- **多会议支持**：支持从 OpenReview、CVF、ECVA 和 DBLP 等平台抓取论文。
- **元数据提取**：自动提取论文 ID、标题、类型（Oral/Poster/Spotlight）、关键词、摘要及 PDF 链接。
- **关键词过滤**：支持对已抓取的论文数据进行二次过滤，快速锁定感兴趣的研究方向。
- **分类统计**：针对部分会议（如 NeurIPS/ICLR/ICML）支持按投稿类型进行筛选。

## 📊 支持的会议列表

| 来源平台 | 支持会议 | 抓取脚本 |
| :--- | :--- | :--- |
| **OpenReview** | NeurIPS, ICLR, ICML | `src/openreview_scraper.py` |
| **CVF / ECVA** | CVPR, ICCV, ECCV | `src/paper_scraper.py` |
| **DBLP** | AAAI, ACMMM | `src/paper_scraper.py` |

## 📂 项目结构

```text
PaperRadar/
├── data/               # 存放抓取的原始 CSV 数据
├── filtered_data/      # 存放过滤后的 CSV 数据
├── src/                # 源代码目录
│   ├── openreview_scraper.py  # OpenReview 平台抓取工具
│   ├── paper_scraper.py       # CVF/DBLP/ECVA 平台抓取工具
│   ├── keyword_filter.py      # 论文关键词过滤工具
│   └── paper_download.py      # 论文 PDF 批量下载工具
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
   pip install pandas requests beautifulsoup4 selenium openreview-py lxml python-dotenv
   ```

3. **浏览器驱动**（仅针对 `paper_scraper.py`）：
   确保已安装 Chrome 浏览器及其对应的 [ChromeDriver](https://chromedriver.chromium.org/downloads)。

## 🚀 使用指南

### 1. 抓取 OpenReview 会议论文 (NeurIPS/ICLR/ICML)
使用 `src/openreview_scraper.py` 抓取数据：
```bash
python src/openreview_scraper.py --conference_name NeurIPS --conference_year 2024
```
*输出文件将保存至 `data/neurips2024_metadata.csv`。*

### 2. 抓取其他会议论文 (CVPR/ICCV/ECCV/AAAI)
使用 `src/paper_scraper.py` 抓取（请根据脚本内定义的会议名进行操作）：
```bash
python src/paper_scraper.py --conference CVPR --year 2023
```

### 3. 按关键词过滤论文
使用 `src/keyword_filter.py` 对 `data` 目录下的 CSV 文件进行过滤：
```bash
python src/keyword_filter.py --keyword "emotion" --conference-name AAAI --conference-year 2025
```
*过滤后的结果将保存至 `filtered_data/` 目录下。*

### 4. 下载论文 PDF
使用 `src/paper_download.py` 根据抓取的元数据批量下载论文（脚本会自动从 CSV 文件名中提取会议和年份）：
```bash
python src/paper_download.py --csv-path data/neurips2025_metadata.csv
```
*下载的 PDF 将按 `年份_会议_标题.pdf` 格式保存至 `downloads/` 目录。*

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

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

## 📂 项目结构

```text
PaperRadar/
├── data/               # 存放抓取的原始 CSV 数据
├── filtered_data/      # 存放过滤后的 CSV 数据
├── src/                # 源代码目录
│   ├── openreview_scraper.py  # OpenReview 平台抓取工具
│   ├── paper_scraper.py       # CVF/DBLP/ECVA 平台抓取工具
│   └── keyword_filter.py      # 论文关键词过滤工具
└── README.md
```

## 📝 注意事项

- **API 限制**：抓取 OpenReview 数据时，建议配置环境变量 `OPENREVIEW_USERNAME` 和 `OPENREVIEW_PASSWORD`。
- **网络环境**：抓取部分海外学术网站（如 CVF）可能需要稳定的网络环境。
- **合法合规**：请在遵守各大学术平台 Robots 协议的前提下使用本工具，仅限科研学术用途。

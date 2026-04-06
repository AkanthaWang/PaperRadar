# Conference Downloads

本项目旨在快速获取最新顶会论文数据，并根据关键词进行筛选。

---

## 📌 数据爬取模块

使用 OpenReview 官方 API 自动爬取指定会议的投稿元数据（如标题、摘要、关键词等），结果保存在结构化的 CSV 文件，位于 `data/` 目录中。
（仅支持ICML、ICLR、NeurIPS）



AAAI有自己的网站
CVPR、ICCV、ECCV也有自己的网站）


## 🛠 使用教程

1. `git clone` 本仓库  
2. 配置 OpenReview 账号环境变量（Windows PowerShell 示例）：  
   `$env:OPENREVIEW_USERNAME="你的邮箱"`  
   `$env:OPENREVIEW_PASSWORD="你的密码"`  
3. 运行 `utils/` 目录下的抓取脚本：  
   `python utils/openreview_scraper.py --venue ICML.cc/2025/Conference --output ./data/icml2025_openreview.csv`  
   （可按需替换会议和输出路径）  
4. F5 运行 `utils/` 目录下的 `openreview_analyzer.py`，静候 `output/` 中出现主题分析结果  
   （效果很差，不建议使用）

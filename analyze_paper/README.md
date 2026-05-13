# Analyze Paper

`analyze_paper` 用于解析 `downloads/` 目录下的论文 PDF，抽取论文文本和原图，并调用 vivo 蓝心大模型 API 生成结构化 Markdown 论文解读。

生成内容包括：

- 一句话总结
- 核心问题
- 核心动机
- 数据集
- 方法
- 实验
- 主要贡献
- 适合引用的观点
- 可能的局限
- 后续可关注问题
- 论文原图

## 目录结构

```text
analyze_paper/
├── analyze.py          # 命令行入口
├── config.py           # 路径、环境变量、模型参数配置
├── llm_client.py       # vivo BlueLM API 客户端
├── md_writer.py        # Markdown 报告写入
├── pdf_parser.py       # PDF 文本和图片解析
├── prompts.py          # 论文分析提示词
├── vivo_auth.py        # vivo AI 网关签名
├── .env.example        # 环境变量示例
├── assets/             # 抽取出的论文图片，运行时生成
├── cache/              # 解析和运行缓存，运行时生成
└── outputs/            # Markdown 报告，运行时生成
```

## 安装依赖

```bash
pip install pymupdf requests python-dotenv tqdm
```

其中：

- `pymupdf`：解析 PDF 文本和图片
- `requests`：调用 vivo API
- `python-dotenv`：从仓库根目录 `.env` 读取密钥
- `tqdm`：批量处理进度条，可选

## 配置 API

在仓库根目录 `.env` 中加入：

```text
PAPER_ANALYZER_APP_ID=your_vivo_app_id
PAPER_ANALYZER_APP_KEY=your_vivo_app_key
PAPER_ANALYZER_MODEL=vivo-BlueLM-TB-Pro
PAPER_ANALYZER_DOMAIN=api-ai.vivo.com.cn
PAPER_ANALYZER_URI=/vivogpt/completions
PAPER_ANALYZER_MAX_IMAGES=8
PAPER_ANALYZER_MAX_CHARS=60000
PAPER_ANALYZER_TIMEOUT=120
PAPER_ANALYZER_TEMPERATURE=0.2
```

也可以参考 `analyze_paper/.env.example`。

注意：不要把真实 AppKEY 写入源码或 README。当前实现只会从环境变量或 `.env` 读取密钥。

## 使用方式

分析 `downloads/` 下所有 PDF：

```bash
python analyze_paper/analyze.py
```

只分析一篇论文：

```bash
python analyze_paper/analyze.py --pdf "D:\Github\PaperRadar\downloads\A 2026_ICLR_Customizing Visual Emotion Evaluation for MLLMs_ An Open-vocabulary, Multifaceted, and Scalable Approach.pdf"
```

限制批量数量：

```bash
python analyze_paper/analyze.py --limit 5
```

覆盖已生成报告：

```bash
python analyze_paper/analyze.py --overwrite
```

只测试 PDF 解析和 Markdown 写入，不调用 API：

```bash
python analyze_paper/analyze.py --limit 1 --no-api --overwrite
```

单独测试 vivo LLM 是否配置成功：

```bash
python analyze_paper/vivo_llm_example.py
```

## 输出位置

默认输出：

```text
analyze_paper/outputs/{paper_stem}.md
analyze_paper/assets/{paper_stem}/figure_01.png
analyze_paper/cache/{paper_stem}.json
```

Markdown 中会使用相对路径插入原图，例如：

```markdown
![Figure 1](../assets/paper_name/figure_01.png)
```

## 实现流程

1. 扫描 PDF

   默认读取 `downloads/*.pdf`，不会递归进入 `downloads/code/`。

2. 解析 PDF

   `pdf_parser.py` 使用 PyMuPDF 完成：

   - 每页文本抽取
   - 元信息读取
   - 年份、会议、标题的文件名推断
   - 图片抽取、尺寸过滤、hash 去重
   - 根据 Figure/Table 上下文优先保留关键图

3. 构造 Prompt

   `prompts.py` 会把论文文本、标题、会议年份、图表线索整理成模型输入。短论文直接生成最终报告；长论文会先按片段总结，再合并成最终报告。

4. 调用 vivo BlueLM

   `llm_client.py` 调用 `https://api-ai.vivo.com.cn/vivogpt/completions`，并通过 `vivo_auth.py` 生成 vivo AI 网关签名头：

   - `X-AI-GATEWAY-APP-ID`
   - `X-AI-GATEWAY-TIMESTAMP`
   - `X-AI-GATEWAY-NONCE`
   - `X-AI-GATEWAY-SIGNED-HEADERS`
   - `X-AI-GATEWAY-SIGNATURE`

   `vivo_llm_example.py` 提供了一个最小调用示例，用于先验证 AppID、AppKEY、模型名和网络是否可用。

5. 写入 Markdown

   `md_writer.py` 生成最终 `.md` 文件，并把抽取出来的原图插入到报告末尾的“论文原图”部分。

## 常用参数

```bash
python analyze_paper/analyze.py \
  --downloads-dir downloads \
  --outputs-dir analyze_paper/outputs \
  --assets-dir analyze_paper/assets \
  --cache-dir analyze_paper/cache \
  --max-images 8 \
  --max-chars 60000
```

## 注意事项

- 如果报告已存在，默认会跳过；使用 `--overwrite` 可重新生成。
- 如果 API 调用失败，会在 `cache/{paper_stem}.json` 记录错误。
- 当前图片抽取是启发式筛选，能保留论文原图，但不保证每张图都有精确 caption。
- 终端里如果中文显示乱码，通常是 PowerShell 编码问题；生成的 Markdown 文件按 UTF-8 写入。
- 如果论文是扫描版 PDF，当前版本不会 OCR，需要后续接入 OCR。

## 后续可增强

- 接入 OCR 处理扫描版论文
- 使用多模态模型直接分析论文图表
- 结合 `data/*.csv` 元数据补全论文链接和代码链接
- 自动生成 `outputs/index.md`
- 对同一会议或同一主题论文生成横向对比报告

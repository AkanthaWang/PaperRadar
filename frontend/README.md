# PaperRadar Frontend

这是一个本地 Web 控制台，用于浏览 `data/reports` 下已经生成的论文报告，也可以选择 PDF 文件或目录，触发 MinerU 解析和 LLM 中文总结。

从项目根目录启动：

```powershell
npm run dev
```

如果 PowerShell 拦截 `npm.ps1`，使用：

```powershell
npm.cmd run dev
```

然后访问终端输出的地址，默认是：

```text
http://127.0.0.1:5173/
```

如果 5173 被占用，服务会自动尝试后续端口，例如 `http://127.0.0.1:5174/`。

数据约定：

- `data/reports/all_reports.json`：论文列表和筛选元数据。
- `data/reports/data/*.json`：单篇论文 JSON。
- `data/reports/blog/*.md`：单篇论文 Markdown 报告。
- `data/reports/img/*`：报告中引用的图像。

任务运行：

- 在“任务运行”页选择 PDF 文件、选择目录，或使用默认目录 `data/pdfs`。
- 选择本机文件/目录时，浏览器会先把 PDF 上传到本地服务的 `data/uploads/jobs/` 临时目录，再启动处理。
- 可以先点“检测路径”确认 PDF 数量和示例文件。
- 后端会逐个 PDF 执行 `python -u -m src.pipeline.cli summarize --parse-missing --pdf ...`，缺少 MinerU 解析时会自动补解析。
- 页面会展示当前文件、MinerU/总结阶段、进度、完成数量、失败数量和 stdout/stderr 日志。
- “扫描子目录”会递归查找 PDF；“覆盖已有解析和报告”会传递 `--overwrite`。
- 运行中可以点“取消任务”停止后续文件处理。

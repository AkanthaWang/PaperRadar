"use strict";

const CONFIG = window.PAPER_RADAR_CONFIG || {};
const API_BASE = CONFIG.API_BASE_URL || "";

function apiUrl(path) {
  if (path.startsWith("/")) path = path.slice(1);
  return API_BASE ? `${API_BASE}/${path}` : `/${path}`;
}

const state = {
  reports: [],
  filtered: [],
  selectedId: null,
  query: "",
  venue: "all",
  year: "all",
  modality: "all",
  tag: "all",
  sort: "recent",
  density: "comfortable",
  view: "runner",
  currentJobId: null,
  jobPollTimer: null,
  sourceMode: "files",
  selectedFiles: [],
  markdownCache: new Map(),
  currentMarkdownHtml: "",
};

const els = {
  status: document.querySelector("#data-status"),
  filtersToolbar: document.querySelector("#filters-toolbar"),
  search: document.querySelector("#search-input"),
  venue: document.querySelector("#venue-filter"),
  year: document.querySelector("#year-filter"),
  modality: document.querySelector("#modality-filter"),
  tag: document.querySelector("#tag-filter"),
  sort: document.querySelector("#sort-select"),
  paperList: document.querySelector("#paper-list"),
  resultCount: document.querySelector("#result-count"),
  resetFilters: document.querySelector("#reset-filters"),
  paperDetail: document.querySelector("#paper-detail"),
  detailMetaLine: document.querySelector("#detail-meta-line"),
  detailTitle: document.querySelector("#detail-title"),
  detailFullTitle: document.querySelector("#detail-full-title"),
  detailTags: document.querySelector("#detail-tags"),
  detailIntro: document.querySelector("#detail-introduction"),
  blogLink: document.querySelector("#blog-link"),
  jsonLink: document.querySelector("#json-link"),
  reportState: document.querySelector("#report-state"),
  reportContent: document.querySelector("#report-content"),
  focusReportContent: document.querySelector("#focus-report-content"),
  reportNav: document.querySelector("#report-nav"),
  reloadReport: document.querySelector("#reload-report"),
  libraryView: document.querySelector("#library-view"),
  reportView: document.querySelector("#report-view"),
  focusTitle: document.querySelector("#focus-title"),
  backToLibrary: document.querySelector("#back-to-library"),
  runnerView: document.querySelector("#runner-view"),
  jobForm: document.querySelector("#job-form"),
  pdfFiles: document.querySelector("#pdf-files"),
  pdfDirectory: document.querySelector("#pdf-directory"),
  pickFiles: document.querySelector("#pick-files"),
  pickDirectory: document.querySelector("#pick-directory"),
  selectedSource: document.querySelector("#selected-source"),
  llmProvider: document.querySelector("#llm-provider"),
  ecnuModel: document.querySelector("#ecnu-model"),
  jobLimit: document.querySelector("#job-limit"),
  outputsDir: document.querySelector("#outputs-dir"),
  reportsDir: document.querySelector("#reports-dir"),
  overwrite: document.querySelector("#overwrite"),
  recursive: document.querySelector("#recursive"),
  useDefaultPath: document.querySelector("#use-default-path"),
  checkPath: document.querySelector("#check-path"),
  jobTitle: document.querySelector("#job-title"),
  jobStage: document.querySelector("#job-stage"),
  jobProgressBar: document.querySelector("#job-progress-bar"),
  jobProgressText: document.querySelector("#job-progress-text"),
  jobParsed: document.querySelector("#job-parsed"),
  jobCompleted: document.querySelector("#job-completed"),
  jobTotal: document.querySelector("#job-total"),
  jobFailed: document.querySelector("#job-failed"),
  jobCurrentFile: document.querySelector("#job-current-file"),
  jobCommand: document.querySelector("#job-command"),
  jobLog: document.querySelector("#job-log"),
  clearLog: document.querySelector("#clear-log"),
  cancelJob: document.querySelector("#cancel-job"),
  navItems: document.querySelectorAll(".nav-item"),
  densityButtons: document.querySelectorAll("[data-density]"),
};

init();

async function init() {
  bindEvents();
  switchView(state.view);
  setStatus("正在加载报告数据", "loading");

  try {
    const reports = await loadReports();
    state.reports = reports.map(normalizeReport).filter((report) => report.id);
    populateFilters();
    applyFilters();

    setStatus(`已加载 ${state.reports.length} 篇报告`, "ready");
  } catch (error) {
    console.error(error);
    setStatus("数据加载失败，请从项目根目录启动静态服务", "error");
    els.paperList.innerHTML = `
      <div class="empty-list">
        无法读取 <code>data/reports/all_reports.json</code>。<br />
        请在项目根目录运行 <code>python -m http.server 5173</code> 后访问
        <code>http://127.0.0.1:5173/frontend/</code>。
      </div>
    `;
  }
}

function bindEvents() {
  els.search.addEventListener("input", (event) => {
    state.query = event.target.value.trim().toLowerCase();
    applyFilters();
  });

  for (const [key, element] of [
    ["venue", els.venue],
    ["year", els.year],
    ["modality", els.modality],
    ["tag", els.tag],
  ]) {
    element.addEventListener("change", (event) => {
      state[key] = event.target.value;
      applyFilters();
    });
  }

  els.sort.addEventListener("change", (event) => {
    state.sort = event.target.value;
    applyFilters();
  });

  els.resetFilters.addEventListener("click", () => {
    state.query = "";
    state.venue = "all";
    state.year = "all";
    state.modality = "all";
    state.tag = "all";
    state.sort = "recent";
    els.search.value = "";
    els.venue.value = "all";
    els.year.value = "all";
    els.modality.value = "all";
    els.tag.value = "all";
    els.sort.value = "recent";
    applyFilters();
  });

  els.paperList.addEventListener("click", (event) => {
    const card = event.target.closest("[data-paper-id]");
    if (!card) return;
    selectPaper(card.dataset.paperId, { loadReport: true });
  });

  els.paperList.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const card = event.target.closest("[data-paper-id]");
    if (!card) return;
    event.preventDefault();
    selectPaper(card.dataset.paperId, { loadReport: true });
  });

  els.reloadReport.addEventListener("click", () => {
    if (!state.selectedId) return;
    state.markdownCache.delete(state.selectedId);
    loadSelectedReport();
  });

  els.backToLibrary.addEventListener("click", () => switchView("library"));

  els.pickFiles.addEventListener("click", () => els.pdfFiles.click());
  els.pickDirectory.addEventListener("click", () => els.pdfDirectory.click());
  els.pdfFiles.addEventListener("change", () => {
    setSourceFiles("files", [...els.pdfFiles.files]);
  });
  els.pdfDirectory.addEventListener("change", () => {
    setSourceFiles("directory", [...els.pdfDirectory.files]);
  });
  els.useDefaultPath.addEventListener("click", () => {
    setDefaultSource();
  });

  els.checkPath.addEventListener("click", checkSourcePath);

  els.clearLog.addEventListener("click", () => {
    els.jobLog.textContent = "";
  });

  els.cancelJob.addEventListener("click", cancelCurrentJob);

  els.jobForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitJob();
  });

  els.navItems.forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.view));
  });

  els.densityButtons.forEach((button) => {
    button.addEventListener("click", () => {
      state.density = button.dataset.density;
      els.densityButtons.forEach((item) => item.classList.toggle("is-active", item === button));
      els.paperList.classList.toggle("is-compact", state.density === "compact");
    });
  });
}

async function loadReports() {
  const dataPaths = [apiUrl("api/reports")];
  if (!API_BASE) {
    dataPaths.push("../data/reports/all_reports.json");
    dataPaths.push("/data/reports/all_reports.json");
  } else {
    dataPaths.push(apiUrl("data/reports/all_reports.json"));
  }

  let lastError;

  for (const path of dataPaths) {
    try {
      const response = await fetch(path, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`${path} returned ${response.status}`);
      }
      const data = await response.json();
      const items = Array.isArray(data) ? data : data.items;
      if (!Array.isArray(items)) {
        throw new Error(`${path} is not an array`);
      }
      return items;
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError || new Error("No report data path succeeded");
}

function normalizeReport(report, index) {
  const id = String(report.id || report.blog?.slug?.split("/").pop() || `paper-${index + 1}`);
  const tags = Array.isArray(report.tags)
    ? report.tags.map((tag) => String(tag).trim()).filter(Boolean)
    : [];

  return {
    id,
    title: cleanText(report.title || report.fullTitle || id),
    fullTitle: cleanText(report.fullTitle || report.title || id),
    year: Number(report.year) || null,
    category: cleanText(report.category || "Uncategorized"),
    type: cleanText(report.type || "Unknown"),
    modality: cleanText(report.modality || "unknown"),
    tags,
    introduction: cleanText(report.introduction || ""),
    venue: cleanText(report.venue || "Unknown"),
    blog: report.blog || { enabled: false, slug: `/blog/${id}` },
  };
}

function populateFilters() {
  setOptions(els.venue, "全部会议", uniqueValues(state.reports.map((report) => report.venue)));
  setOptions(
    els.year,
    "全部年份",
    uniqueValues(state.reports.map((report) => report.year).filter(Boolean)).sort((a, b) => b - a),
  );
  setOptions(els.modality, "全部模态", uniqueValues(state.reports.map((report) => report.modality)));

  const tagCounts = new Map();
  state.reports.forEach((report) => {
    report.tags.forEach((tag) => tagCounts.set(tag, (tagCounts.get(tag) || 0) + 1));
  });
  const tags = [...tagCounts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([tag]) => tag);
  setOptions(els.tag, "全部标签", tags);
}

function setOptions(select, label, values) {
  select.innerHTML = "";
  select.append(new Option(label, "all"));
  values.forEach((value) => select.append(new Option(String(value), String(value))));
}

function applyFilters() {
  const query = state.query;
  const previousSelectedId = state.selectedId;

  state.filtered = state.reports
    .filter((report) => {
      const haystack = [
        report.title,
        report.fullTitle,
        report.introduction,
        report.venue,
        report.modality,
        ...report.tags,
      ]
        .join(" ")
        .toLowerCase();

      return (
        (!query || haystack.includes(query)) &&
        (state.venue === "all" || report.venue === state.venue) &&
        (state.year === "all" || String(report.year) === state.year) &&
        (state.modality === "all" || report.modality === state.modality) &&
        (state.tag === "all" || report.tags.includes(state.tag))
      );
    })
    .sort(sortReports);

  if (!state.filtered.some((report) => report.id === state.selectedId) && state.filtered[0]) {
    state.selectedId = state.filtered[0].id;
  }
  if (!state.filtered.length) {
    state.selectedId = null;
    clearDetail();
  }

  renderPaperList();
  if (state.selectedId && state.selectedId !== previousSelectedId) {
    const selected = state.reports.find((report) => report.id === state.selectedId);
    if (selected) {
      renderDetail(selected);
      loadSelectedReport();
    }
  }
}

function sortReports(a, b) {
  if (state.sort === "title") {
    return a.title.localeCompare(b.title);
  }
  if (state.sort === "venue") {
    return a.venue.localeCompare(b.venue) || b.year - a.year || a.title.localeCompare(b.title);
  }
  return (b.year || 0) - (a.year || 0) || a.venue.localeCompare(b.venue) || a.title.localeCompare(b.title);
}

function renderPaperList() {
  els.resultCount.textContent = `${state.filtered.length} 篇论文`;

  if (!state.filtered.length) {
    els.paperList.innerHTML = `<div class="empty-list">没有匹配的论文，调整搜索词或筛选条件。</div>`;
    return;
  }

  els.paperList.innerHTML = state.filtered
    .map((report) => {
      const selected = report.id === state.selectedId;
      const intro = report.introduction || "暂无简介。";
      const tags = report.tags
        .slice(0, 4)
        .map((tag) => `<span class="tag-chip">${escapeHtml(tag)}</span>`)
        .join("");

      return `
        <button
          class="paper-card${selected ? " is-selected" : ""}"
          type="button"
          data-paper-id="${escapeHtml(report.id)}"
          role="option"
          aria-selected="${selected ? "true" : "false"}"
        >
          <div class="paper-card-top">
            <span class="meta-chip is-accent">${escapeHtml(report.venue)}</span>
            <span class="meta-chip">${escapeHtml(report.year || "-")}</span>
          </div>
          <h4>${escapeHtml(report.title)}</h4>
          <p>${escapeHtml(intro)}</p>
          <div class="paper-tags">${tags}</div>
        </button>
      `;
    })
    .join("");
}

function selectPaper(id, options = {}) {
  const report = state.reports.find((item) => item.id === id);
  if (!report) return;

  state.selectedId = id;
  renderPaperList();
  renderDetail(report);
  if (options.loadReport) {
    loadSelectedReport();
  }
}

function renderDetail(report) {
  els.paperDetail.hidden = false;

  els.detailMetaLine.textContent = [report.venue, report.year, report.type, report.modality]
    .filter(Boolean)
    .join(" / ");
  els.detailTitle.textContent = report.title;
  els.detailFullTitle.textContent = report.fullTitle;
  els.detailIntro.textContent = report.introduction || "暂无简介。";
  els.blogLink.href = markdownUrl(report.id);
  els.jsonLink.href = apiUrl(`data/reports/data/${encodeURIComponent(report.id)}.json`);
  els.focusTitle.textContent = report.title;

  const baseChips = [
    `<span class="meta-chip is-warm">${escapeHtml(report.category)}</span>`,
    `<span class="meta-chip">${escapeHtml(report.type)}</span>`,
    `<span class="meta-chip">${escapeHtml(report.modality)}</span>`,
  ];
  const tagChips = report.tags.map((tag) => `<span class="tag-chip">${escapeHtml(tag)}</span>`);
  els.detailTags.innerHTML = [...baseChips, ...tagChips].join("");
}

function clearDetail() {
  els.paperDetail.hidden = true;
  els.reportContent.innerHTML = "";
  els.focusReportContent.innerHTML = "";
  els.reportNav.innerHTML = "";
  els.reportState.textContent = "尚未加载";
}

async function loadSelectedReport() {
  const id = state.selectedId;
  if (!id) return;

  els.reportState.textContent = "正在读取 Markdown";
  els.reportContent.innerHTML = `<div class="loading">正在加载报告内容。</div>`;
  els.reportNav.innerHTML = "";

  try {
    const markdown = await getMarkdown(id);
    const html = renderMarkdown(markdown, id);
    state.currentMarkdownHtml = html;
    els.reportContent.innerHTML = html;
    els.focusReportContent.innerHTML = html;
    renderReportNav(markdown);
    els.reportState.textContent = "已加载 Markdown 报告";
  } catch (error) {
    console.error(error);
    const message = `
      <div class="error">
        未找到 <code>data/reports/blog/${escapeHtml(id)}.md</code>，可先运行 summarize 阶段生成报告。
      </div>
    `;
    state.currentMarkdownHtml = message;
    els.reportContent.innerHTML = message;
    els.focusReportContent.innerHTML = message;
    els.reportState.textContent = "报告读取失败";
  }
}

async function getMarkdown(id) {
  if (state.markdownCache.has(id)) {
    return state.markdownCache.get(id);
  }

  const response = await fetch(markdownUrl(id), { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Markdown not found: ${id}`);
  }
  const text = await response.text();
  state.markdownCache.set(id, text);
  return text;
}

function markdownUrl(id) {
  return apiUrl(`data/reports/blog/${encodeURIComponent(id)}.md`);
}

function markdownPath(id) {
  return markdownUrl(id);
}

function switchView(view) {
  state.view = view;
  const isReport = view === "report";
  const isRunner = view === "runner";

  els.runnerView.hidden = !isRunner;
  els.filtersToolbar.hidden = isReport || isRunner;
  els.libraryView.hidden = isReport || isRunner;
  els.reportView.hidden = !isReport;
  els.navItems.forEach((button) => {
    const active = button.dataset.view === view;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });

  if (isReport && !state.currentMarkdownHtml && state.selectedId) {
    loadSelectedReport();
  }
}

async function submitJob() {
  const payload = {
    llmProvider: els.llmProvider.value,
    ecnuModel: els.ecnuModel.value.trim(),
    limit: els.jobLimit.value ? Number(els.jobLimit.value) : undefined,
    outputsDir: els.outputsDir.value.trim(),
    reportsDir: els.reportsDir.value.trim(),
    overwrite: els.overwrite.checked,
    recursive: els.recursive.checked,
  };

  if (state.sourceMode !== "default" && !state.selectedFiles.length) {
    renderJobError("请先选择 PDF 文件或目录。");
    return;
  }

  setFormRunning(true);
  renderJobPending();

  try {
    const response =
      state.sourceMode === "default"
        ? await fetch(apiUrl("api/jobs"), {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ ...payload, path: "data/pdfs" }),
          })
        : await uploadAndCreateJob(payload);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || data.detail || "任务创建失败");
    }
    state.currentJobId = data.id;
    renderJob(data);
    startJobPolling(data.id);
  } catch (error) {
    setFormRunning(false);
    renderJobError(error.message);
  }
}

async function uploadAndCreateJob(payload) {
  const form = new FormData();
  form.append("payload", JSON.stringify({ ...payload, sourceMode: state.sourceMode }));
  state.selectedFiles.forEach((file) => {
    form.append("pdfs", file, file.webkitRelativePath || file.name);
  });
  return fetch(apiUrl("api/jobs/upload"), {
    method: "POST",
    body: form,
  });
}

function startJobPolling(id) {
  if (state.jobPollTimer) {
    clearInterval(state.jobPollTimer);
  }

  state.jobPollTimer = setInterval(async () => {
    try {
      const response = await fetch(apiUrl(`api/jobs/${encodeURIComponent(id)}`));
      const job = await response.json();
      if (!response.ok) {
        throw new Error(job.error || "任务状态读取失败");
      }
      renderJob(job);
      if (job.status === "completed" || job.status === "failed") {
        clearInterval(state.jobPollTimer);
        state.jobPollTimer = null;
        setFormRunning(false);
        if (job.status === "completed") {
          await refreshLibraryData();
        }
      }
    } catch (error) {
      clearInterval(state.jobPollTimer);
      state.jobPollTimer = null;
      setFormRunning(false);
      renderJobError(error.message);
    }
  }, 1400);
}

function renderJobPending() {
  els.jobTitle.textContent = "正在创建任务";
  els.jobStage.textContent = "queued";
  els.jobProgressBar.style.width = "0%";
  els.jobProgressText.textContent = "0%";
  els.jobCompleted.textContent = "0";
  els.jobParsed.textContent = "0";
  els.jobTotal.textContent = "0";
  els.jobFailed.textContent = "0";
  els.jobCurrentFile.textContent = "尚未选择文件。";
  els.jobCommand.textContent = "等待服务端启动命令。";
  els.jobLog.textContent = "正在提交任务...";
  els.cancelJob.disabled = true;
}

function renderJob(job) {
  const progress = Math.max(0, Math.min(100, Number(job.progress) || 0));
  els.jobTitle.textContent = `${job.statusLabel || statusLabel(job.status)} · ${job.inputType === "directory" ? "目录" : "文件"}`;
  els.jobStage.textContent = stageLabel(job.stage);
  els.jobProgressBar.style.width = `${progress}%`;
  els.jobProgressText.textContent = `${progress}%`;
  els.jobParsed.textContent = String(job.parsed || 0);
  els.jobCompleted.textContent = String(job.completed || 0);
  els.jobTotal.textContent = String(job.pdfCount || 0);
  els.jobFailed.textContent = String(job.failed || 0);
  els.jobCurrentFile.textContent = job.currentFile ? `当前文件：${job.currentFile}` : "尚未选择文件。";
  els.jobCommand.textContent = job.currentCommand || job.command || "尚未启动命令。";
  els.cancelJob.disabled = !(job.status === "running" || job.status === "queued");

  const logs = Array.isArray(job.logs) ? job.logs : [];
  els.jobLog.textContent = logs.length
    ? logs.map((item) => `[${formatTime(item.time)}] ${item.stream}: ${item.message}`).join("\n")
    : "等待任务输出。";
  els.jobLog.scrollTop = els.jobLog.scrollHeight;
}

function renderJobError(message) {
  els.jobTitle.textContent = "任务错误";
  els.jobStage.textContent = "failed";
  els.jobCommand.textContent = "任务未启动。";
  els.jobLog.textContent = message;
  els.cancelJob.disabled = true;
}

function setFormRunning(running) {
  els.jobForm.querySelectorAll("button, input, select").forEach((element) => {
    if (element.id === "clear-log") return;
    element.disabled = running;
  });
}

async function refreshLibraryData() {
  const reports = await loadReports();
  state.reports = reports.map(normalizeReport).filter((report) => report.id);
  populateFilters();
  applyFilters();
  setStatus(`已加载 ${state.reports.length} 篇报告`, "ready");
}

function statusLabel(status) {
  const labels = {
    queued: "排队中",
    running: "运行中",
    completed: "已完成",
    failed: "失败",
    canceled: "已取消",
  };
  return labels[status] || status || "未知";
}

function stageLabel(stage) {
  const labels = {
    queued: "排队",
    starting: "启动",
    mineru: "MinerU",
    summarizing: "总结",
    completed: "完成",
    failed: "失败",
    canceled: "取消",
    idle: "空闲",
  };
  return labels[stage] || stage || "空闲";
}

async function checkSourcePath() {
  if (state.sourceMode !== "default") {
    if (!state.selectedFiles.length) {
      renderJobError("请先选择 PDF 文件或目录。");
      return;
    }
    const count = state.selectedFiles.filter((file) => file.name.toLowerCase().endsWith(".pdf")).length;
    els.jobTitle.textContent = "选择可用";
    els.jobStage.textContent = state.sourceMode === "directory" ? "目录" : "文件";
    els.jobProgressBar.style.width = "0%";
    els.jobProgressText.textContent = "0%";
    els.jobParsed.textContent = "0";
    els.jobCompleted.textContent = "0";
    els.jobTotal.textContent = String(count);
    els.jobFailed.textContent = "0";
    els.jobCurrentFile.textContent = state.selectedFiles[0] ? `示例：${state.selectedFiles[0].webkitRelativePath || state.selectedFiles[0].name}` : "未找到示例文件。";
    els.jobCommand.textContent = state.sourceMode === "directory" ? "浏览器选择目录，运行时上传到本地服务。" : "浏览器选择 PDF，运行时上传到本地服务。";
    els.jobLog.textContent = `已选择 ${count} 个 PDF。`;
    return;
  }

  try {
    const response = await fetch(apiUrl("api/path-info"), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ path: "data/pdfs", recursive: els.recursive.checked }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || data.detail || "路径检测失败");
    }
    els.jobTitle.textContent = "路径可用";
    els.jobStage.textContent = data.type === "directory" ? "目录" : "文件";
    els.jobProgressBar.style.width = "0%";
    els.jobProgressText.textContent = "0%";
    els.jobParsed.textContent = "0";
    els.jobCompleted.textContent = "0";
    els.jobTotal.textContent = String(data.pdfCount || 0);
    els.jobFailed.textContent = "0";
    els.jobCurrentFile.textContent = data.sample?.length ? `示例：${data.sample[0]}` : "未找到示例文件。";
    els.jobCommand.textContent = data.resolvedPath;
    els.jobLog.textContent = `检测到 ${data.pdfCount} 个 PDF。${data.recursive ? "已包含子目录。" : "未扫描子目录。"}`;
  } catch (error) {
    renderJobError(error.message);
  }
}

function setSourceFiles(mode, files) {
  state.sourceMode = mode;
  state.selectedFiles = files.filter((file) => file.name.toLowerCase().endsWith(".pdf"));
  if (mode !== "files") {
    els.pdfFiles.value = "";
  }
  if (mode !== "directory") {
    els.pdfDirectory.value = "";
  }
  updateSourceButtons();
  updateSelectedSource();
}

function setDefaultSource() {
  state.sourceMode = "default";
  state.selectedFiles = [];
  els.pdfFiles.value = "";
  els.pdfDirectory.value = "";
  updateSourceButtons();
  updateSelectedSource();
}

function updateSourceButtons() {
  [
    [els.pickFiles, "files"],
    [els.pickDirectory, "directory"],
    [els.useDefaultPath, "default"],
  ].forEach(([button, mode]) => {
    button.classList.toggle("is-selected", state.sourceMode === mode);
  });
}

function updateSelectedSource() {
  if (state.sourceMode === "default") {
    els.selectedSource.textContent = "已选择默认目录：data/pdfs";
    return;
  }
  if (!state.selectedFiles.length) {
    els.selectedSource.textContent = "尚未选择 PDF。";
    return;
  }
  const first = state.selectedFiles[0].webkitRelativePath || state.selectedFiles[0].name;
  const suffix = state.selectedFiles.length > 1 ? ` 等 ${state.selectedFiles.length} 个 PDF` : "";
  els.selectedSource.textContent = `已选择：${first}${suffix}`;
}

async function cancelCurrentJob() {
  if (!state.currentJobId) return;
  els.cancelJob.disabled = true;
  try {
    const response = await fetch(apiUrl(`api/jobs/${encodeURIComponent(state.currentJobId)}/cancel`), {
      method: "POST",
    });
    const job = await response.json();
    if (!response.ok) {
      throw new Error(job.error || "取消任务失败");
    }
    renderJob(job);
  } catch (error) {
    renderJobError(error.message);
  }
}

function formatTime(value) {
  if (!value) return "--:--:--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--:--:--";
  return date.toLocaleTimeString("zh-CN", { hour12: false });
}

function renderReportNav(markdown) {
  const headings = [...markdown.matchAll(/^##\s+(.+)$/gm)]
    .map((match) => cleanText(match[1]))
    .slice(0, 14);

  if (!headings.length) {
    els.reportNav.innerHTML = `<span class="meta-chip">无目录</span>`;
    return;
  }

  els.reportNav.innerHTML = headings
    .map((heading) => `<a href="#${headingId(heading)}">${escapeHtml(heading)}</a>`)
    .join("");
}

function renderMarkdown(markdown, paperId) {
  const imgBase = apiUrl("data/reports/img/");
  const normalized = markdown
    .replace(/src=(["'])\.\.\/img\//g, `src=$1${imgBase}`)
    .replace(/!\[([^\]]*)\]\(\.\.\/img\//g, `![$1](${imgBase}`);

  const lines = normalized.split(/\r?\n/);
  const html = [];
  let listType = null;
  let paragraph = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    html.push(`<p>${formatInline(paragraph.join(" "))}</p>`);
    paragraph = [];
  };

  const closeList = () => {
    if (!listType) return;
    html.push(`</${listType}>`);
    listType = null;
  };

  for (let index = 0; index < lines.length; index += 1) {
    const rawLine = lines[index];
    const line = rawLine.trim();

    if (!line) {
      flushParagraph();
      closeList();
      continue;
    }

    if (/^<\/?p(\s[^>]*)?>$/i.test(line)) {
      flushParagraph();
      closeList();
      continue;
    }

    if (isHtmlImageLine(line)) {
      flushParagraph();
      closeList();
      html.push(renderHtmlImage(line, paperId));
      continue;
    }

    if (isHtmlCaptionLine(line)) {
      flushParagraph();
      closeList();
      html.push(`<p class="figure-caption">${formatInline(stripHtml(line))}</p>`);
      continue;
    }

    if (line.startsWith("|") && lines[index + 1]?.trim().startsWith("|")) {
      flushParagraph();
      closeList();
      const tableLines = [];
      while (index < lines.length && lines[index].trim().startsWith("|")) {
        tableLines.push(lines[index].trim());
        index += 1;
      }
      index -= 1;
      html.push(renderTable(tableLines));
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      closeList();
      const level = Math.min(heading[1].length, 4);
      const text = cleanText(heading[2]);
      const idAttr = level === 2 ? ` id="${headingId(text)}"` : "";
      html.push(`<h${level}${idAttr}>${formatInline(text)}</h${level}>`);
      continue;
    }

    const blockquote = line.match(/^>\s?(.*)$/);
    if (blockquote) {
      flushParagraph();
      closeList();
      html.push(`<blockquote>${formatInline(blockquote[1])}</blockquote>`);
      continue;
    }

    const unordered = line.match(/^[-*]\s+(.+)$/);
    if (unordered) {
      flushParagraph();
      if (listType !== "ul") {
        closeList();
        listType = "ul";
        html.push("<ul>");
      }
      html.push(`<li>${formatInline(unordered[1])}</li>`);
      continue;
    }

    const ordered = line.match(/^\d+\.\s+(.+)$/);
    if (ordered) {
      flushParagraph();
      if (listType !== "ol") {
        closeList();
        listType = "ol";
        html.push("<ol>");
      }
      html.push(`<li>${formatInline(ordered[1])}</li>`);
      continue;
    }

    const image = line.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
    if (image) {
      flushParagraph();
      closeList();
      html.push(
        `<img src="${escapeAttribute(image[2])}" alt="${escapeAttribute(image[1] || "paper figure")}" loading="lazy" />`,
      );
      continue;
    }

    paragraph.push(line);
  }

  flushParagraph();
  closeList();
  return html.join("\n");
}

function renderTable(lines) {
  if (lines.length < 2) return "";
  const rows = lines
    .filter((line, index) => index !== 1 || !/^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(line))
    .map((line) =>
      line
        .replace(/^\|/, "")
        .replace(/\|$/, "")
        .split("|")
        .map((cell) => cell.trim()),
    );

  const [head, ...body] = rows;
  return `
    <table>
      <thead><tr>${head.map((cell) => `<th>${formatInline(cell)}</th>`).join("")}</tr></thead>
      <tbody>${body
        .map((row) => `<tr>${row.map((cell) => `<td>${formatInline(cell)}</td>`).join("")}</tr>`)
        .join("")}</tbody>
    </table>
  `;
}

function isHtmlImageLine(line) {
  return /<img\s/i.test(line);
}

function isHtmlCaptionLine(line) {
  return /^<p/i.test(line) && /<em>/i.test(line);
}

function renderHtmlImage(line, paperId) {
  const src = attrFromHtml(line, "src") || apiUrl(`data/reports/img/${paperId}/`);
  const alt = attrFromHtml(line, "alt") || "paper figure";
  return `<img src="${escapeAttribute(src)}" alt="${escapeAttribute(alt)}" loading="lazy" />`;
}

function attrFromHtml(html, attr) {
  const match = html.match(new RegExp(`${attr}=["']([^"']+)["']`, "i"));
  return match ? match[1] : "";
}

function stripHtml(html) {
  return html
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/?[^>]+>/g, "")
    .trim();
}

function formatInline(text) {
  let output = escapeHtml(text);

  output = output.replace(/`([^`]+)`/g, "<code>$1</code>");
  output = output.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  output = output.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  output = output.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    (_match, label, url) =>
      `<a href="${escapeAttribute(url)}" target="_blank" rel="noreferrer">${label}</a>`,
  );
  return output;
}

function setStatus(message, status) {
  els.status.textContent = message;
  els.status.classList.toggle("is-ready", status === "ready");
  els.status.classList.toggle("is-error", status === "error");
}

function uniqueValues(values) {
  return [...new Set(values.filter((value) => value !== null && value !== undefined && value !== ""))];
}

function headingId(text) {
  return `section-${cleanText(text)
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "")}`;
}

function cleanText(value) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .trim();
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replace(/`/g, "&#096;");
}

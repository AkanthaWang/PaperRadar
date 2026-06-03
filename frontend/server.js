"use strict";

const { spawn } = require("node:child_process");
const fs = require("node:fs");
const fsp = require("node:fs/promises");
const http = require("node:http");
const path = require("node:path");
const { URL } = require("node:url");

const ROOT = path.resolve(__dirname, "..");
const FRONTEND_DIR = path.join(ROOT, "frontend");
const DATA_DIR = path.join(ROOT, "data");
const UPLOAD_DIR = path.join(DATA_DIR, "uploads", "jobs");
const DEFAULT_PORT = Number(process.env.PORT || 5173);
const PYTHON = process.env.PAPERRADAR_PYTHON || process.env.PYTHON || "python";
const MAX_LOG_LINES = 800;
const jobs = new Map();

const CORS_ORIGIN = process.env.CORS_ORIGIN || "*";

function setCorsHeaders(response) {
  response.setHeader("Access-Control-Allow-Origin", CORS_ORIGIN);
  response.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  response.setHeader("Access-Control-Allow-Headers", "Content-Type");
}

const MIME_TYPES = {
  ".css": "text/css; charset=utf-8",
  ".gif": "image/gif",
  ".html": "text/html; charset=utf-8",
  ".ico": "image/x-icon",
  ".jpeg": "image/jpeg",
  ".jpg": "image/jpeg",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".md": "text/markdown; charset=utf-8",
  ".pdf": "application/pdf",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".txt": "text/plain; charset=utf-8",
  ".webp": "image/webp",
};

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

async function main() {
  const server = http.createServer((request, response) => {
    handleRequest(request, response).catch((error) => {
      console.error(error);
      const statusCode = error.statusCode || 500;
      sendJson(response, statusCode, {
        error: statusCode === 500 ? "Internal server error" : error.message,
        detail: error.message,
      });
    });
  });

  const port = await listen(server, DEFAULT_PORT);
  console.log(`PaperRadar frontend: http://127.0.0.1:${port}/`);
  console.log(`Python command: ${PYTHON}`);
}

function listen(server, startPort) {
  return new Promise((resolve, reject) => {
    const tryPort = (port) => {
      server.once("error", (error) => {
        if (error.code === "EADDRINUSE" && port < startPort + 20) {
          tryPort(port + 1);
          return;
        }
        reject(error);
      });
      server.listen(port, "127.0.0.1", () => resolve(port));
    };
    tryPort(startPort);
  });
}

async function handleRequest(request, response) {
  setCorsHeaders(response);

  if (request.method === "OPTIONS") {
    response.writeHead(204);
    response.end();
    return;
  }

  const url = new URL(request.url, "http://127.0.0.1");

  if (request.method === "GET" && url.pathname === "/api/health") {
    sendJson(response, 200, { ok: true, python: PYTHON });
    return;
  }

  if (request.method === "GET" && url.pathname === "/api/reports") {
    sendJson(response, 200, await readReports());
    return;
  }

  if (request.method === "POST" && url.pathname === "/api/path-info") {
    const payload = await readJsonBody(request);
    sendJson(response, 200, publicPathInfo(await inspectSourcePath(payload)));
    return;
  }

  if (request.method === "GET" && url.pathname === "/api/jobs") {
    sendJson(response, 200, { jobs: [...jobs.values()].map(publicJob) });
    return;
  }

  if (request.method === "POST" && url.pathname === "/api/jobs") {
    const payload = await readJsonBody(request);
    const job = await createJob(payload);
    sendJson(response, 202, publicJob(job));
    return;
  }

  if (request.method === "POST" && url.pathname === "/api/jobs/upload") {
    const { payload, uploadDir } = await readMultipartUpload(request);
    const job = await createJob({ ...payload, path: uploadDir, recursive: true, uploaded: true });
    sendJson(response, 202, publicJob(job));
    return;
  }

  const jobMatch = url.pathname.match(/^\/api\/jobs\/([^/]+)$/);
  if (request.method === "GET" && jobMatch) {
    const job = jobs.get(jobMatch[1]);
    if (!job) {
      sendJson(response, 404, { error: "Job not found" });
      return;
    }
    sendJson(response, 200, publicJob(job));
    return;
  }

  const cancelMatch = url.pathname.match(/^\/api\/jobs\/([^/]+)\/cancel$/);
  if (request.method === "POST" && cancelMatch) {
    const job = jobs.get(cancelMatch[1]);
    if (!job) {
      sendJson(response, 404, { error: "Job not found" });
      return;
    }
    cancelJob(job);
    sendJson(response, 200, publicJob(job));
    return;
  }

  await serveStatic(url.pathname, response);
}

async function createJob(payload) {
  const pathInfo = await inspectSourcePath(payload);
  const limit = positiveInteger(payload.limit);
  const files = limit ? pathInfo.files.slice(0, limit) : pathInfo.files;
  const pdfCount = files.length;

  const id = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const job = {
    id,
    sourcePath: pathInfo.resolvedPath,
    inputType: pathInfo.type,
    recursive: pathInfo.recursive,
    files,
    pdfCount,
    command: `${files.length} file(s) x ${formatCommand(PYTHON, ["-u", ...buildCommandArgs(payload, "<pdf>")])}`,
    currentCommand: "",
    currentFile: "",
    currentIndex: 0,
    currentPhase: "",
    status: "queued",
    stage: "queued",
    progress: 0,
    parsed: 0,
    completed: 0,
    failed: 0,
    startedAt: new Date().toISOString(),
    finishedAt: null,
    exitCode: null,
    reports: [],
    logs: [],
    child: null,
  };

  jobs.set(id, job);
  runNextFile(job, payload);
  return job;
}

function buildCommandArgs(payload, pdfPath) {
  const args = ["-m", "src.pipeline.cli", "summarize", "--parse-missing", "--pdf", pdfPath];

  if (payload.overwrite) args.push("--overwrite");
  if (payload.llmProvider && payload.llmProvider !== "env") args.push("--llm-provider", payload.llmProvider);
  if (payload.ecnuModel) args.push("--ecnu-model", payload.ecnuModel);
  if (payload.reportsDir) args.push("--reports-dir", normalizeUserPath(payload.reportsDir));
  if (payload.outputsDir) args.push("--outputs-dir", normalizeUserPath(payload.outputsDir));
  if (payload.maxImages) args.push("--max-images", String(payload.maxImages));
  if (payload.summaryMaxChars) args.push("--summary-max-chars", String(payload.summaryMaxChars));
  if (payload.summaryChunkChars) args.push("--summary-chunk-chars", String(payload.summaryChunkChars));

  return args;
}

function runNextFile(job, payload) {
  if (job.status === "canceled") {
    finishCanceledJob(job);
    return;
  }
  if (job.currentIndex >= job.files.length) {
    finishCompletedJob(job);
    return;
  }

  const pdfPath = job.files[job.currentIndex];
  const commandArgs = buildCommandArgs(payload, pdfPath);
  job.status = "running";
  job.stage = "starting";
  job.currentPhase = "starting";
  job.currentFile = path.basename(pdfPath);
  job.currentCommand = formatCommand(PYTHON, ["-u", ...commandArgs]);
  updateProgress(job);
  appendLog(job, "system", `开始处理 ${job.currentIndex + 1}/${job.pdfCount}: ${pdfPath}`);

  const child = spawn(PYTHON, ["-u", ...commandArgs], {
    cwd: ROOT,
    env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    windowsHide: true,
  });

  job.child = child;

  child.stdout.on("data", (chunk) => handleOutput(job, "stdout", chunk));
  child.stderr.on("data", (chunk) => handleOutput(job, "stderr", chunk));
  child.on("error", (error) => {
    job.failed += 1;
    appendLog(job, "error", error.message);
  });
  child.on("close", async (code) => {
    job.child = null;
    if (job.status === "canceled") {
      finishCanceledJob(job);
      return;
    }
    if (code === 0) {
      job.completed += 1;
      appendLog(job, "system", `完成: ${job.currentFile}`);
    } else {
      job.failed += 1;
      appendLog(job, "system", `失败: ${job.currentFile}，退出码 ${code}。`);
    }
    job.currentIndex += 1;
    updateProgress(job);
    runNextFile(job, payload);
  });
}

function handleOutput(job, stream, chunk) {
  const text = chunk.toString("utf8");
  text.split(/\r?\n/).forEach((line) => {
    const clean = line.trim();
    if (!clean) return;
    appendLog(job, stream, clean);
    updateProgressFromLine(job, clean);
  });
}

function updateProgressFromLine(job, line) {
  if (/Parse PDF with MinerU|MinerU parsing|Wrote MinerU raw Markdown|成功解析/.test(line)) {
    job.stage = "mineru";
    job.currentPhase = "mineru";
  }
  if (/Summarize MinerU Markdown|Summarizing|成功生成摘要/.test(line)) {
    job.stage = "summarizing";
    job.currentPhase = "summarizing";
  }
  if (/Skip existing MinerU Markdown/.test(line)) {
    job.stage = "mineru";
    job.currentPhase = "mineru";
  }
  if (/Wrote MinerU raw Markdown|成功解析/.test(line)) {
    job.parsed = Math.min(job.pdfCount, job.parsed + 1);
  }
  updateProgress(job);
}

function updateProgress(job) {
  if (!job.pdfCount) {
    job.progress = 0;
    return;
  }
  const settled = Math.min(job.pdfCount, job.completed + job.failed);
  const phaseWeight = job.status === "running" ? phaseProgress(job.currentPhase) : 0;
  const raw = ((settled + phaseWeight) / job.pdfCount) * 100;
  job.progress = Math.min(job.status === "completed" ? 100 : 99, Math.max(job.progress || 0, Math.round(raw)));
}

function phaseProgress(phase) {
  if (phase === "mineru") return 0.38;
  if (phase === "summarizing") return 0.72;
  if (phase === "starting") return 0.12;
  return 0;
}

async function finishCompletedJob(job) {
  job.status = job.failed ? "failed" : "completed";
  job.stage = job.failed ? "failed" : "completed";
  job.exitCode = job.failed ? 1 : 0;
  job.finishedAt = new Date().toISOString();
  job.currentPhase = "";
  job.currentFile = "";
  job.currentCommand = "";
  job.progress = 100;
  appendLog(job, "system", job.failed ? "任务结束，但存在失败文件。" : "任务完成。");
  await refreshReports(job);
}

function finishCanceledJob(job) {
  job.stage = "canceled";
  job.finishedAt = job.finishedAt || new Date().toISOString();
  job.currentPhase = "";
  job.currentCommand = "";
  if (!job.logs.some((entry) => entry.message === "任务已取消。")) {
    appendLog(job, "system", "任务已取消。");
  }
}

async function refreshReports(job) {
  const script = path.join(ROOT, "scripts", "combine_reports.py");
  await new Promise((resolve) => {
    const child = spawn(PYTHON, [script], {
      cwd: ROOT,
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
      windowsHide: true,
    });
    child.stdout.on("data", (chunk) => appendLog(job, "stdout", chunk.toString("utf8").trim()));
    child.stderr.on("data", (chunk) => appendLog(job, "stderr", chunk.toString("utf8").trim()));
    child.on("close", () => resolve());
    child.on("error", () => resolve());
  });

  const reports = await readReports();
  job.reports = reports.items.slice(0, 8);
}

function appendLog(job, stream, message) {
  if (!message) return;
  job.logs.push({
    time: new Date().toISOString(),
    stream,
    message,
  });
  if (job.logs.length > MAX_LOG_LINES) {
    job.logs.splice(0, job.logs.length - MAX_LOG_LINES);
  }
}

async function readReports() {
  const allReportsPath = path.join(DATA_DIR, "reports", "all_reports.json");
  try {
    const text = await fsp.readFile(allReportsPath, "utf8");
    const items = JSON.parse(text);
    return { items: Array.isArray(items) ? items : [] };
  } catch {
    return { items: [] };
  }
}

async function countPdfs(dir) {
  return listPdfFiles(dir, false).then((files) => files.length);
}

function normalizeUserPath(value) {
  const raw = String(value || "").trim().replace(/^["']|["']$/g, "");
  if (!raw) return "";
  return path.resolve(ROOT, raw);
}

function positiveInteger(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return null;
  return Math.floor(number);
}

async function inspectSourcePath(payload) {
  const sourcePath = normalizeUserPath(payload.path || payload.sourcePath || "");
  if (!sourcePath) {
    const error = new Error("请输入 PDF 文件路径或 PDF 目录路径。");
    error.statusCode = 400;
    throw error;
  }

  let stat;
  try {
    stat = await fsp.stat(sourcePath);
  } catch {
    const error = new Error(`路径不存在: ${sourcePath}`);
    error.statusCode = 400;
    throw error;
  }

  const isPdfFile = stat.isFile() && sourcePath.toLowerCase().endsWith(".pdf");
  const isDirectory = stat.isDirectory();
  if (!isPdfFile && !isDirectory) {
    const error = new Error("仅支持 PDF 文件或包含 PDF 的目录。");
    error.statusCode = 400;
    throw error;
  }

  const recursive = Boolean(payload.recursive);
  const files = isPdfFile ? [sourcePath] : await listPdfFiles(sourcePath, recursive);
  if (!files.length) {
    const error = new Error(`未找到 PDF: ${sourcePath}`);
    error.statusCode = 400;
    throw error;
  }

  return {
    resolvedPath: sourcePath,
    type: isDirectory ? "directory" : "file",
    recursive,
    pdfCount: files.length,
    files,
    sample: files.slice(0, 5).map((file) => path.relative(ROOT, file) || file),
  };
}

async function listPdfFiles(dir, recursive) {
  const result = [];
  const entries = await fsp.readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isFile() && entry.name.toLowerCase().endsWith(".pdf")) {
      result.push(fullPath);
    } else if (recursive && entry.isDirectory()) {
      result.push(...(await listPdfFiles(fullPath, true)));
    }
  }
  return result.sort((a, b) => a.localeCompare(b));
}

function cancelJob(job) {
  if (job.status !== "running" && job.status !== "queued") {
    return;
  }
  job.status = "canceled";
  job.stage = "canceled";
  if (job.child) {
    job.child.kill();
  } else {
    finishCanceledJob(job);
  }
}

function formatCommand(command, args) {
  return [command, ...args].map(quoteArg).join(" ");
}

function quoteArg(value) {
  const text = String(value);
  if (!/[\s"'&|<>]/.test(text)) return text;
  return `"${text.replace(/"/g, '\\"')}"`;
}

function publicPathInfo(pathInfo) {
  return {
    resolvedPath: pathInfo.resolvedPath,
    type: pathInfo.type,
    recursive: pathInfo.recursive,
    pdfCount: pathInfo.pdfCount,
    sample: pathInfo.sample,
  };
}

async function readJsonBody(request) {
  const chunks = [];
  for await (const chunk of request) {
    chunks.push(chunk);
    if (Buffer.concat(chunks).length > 1024 * 1024) {
      const error = new Error("Request body too large");
      error.statusCode = 413;
      throw error;
    }
  }

  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
  } catch {
    const error = new Error("Invalid JSON body");
    error.statusCode = 400;
    throw error;
  }
}

async function readMultipartUpload(request) {
  const contentType = request.headers["content-type"] || "";
  const boundaryMatch = contentType.match(/boundary=(?:"([^"]+)"|([^;]+))/i);
  if (!boundaryMatch) {
    const error = new Error("Missing multipart boundary");
    error.statusCode = 400;
    throw error;
  }

  const body = await readRequestBuffer(request, 1024 * 1024 * 1024);
  const boundary = Buffer.from(`--${boundaryMatch[1] || boundaryMatch[2]}`);
  const uploadDir = path.join(UPLOAD_DIR, new Date().toISOString().replace(/[:.]/g, "-"));
  await fsp.mkdir(uploadDir, { recursive: true });

  let payload = {};
  let savedFiles = 0;
  for (const part of splitMultipart(body, boundary)) {
    const parsed = parseMultipartPart(part);
    if (!parsed) continue;
    if (parsed.name === "payload") {
      try {
        payload = JSON.parse(parsed.data.toString("utf8") || "{}");
      } catch {
        const error = new Error("上传参数不是有效 JSON。");
        error.statusCode = 400;
        throw error;
      }
      continue;
    }
    if (parsed.name !== "pdfs" || !parsed.filename) continue;
    if (!parsed.filename.toLowerCase().endsWith(".pdf")) continue;
    const target = safeUploadPath(uploadDir, parsed.filename);
    await fsp.mkdir(path.dirname(target), { recursive: true });
    await fsp.writeFile(target, parsed.data);
    savedFiles += 1;
  }

  if (!savedFiles) {
    const error = new Error("没有上传 PDF 文件。");
    error.statusCode = 400;
    throw error;
  }

  return { payload, uploadDir };
}

async function readRequestBuffer(request, maxBytes) {
  const chunks = [];
  let total = 0;
  for await (const chunk of request) {
    total += chunk.length;
    if (total > maxBytes) {
      const error = new Error("Request body too large");
      error.statusCode = 413;
      throw error;
    }
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

function splitMultipart(body, boundary) {
  const parts = [];
  let start = body.indexOf(boundary);
  while (start !== -1) {
    start += boundary.length;
    if (body[start] === 45 && body[start + 1] === 45) break;
    if (body[start] === 13 && body[start + 1] === 10) start += 2;
    let end = body.indexOf(boundary, start);
    if (end === -1) break;
    let part = body.subarray(start, end);
    if (part.length >= 2 && part[part.length - 2] === 13 && part[part.length - 1] === 10) {
      part = part.subarray(0, part.length - 2);
    }
    parts.push(part);
    start = end;
  }
  return parts;
}

function parseMultipartPart(part) {
  const separator = Buffer.from("\r\n\r\n");
  const headerEnd = part.indexOf(separator);
  if (headerEnd === -1) return null;
  const headers = part.subarray(0, headerEnd).toString("utf8");
  const data = part.subarray(headerEnd + separator.length);
  const disposition = headers.match(/content-disposition:\s*form-data;([^\r\n]+)/i);
  if (!disposition) return null;
  const name = disposition[1].match(/name="([^"]+)"/i)?.[1] || "";
  const filename = disposition[1].match(/filename="([^"]*)"/i)?.[1] || "";
  return { name, filename, data };
}

function safeUploadPath(uploadDir, filename) {
  const normalized = filename.replace(/\\/g, "/");
  const parts = normalized
    .split("/")
    .map((part) => part.replace(/[<>:"|?*\x00-\x1F]/g, "_").trim())
    .filter((part) => part && part !== "." && part !== "..");
  const target = path.resolve(uploadDir, ...parts);
  if (!target.startsWith(path.resolve(uploadDir))) {
    return path.join(uploadDir, path.basename(filename));
  }
  return target;
}

async function serveStatic(urlPath, response) {
  let pathname = decodeURIComponent(urlPath);
  if (pathname === "/") pathname = "/frontend/index.html";
  if (pathname === "/frontend") pathname = "/frontend/index.html";

  let baseDir = ROOT;
  let filePath = path.join(ROOT, pathname);

  if (pathname.startsWith("/frontend/")) {
    baseDir = FRONTEND_DIR;
    filePath = path.join(FRONTEND_DIR, pathname.replace(/^\/frontend\//, ""));
  } else if (pathname.startsWith("/data/reports/")) {
    baseDir = path.join(DATA_DIR, "reports");
    filePath = path.join(baseDir, pathname.replace(/^\/data\/reports\//, ""));
  }

  const resolved = path.resolve(filePath);
  if (!resolved.startsWith(path.resolve(baseDir))) {
    sendText(response, 403, "Forbidden");
    return;
  }

  let stat;
  try {
    stat = await fsp.stat(resolved);
  } catch {
    sendText(response, 404, "Not found");
    return;
  }

  if (stat.isDirectory()) {
    await serveStatic(path.join(pathname, "index.html").replaceAll("\\", "/"), response);
    return;
  }

  response.writeHead(200, {
    "content-type": MIME_TYPES[path.extname(resolved).toLowerCase()] || "application/octet-stream",
    "content-length": stat.size,
    "cache-control": "no-store",
  });
  fs.createReadStream(resolved).pipe(response);
}

function sendJson(response, statusCode, payload) {
  response.writeHead(statusCode, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
  });
  response.end(JSON.stringify(payload));
}

function sendText(response, statusCode, text) {
  response.writeHead(statusCode, { "content-type": "text/plain; charset=utf-8" });
  response.end(text);
}

function publicJob(job) {
  return {
    id: job.id,
    sourcePath: job.sourcePath,
    inputType: job.inputType,
    pdfCount: job.pdfCount,
    command: job.command,
    currentCommand: job.currentCommand,
    currentFile: job.currentFile,
    status: job.status,
    stage: job.stage,
    progress: job.progress,
    parsed: job.parsed,
    completed: job.completed,
    failed: job.failed,
    startedAt: job.startedAt,
    finishedAt: job.finishedAt,
    exitCode: job.exitCode,
    reports: job.reports,
    logs: job.logs,
  };
}

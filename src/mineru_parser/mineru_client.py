from __future__ import annotations

import os
import re
import shutil
import time
import zipfile
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from src.config import AnalyzerSettings


MAX_UPLOAD_FILENAME_BYTES = 120


class MinerUError(RuntimeError):
    pass


@dataclass
class MinerUResult:
    task_id: str
    markdown: str
    output_dir: Path
    raw_result: dict[str, Any]


def shorten_upload_filename(filename: str, max_bytes: int = MAX_UPLOAD_FILENAME_BYTES) -> str:
    if len(filename.encode("utf-8")) <= max_bytes:
        return filename

    path = Path(filename)
    suffix = path.suffix or ".pdf"
    digest = hashlib.sha1(filename.encode("utf-8")).hexdigest()[:10]
    budget = max_bytes - len(suffix.encode("utf-8")) - len(digest) - 1
    if budget < 12:
        return f"{digest}{suffix}"

    stem = sanitize_upload_stem(path.stem)
    stem = truncate_utf8(stem, budget)
    return f"{stem}-{digest}{suffix}"


def sanitize_upload_stem(stem: str) -> str:
    stem = re.sub(r'[\\/:*?"<>|]+', "_", stem)
    stem = re.sub(r"\s+", "_", stem).strip("._- ")
    return stem or "paper"


def truncate_utf8(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return truncated.rstrip("._- ") or "paper"


class MinerUClient:
    def __init__(
        self,
        token: str,
        base_url: str = "https://mineru.net",
        model_version: str = "vlm",
        enable_formula: bool = True,
        enable_table: bool = True,
        language: str | None = None,
        timeout: int = 900,
        poll_interval: int = 5,
        user_token: str | None = None,
    ) -> None:
        self.token = token
        self.base_url = self._normalize_base_url(base_url)
        self.model_version = model_version
        self.enable_formula = enable_formula
        self.enable_table = enable_table
        self.language = language
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.user_token = user_token

    @classmethod
    def from_settings(cls, settings: AnalyzerSettings) -> "MinerUClient":
        settings.require_mineru_credentials()
        assert settings.mineru_token is not None
        return cls(
            token=settings.mineru_token,
            base_url=settings.mineru_base_url,
            model_version=settings.mineru_model_version,
            enable_formula=settings.mineru_enable_formula,
            enable_table=settings.mineru_enable_table,
            language=settings.mineru_language,
            timeout=settings.mineru_timeout,
            poll_interval=settings.mineru_poll_interval,
            user_token=settings.mineru_user_token,
        )

    @staticmethod
    def _normalize_base_url(value: str) -> str:
        value = value.strip().rstrip("/")
        if value.endswith("/api/v4/extract/task"):
            value = value[: -len("/api/v4/extract/task")]
        elif value.endswith("/api/v4"):
            value = value[: -len("/api/v4")]
        return value or "https://mineru.net"

    def parse_pdf(
        self,
        pdf: str | Path,
        output_dir: str | Path,
        overwrite: bool = False,
    ) -> MinerUResult:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        pdf_value = str(pdf)
        if self._is_url(pdf_value):
            task_id = self.submit_url(pdf_value)
            result = self.wait_for_result(task_id)
            run_id = task_id
        else:
            batch_id = self.submit_file(Path(pdf_value))
            result = self.wait_for_batch_result(batch_id)
            run_id = batch_id

        extract_dir = output_dir / run_id
        if extract_dir.exists() and overwrite:
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)

        markdown = self._materialize_markdown(result, extract_dir)
        markdown = self._rewrite_markdown_asset_paths(markdown, extract_dir, output_dir)
        return MinerUResult(
            task_id=run_id,
            markdown=markdown,
            output_dir=extract_dir,
            raw_result=result,
        )

    def submit_url(self, pdf_url: str) -> str:
        payload = self._task_payload({"url": pdf_url})
        data = self._post_json("/api/v4/extract/task", payload)
        task_id = self._find_task_id(data)
        if not task_id:
            raise MinerUError(f"Cannot find task id in MinerU response: {data}")
        return task_id

    def submit_file(self, pdf_path: Path) -> str:
        if not pdf_path.exists():
            raise MinerUError(f"PDF does not exist: {pdf_path}")

        upload_filename = shorten_upload_filename(pdf_path.name)
        if upload_filename != pdf_path.name:
            print(f"MinerU upload filename shortened: {pdf_path.name} -> {upload_filename}")

        upload_info = self._request_upload_url(upload_filename)
        batch_id = self._pick_first(upload_info, "batch_id", "batchId")
        if not batch_id:
            raise MinerUError(f"Cannot find batch id in MinerU response: {upload_info}")

        upload_url = self._pick_first(
            upload_info,
            "upload_url",
            "uploadUrl",
            "url",
            "put_url",
            "putUrl",
        )
        if not upload_url:
            raise MinerUError(f"Cannot find upload URL in MinerU response: {upload_info}")

        with pdf_path.open("rb") as file:
            upload_response = requests.put(
                upload_url,
                data=file,
                timeout=self.timeout,
            )
        if upload_response.status_code not in range(200, 300):
            raise MinerUError(f"MinerU upload failed: HTTP {upload_response.status_code}: {upload_response.text[:500]}")

        return str(batch_id)

    def wait_for_result(self, task_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout
        last_result: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            result = self.get_result(task_id)
            last_result = result
            status = self._find_status(result)
            if status in {"done", "success", "completed", "finish", "finished", "succeeded"}:
                return result
            if status in {"failed", "fail", "error", "canceled", "cancelled"}:
                raise MinerUError(f"MinerU task failed: {result}")
            time.sleep(max(1, self.poll_interval))
        raise MinerUError(f"Timed out waiting for MinerU task {task_id}. Last result: {last_result}")

    def get_result(self, task_id: str) -> dict[str, Any]:
        return self._get_json(f"/api/v4/extract/task/{task_id}")

    def wait_for_batch_result(self, batch_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout
        last_result: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            result = self.get_batch_result(batch_id)
            last_result = result
            extract_result = self._first_extract_result(result)
            status = self._find_status(extract_result or result)
            if status in {"done", "success", "completed", "finish", "finished", "succeeded"}:
                return extract_result or result
            if status in {"failed", "fail", "error", "canceled", "cancelled"}:
                raise MinerUError(f"MinerU batch task failed: {result}")
            time.sleep(max(1, self.poll_interval))
        raise MinerUError(f"Timed out waiting for MinerU batch {batch_id}. Last result: {last_result}")

    def get_batch_result(self, batch_id: str) -> dict[str, Any]:
        return self._get_json(f"/api/v4/extract-results/batch/{batch_id}")

    def _request_upload_url(self, filename: str) -> dict[str, Any]:
        payload = {
            "files": [
                {
                    "name": filename,
                    "data_id": Path(filename).stem,
                }
            ],
            "model_version": self.model_version,
            "enable_formula": self.enable_formula,
            "enable_table": self.enable_table,
        }
        if self.language:
            payload["language"] = self.language
        if self.user_token:
            payload["user_token"] = self.user_token
        data = self._post_json("/api/v4/file-urls/batch", payload)

        item = self._first_file_item(data)
        if not item:
            raise MinerUError(f"Cannot find file upload item in MinerU response: {data}")
        item.setdefault("batch_id", data.get("batch_id"))
        return item

    def _task_payload(self, extra: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model_version": self.model_version,
            "enable_formula": self.enable_formula,
            "enable_table": self.enable_table,
        }
        if self.language:
            payload["language"] = self.language
        if self.user_token:
            payload["user_token"] = self.user_token
        payload.update(extra)
        return payload

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        if self.user_token:
            headers["token"] = self.user_token
        return headers

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(
            urljoin(self.base_url + "/", path.lstrip("/")),
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        return self._decode_response(response)

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = requests.get(
            urljoin(self.base_url + "/", path.lstrip("/")),
            headers=self._headers(),
            params=params,
            timeout=self.timeout,
        )
        return self._decode_response(response)

    @staticmethod
    def _decode_response(response: requests.Response) -> dict[str, Any]:
        if response.status_code not in range(200, 300):
            raise MinerUError(f"MinerU HTTP {response.status_code}: {response.text[:500]}")
        try:
            obj = response.json()
        except ValueError as exc:
            raise MinerUError(f"MinerU returned non-JSON response: {response.text[:500]}") from exc

        code = obj.get("code")
        if code not in (0, "0", None, 200, "200"):
            raise MinerUError(f"MinerU API error: {obj}")
        data = obj.get("data", obj)
        return data if isinstance(data, dict) else {"data": data}

    def _materialize_markdown(self, result: dict[str, Any], extract_dir: Path) -> str:
        markdown = self._pick_first(
            result,
            "full_md",
            "fullMd",
            "markdown",
            "md_content",
            "mdContent",
        )
        if markdown:
            return str(markdown)

        download_url = self._find_download_url(result)
        if not download_url:
            raise MinerUError(f"Cannot find Markdown content or download URL in MinerU result: {result}")

        archive_path = extract_dir / "mineru_output.zip"
        self._download(download_url, archive_path)
        try:
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(extract_dir)
        except zipfile.BadZipFile as exc:
            raise MinerUError(f"MinerU download is not a valid zip: {archive_path}") from exc

        md_path = self._find_markdown_file(extract_dir)
        if not md_path:
            raise MinerUError(f"Cannot find Markdown file in MinerU output: {extract_dir}")
        return md_path.read_text(encoding="utf-8")

    def _download(self, url: str, output_path: Path) -> None:
        with requests.get(url, stream=True, timeout=self.timeout) as response:
            if response.status_code not in range(200, 300):
                raise MinerUError(f"MinerU download failed: HTTP {response.status_code}: {response.text[:500]}")
            with output_path.open("wb") as file:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        file.write(chunk)

    @staticmethod
    def _find_markdown_file(root: Path) -> Path | None:
        candidates = sorted(root.rglob("*.md"), key=lambda path: (path.name != "full.md", len(path.parts)))
        return candidates[0] if candidates else None

    @staticmethod
    def _rewrite_markdown_asset_paths(markdown: str, extract_dir: Path, output_dir: Path) -> str:
        def replace(match: re.Match[str]) -> str:
            alt_text = match.group(1)
            asset_path = match.group(2).strip()
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", asset_path) or asset_path.startswith("#"):
                return match.group(0)
            candidate = extract_dir / asset_path
            if not candidate.exists():
                found = next((path for path in extract_dir.rglob(Path(asset_path).name) if path.is_file()), None)
                if not found:
                    return match.group(0)
                candidate = found
            relative = os.path.relpath(candidate, output_dir).replace("\\", "/")
            return f"![{alt_text}]({relative})"

        return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", replace, markdown)

    @staticmethod
    def _is_url(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"}

    @staticmethod
    def _strip_query(url: str) -> str:
        parsed = urlparse(url)
        return parsed._replace(query="", fragment="").geturl()

    @classmethod
    def _find_task_id(cls, data: Any) -> str:
        task_id = cls._pick_first(data, "task_id", "taskId", "id")
        return str(task_id) if task_id else ""

    @classmethod
    def _find_status(cls, data: Any) -> str:
        status = cls._pick_first(data, "state", "status", "task_status", "taskStatus")
        return str(status or "").strip().lower()

    @classmethod
    def _find_download_url(cls, data: Any) -> str:
        value = cls._pick_first(
            data,
            "full_zip_url",
            "fullZipUrl",
            "zip_url",
            "zipUrl",
            "download_url",
            "downloadUrl",
        )
        return str(value) if value else ""

    @classmethod
    def _first_file_item(cls, data: Any) -> dict[str, Any]:
        if isinstance(data, dict):
            for key in ("files", "file_urls", "fileUrls", "batch", "data"):
                value = data.get(key)
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    return value[0]
                if isinstance(value, list) and value and isinstance(value[0], str):
                    return {"upload_url": value[0]}
                if isinstance(value, dict):
                    nested = cls._first_file_item(value)
                    if nested:
                        return nested
            if any(key.lower().endswith("url") for key in data):
                return data
        return {}

    @staticmethod
    def _first_extract_result(data: Any) -> dict[str, Any]:
        if isinstance(data, dict):
            value = data.get("extract_result") or data.get("extractResult")
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value[0]
            if isinstance(value, dict):
                return value
        return {}

    @classmethod
    def _pick_first(cls, data: Any, *keys: str) -> Any:
        if isinstance(data, dict):
            for key in keys:
                value = data.get(key)
                if value not in (None, ""):
                    return value
            for value in data.values():
                found = cls._pick_first(value, *keys)
                if found not in (None, ""):
                    return found
        elif isinstance(data, list):
            for item in data:
                found = cls._pick_first(item, *keys)
                if found not in (None, ""):
                    return found
        return None

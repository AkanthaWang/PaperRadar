from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin, urlparse

import requests

from src.config import AnalyzerSettings
from .vivo_auth import gen_sign_headers


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    def complete(self, prompt: str, system_prompt: str | None = None) -> str:
        ...


def create_llm_client(settings: AnalyzerSettings) -> LLMClient:
    provider = (settings.llm_provider or "vivo").strip().lower()
    if provider == "ecnu":
        return ECNULMClient.from_settings(settings)
    if provider == "vivo":
        return VivoBlueLMClient.from_settings(settings)
    raise RuntimeError(f"Unsupported LLM provider: {settings.llm_provider}. Use vivo or ecnu.")


@dataclass
class VivoBlueLMClient:
    app_id: str
    app_key: str
    auth_mode: str = "hmac"
    domain: str = "api-ai.vivo.com.cn"
    uri: str = "/vivogpt/completions"
    model: str = "vivo-BlueLM-TB-Pro"
    timeout: int = 120
    temperature: float = 0.2
    max_retries: int = 2

    @classmethod
    def from_settings(cls, settings: AnalyzerSettings) -> "VivoBlueLMClient":
        settings.require_llm_credentials()
        assert settings.app_id is not None
        assert settings.app_key is not None
        return cls(
            app_id=settings.app_id,
            app_key=settings.app_key,
            auth_mode=settings.auth_mode,
            domain=settings.domain,
            uri=settings.uri,
            model=settings.model,
            timeout=settings.timeout,
            temperature=settings.temperature,
            max_retries=settings.max_retries,
        )

    @property
    def url(self) -> str:
        return self._request_url()

    @property
    def request_path(self) -> str:
        parsed = urlparse(self.domain or "")
        base_path = parsed.path.rstrip("/")
        uri_path = self.uri if self.uri.startswith("/") else f"/{self.uri}"
        full_path = f"{base_path}{uri_path}"
        return full_path if full_path.startswith("/") else f"/{full_path}"

    def _request_url(self) -> str:
        domain = self.domain or ""
        parsed = urlparse(domain)
        if parsed.scheme:
            base = f"{parsed.scheme}://{parsed.netloc}"
        else:
            base = f"https://{domain.lstrip('/').rstrip('/')}"
        return f"{base}{self.request_path}"

    def complete(self, prompt: str, system_prompt: str | None = None) -> str:
        user_content = prompt if not system_prompt else f"{system_prompt}\n\n{prompt}"
        messages = [{"role": "user", "content": user_content}]
        payload = {
            "messages": messages,
            "model": self.model,
            "sessionId": str(uuid.uuid4()),
            "extra": {
                "temperature": self.temperature,
            },
        }

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return self._post(payload)
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(1.5 * (attempt + 1))
        raise LLMError(f"vivo LLM request failed after retries: {last_error}") from last_error

    def _post(self, payload: dict[str, object]) -> str:
        params = {"requestId": str(uuid.uuid4())}
        headers = self._build_headers(params)
        headers["Content-Type"] = "application/json"

        response = requests.post(
            self.url,
            json=payload,
            headers=headers,
            params=params,
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise LLMError(f"HTTP {response.status_code}: {response.text[:500]}")

        try:
            obj = response.json()
        except ValueError as exc:
            raise LLMError(f"Invalid JSON response: {response.text[:500]}") from exc

        if obj.get("code") not in (0, "0", None):
            raise LLMError(f"API error: {obj}")

        data = obj.get("data", obj)
        content = self._extract_content(data)
        if not content:
            raise LLMError(f"Cannot find content in response: {obj}")
        return content

    def _build_headers(self, params: dict[str, object]) -> dict[str, str]:
        auth_mode = (self.auth_mode or "hmac").strip().lower()
        if auth_mode == "bearer":
            return {"Authorization": f"Bearer {self.app_key}"}
        headers = gen_sign_headers(self.app_id, self.app_key, "POST", self.request_path, params)
        return headers

    @staticmethod
    def _extract_content(data: object) -> str:
        if isinstance(data, str):
            return data
        if not isinstance(data, dict):
            return ""

        content = data.get("content")
        if isinstance(content, str):
            return content

        content_list = data.get("contentList")
        if isinstance(content_list, list):
            parts: list[str] = []
            for item in content_list:
                if isinstance(item, dict) and isinstance(item.get("content"), str):
                    parts.append(item["content"])
                elif isinstance(item, str):
                    parts.append(item)
            if parts:
                return "\n".join(parts)

        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict) and isinstance(message.get("content"), str):
                    return message["content"]
                if isinstance(first.get("text"), str):
                    return first["text"]

        return ""


@dataclass
class ECNULMClient:
    api_key: str
    base_url: str = "https://chat.ecnu.edu.cn/open/api/v1"
    model: str = "ecnu-max"
    thinking_type: str = "disabled"
    timeout: int = 120
    temperature: float = 0.2
    max_retries: int = 2

    @classmethod
    def from_settings(cls, settings: AnalyzerSettings) -> "ECNULMClient":
        settings.require_llm_credentials()
        assert settings.ecnu_api_key is not None
        return cls(
            api_key=settings.ecnu_api_key,
            base_url=settings.ecnu_base_url,
            model=settings.ecnu_model,
            thinking_type=settings.ecnu_thinking_type,
            timeout=settings.timeout,
            temperature=settings.temperature,
            max_retries=settings.max_retries,
        )

    @property
    def chat_url(self) -> str:
        return urljoin(self.base_url.rstrip("/") + "/", "chat/completions")

    @property
    def models_url(self) -> str:
        return urljoin(self.base_url.rstrip("/") + "/", "models")

    def complete(self, prompt: str, system_prompt: str | None = None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "thinking": {
                "type": self.thinking_type,
            },
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return self._post(payload)
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(1.5 * (attempt + 1))
        raise LLMError(f"ECNU LLM request failed after retries: {last_error}") from last_error

    def list_models(self) -> dict[str, object]:
        response = requests.get(
            self.models_url,
            headers=self._headers(),
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise LLMError(f"ECNU models HTTP {response.status_code}: {response.text[:500]}")
        try:
            obj = response.json()
        except ValueError as exc:
            raise LLMError(f"Invalid ECNU models JSON response: {response.text[:500]}") from exc
        return obj if isinstance(obj, dict) else {"data": obj}

    def _post(self, payload: dict[str, object]) -> str:
        response = requests.post(
            self.chat_url,
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise LLMError(f"ECNU HTTP {response.status_code}: {response.text[:500]}")

        try:
            obj = response.json()
        except ValueError as exc:
            raise LLMError(f"Invalid ECNU JSON response: {response.text[:500]}") from exc

        if isinstance(obj, dict) and obj.get("error"):
            raise LLMError(f"ECNU API error: {obj['error']}")

        content = self._extract_content(obj)
        if not content:
            raise LLMError(f"Cannot find content in ECNU response: {obj}")
        return content

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    @staticmethod
    def _extract_content(data: object) -> str:
        if isinstance(data, str):
            return data
        if not isinstance(data, dict):
            return ""

        content = data.get("content")
        if isinstance(content, str):
            return content

        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str):
                        return content
                    if isinstance(content, list):
                        parts = []
                        for item in content:
                            if isinstance(item, dict) and isinstance(item.get("text"), str):
                                parts.append(item["text"])
                            elif isinstance(item, str):
                                parts.append(item)
                        if parts:
                            return "\n".join(parts)
                text = first.get("text")
                if isinstance(text, str):
                    return text

        data_obj = data.get("data")
        if isinstance(data_obj, dict):
            return ECNULMClient._extract_content(data_obj)
        if isinstance(data_obj, str):
            return data_obj

        return ""

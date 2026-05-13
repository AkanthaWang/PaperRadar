from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_dotenv_if_available(root: Path = PROJECT_ROOT) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(root / ".env")


def env_first(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value not in (None, ""):
            return value
    return default


def resolve_path(value: str | Path, root: Path = PROJECT_ROOT) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return int(raw)


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return float(raw)


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class AnalyzerSettings:
    project_root: Path
    downloads_dir: Path
    outputs_dir: Path
    assets_dir: Path
    cache_dir: Path
    auth_mode: str
    app_id: str | None
    app_key: str | None = field(repr=False)
    domain: str
    uri: str
    model: str
    timeout: int
    temperature: float
    max_images: int
    max_chars: int
    chunk_chars: int
    max_chunks: int
    max_retries: int
    parser: str
    mineru_token: str | None = field(repr=False)
    mineru_base_url: str
    mineru_model_version: str
    mineru_enable_formula: bool
    mineru_enable_table: bool
    mineru_language: str | None
    mineru_timeout: int
    mineru_poll_interval: int
    mineru_user_token: str | None = field(repr=False)

    @classmethod
    def from_env(cls, project_root: Path = PROJECT_ROOT) -> "AnalyzerSettings":
        load_dotenv_if_available(project_root)
        mineru_token = env_first(
            "MINERU_API_TOKEN",
            "MINERU_API_KEY",
            "PAPER_ANALYZER_MINERU_TOKEN",
        )
        default_parser = "mineru" if mineru_token else "local"
        return cls(
            project_root=project_root,
            downloads_dir=resolve_path(
                env_first("PAPER_ANALYZER_DOWNLOADS_DIR", default="downloads"),
                project_root,
            ),
            outputs_dir=resolve_path(
                env_first("PAPER_ANALYZER_OUTPUTS_DIR", default="analyze_paper/outputs"),
                project_root,
            ),
            assets_dir=resolve_path(
                env_first("PAPER_ANALYZER_ASSETS_DIR", default="analyze_paper/assets"),
                project_root,
            ),
            cache_dir=resolve_path(
                env_first("PAPER_ANALYZER_CACHE_DIR", default="analyze_paper/cache"),
                project_root,
            ),
            auth_mode=env_first("PAPER_ANALYZER_AUTH_MODE", default="hmac") or "hmac",
            app_id=env_first("PAPER_ANALYZER_APP_ID", "VIVO_APP_ID", "APP_ID"),
            app_key=env_first("PAPER_ANALYZER_APP_KEY", "VIVO_APP_KEY", "APP_KEY"),
            domain=env_first("PAPER_ANALYZER_DOMAIN", default="api-ai.vivo.com.cn") or "api-ai.vivo.com.cn",
            uri=env_first("PAPER_ANALYZER_URI", default="/vivogpt/completions") or "/vivogpt/completions",
            model=env_first("PAPER_ANALYZER_MODEL", default="vivo-BlueLM-TB-Pro") or "vivo-BlueLM-TB-Pro",
            timeout=env_int("PAPER_ANALYZER_TIMEOUT", 120),
            temperature=env_float("PAPER_ANALYZER_TEMPERATURE", 0.2),
            max_images=env_int("PAPER_ANALYZER_MAX_IMAGES", 8),
            max_chars=env_int("PAPER_ANALYZER_MAX_CHARS", 60000),
            chunk_chars=env_int("PAPER_ANALYZER_CHUNK_CHARS", 24000),
            max_chunks=env_int("PAPER_ANALYZER_MAX_CHUNKS", 8),
            max_retries=env_int("PAPER_ANALYZER_MAX_RETRIES", 2),
            parser=env_first("PAPER_ANALYZER_PARSER", default=default_parser) or default_parser,
            mineru_token=mineru_token,
            mineru_base_url=env_first(
                "MINERU_API_BASE_URL",
                "MINERU_API_DOMAIN",
                default="https://mineru.net",
            )
            or "https://mineru.net",
            mineru_model_version=env_first("MINERU_MODEL_VERSION", default="vlm") or "vlm",
            mineru_enable_formula=env_bool("MINERU_ENABLE_FORMULA", True),
            mineru_enable_table=env_bool("MINERU_ENABLE_TABLE", True),
            mineru_language=env_first("MINERU_LANGUAGE"),
            mineru_timeout=env_int("MINERU_TIMEOUT", 900),
            mineru_poll_interval=env_int("MINERU_POLL_INTERVAL", 5),
            mineru_user_token=env_first("MINERU_USER_TOKEN"),
        )

    def ensure_dirs(self) -> None:
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def require_llm_credentials(self) -> None:
        auth_mode = (self.auth_mode or "hmac").strip().lower()
        missing = []
        if auth_mode != "bearer" and not self.app_id:
            missing.append("PAPER_ANALYZER_APP_ID")
        if not self.app_key:
            missing.append("PAPER_ANALYZER_APP_KEY")
        if missing:
            names = ", ".join(missing)
            raise RuntimeError(
                f"Missing vivo LLM credentials: {names}. "
                "Put them in the repository .env file or export them before running."
            )

    def require_mineru_credentials(self) -> None:
        if not self.mineru_token:
            raise RuntimeError(
                "Missing MinerU API token: MINERU_API_TOKEN or MINERU_API_KEY. "
                "Put it in the repository .env file or export it before running."
            )

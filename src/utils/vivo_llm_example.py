from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.config import AnalyzerSettings, PROJECT_ROOT
from src.utils.llm_client import VivoBlueLMClient


def main() -> int:
    settings = AnalyzerSettings.from_env(PROJECT_ROOT)
    client = VivoBlueLMClient.from_settings(settings)
    prompt = "请用一句话说明你可以如何帮助总结论文。"
    print(client.complete(prompt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

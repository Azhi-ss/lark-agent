"""配置：路径、API key、写回开关等。环境变量优先。"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _find_lark_cli() -> str:
    """定位 lark-cli 可执行文件。"""
    return os.environ.get("LARK_CLI_PATH", "lark-cli")


@dataclass(frozen=True)
class Settings:
    lark_cli: str = _find_lark_cli()
    lark_as: str = "user"
    api_version: str = "v2"
    writeback_enabled: bool = os.environ.get("LARK_WRITEBACK", "1") == "1"
    anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    cors_origins: tuple[str, ...] = (
        os.environ.get("WEB_ORIGIN", "http://localhost:5173"),
    )


settings = Settings()

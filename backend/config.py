"""配置：路径、API key、写回开关等。环境变量优先。"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace


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


# ----- 运行时可变的 LLM 接入配置 -----
#
# 启动配置 Settings 是 frozen 的（不可变原则）。LLM 的 base_url / api_key /
# model 需要支持运行时从设置面板修改，故单独放一个可变状态变量持有 frozen 实例：
# update 时用 dataclasses.replace 生成新实例整体替换，保持不可变原则。
# 默认值仍从环境变量取，首次启动等价于旧行为；设置面板 POST 后即时覆盖。
@dataclass(frozen=True)
class RuntimeLLMConfig:
    """运行时可修改的 LLM 接入配置（frozen，update 返回新实例）。"""

    base_url: str = os.environ.get("ANTHROPIC_BASE_URL", "")
    api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
    auth_token: str = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    model: str = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    # 扩展思考（仅真 Anthropic Claude / api_key 模式生效；火山代理默认开思考、不认此参数）
    thinking_enabled: bool = os.environ.get("ANTHROPIC_THINKING", "0") == "1"
    thinking_budget: int = int(os.environ.get("ANTHROPIC_THINKING_BUDGET", "8000"))


_runtime_llm = RuntimeLLMConfig()


def get_runtime_llm() -> RuntimeLLMConfig:
    """返回运行时 LLM 配置单例。"""
    return _runtime_llm


def update_runtime_llm(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    auth_token: str | None = None,
    model: str | None = None,
    thinking_enabled: bool | None = None,
    thinking_budget: int | None = None,
) -> None:
    """部分更新运行时 LLM 配置；传 None 的字段保持不变（用于密码框留空=不改）。

    frozen 实例不可原地 mutate，用 replace 生成新实例整体替换全局引用。
    """
    global _runtime_llm
    updates: dict[str, object] = {}
    if base_url is not None:
        updates["base_url"] = base_url
    if api_key is not None:
        updates["api_key"] = api_key
    if auth_token is not None:
        updates["auth_token"] = auth_token
    if model is not None:
        updates["model"] = model
    if thinking_enabled is not None:
        updates["thinking_enabled"] = thinking_enabled
    if thinking_budget is not None:
        updates["thinking_budget"] = thinking_budget
    if updates:
        _runtime_llm = replace(_runtime_llm, **updates)

"""backend/config.py 单元测试。

注意:Settings 字段默认值在模块导入时从 os.environ 求值,因此本测试聚焦于
显式构造、frozen 语义、以及 _find_lark_cli 的环境变量分支。
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from backend.config import Settings, _find_lark_cli, settings


def test_settings_is_frozen():
    """Settings 必须 frozen,字段赋值应抛异常。"""
    s = Settings()
    with pytest.raises(FrozenInstanceError):
        s.lark_as = "tenant"  # type: ignore[misc]


def test_module_settings_instance_exists():
    """模块级 settings 是 Settings 实例,字段类型符合契约。"""
    assert isinstance(settings, Settings)
    assert settings.lark_as == "user"
    assert settings.api_version == "v2"
    assert isinstance(settings.cors_origins, tuple)


def test_settings_explicit_construction():
    """显式传参构造,字段原样保留(不可变记录语义)。"""
    s = Settings(
        lark_cli="/custom/lark-cli",
        writeback_enabled=False,
        anthropic_api_key="sk-test",
        anthropic_model="claude-sonnet-4-6",
        cors_origins=("http://a", "http://b"),
    )
    assert s.lark_cli == "/custom/lark-cli"
    assert s.writeback_enabled is False
    assert s.anthropic_api_key == "sk-test"
    assert s.cors_origins == ("http://a", "http://b")


def test_find_lark_cli_default():
    """无 LARK_CLI_PATH 时返回默认 'lark-cli'。"""
    assert _find_lark_cli() == "lark-cli"


def test_find_lark_cli_respects_env(monkeypatch):
    """设置 LARK_CLI_PATH 时返回该路径。"""
    monkeypatch.setenv("LARK_CLI_PATH", "/opt/bin/lark-cli")
    assert _find_lark_cli() == "/opt/bin/lark-cli"

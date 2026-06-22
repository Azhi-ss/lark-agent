"""run_agent_stream / run_solution_stream 流式核心逻辑单测（P3 阶段5）。

直接驱动 agent.py 的两个 stream 生成器（不经 FastAPI 路由），用伪造的
anthropic stream 事件序列（content_block_start / content_block_delta /
content_block_stop）覆盖关键分支：
- 正常产出 artifact 结构
- 畸形 JSON → error 事件（不再静默吞掉）
- 模型未调 tool → error 而非 bare complete
- 0 replacements 不发 action_required
- APIError → error 收尾不发 complete

mock 策略：替换 anthropic.Anthropic 类，messages.stream 返回伪造上下文管理器，
迭代它产出预构造的 stream 事件对象（duck-typed：带 .type / .content_block / .delta）。
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import anthropic
import pytest

from backend.agent import agent as agent_mod
from backend.config import update_runtime_llm


def _ev(type_: str, **kw):
    """构造 duck-typed stream 事件，字段按需补。"""
    return SimpleNamespace(type=type_, **kw)


def _content_block(block_type: str, name: str | None = None):
    return SimpleNamespace(type=block_type, name=name)


def _delta(delta_type: str, **kw):
    return SimpleNamespace(type=delta_type, **kw)


class _FakeStream:
    """伪造 client.messages.stream 返回的上下文管理器；迭代产出事件序列。"""

    def __init__(self, events):
        self._events = list(events)

    def __enter__(self):
        return iter(self._events)

    def __exit__(self, *exc):
        return False


class _FakeMessages:
    def __init__(self, events):
        self._events = events
        self.stream = lambda *a, **kw: _FakeStream(self._events)


class _FakeClient:
    def __init__(self, events, **kwargs):
        self.kwargs = kwargs
        self.messages = _FakeMessages(events)


def _patch_client(events):
    """返回 context manager，把 anthropic.Anthropic 替换为产出指定事件的假 client。"""
    return patch.object(anthropic, "Anthropic", lambda **kw: _FakeClient(events, **kw))


def _reset_llm():
    update_runtime_llm(api_key="sk-test", model="test-model")


# ===== run_agent_stream =====


def _edit_doc_events(tool_raw: str, *, text: str = "分析中"):
    """构造一条 edit_document tool_use 流（含 thinking + assistant_text + tool JSON）。"""
    return [
        _ev("content_block_start", content_block=_content_block("thinking")),
        _ev("content_block_delta", delta=_delta("thinking_delta", thinking="思路")),
        _ev("content_block_stop"),
        _ev("content_block_start", content_block=_content_block("text")),
        _ev("content_block_delta", delta=_delta("text_delta", text=text)),
        _ev("content_block_stop"),
        _ev("content_block_start", content_block=_content_block("tool_use", name="edit_document")),
        _ev("content_block_delta", delta=_delta("input_json_delta", partial_json=tool_raw)),
        _ev("content_block_stop"),
    ]


def test_run_agent_stream_normal_artifact_and_action_required():
    """正常流：artifact(document_edits) 带 replacements，且 1 条替换发 action_required + complete。"""
    _reset_llm()
    raw = json.dumps({"replacements": [{"pattern": "旧", "content": "新", "reason": "润色"}]})
    with _patch_client(_edit_doc_events(raw)):
        events = list(agent_mod.run_agent_stream("doc", "改一下"))

    types = [e.type for e in events]
    assert "artifact" in types
    assert "complete" in types
    art = next(e for e in events if e.type == "artifact")
    assert art.data["artifact_type"] == "document_edits"
    reps = art.data["payload"]["replacements"]
    assert len(reps) == 1
    assert reps[0]["pattern"] == "旧"
    assert reps[0]["content"] == "新"
    # 有替换 → 发 writeback_confirmation action_required
    assert "action_required" in types
    ar = next(e for e in events if e.type == "action_required")
    assert ar.data["reason"] == "writeback_confirmation"


def test_run_agent_stream_malformed_json_emits_error_not_complete():
    """畸形 tool JSON → error 事件，且其后不发 artifact/complete（显式报错而非静默）。"""
    _reset_llm()
    with _patch_client(_edit_doc_events("{not valid json")):
        events = list(agent_mod.run_agent_stream("doc", "改"))

    types = [e.type for e in events]
    assert "error" in types
    err = next(e for e in events if e.type == "error")
    assert "edit_document" in err.data["message"]
    # 关键：不应产出 artifact / action_required / complete
    assert "artifact" not in types
    assert "action_required" not in types
    assert "complete" not in types


def test_run_agent_stream_no_tool_called_emits_error():
    """模型未调用 edit_document → error（无 artifact、无 bare complete）。"""
    _reset_llm()
    events_seq = [
        _ev("content_block_start", content_block=_content_block("text")),
        _ev("content_block_delta", delta=_delta("text_delta", text="我不知道")),
        _ev("content_block_stop"),
    ]
    with _patch_client(events_seq):
        events = list(agent_mod.run_agent_stream("doc", "改"))

    types = [e.type for e in events]
    assert "error" in types
    assert "artifact" not in types
    assert "action_required" not in types
    assert "complete" not in types


def test_run_agent_stream_empty_replacements_no_action_required():
    """0 条替换：仍发 artifact，但不发 action_required（无内容可写回）。"""
    _reset_llm()
    raw = json.dumps({"replacements": []})
    with _patch_client(_edit_doc_events(raw)):
        events = list(agent_mod.run_agent_stream("doc", "改"))

    types = [e.type for e in events]
    assert "artifact" in types
    assert "complete" in types
    art = next(e for e in events if e.type == "artifact")
    assert art.data["payload"]["replacements"] == []
    # 0 条替换 → 不发 writeback 确认（避免 timeline 让确认、drawer 无内容可写的矛盾 UX）
    assert "action_required" not in types


def test_run_agent_stream_api_error_emits_error_no_complete():
    """APIError → error 收尾，不发 complete。"""
    _reset_llm()

    class _BoomStream:
        def __enter__(self):
            raise anthropic.APIStatusError(
                message="boom",
                response=__import__("httpx").Response(
                    status_code=500,
                    request=__import__("httpx").Request("POST", "https://x"),
                ),
                body=None,
            )

        def __exit__(self, *exc):
            return False

    class _BoomMessages:
        stream = lambda *a, **kw: _BoomStream()  # noqa: E731

    class _BoomClient:
        def __init__(self, **kwargs):
            self.messages = _BoomMessages()

    with patch.object(anthropic, "Anthropic", lambda **kw: _BoomClient()):
        events = list(agent_mod.run_agent_stream("doc", "改"))

    types = [e.type for e in events]
    assert "error" in types
    err = next(e for e in events if e.type == "error")
    assert "LLM 调用失败" in err.data["message"]
    assert "complete" not in types


# ===== run_solution_stream =====


def _produce_solution_events(tool_raw: str, *, text: str = "基于上下文"):
    """构造一条 produce_solution tool_use 流。"""
    return [
        _ev("content_block_start", content_block=_content_block("text")),
        _ev("content_block_delta", delta=_delta("text_delta", text=text)),
        _ev("content_block_stop"),
        _ev("content_block_start", content_block=_content_block("tool_use", name="produce_solution")),
        _ev("content_block_delta", delta=_delta("input_json_delta", partial_json=tool_raw)),
        _ev("content_block_stop"),
    ]


def test_run_solution_stream_normal_artifact():
    """正常流：artifact(solution) + complete；首轮无 overwrite 确认。"""
    _reset_llm()
    raw = json.dumps({"title": "方案", "markdown": "# 方案", "summary": "初版"})
    with _patch_client(_produce_solution_events(raw)):
        events = list(
            agent_mod.run_solution_stream(
                [{"url": "u", "markdown": "# 需求"}],
                [{"role": "user", "content": "出方案"}],
                has_previous_solution=False,
            )
        )

    types = [e.type for e in events]
    assert "artifact" in types
    assert "complete" in types
    art = next(e for e in events if e.type == "artifact")
    assert art.data["artifact_type"] == "solution"
    assert art.data["payload"]["markdown"] == "# 方案"
    # 首轮不发 overwrite 确认
    assert "action_required" not in types


def test_run_solution_stream_non_first_round_emits_overwrite_confirmation():
    """非首轮 + 正常产出 → artifact + action_required(overwrite) + complete。"""
    _reset_llm()
    raw = json.dumps({"title": "方案", "markdown": "# v2", "summary": "改"})
    with _patch_client(_produce_solution_events(raw)):
        events = list(
            agent_mod.run_solution_stream(
                [],
                [
                    {"role": "user", "content": "出方案"},
                    {"role": "assistant", "content": "好"},
                    {"role": "user", "content": "改"},
                ],
                has_previous_solution=True,
            )
        )

    types = [e.type for e in events]
    assert "action_required" in types
    ar = next(e for e in events if e.type == "action_required")
    assert ar.data["reason"] == "overwrite_solution_confirmation"


def test_run_solution_stream_malformed_json_emits_error():
    """畸形 produce_solution JSON → error，不发 artifact/complete。"""
    _reset_llm()
    with _patch_client(_produce_solution_events("{broken")):
        events = list(
            agent_mod.run_solution_stream(
                [], [{"role": "user", "content": "出方案"}], has_previous_solution=False
            )
        )

    types = [e.type for e in events]
    assert "error" in types
    err = next(e for e in events if e.type == "error")
    assert "produce_solution" in err.data["message"]
    assert "artifact" not in types
    assert "complete" not in types


def test_run_solution_stream_no_tool_called_emits_error_not_bare_complete():
    """模型未调 produce_solution → error（solution is None），不发 bare complete。"""
    _reset_llm()
    events_seq = [
        _ev("content_block_start", content_block=_content_block("text")),
        _ev("content_block_delta", delta=_delta("text_delta", text="我没调工具")),
        _ev("content_block_stop"),
    ]
    with _patch_client(events_seq):
        events = list(
            agent_mod.run_solution_stream(
                [], [{"role": "user", "content": "出方案"}], has_previous_solution=False
            )
        )

    types = [e.type for e in events]
    assert "error" in types
    assert "complete" not in types
    assert "artifact" not in types


def test_run_solution_stream_empty_messages_emits_error():
    """空 messages → 直接 error（参数校验）。"""
    _reset_llm()
    with _patch_client([]):
        events = list(
            agent_mod.run_solution_stream([], [], has_previous_solution=False)
        )
    types = [e.type for e in events]
    assert "error" in types
    assert "messages" in events[0].data["message"]


@pytest.fixture(autouse=True)
def _cleanup_llm():
    """每个测试后重置运行时 LLM 配置，避免跨测试污染。"""
    yield
    update_runtime_llm(api_key="", auth_token="", base_url="", model="claude-sonnet-4-6")

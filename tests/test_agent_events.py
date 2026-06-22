"""P3 阶段5 后端 SSE 产品语义事件解析测试。

覆盖 /agent/chat 与 /agent/solution 两个 SSE 端点的事件序列契约：
- monkeypatch run_agent_stream / run_solution_stream 返回伪造 AgentEvent 序列
- TestClient.post 拿 text/event-stream，解析 data: 行，断言事件类型与顺序
- 不触发真实 LLM / lark 调用（fetch_doc 也 monkeypatch）
- writeback_enabled=False 作为安全网，避免任何写回侧 lark 调用
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from backend.agent.agent import AgentEvent
from backend.config import Settings
from backend.lark.cli_wrapper import FetchResult
from backend.main import app

client = TestClient(app)


def _parse_sse_events(text: str) -> list[dict]:
    """解析 SSE 文本流，返回 [{type, data}, ...] 事件列表。

    SSE 帧格式为 `data: {json}\n\n`，按行扫描取 data: 前缀即可。
    """
    events: list[dict] = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            if payload:
                events.append(json.loads(payload))
    return events


def _types(events: list[dict]) -> list[str]:
    """提取事件类型有序列表，便于整体断言事件序列。"""
    return [e["type"] for e in events]


def _fake_fetch(doc_ref, *, doc_format="xml", detail="simple"):
    """伪造 fetch_doc：返回带 id 的合法 XML，供路由 parse_xml 不抛错。

    路由 /agent/chat 会 fetch → parse_xml → blocks_to_text 得到 doc_text，
    再传给 run_agent_stream（已被 monkeypatch，不真正消费 doc_text）。
    """
    return FetchResult(
        document_id="doc-fake",
        revision_id=7,
        content_xml='<title id="blkcnT">周报</title><p id="blkcnA">本周内容</p>',
    )


def _disable_writeback(monkeypatch) -> None:
    """统一关闭写回，作为安全网避免任何真实 lark 写调用。"""
    monkeypatch.setattr(
        "backend.api.routes.settings",
        Settings(writeback_enabled=False),
    )


# ===== /agent/chat：文档编辑事件序列 =====


def test_agent_chat_emits_full_event_sequence(monkeypatch):
    """/agent/chat 完整事件流：status → thinking_summary → assistant_text(增量)
    → artifact(document_edits) → action_required(writeback_confirmation) → complete。
    """
    _disable_writeback(monkeypatch)
    monkeypatch.setattr("backend.api.routes.fetch_doc", _fake_fetch)

    def fake_stream(doc_text, instruction, *, model=None):
        yield AgentEvent("thinking_summary", {"text": "分析上下文"})
        # assistant_text 是增量 delta，前端累积；这里发两条验证多帧透传
        yield AgentEvent("assistant_text", {"text": "我来帮你"})
        yield AgentEvent("assistant_text", {"text": "修改"})
        yield AgentEvent(
            "artifact",
            {
                "artifact_type": "document_edits",
                "title": "修改建议",
                "summary": "1 处修改建议",
                "payload": {
                    "replacements": [
                        {"pattern": "本周内容", "content": "本周要点", "reason": "提炼"}
                    ],
                    "final_text": "本周要点",
                },
            },
        )
        yield AgentEvent("action_required", {"reason": "writeback_confirmation"})
        yield AgentEvent("complete", {})

    monkeypatch.setattr("backend.api.routes.run_agent_stream", fake_stream)

    resp = client.post(
        "/api/agent/chat",
        json={"url": "https://example.feishu.cn/docx/fake", "instruction": "提炼要点"},
    )
    assert resp.status_code == 200
    events = _parse_sse_events(resp.text)

    # 事件类型顺序严格匹配契约
    assert _types(events) == [
        "status",
        "thinking_summary",
        "assistant_text",
        "assistant_text",
        "artifact",
        "action_required",
        "complete",
    ]

    # status 由路由硬编码（加载上下文中）
    assert events[0]["data"]["label"] == "加载上下文中"

    # thinking_summary 增量 delta
    assert events[1]["data"]["text"] == "分析上下文"

    # assistant_text 多帧增量，各自独立透传
    assert events[2]["data"]["text"] == "我来帮你"
    assert events[3]["data"]["text"] == "修改"

    # artifact 契约：artifact_type + title + summary + payload(replacements/final_text)
    art = events[4]
    assert art["data"]["artifact_type"] == "document_edits"
    assert art["data"]["title"] == "修改建议"
    assert art["data"]["summary"] == "1 处修改建议"
    rep = art["data"]["payload"]["replacements"][0]
    assert rep["pattern"] == "本周内容"
    assert rep["content"] == "本周要点"
    assert rep["reason"] == "提炼"
    assert art["data"]["payload"]["final_text"] == "本周要点"

    # action_required 契约：reason=writeback_confirmation
    assert events[5]["data"]["reason"] == "writeback_confirmation"

    # complete 无 data
    assert events[6]["data"] == {}


def test_agent_chat_emits_error_event(monkeypatch):
    """/agent/chat 在 agent 流产出 error 事件时，SSE 透传 error（status 仍先发）。"""
    _disable_writeback(monkeypatch)
    monkeypatch.setattr("backend.api.routes.fetch_doc", _fake_fetch)

    def fake_stream(doc_text, instruction, *, model=None):
        yield AgentEvent("error", {"message": "LLM 调用失败: boom"})

    monkeypatch.setattr("backend.api.routes.run_agent_stream", fake_stream)

    resp = client.post(
        "/api/agent/chat",
        json={"url": "https://example.feishu.cn/docx/fake", "instruction": "提炼"},
    )
    assert resp.status_code == 200
    events = _parse_sse_events(resp.text)
    assert _types(events) == ["status", "error"]
    assert events[1]["data"]["message"] == "LLM 调用失败: boom"


# ===== /agent/solution：方案构建事件序列 =====


def _fake_solution_stream(docs, messages, *, has_previous_solution=False, model=None):
    """伪造方案流：镜像真实 run_solution_stream 语义。

    首轮（has_previous_solution=False）不发 action_required；
    非首轮发 action_required(overwrite_solution_confirmation)。
    """
    summary = "初版" if not has_previous_solution else "新增时间表"
    yield AgentEvent("thinking_summary", {"text": "构思方案"})
    yield AgentEvent("assistant_text", {"text": "基于上下文"})
    yield AgentEvent(
        "artifact",
        {
            "artifact_type": "solution",
            "title": "方案标题",
            "summary": summary,
            "payload": {
                "title": "方案标题",
                "markdown": "# 方案\n## 背景",
                "summary": summary,
            },
        },
    )
    if has_previous_solution:
        yield AgentEvent(
            "action_required",
            {"reason": "overwrite_solution_confirmation"},
        )
    yield AgentEvent("complete", {})


def test_solution_first_round_no_action_required(monkeypatch):
    """首轮方案（仅 1 条消息）：artifact(solution) → complete，无 action_required。"""
    _disable_writeback(monkeypatch)
    monkeypatch.setattr("backend.api.routes.run_solution_stream", _fake_solution_stream)

    resp = client.post(
        "/api/agent/solution",
        json={
            "docs": [{"url": "https://x.feishu.cn/docx/d1", "markdown": "# 需求"}],
            "messages": [{"role": "user", "content": "帮我出个方案"}],
        },
    )
    assert resp.status_code == 200
    events = _parse_sse_events(resp.text)
    # 首轮无 action_required
    assert _types(events) == [
        "status",
        "thinking_summary",
        "assistant_text",
        "artifact",
        "complete",
    ]
    # artifact(solution) 契约
    art = events[3]
    assert art["data"]["artifact_type"] == "solution"
    assert art["data"]["title"] == "方案标题"
    assert art["data"]["summary"] == "初版"
    assert art["data"]["payload"]["markdown"] == "# 方案\n## 背景"
    assert art["data"]["payload"]["summary"] == "初版"
    # complete 无 data
    assert events[4]["data"] == {}


def test_solution_non_first_round_has_overwrite_confirmation(monkeypatch):
    """非首轮方案（>1 条消息）：artifact(solution) →
    action_required(overwrite_solution_confirmation) → complete。
    """
    _disable_writeback(monkeypatch)
    monkeypatch.setattr("backend.api.routes.run_solution_stream", _fake_solution_stream)

    resp = client.post(
        "/api/agent/solution",
        json={
            "docs": [{"url": "https://x.feishu.cn/docx/d1", "markdown": "# 需求"}],
            "messages": [
                {"role": "user", "content": "帮我出个方案"},
                {"role": "assistant", "content": "好的"},
                {"role": "user", "content": "加个时间表"},
            ],
        },
    )
    assert resp.status_code == 200
    events = _parse_sse_events(resp.text)
    assert _types(events) == [
        "status",
        "thinking_summary",
        "assistant_text",
        "artifact",
        "action_required",
        "complete",
    ]
    # 非首轮 summary 反映增量改动
    assert events[3]["data"]["summary"] == "新增时间表"
    # action_required 契约：reason=overwrite_solution_confirmation
    assert events[4]["data"]["reason"] == "overwrite_solution_confirmation"
    assert events[5]["data"] == {}


def test_solution_emits_error_event(monkeypatch):
    """/agent/solution 在 agent 流产出 error 事件时，SSE 透传 error（status 仍先发）。"""
    _disable_writeback(monkeypatch)

    def fake_stream(docs, messages, *, has_previous_solution=False, model=None):
        yield AgentEvent("error", {"message": "LLM 调用失败: timeout"})

    monkeypatch.setattr("backend.api.routes.run_solution_stream", fake_stream)

    resp = client.post(
        "/api/agent/solution",
        json={"docs": [], "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 200
    events = _parse_sse_events(resp.text)
    assert _types(events) == ["status", "error"]
    assert events[1]["data"]["message"] == "LLM 调用失败: timeout"


def test_solution_has_previous_solution_is_messages_length_driven(monkeypatch):
    """路由按 len(messages) > 1 决定 has_previous_solution：恰好 2 条消息即视为非首轮。

    用调用记录验证透传给 run_solution_stream 的 flag，锁定路由分支判定逻辑。
    """
    _disable_writeback(monkeypatch)

    captured: list[bool] = []

    def capturing_stream(docs, messages, *, has_previous_solution=False, model=None):
        captured.append(has_previous_solution)
        yield AgentEvent("complete", {})

    monkeypatch.setattr("backend.api.routes.run_solution_stream", capturing_stream)

    # 1 条消息 → 首轮
    client.post(
        "/api/agent/solution",
        json={"docs": [], "messages": [{"role": "user", "content": "a"}]},
    )
    # 2 条消息 → 非首轮
    client.post(
        "/api/agent/solution",
        json={
            "messages": [
                {"role": "user", "content": "a"},
                {"role": "assistant", "content": "b"},
            ]
        },
    )
    assert captured == [False, True]

"""Agent 核心：基于 Anthropic SDK + 火山代理，提炼与修改飞书周报。

设计：
- agent 看到文档的真实 markdown + 用户指令
- 通过 edit_document 工具产出一组 Replacement（pattern→content，markdown str_replace 语义）
- 不立即写飞书：replacements 返回给前端，用户确认 diff 后由 /doc/apply 执行
- 流式 yield 事件（thinking / text / tool_use / done），供 SSE 推送
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import anthropic

from backend.config import settings

SYSTEM_PROMPT_SOLUTION = """你是方案架构师。用户会给你 N 份上下文文档（需求文档 / 聊天记录 / 能力清单 / 现有方案等）以及一段对话历史。你的目标是基于全部上下文和对话语境，产出一份完整、结构化、可落地的解决方案。

工作方式：
1. 通读所有上下文文档，识别真实的目标、约束、能力边界。
2. 与用户对话时，先用简短自然语言回应（说明理解和取舍），再调用 `produce_solution` 工具产出最新一版完整方案。
3. 后续轮次，用户可能要求"在第3节加一个时间表""把语气改正式""收紧某模块"等增量修改 —— 你应基于上一轮方案 + 新指令产出**全量替换**的新版方案 markdown。
4. 方案必须结构化（Markdown 标题/列表/表格），覆盖：背景、目标、范围、关键设计、分阶段任务、风险与对策、验收标准；视上下文裁剪。
5. 方案语言与上下文保持一致（中文）。
6. 不要臆造上下文里没有的事实；如果信息不足，明确写出"待确认"。

每一轮你都必须调用一次 `produce_solution`，参数：
- `title`：方案标题（一句话）。
- `markdown`：完整方案正文（Markdown，包含所有章节）。
- `summary`：本轮相对上一版的改动摘要（首轮写"初版"）。
"""

SYSTEM_PROMPT = """你是飞书周报编辑助手。用户会给你一份周报的 Markdown 原文和一条编辑指令（如"提炼本周要点""精简第二段""修正错别字"）。

你的能力：
1. 提炼：理解周报内容，生成结构化摘要/要点。
2. 修改：按指令对原文做精准编辑。

修改方式：调用 `edit_document` 工具，传入 `replacements` 数组。每个 replacement 是一次 Markdown 文本替换：
- `pattern`：原文中**真实存在、连续**的文本片段（必须逐字匹配，否则替换失败）。可用 `前缀...后缀` 省略号语法匹配首尾明显的大段内容。
- `content`：替换后的完整文本（Markdown）。
- `reason`：简短说明为什么这么改。

规则：
- pattern 必须来自原文，不要臆造。短而独特优先，避免歧义匹配。
- 一次只产出必要的一处或多处替换；不要无依据地重写整篇。
- 提炼类需求：把摘要作为新内容，pattern 选摘要要插入位置附近的一段原文，content = 摘要 + 原文（在原位置前插入），或在文末追加。
- 输出语言与原文一致（中文）。
"""


@dataclass(frozen=True)
class Replacement:
    """一次 markdown str_replace 编辑建议。"""

    pattern: str
    content: str
    reason: str = ""


@dataclass(frozen=True)
class AgentEvent:
    """流式事件，供 SSE 推送。"""

    type: str  # thinking / text / tool_use / done / error
    data: dict[str, Any]

    def as_sse(self) -> str:
        import json
        payload = json.dumps({"type": self.type, "data": self.data}, ensure_ascii=False)
        return f"data: {payload}\n\n"


EDIT_TOOL: dict[str, Any] = {
    "name": "edit_document",
    "description": "对周报 Markdown 原文提出一处或多处文本替换。pattern 必须逐字匹配原文。",
    "input_schema": {
        "type": "object",
        "properties": {
            "replacements": {
                "type": "array",
                "description": "替换列表，按顺序应用",
                "items": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "原文中真实存在的连续文本片段，可用 前缀...后缀 省略号语法"},
                        "content": {"type": "string", "description": "替换后的完整 Markdown 文本"},
                        "reason": {"type": "string", "description": "修改理由"},
                    },
                    "required": ["pattern", "content"],
                },
            }
        },
        "required": ["replacements"],
    },
}


PRODUCE_TOOL: dict[str, Any] = {
    "name": "produce_solution",
    "description": "产出/更新一份完整结构化方案 Markdown。每一轮都应调用一次（全量替换上一版）。",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "方案标题（一句话）"},
            "markdown": {"type": "string", "description": "完整方案正文，结构化 Markdown"},
            "summary": {"type": "string", "description": "本轮改动摘要；首轮写'初版'"},
        },
        "required": ["title", "markdown"],
    },
}


@dataclass(frozen=True)
class Solution:
    """一份结构化方案。"""

    title: str
    markdown: str
    summary: str = ""


def _make_client() -> anthropic.Anthropic:
    """构造 anthropic client，兼容火山代理（base_url + auth_token）。"""
    kwargs: dict[str, Any] = {}
    if settings.anthropic_api_key:
        kwargs["api_key"] = settings.anthropic_api_key
    else:
        # 走环境里的火山代理：ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN
        kwargs["auth_token"] = os.environ["ANTHROPIC_AUTH_TOKEN"]
        kwargs["base_url"] = os.environ["ANTHROPIC_BASE_URL"]
    return anthropic.Anthropic(**kwargs)


def run_agent(
    markdown: str,
    instruction: str,
    *,
    model: str | None = None,
) -> tuple[list[Replacement], str]:
    """非流式运行 agent，返回 (replacements, final_text)。"""
    client = _make_client()
    user_msg = f"# 周报原文（Markdown）\n\n{markdown}\n\n---\n# 编辑指令\n{instruction}"
    resp = client.messages.create(
        model=model or settings.anthropic_model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[EDIT_TOOL],
        messages=[{"role": "user", "content": user_msg}],
    )

    replacements: list[Replacement] = []
    texts: list[str] = []
    for blk in resp.content:
        if blk.type == "text":
            texts.append(blk.text)
        elif blk.type == "tool_use" and blk.name == "edit_document":
            for r in blk.input.get("replacements", []):
                replacements.append(
                    Replacement(
                        pattern=r.get("pattern", ""),
                        content=r.get("content", ""),
                        reason=r.get("reason", ""),
                    )
                )
    return replacements, "\n".join(texts)


def run_agent_stream(
    markdown: str,
    instruction: str,
    *,
    model: str | None = None,
) -> Iterator[AgentEvent]:
    """流式运行 agent，yield 事件。

    事件类型：thinking / text（增量）/ tool_use / done（含 replacements）/ error。
    """
    try:
        client = _make_client()
    except KeyError as exc:
        yield AgentEvent("error", {"message": f"缺少环境变量: {exc}"})
        return

    user_msg = f"# 周报原文（Markdown）\n\n{markdown}\n\n---\n# 编辑指令\n{instruction}"
    try:
        with client.messages.stream(
            model=model or settings.anthropic_model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=[EDIT_TOOL],
            messages=[{"role": "user", "content": user_msg}],
        ) as stream:
            replacements: list[Replacement] = []
            text_buf: list[str] = []
            current_tool_input: dict[str, Any] = {}
            for event in stream:
                et = event.type
                if et == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        current_tool_input = {"name": block.name}
                elif et == "content_block_delta":
                    delta = event.delta
                    if delta.type == "thinking_delta":
                        yield AgentEvent("thinking", {"text": delta.thinking})
                    elif delta.type == "text_delta":
                        text_buf.append(delta.text)
                        yield AgentEvent("text", {"text": delta.text})
                    elif delta.type == "input_json_delta":
                        current_tool_input.setdefault("_raw", "")
                        current_tool_input["_raw"] += delta.partial_json
                elif et == "content_block_stop":
                    if current_tool_input.get("name") == "edit_document":
                        import json
                        try:
                            parsed = json.loads(current_tool_input.get("_raw", "{}"))
                            for r in parsed.get("replacements", []):
                                replacements.append(
                                    Replacement(
                                        pattern=r.get("pattern", ""),
                                        content=r.get("content", ""),
                                        reason=r.get("reason", ""),
                                    )
                                )
                        except json.JSONDecodeError:
                            pass
                        current_tool_input = {}
            final_text = "".join(text_buf)
            yield AgentEvent("done", {
                "replacements": [
                    {"pattern": r.pattern, "content": r.content, "reason": r.reason}
                    for r in replacements
                ],
                "final_text": final_text,
            })
    except anthropic.APIError as exc:
        yield AgentEvent("error", {"message": f"LLM 调用失败: {exc}"})


def _build_docs_context(docs: list[dict[str, Any]]) -> str:
    """把多份文档拼接成单条上下文字符串，供 user 消息引用。"""
    if not docs:
        return "（无上下文文档）"
    parts: list[str] = ["# 上下文文档"]
    for i, d in enumerate(docs, start=1):
        url = str(d.get("url", "")).strip()
        md = str(d.get("markdown", ""))
        parts.append(f"\n## 文档{i}: {url}\n{md}")
    return "\n".join(parts)


def run_solution_stream(
    docs: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
) -> Iterator[AgentEvent]:
    """方案构建模式：基于多份文档 + 多轮对话，流式产出/更新 Solution。

    docs: [{url, markdown}, ...]
    messages: [{role: 'user'|'assistant', content: str}, ...]
    事件类型：thinking / text / done（含 solution: {title, markdown, summary}）/ error。
    """
    try:
        client = _make_client()
    except KeyError as exc:
        yield AgentEvent("error", {"message": f"缺少环境变量: {exc}"})
        return

    if not messages:
        yield AgentEvent("error", {"message": "messages 不能为空"})
        return

    # 把文档上下文塞进第一条 user 消息（其余消息保持原样）
    docs_block = _build_docs_context(docs)
    chat_messages: list[dict[str, Any]] = []
    first_user_seen = False
    for m in messages:
        role = m.get("role", "user")
        content = str(m.get("content", ""))
        if role == "user" and not first_user_seen:
            content = f"{docs_block}\n\n---\n\n{content}"
            first_user_seen = True
        chat_messages.append({"role": role, "content": content})

    try:
        with client.messages.stream(
            model=model or settings.anthropic_model,
            max_tokens=8192,
            system=SYSTEM_PROMPT_SOLUTION,
            tools=[PRODUCE_TOOL],
            messages=chat_messages,
        ) as stream:
            text_buf: list[str] = []
            current_tool_input: dict[str, Any] = {}
            solution: Solution | None = None
            for event in stream:
                et = event.type
                if et == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        current_tool_input = {"name": block.name}
                elif et == "content_block_delta":
                    delta = event.delta
                    if delta.type == "thinking_delta":
                        yield AgentEvent("thinking", {"text": delta.thinking})
                    elif delta.type == "text_delta":
                        text_buf.append(delta.text)
                        yield AgentEvent("text", {"text": delta.text})
                    elif delta.type == "input_json_delta":
                        current_tool_input.setdefault("_raw", "")
                        current_tool_input["_raw"] += delta.partial_json
                elif et == "content_block_stop":
                    if current_tool_input.get("name") == "produce_solution":
                        import json
                        try:
                            parsed = json.loads(current_tool_input.get("_raw", "{}"))
                            solution = Solution(
                                title=str(parsed.get("title", "")),
                                markdown=str(parsed.get("markdown", "")),
                                summary=str(parsed.get("summary", "")),
                            )
                        except json.JSONDecodeError:
                            pass
                        current_tool_input = {}
            final_text = "".join(text_buf)
            done_payload: dict[str, Any] = {"final_text": final_text}
            if solution is not None:
                done_payload["solution"] = {
                    "title": solution.title,
                    "markdown": solution.markdown,
                    "summary": solution.summary,
                }
            yield AgentEvent("done", done_payload)
    except anthropic.APIError as exc:
        yield AgentEvent("error", {"message": f"LLM 调用失败: {exc}"})

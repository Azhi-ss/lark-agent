"""FastAPI 路由：文档加载、agent 对话（SSE）、写回飞书、方案构建会话。"""
from __future__ import annotations

import io
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.agent.agent import run_agent_stream, run_solution_stream
from backend.config import get_runtime_llm, settings, update_runtime_llm
from backend.lark.cli_wrapper import LarkError, fetch_doc, update_doc
from backend.lark.doc_xml import parse_xml

router = APIRouter()

# 会话存储目录：~/.lark_agent/sessions
SESSIONS_DIR: Path = Path.home() / ".lark_agent" / "sessions"


def _ensure_sessions_dir() -> Path:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return SESSIONS_DIR


@dataclass(frozen=True)
class SessionMeta:
    """会话元信息（不可变），用于列表展示。"""

    session_id: str
    name: str
    saved_at: str
    doc_count: int


class LoadRequest(BaseModel):
    url: str = Field(..., description="飞书文档 URL（docx/wiki）")


class LoadResponse(BaseModel):
    document_id: str
    revision_id: int
    markdown: str
    block_count: int


class ChatRequest(BaseModel):
    markdown: str
    instruction: str


class ReplacementItem(BaseModel):
    pattern: str
    content: str
    reason: str = ""


class ApplyRequest(BaseModel):
    url: str
    replacements: list[ReplacementItem]
    revision_id: int = -1


@router.post("/doc/load", response_model=LoadResponse)
def load_doc(req: LoadRequest) -> LoadResponse:
    """加载飞书文档：返回 markdown（agent 用）+ block 数（前端用）。"""
    try:
        md = fetch_doc(req.url, doc_format="markdown")
        xml = fetch_doc(req.url, doc_format="xml")
    except LarkError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    blocks = parse_xml(xml.content_xml)
    return LoadResponse(
        document_id=md.document_id,
        revision_id=md.revision_id,
        markdown=md.content_xml,
        block_count=len(blocks),
    )


@router.post("/agent/chat")
async def agent_chat(req: ChatRequest):
    """SSE 流：推送 agent 的 thinking / text / done 事件。"""
    from fastapi.responses import StreamingResponse

    def gen():
        for ev in run_agent_stream(req.markdown, req.instruction):
            yield ev.as_sse()

    return StreamingResponse(gen(), media_type="text/event-stream")


class SolutionDoc(BaseModel):
    url: str = ""
    markdown: str = ""


class SolutionMessage(BaseModel):
    role: str = "user"
    content: str = ""


class SolutionRequest(BaseModel):
    docs: list[SolutionDoc] = Field(default_factory=list)
    messages: list[SolutionMessage] = Field(default_factory=list)


@router.post("/agent/solution")
async def agent_solution(req: SolutionRequest):
    """SSE 流：方案构建模式。事件 thinking / text / done(含 solution) / error。"""
    from fastapi.responses import StreamingResponse

    docs = [d.model_dump() for d in req.docs]
    messages = [m.model_dump() for m in req.messages]

    def gen():
        for ev in run_solution_stream(docs, messages):
            yield ev.as_sse()

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/doc/apply")
def apply_edits(req: ApplyRequest) -> dict[str, Any]:
    """把 replacements 逐个作为 markdown str_replace 写回飞书。"""
    if not settings.writeback_enabled:
        return {"simulated": True, "count": len(req.replacements), "results": []}

    results: list[dict[str, Any]] = []
    for i, rep in enumerate(req.replacements):
        try:
            data = update_doc(
                req.url,
                command="str_replace",
                pattern=rep.pattern,
                content=rep.content,
                doc_format="markdown",
                revision_id=-1,  # 始终基于最新版本，避免旧版本匹配失败
            )
            results.append({"index": i, "ok": True, "data": data})
        except LarkError as exc:
            results.append({"index": i, "ok": False, "error": str(exc), "raw": exc.raw})
    return {
        "ok": all(r["ok"] for r in results),
        "count": len(results),
        "results": results,
    }


@router.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "writeback_enabled": settings.writeback_enabled,
        "model": get_runtime_llm().model,
    }


# ===== LLM 设置（运行时可改） =====


class LlmSettingsResponse(BaseModel):
    """LLM 接入配置；敏感字段只回布尔，不回明文。"""

    base_url: str
    model: str
    has_api_key: bool
    has_auth_token: bool


class LlmSettingsUpdate(BaseModel):
    """部分更新；留空（None）的字段保持不变，用于密码框留空=不改。"""

    base_url: str | None = None
    api_key: str | None = None
    auth_token: str | None = None
    model: str | None = None


def _llm_response() -> LlmSettingsResponse:
    cfg = get_runtime_llm()
    return LlmSettingsResponse(
        base_url=cfg.base_url,
        model=cfg.model,
        has_api_key=bool(cfg.api_key),
        has_auth_token=bool(cfg.auth_token),
    )


@router.get("/settings/llm", response_model=LlmSettingsResponse)
def get_llm_settings() -> LlmSettingsResponse:
    """读取当前 LLM 接入配置（敏感字段脱敏）。"""
    return _llm_response()


@router.post("/settings/llm", response_model=LlmSettingsResponse)
def update_llm_settings(req: LlmSettingsUpdate) -> LlmSettingsResponse:
    """更新 LLM 接入配置；None 字段不覆盖（密码框留空=保留原值）。"""
    # 空串视为"清空该字段"的明确意图，仅在 None 时跳过
    update_runtime_llm(
        base_url=req.base_url,
        api_key=req.api_key,
        auth_token=req.auth_token,
        model=req.model,
    )
    return _llm_response()


# ===== Phase 2 新增端点 =====


class ExportRequest(BaseModel):
    markdown: str
    filename: str = "document.md"


@router.post("/doc/export")
def export_markdown(req: ExportRequest):
    """把 markdown 作为附件下载。"""
    from fastapi.responses import StreamingResponse

    buf = io.BytesIO(req.markdown.encode("utf-8"))
    safe_name = req.filename or "document.md"
    if not safe_name.lower().endswith(".md"):
        safe_name += ".md"
    headers = {"Content-Disposition": f'attachment; filename="{safe_name}"'}
    return StreamingResponse(buf, media_type="text/markdown", headers=headers)


class LoadManyRequest(BaseModel):
    urls: list[str] = Field(default_factory=list)


class LoadManyItem(BaseModel):
    url: str
    document_id: str | None = None
    revision_id: int | None = None
    markdown: str | None = None
    block_count: int | None = None
    error: str | None = None


class LoadManyResponse(BaseModel):
    docs: list[LoadManyItem]


@router.post("/doc/load_many", response_model=LoadManyResponse)
def load_many(req: LoadManyRequest) -> LoadManyResponse:
    """批量加载文档：单份失败不影响其他。"""
    docs: list[LoadManyItem] = []
    for url in req.urls:
        try:
            md = fetch_doc(url, doc_format="markdown")
            xml = fetch_doc(url, doc_format="xml")
            blocks = parse_xml(xml.content_xml)
            docs.append(
                LoadManyItem(
                    url=url,
                    document_id=md.document_id,
                    revision_id=md.revision_id,
                    markdown=md.content_xml,
                    block_count=len(blocks),
                )
            )
        except LarkError as exc:
            docs.append(LoadManyItem(url=url, error=str(exc)))
        except Exception as exc:  # noqa: BLE001 - 兜底，不让单份拖垮整个请求
            docs.append(LoadManyItem(url=url, error=f"unexpected: {exc!s}"))
    return LoadManyResponse(docs=docs)


class WorkspaceSaveRequest(BaseModel):
    session_id: str | None = None
    name: str
    doc_urls: list[str] = Field(default_factory=list)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    solution_markdown: str = ""


class WorkspaceSaveResponse(BaseModel):
    session_id: str
    saved_at: str


@router.post("/workspace/save", response_model=WorkspaceSaveResponse)
def workspace_save(req: WorkspaceSaveRequest) -> WorkspaceSaveResponse:
    """保存方案构建会话到 ~/.lark_agent/sessions/{session_id}.json。"""
    sessions_dir = _ensure_sessions_dir()
    session_id = req.session_id or uuid.uuid4().hex
    saved_at = datetime.now(UTC).isoformat()
    payload: dict[str, Any] = {
        "session_id": session_id,
        "name": req.name,
        "saved_at": saved_at,
        "doc_urls": req.doc_urls,
        "messages": req.messages,
        "solution_markdown": req.solution_markdown,
    }
    path = sessions_dir / f"{session_id}.json"
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"写入会话失败: {exc!s}") from exc
    return WorkspaceSaveResponse(session_id=session_id, saved_at=saved_at)


@router.get("/workspace/list")
def workspace_list() -> dict[str, Any]:
    """列出所有会话（仅元信息）。"""
    sessions_dir = _ensure_sessions_dir()
    metas: list[dict[str, Any]] = []
    for path in sorted(sessions_dir.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        meta = SessionMeta(
            session_id=str(data.get("session_id", path.stem)),
            name=str(data.get("name", "")),
            saved_at=str(data.get("saved_at", "")),
            doc_count=len(data.get("doc_urls", []) or []),
        )
        metas.append(
            {
                "session_id": meta.session_id,
                "name": meta.name,
                "saved_at": meta.saved_at,
                "doc_count": meta.doc_count,
            }
        )
    # 按 saved_at 倒序
    metas.sort(key=lambda m: m["saved_at"], reverse=True)
    return {"sessions": metas}


@router.get("/workspace/{session_id}")
def workspace_get(session_id: str) -> dict[str, Any]:
    """加载某个会话的完整数据。"""
    sessions_dir = _ensure_sessions_dir()
    path = sessions_dir / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"session 不存在: {session_id}")
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"读取会话失败: {exc!s}") from exc

"""FastAPI 路由：文档加载、agent 对话（SSE）、写回飞书、方案构建会话。"""
from __future__ import annotations

import io
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import anthropic  # 模块级，便于测试 monkeypatch
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.agent.agent import run_agent_stream, run_solution_stream
from backend.config import get_runtime_llm, settings, update_runtime_llm
from backend.lark.cli_wrapper import LarkError, fetch_doc, search_docs, update_doc
from backend.lark.doc_xml import blocks_to_blocklist, parse_xml

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
    blocks: list[dict[str, Any]] = Field(default_factory=list)


class ChatRequest(BaseModel):
    markdown: str
    instruction: str


class ReplacementItem(BaseModel):
    pattern: str
    content: str
    reason: str = ""


class BlockEdit(BaseModel):
    block_id: str
    content: str


class ApplyRequest(BaseModel):
    url: str
    replacements: list[ReplacementItem] = Field(default_factory=list)
    revision_id: int = -1
    edits: list[BlockEdit] = Field(default_factory=list)


@router.post("/doc/load", response_model=LoadResponse)
def load_doc(req: LoadRequest) -> LoadResponse:
    """加载飞书文档：返回 markdown（agent 用）+ block 数 + blocks（逐块编辑用）。"""
    try:
        md = fetch_doc(req.url, doc_format="markdown")
        xml = fetch_doc(req.url, doc_format="xml", detail="with-ids")
    except LarkError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    blocks = blocks_to_blocklist(xml.content_xml)
    return LoadResponse(
        document_id=md.document_id,
        revision_id=md.revision_id,
        markdown=md.content_xml,
        block_count=len(blocks),
        blocks=blocks,
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


def _is_revision_conflict(exc: LarkError) -> bool:
    """启发式判断 LarkError 是否为 revision_id 版本冲突。

    lark-cli 未暴露稳定的冲突错误码，按 message/raw 中的关键词判定。
    """
    blob = str(exc)
    if exc.raw:
        blob += " " + json.dumps(exc.raw, ensure_ascii=False)
    lowered = blob.lower()
    return any(kw in lowered for kw in ("revision", "版本", "conflict", "stale"))


def _extract_revision_id(data: dict[str, Any], fallback: int) -> int:
    """从 update_doc 返回数据中取新 revision_id，取不到则回退 fallback。"""
    doc = data.get("document") if isinstance(data, dict) else None
    if isinstance(doc, dict):
        try:
            return int(doc.get("revision_id", fallback))
        except (TypeError, ValueError):
            return fallback
    return fallback


def _apply_block_edits(req: ApplyRequest) -> dict[str, Any]:
    """block_replace 串行 + 乐观锁（计划 §5.3）。

    cur_rev 从 req.revision_id 开始，每次用 update_doc 返回的新 revision_id 更新；
    版本冲突则标记 conflict 并中断后续。
    """
    if not settings.writeback_enabled:
        return {
            "ok": True,
            "mode": "block_replace",
            "simulated": True,
            "final_revision_id": req.revision_id,
            "conflict": False,
            "count": len(req.edits),
            "results": [
                {"block_id": e.block_id, "ok": True, "new_revision_id": req.revision_id}
                for e in req.edits
            ],
        }

    # 写前乐观锁校验：飞书 block_replace 对过期 revision_id 静默不写且不报错，
    # 无法依赖其返回值判断冲突，故写前显式 fetch 当前版本比对。
    # （联调实测：过期 revision_id 写回返回 ok 但 revision 不递增、内容不变。）
    try:
        current = fetch_doc(req.url, doc_format="markdown")
    except LarkError as exc:
        return {
            "ok": False,
            "mode": "block_replace",
            "final_revision_id": req.revision_id,
            "conflict": False,
            "count": 0,
            "results": [],
            "error": f"校验文档版本失败: {exc}",
        }
    if current.revision_id != req.revision_id:
        return {
            "ok": False,
            "mode": "block_replace",
            "final_revision_id": current.revision_id,
            "conflict": True,
            "count": 0,
            "results": [],
            "message": "文档已被修改，请重新加载后再编辑",
        }

    cur_rev = req.revision_id
    results: list[dict[str, Any]] = []
    conflict = False
    for e in req.edits:
        try:
            data = update_doc(
                req.url,
                command="block_replace",
                block_id=e.block_id,
                content=e.content,
                doc_format="markdown",
                revision_id=cur_rev,
            )
            new_rev = _extract_revision_id(data, cur_rev)
            results.append({"block_id": e.block_id, "ok": True, "new_revision_id": new_rev})
            cur_rev = new_rev
        except LarkError as exc:
            is_conflict = _is_revision_conflict(exc)
            results.append(
                {
                    "block_id": e.block_id,
                    "ok": False,
                    "error": str(exc),
                    "raw": exc.raw,
                    "conflict": is_conflict,
                }
            )
            if is_conflict:
                conflict = True
                break
    return {
        "ok": all(r["ok"] for r in results) and not conflict,
        "mode": "block_replace",
        "final_revision_id": cur_rev,
        "conflict": conflict,
        "count": len(results),
        "results": results,
    }


@router.post("/doc/apply")
def apply_edits(req: ApplyRequest) -> dict[str, Any]:
    """写回飞书：优先 block-level edits（block_replace + 乐观锁），否则降级 str_replace。"""
    if req.edits:
        return _apply_block_edits(req)

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
    """LLM 接入配置；按用户决策回明文，前端密码框默认遮罩、可切换显示。"""

    base_url: str
    model: str
    api_key: str
    auth_token: str


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
        api_key=cfg.api_key,
        auth_token=cfg.auth_token,
    )


@router.get("/settings/llm", response_model=LlmSettingsResponse)
def get_llm_settings() -> LlmSettingsResponse:
    """读取当前 LLM 接入配置（含明文 key）。"""
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


# ===== LLM 连接检测（临时配置，不落库） =====
#
# 检测用面板当前输入的配置临时构造 client，发一个 max_tokens=1 的真实推理请求，
# 不修改运行时配置。失败按错误类型分类，延迟分级供前端着色。


class LlmTestRequest(BaseModel):
    """检测请求：用面板当前输入的配置临时测，不落库。"""

    base_url: str = ""
    api_key: str = ""
    auth_token: str = ""
    model: str = ""


class LlmTestResponse(BaseModel):
    """检测结果：ok + 延迟 + 错误分类 + 原始信息。"""

    ok: bool
    latency_ms: int | None = None
    error_type: str | None = None  # network / auth / model / rate_limit / unknown
    detail: str = ""


def _classify_llm_error(exc: Exception) -> tuple[str, str]:
    """把 anthropic 异常分类成 (error_type, detail)。"""
    # 鉴权失败
    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return "auth", "鉴权失败，检查 API Key / Auth Token"
    # 模型不存在 / 资源不存在
    if isinstance(exc, anthropic.NotFoundError):
        return "model", "模型名无效或端点不存在，检查 Model / Base URL"
    # 限流
    if isinstance(exc, anthropic.RateLimitError):
        return "rate_limit", "触发限流，稍后重试"
    # 网络/连接类：APITimeoutError、APIConnectionError
    if isinstance(exc, (anthropic.APITimeoutError, anthropic.APIConnectionError)):
        return "network", "网络不通或超时，检查 Base URL 与网络"
    # 其它 API 错误
    if isinstance(exc, anthropic.APIStatusError):
        return "unknown", f"HTTP {exc.status_code}: {exc!s}"
    return "unknown", str(exc)


@router.post("/settings/llm/test", response_model=LlmTestResponse)
def test_llm_settings(req: LlmTestRequest) -> LlmTestResponse:
    """用临时配置检测 LLM 连通性，不落库。"""
    import time

    # 临时构造 client（不写回 get_runtime_llm）
    kwargs: dict[str, Any] = {}
    if req.api_key:
        kwargs["api_key"] = req.api_key
    else:
        kwargs["auth_token"] = req.auth_token
        kwargs["base_url"] = req.base_url
    if req.base_url and "base_url" not in kwargs:
        kwargs["base_url"] = req.base_url
    # 10s 超时，避免慢代理挂死同步请求
    kwargs["timeout"] = 10.0

    try:
        client = anthropic.Anthropic(**kwargs)
    except Exception as exc:  # noqa: BLE001 - 构造失败统一分类
        etype, detail = _classify_llm_error(exc)
        return LlmTestResponse(ok=False, error_type=etype, detail=detail)

    start = time.perf_counter()
    try:
        client.messages.create(
            model=req.model or "claude-sonnet-4-6",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
    except Exception as exc:  # noqa: BLE001 - 推理失败统一分类
        etype, detail = _classify_llm_error(exc)
        return LlmTestResponse(ok=False, error_type=etype, detail=detail)
    latency_ms = int((time.perf_counter() - start) * 1000)
    return LlmTestResponse(ok=True, latency_ms=latency_ms)


# ===== Phase 2 新增端点 =====


# ===== 文档搜索 =====


class SearchItemOut(BaseModel):
    url: str
    title: str
    summary: str
    owner: str
    updated_at: str
    doc_type: str
    entity_type: str


class SearchResponse(BaseModel):
    results: list[SearchItemOut]
    has_more: bool
    page_token: str


@router.get("/docs/search", response_model=SearchResponse)
def docs_search(
    query: str,
    page_size: int = 15,
    page_token: str | None = None,
) -> SearchResponse:
    """搜索飞书文档（docx/wiki/sheet），返回规整结果 + 分页。"""
    if not query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")
    try:
        res = search_docs(query, page_size=page_size, page_token=page_token)
    except LarkError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return SearchResponse(
        results=[
            SearchItemOut(
                url=it.url,
                title=it.title,
                summary=it.summary,
                owner=it.owner,
                updated_at=it.updated_at,
                doc_type=it.doc_type,
                entity_type=it.entity_type,
            )
            for it in res.items
        ],
        has_more=res.has_more,
        page_token=res.page_token,
    )


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

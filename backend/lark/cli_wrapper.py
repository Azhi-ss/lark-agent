"""lark-cli 子进程封装：文档读取、局部更新。"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any

from backend.config import settings


class LarkError(Exception):
    """lark-cli 调用失败的统一异常。"""

    def __init__(self, message: str, *, raw: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.raw = raw


@dataclass(frozen=True)
class FetchResult:
    """文档读取结果（不可变）。"""

    document_id: str
    revision_id: int
    content_xml: str  # 飞书 docx v2 返回的 XML

    @property
    def block_count_hint(self) -> int:
        return self.content_xml.count("<")


def _run(args: list[str]) -> dict[str, Any]:
    """执行 lark-cli 并解析 JSON 输出。失败抛 LarkError。"""
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=120, check=False
        )
    except FileNotFoundError as exc:
        raise LarkError(
            f"lark-cli 未找到 (path={settings.lark_cli})，请确认已安装或设置 LARK_CLI_PATH"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise LarkError("lark-cli 调用超时（120s）") from exc

    stdout = proc.stdout.strip()
    if not stdout:
        raise LarkError(
            f"lark-cli 无输出，exit={proc.returncode}, stderr={proc.stderr[:500]}"
        )

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise LarkError(
            f"lark-cli 输出非 JSON: {stdout[:300]}",
            raw={"stderr": proc.stderr[:500]},
        ) from exc

    if not payload.get("ok", False):
        err = payload.get("error", {})
        raise LarkError(err.get("message", "lark-cli 返回 ok=false"), raw=payload)
    return payload


def fetch_doc(doc_ref: str, *, doc_format: str = "xml") -> FetchResult:
    """读取飞书文档，返回内容与版本。

    Args:
        doc_ref: 文档 URL（自动推断 docx/wiki 类型）或 token。
        doc_format: xml（默认，含 block 结构）或 markdown（纯文本，str_replace 友好）。
    """
    args = [
        settings.lark_cli, "docs", "+fetch",
        "--api-version", settings.api_version,
        "--as", settings.lark_as,
        "--doc", doc_ref,
        "--doc-format", doc_format,
    ]
    payload = _run(args)
    doc = payload["data"]["document"]
    return FetchResult(
        document_id=doc["document_id"],
        revision_id=int(doc.get("revision_id", 0)),
        content_xml=doc["content"],
    )


@dataclass(frozen=True)
class SearchItem:
    """单条搜索结果（不可变，已规整为前端友好字段）。"""

    url: str
    title: str  # 纯文本（高亮已转 <mark>）
    summary: str  # 纯文本（高亮已转 <mark>）
    owner: str
    updated_at: str  # ISO 字符串
    doc_type: str  # DOCX / SHEET / ...
    entity_type: str  # WIKI / DOC


@dataclass(frozen=True)
class SearchResult:
    """搜索结果集（不可变）。"""

    items: tuple[SearchItem, ...]
    has_more: bool
    page_token: str


def search_docs(
    query: str,
    *,
    page_size: int = 15,
    page_token: str | None = None,
) -> SearchResult:
    """搜索飞书文档（docx/wiki/sheet）。

    Args:
        query: 搜索关键词。
        page_size: 每页条数（lark 上限 20）。
        page_token: 上一页返回的 token，取下一页。
    """
    args = [
        settings.lark_cli, "docs", "+search",
        "--as", settings.lark_as,
        "--query", query,
        "--page-size", str(page_size),
    ]
    if page_token:
        args += ["--page-token", page_token]
    payload = _run(args)
    data = payload.get("data", {})
    raw_items = data.get("results", []) or []
    items = tuple(_parse_search_item(r) for r in raw_items)
    return SearchResult(
        items=items,
        has_more=bool(data.get("has_more", False)),
        page_token=str(data.get("page_token", "") or ""),
    )


def _parse_search_item(raw: dict[str, Any]) -> SearchItem:
    """把 lark 搜索原始条目规整为 SearchItem。"""
    meta = raw.get("result_meta", {}) or {}
    return SearchItem(
        url=str(meta.get("url", "")),
        title=_to_safe_highlight(str(raw.get("title_highlighted", "") or meta.get("title", ""))),
        summary=_to_safe_highlight(str(raw.get("summary_highlighted", ""))),
        owner=str(meta.get("owner_name", "") or ""),
        updated_at=str(meta.get("update_time_iso", "") or ""),
        doc_type=str(meta.get("doc_types", "") or ""),
        entity_type=str(raw.get("entity_type", "") or ""),
    )


def _to_safe_highlight(text: str) -> str:
    """把 lark 高亮串转成只含 <mark> 的安全 HTML。

    策略：先全文 HTML 转义（锁死 XSS），再把 lark 的 <h>/<hb>/<b> 标签还原为 <mark>。
    其余内容（含用户原始文本）保持转义，无法注入任意标签。
    """
    import html

    # 1. 全文转义：所有 < > & 变实体
    escaped = html.escape(text, quote=False)
    # 2. lark 高亮标签已变成实体形式（&lt;h&gt; 等），还原为 <mark>...</mark>
    #    只匹配这几种已知标签，其余实体保持转义
    for tag in ("h", "hb", "b"):
        # 闭合标签 </tag>
        escaped = escaped.replace(f"&lt;/{tag}&gt;", "</mark>")
        # 开标签 <tag>（不含属性，lark 高亮标签无属性）
        escaped = escaped.replace(f"&lt;{tag}&gt;", "<mark>")
    return escaped


def update_doc(
    doc_ref: str,
    *,
    command: str,
    content: str = "",
    pattern: str | None = None,
    block_id: str | None = None,
    doc_format: str = "xml",
    revision_id: int = -1,
) -> dict[str, Any]:
    """局部更新飞书文档。

    Args:
        command: str_replace / block_insert_after / block_replace / append / overwrite 等。
        content: 写入内容（str_replace 时为替换后文本，传空串即删除）。
        pattern: str_replace 的匹配文本（markdown 模式支持跨行 + 前缀...后缀语法）。
        block_id: block_* 操作的目标 block ID，-1 表示末尾。
        doc_format: xml（默认，精准编辑）或 markdown（跨行 str_replace）。
        revision_id: 基准版本号，-1 = 最新。
    """
    if not settings.writeback_enabled:
        return {
            "simulated": True,
            "command": command,
            "pattern": pattern,
            "content_len": len(content),
            "message": "LARK_WRITEBACK=0，仅模拟未真正写回",
        }

    args = [
        settings.lark_cli, "docs", "+update",
        "--api-version", settings.api_version,
        "--as", settings.lark_as,
        "--doc", doc_ref,
        "--command", command,
        "--doc-format", doc_format,
        "--revision-id", str(revision_id),
    ]
    # content 用 stdin 传递，避免 shell 转义和长文本截断
    if content:
        args += ["--content", "-"]
    if pattern is not None:
        args += ["--pattern", pattern]
    if block_id is not None:
        args += ["--block-id", block_id]

    # content 可能含特殊字符，走 stdin
    try:
        proc = subprocess.run(
            args, input=content, capture_output=True, text=True, timeout=120, check=False,
        )
    except FileNotFoundError as exc:
        raise LarkError("lark-cli 未找到") from exc
    except subprocess.TimeoutExpired as exc:
        raise LarkError("lark-cli update 超时") from exc

    stdout = proc.stdout.strip()
    if not stdout:
        raise LarkError(
            f"lark-cli update 无输出，exit={proc.returncode}, stderr={proc.stderr[:500]}"
        )
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise LarkError(f"update 输出非 JSON: {stdout[:300]}") from exc
    if not payload.get("ok", False):
        err = payload.get("error", {})
        raise LarkError(err.get("message", "update ok=false"), raw=payload)
    return payload.get("data", {})

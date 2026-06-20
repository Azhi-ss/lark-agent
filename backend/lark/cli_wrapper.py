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

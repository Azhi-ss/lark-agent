"""阶段 1 验证脚本：给定文档 URL，打印 fetch 摘要。

用法：
    uv run python -m backend.lark.verify_fetch <文档URL>
"""
from __future__ import annotations

import sys

from backend.lark.cli_wrapper import LarkError, fetch_doc


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python -m backend.lark.verify_fetch <文档URL>", file=sys.stderr)
        return 2

    doc_ref = sys.argv[1]
    try:
        result = fetch_doc(doc_ref)
    except LarkError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        if exc.raw:
            print(f"raw: {exc.raw}", file=sys.stderr)
        return 1

    print(f"[OK] document_id = {result.document_id}")
    print(f"[OK] revision_id = {result.revision_id}")
    print(f"[OK] content_xml 长度 = {len(result.content_xml)} 字符")
    print(f"[OK] 块数量近似 = {result.block_count_hint}")
    print("--- 前 400 字符预览 ---")
    print(result.content_xml[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

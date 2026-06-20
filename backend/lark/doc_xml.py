"""飞书 docx XML 解析与 block 级 diff。

把 v2 API 返回的 XML 解析成结构化 Block 列表，供前端渲染和 agent 理解；
并提供 block 级 diff，供界面展示"agent 改了哪些块"。

设计原则：
- Block 不可变（frozen dataclass）
- 解析只读不修改原始 XML
- diff 基于块的文本指纹（kind+normalized text），用 difflib 做序列对齐
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from difflib import SequenceMatcher

# 飞书 docx 的顶层块标签
_BLOCK_TAGS = {
    "title", "h1", "h2", "h3", "h4", "p", "ul", "ol", "table",
    "pre", "figure", "img", "bookmark", "hr", "callout", "grid",
}


@dataclass(frozen=True)
class Block:
    """一个可渲染的文档块。"""

    kind: str  # title / h1 / p / ul / table / pre / figure ...
    text: str  # 该块的纯文本（递归抽取）
    level: int = 0  # 标题级别（h1=1, h2=2...），非标题为 0
    raw_xml: str = ""  # 原始 XML 片段，用于 str_replace / 回显
    children: tuple["Block", ...] = field(default_factory=tuple)
    meta: dict[str, str] = field(default_factory=dict)  # 额外属性（seq, lang, href ...）

    @property
    def fingerprint(self) -> str:
        """块的文本指纹，用于 diff 匹配。"""
        return f"{self.kind}:{_normalize(self.text)}"


@dataclass(frozen=True)
class DiffOp:
    """单个块变更。tag: equal / replace / delete / insert。"""

    tag: str
    old: Block | None
    new: Block | None


def _normalize(text: str) -> str:
    """归一化文本：去空白，降低误判 diff。"""
    return re.sub(r"\s+", "", text)


def _text_of(elem: ET.Element) -> str:
    """递归抽取元素内全部纯文本。"""
    return "".join(elem.itertext())


def _meta_of(elem: ET.Element) -> dict[str, str]:
    """提取关键属性到 meta。"""
    keep = {"seq", "seq-level", "lang", "href", "name", "alt", "done"}
    return {k: v for k, v in elem.attrib.items() if k in keep}


def _parse_block(elem: ET.Element) -> Block:
    """把单个 XML 元素解析成 Block。"""
    tag = elem.tag
    text = _text_of(elem)
    level = {"h1": 1, "h2": 2, "h3": 3, "h4": 4}.get(tag, 0)

    children: tuple[Block, ...] = ()
    if tag in ("ul", "ol"):
        children = tuple(_parse_block(li) for li in elem.findall("li"))
    elif tag == "table":
        rows = []
        for tr in elem.iter("tr"):
            cells = tuple(_text_of(td) for td in tr.findall("td") + tr.findall("th"))
            rows.append(Block(kind="row", text=" | ".join(cells)))
        children = tuple(rows)

    return Block(
        kind=tag,
        text=text,
        level=level,
        raw_xml=ET.tostring(elem, encoding="unicode"),
        children=children,
        meta=_meta_of(elem),
    )


def parse_xml(content_xml: str) -> list[Block]:
    """把飞书 docx XML 解析成 Block 列表。

    飞书返回的 content 是顶层块的拼接（无单一根元素），用 <root> 包裹后解析。
    """
    wrapped = f"<root>{content_xml}</root>"
    root = ET.fromstring(wrapped)
    blocks: list[Block] = []
    for child in root:
        blocks.append(_parse_block(child))
    return blocks


def blocks_to_text(blocks: list[Block]) -> str:
    """把 Block 列表转成易读的纯文本（给 agent 看文档全貌）。"""
    lines: list[str] = []
    for b in blocks:
        if b.kind == "title":
            lines.append(f"# {b.text}")
        elif b.level:
            lines.append(f"{'#' * (b.level + 1)} {b.text}")
        elif b.kind in ("ul", "ol"):
            for i, li in enumerate(b.children, 1):
                prefix = f"{i}." if b.kind == "ol" else "-"
                lines.append(f"{prefix} {li.text}")
        elif b.kind == "table":
            for row in b.children:
                lines.append(f"| {row.text} |")
        elif b.kind == "pre":
            lines.append(f"```\n{b.text}\n```")
        elif b.kind in ("figure", "img"):
            lines.append(f"[图片/附件: {b.meta.get('name', b.text[:30])}]")
        elif b.kind == "bookmark":
            lines.append(f"[书签: {b.meta.get('name', '')}]")
        elif b.kind == "cite":
            lines.append(f"[引用文件: {b.meta.get('title', '')}]")
        else:
            lines.append(b.text)
    return "\n".join(lines)


def diff_blocks(old: list[Block], new: list[Block]) -> list[DiffOp]:
    """两份 Block 列表的块级 diff。

    用指纹序列做 SequenceMatcher 对齐，输出 equal/replace/delete/insert。
    """
    matcher = SequenceMatcher(
        a=[b.fingerprint for b in old],
        b=[b.fingerprint for b in new],
        autojunk=False,
    )
    ops: list[DiffOp] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i1, i2):
                ops.append(DiffOp(tag="equal", old=old[k], new=old[k]))
        elif tag == "replace":
            n = min(i2 - i1, j2 - j1)
            for k in range(n):
                ops.append(DiffOp(tag="replace", old=old[i1 + k], new=new[j1 + k]))
            for k in range(i1 + n, i2):
                ops.append(DiffOp(tag="delete", old=old[k], new=None))
            for k in range(j1 + n, j2):
                ops.append(DiffOp(tag="insert", old=None, new=new[k]))
        elif tag == "delete":
            for k in range(i1, i2):
                ops.append(DiffOp(tag="delete", old=old[k], new=None))
        elif tag == "insert":
            for k in range(j1, j2):
                ops.append(DiffOp(tag="insert", old=None, new=new[k]))
    return ops


def summarize_diff(ops: list[DiffOp]) -> dict[str, int]:
    """统计 diff：各类型块数量。"""
    counts: dict[str, int] = {"equal": 0, "replace": 0, "insert": 0, "delete": 0}
    for op in ops:
        counts[op.tag] = counts.get(op.tag, 0) + 1
    return counts

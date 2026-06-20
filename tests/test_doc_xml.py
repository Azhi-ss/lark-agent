"""backend/lark/doc_xml.py 单元测试。

覆盖:Block 不可变、parse_xml 各类块、blocks_to_text 渲染、diff_blocks、summarize_diff。
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from backend.lark.doc_xml import (
    Block,
    DiffOp,
    blocks_to_text,
    diff_blocks,
    parse_xml,
    summarize_diff,
)


def test_block_is_frozen():
    """Block 必须不可变(frozen dataclass),赋值应抛 FrozenInstanceError。"""
    b = Block(kind="p", text="hi")
    with pytest.raises(FrozenInstanceError):
        b.text = "mutated"  # type: ignore[misc]


def test_block_fingerprint_normalizes_whitespace():
    """指纹归一化空白,首尾空白不同的同 kind 块指纹应相同。"""
    a = Block(kind="p", text="hello world")
    b = Block(kind="p", text="  hello   world  ")
    assert a.fingerprint == b.fingerprint


def test_parse_xml_extracts_title_and_paragraph():
    """顶层块拼接(无根元素)被 <root> 包裹后正确解析。"""
    xml = "<title>周报标题</title><p>第一段正文</p>"
    blocks = parse_xml(xml)
    assert len(blocks) == 2
    assert blocks[0].kind == "title"
    assert blocks[0].text == "周报标题"
    assert blocks[1].kind == "p"
    assert blocks[1].text == "第一段正文"


def test_parse_xml_heading_levels():
    """h1~h4 映射到 level 1~4,非标题 level 为 0。"""
    xml = "<h1>大标题</h1><h2>中标题</h2><p>正文</p>"
    blocks = parse_xml(xml)
    assert blocks[0].level == 1
    assert blocks[1].level == 2
    assert blocks[2].level == 0


def test_parse_xml_unordered_list_children():
    """ul/ol 的 li 解析为子块。"""
    xml = "<ul><li>苹果</li><li>香蕉</li></ul>"
    blocks = parse_xml(xml)
    assert len(blocks) == 1
    ul = blocks[0]
    assert ul.kind == "ul"
    assert len(ul.children) == 2
    assert ul.children[0].text == "苹果"


def test_parse_xml_table_rows():
    """table 的 tr 解析为 row 子块,单元格用 | 连接。"""
    xml = "<table><tr><td>A</td><td>B</td></tr></table>"
    blocks = parse_xml(xml)
    assert blocks[0].kind == "table"
    assert len(blocks[0].children) == 1
    assert blocks[0].children[0].text == "A | B"


def test_parse_xml_meta_keeps_known_attrs():
    """meta 只保留白名单属性(seq/lang/href/name/alt/done)。"""
    xml = '<pre lang="python" data-x="ignore">code</pre>'
    blocks = parse_xml(xml)
    assert blocks[0].meta == {"lang": "python"}


def test_parse_xml_empty_returns_empty_list():
    """空 XML 返回空列表。"""
    assert parse_xml("") == []


def test_blocks_to_text_title_and_heading():
    """title 渲染为 #,h1 渲染为 ##(level+1)。"""
    blocks = parse_xml("<title>T</title><h1>S</h1>")
    text = blocks_to_text(blocks)
    assert text == "# T\n## S"


def test_blocks_to_text_ordered_list_numbered():
    """ol 子项渲染为带序号。"""
    blocks = parse_xml("<ol><li>一</li><li>二</li></ol>")
    assert blocks_to_text(blocks) == "1. 一\n2. 二"


def test_blocks_to_text_code_block_wrapped():
    """pre 渲染为 ``` 围栏。"""
    blocks = parse_xml("<pre>print(1)</pre>")
    assert blocks_to_text(blocks) == "```\nprint(1)\n```"


def test_diff_blocks_equal():
    """两份相同文档 diff 全为 equal。"""
    a = parse_xml("<p>x</p><p>y</p>")
    ops = diff_blocks(a, a)
    assert all(op.tag == "equal" for op in ops)
    assert summarize_diff(ops)["equal"] == 2


def test_diff_blocks_insert_and_delete():
    """新增块→insert,删除块→delete。"""
    old = parse_xml("<p>a</p>")
    new = parse_xml("<p>a</p><p>b</p>")
    ops = diff_blocks(old, new)
    tags = [op.tag for op in ops]
    assert "equal" in tags
    assert "insert" in tags
    insert_ops = [op for op in ops if op.tag == "insert"]
    assert insert_ops[0].new is not None
    assert insert_ops[0].old is None


def test_diff_blocks_replace():
    """同位置文本变化→replace。"""
    old = parse_xml("<p>a</p>")
    new = parse_xml("<p>b</p>")
    ops = diff_blocks(old, new)
    replace_ops = [op for op in ops if op.tag == "replace"]
    assert len(replace_ops) == 1
    assert isinstance(replace_ops[0], DiffOp)
    assert replace_ops[0].old.text == "a"
    assert replace_ops[0].new.text == "b"


def test_summarize_diff_counts_all_tags():
    """summarize_diff 返回四种 tag 计数键。"""
    old = parse_xml("<p>a</p><p>b</p>")
    new = parse_xml("<p>a</p><p>c</p><p>d</p>")
    summary = summarize_diff(diff_blocks(old, new))
    assert set(summary.keys()) == {"equal", "replace", "insert", "delete"}
    assert summary["equal"] == 1
    assert summary["replace"] == 1
    assert summary["insert"] == 1

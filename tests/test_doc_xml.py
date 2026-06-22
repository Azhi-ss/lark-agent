"""backend/lark/doc_xml.py 单元测试。

覆盖:Block 不可变、parse_xml 各类块、blocks_to_text 渲染、diff_blocks、summarize_diff。
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from backend.lark.doc_xml import (
    Block,
    DiffOp,
    block_to_markdown,
    blocks_to_blocklist,
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
    """meta 只保留白名单属性(seq/lang/href/name/alt/done/id)。"""
    xml = '<pre lang="python" data-x="ignore">code</pre>'
    blocks = parse_xml(xml)
    assert blocks[0].meta == {"lang": "python"}


def test_parse_xml_meta_preserves_id_attr():
    """with-ids 模式下 block 的 id 属性必须进 meta（block_replace 定位用）。"""
    xml = '<p id="blkcnA">文本</p>'
    blocks = parse_xml(xml)
    assert blocks[0].meta["id"] == "blkcnA"


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


# ===== block_to_markdown：各 kind 渲染为 markdown 片段（计划 §5.4） =====


@pytest.mark.parametrize(
    "xml, expected",
    [
        pytest.param("<title>周报</title>", "# 周报", id="title"),
        pytest.param("<h1>大标题</h1>", "# 大标题", id="h1"),
        pytest.param("<p>正文</p>", "正文", id="p"),
        pytest.param("<ul><li>苹果</li><li>香蕉</li></ul>", "- 苹果\n- 香蕉", id="ul"),
        pytest.param("<ol><li>一</li><li>二</li></ol>", "1. 一\n2. 二", id="ol"),
        pytest.param("<pre>print(1)</pre>", "```\nprint(1)\n```", id="pre"),
        pytest.param(
            "<table><tr><td>A</td><td>B</td></tr><tr><td>C</td><td>D</td></tr></table>",
            "| A | B |\n| --- | --- |\n| C | D |",
            id="table",
        ),
    ],
)
def test_block_to_markdown_renders_each_kind(xml, expected):
    """block_to_markdown 把各 kind 块渲染为正确 markdown 语法。"""
    block = parse_xml(xml)[0]
    assert block_to_markdown(block) == expected


def test_block_to_markdown_pre_includes_lang_header():
    """pre 带 lang 属性时围栏代码块带语言头（```python）。"""
    block = parse_xml('<pre lang="python">print(1)</pre>')[0]
    assert block_to_markdown(block) == "```python\nprint(1)\n```"


# ===== blocks_to_blocklist：前端 Block 契约（P2 §3.1，XML 单一真相源） =====


def test_blocks_to_blocklist_returns_contract_fields():
    """blocks_to_blocklist 输出 P2 契约字段：block_id/kind/text/raw_xml/level。"""
    xml = (
        '<title id="blkcnT">周报</title>'
        '<p id="blkcnA">第一段</p>'
        '<p id="blkcnB">第二段</p>'
    )
    result = blocks_to_blocklist(xml)
    assert len(result) == 3
    for item in result:
        assert set(item.keys()) == {
            "block_id",
            "kind",
            "text",
            "raw_xml",
            "level",
        }
    assert result[0]["block_id"] == "blkcnT"
    assert result[0]["kind"] == "title"
    assert result[0]["text"] == "周报"
    assert result[0]["level"] == 0
    # raw_xml 含 id 属性，是写回用的原始 XML 片段
    assert 'id="blkcnT"' in result[0]["raw_xml"]
    assert "周报" in result[0]["raw_xml"]
    assert result[1]["block_id"] == "blkcnA"
    assert result[1]["kind"] == "p"
    assert result[1]["text"] == "第一段"
    assert 'id="blkcnA"' in result[1]["raw_xml"]
    assert result[2]["block_id"] == "blkcnB"
    assert result[2]["raw_xml"].startswith("<p")


def test_blocks_to_blocklist_defaults_block_id_to_empty_when_no_id():
    """无 id 属性的 block，block_id 回退为空串（契约：title 等无 id 为 ""）。"""
    result = blocks_to_blocklist("<p>无 id 段落</p>")
    assert len(result) == 1
    assert result[0]["block_id"] == ""
    assert result[0]["kind"] == "p"


def test_block_id_of_extracts_id_from_meta():
    """block_id_of 取 meta['id']，无则空串。"""
    from backend.lark.doc_xml import block_id_of, parse_xml

    [b_with, b_without] = parse_xml(
        '<p id="blkcnX">有</p><p>没有</p>'
    )
    assert block_id_of(b_with) == "blkcnX"
    assert block_id_of(b_without) == ""

"""搜索功能测试:高亮安全函数 + 搜索端点(mock lark)。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.lark.cli_wrapper import SearchItem, SearchResult
from backend.main import app

client = TestClient(app)


# ===== _to_safe_highlight 安全性单测 =====


def test_highlight_converts_lark_tags_to_mark():
    """lark 的 <h>/<hb>/<b> 都转成 <mark>。"""
    from backend.lark.cli_wrapper import _to_safe_highlight

    assert _to_safe_highlight("a<h>b</h>c") == "a<mark>b</mark>c"
    assert _to_safe_highlight("a<hb>b</hb>c") == "a<mark>b</mark>c"
    assert _to_safe_highlight("a<b>b</b>c") == "a<mark>b</mark>c"


def test_highlight_escapes_arbitrary_html():
    """用户文本里的任意标签必须被转义,不能注入。"""
    from backend.lark.cli_wrapper import _to_safe_highlight

    # script 标签必须被转义成实体,不是真标签
    out = _to_safe_highlight("<script>alert(1)</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_highlight_preserves_plain_text():
    """无标签的纯文本原样返回。"""
    from backend.lark.cli_wrapper import _to_safe_highlight

    assert _to_safe_highlight("普通周报标题") == "普通周报标题"


def test_highlight_handles_empty():
    from backend.lark.cli_wrapper import _to_safe_highlight

    assert _to_safe_highlight("") == ""


# ===== 搜索端点(mock search_docs) =====


def _fake_search_result() -> SearchResult:
    return SearchResult(
        items=(
            SearchItem(
                url="https://x.feishu.cn/wiki/ABC",
                title="<mark>周报</mark>第一篇",
                summary="本周<mark>要点</mark>",
                owner="张三",
                updated_at="2026-06-18T00:00:00+08:00",
                doc_type="DOCX",
                entity_type="WIKI",
            ),
        ),
        has_more=True,
        page_token="next-token",
    )


def test_docs_search_returns_contract(monkeypatch):
    """GET /api/docs/search 返回规整字段 + 分页。"""
    monkeypatch.setattr(
        "backend.api.routes.search_docs",
        lambda q, **kw: _fake_search_result(),
    )
    resp = client.get("/api/docs/search", params={"query": "周报"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_more"] is True
    assert body["page_token"] == "next-token"
    item = body["results"][0]
    assert item["url"] == "https://x.feishu.cn/wiki/ABC"
    assert item["owner"] == "张三"
    assert item["entity_type"] == "WIKI"
    assert set(item.keys()) == {
        "url", "title", "summary", "owner", "updated_at", "doc_type", "entity_type"
    }


def test_docs_search_passes_pagination(monkeypatch):
    """page_size / page_token 透传给 search_docs。"""
    captured = {}

    def fake(q, *, page_size=15, page_token=None):
        captured["page_size"] = page_size
        captured["page_token"] = page_token
        return _fake_search_result()

    monkeypatch.setattr("backend.api.routes.search_docs", fake)
    client.get(
        "/api/docs/search",
        params={"query": "x", "page_size": 20, "page_token": "tok-1"},
    )
    assert captured["page_size"] == 20
    assert captured["page_token"] == "tok-1"


def test_docs_search_rejects_empty_query():
    """空 query 返回 400。"""
    resp = client.get("/api/docs/search", params={"query": "  "})
    assert resp.status_code == 400


def test_docs_search_propagates_lark_error_as_502(monkeypatch):
    """search_docs 抛 LarkError 时返回 502。"""
    from backend.lark.cli_wrapper import LarkError

    def raising(q, **kw):
        raise LarkError("搜索服务不可用")

    monkeypatch.setattr("backend.api.routes.search_docs", raising)
    resp = client.get("/api/docs/search", params={"query": "x"})
    assert resp.status_code == 502
    assert "搜索服务不可用" in resp.json()["detail"]

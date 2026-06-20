"""backend/api/routes.py 路由层测试。

用 FastAPI TestClient,mock lark fetch,覆盖:
- /api/health:健康检查返回 200 + 契约字段
- /api/doc/apply:LARK_WRITEBACK=0 时走模拟分支(不真正调用 lark-cli)
- /api/doc/load:mock fetch_doc 后返回 block_count
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.lark.cli_wrapper import FetchResult
from backend.main import app

client = TestClient(app)


def test_health_returns_ok_and_contract_fields():
    """/api/health 返回 200,含 ok/writeback_enabled/model。"""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "writeback_enabled" in body
    assert "model" in body


def test_apply_returns_simulated_when_writeback_disabled(monkeypatch):
    """writeback_enabled=False 时 /api/doc/apply 返回 simulated,不调 lark-cli。"""
    monkeypatch.setattr(
        "backend.api.routes.settings",
        Settings(writeback_enabled=False),
    )
    resp = client.post(
        "/api/doc/apply",
        json={
            "url": "https://example.feishu.cn/docx/fake",
            "replacements": [
                {"pattern": "旧", "content": "新", "reason": "测试"},
            ],
            "revision_id": -1,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["simulated"] is True
    assert body["count"] == 1
    assert body["results"] == []


def test_apply_validates_empty_replacements(monkeypatch):
    """空 replacements 列表也应被接受(模拟分支),count=0。"""
    monkeypatch.setattr(
        "backend.api.routes.settings",
        Settings(writeback_enabled=False),
    )
    resp = client.post(
        "/api/doc/apply",
        json={"url": "https://example.feishu.cn/docx/fake", "replacements": []},
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


def test_load_doc_returns_block_count(monkeypatch):
    """mock fetch_doc 后,/api/doc/load 返回 markdown + block_count。"""
    fake_md = FetchResult(
        document_id="doc123",
        revision_id=5,
        content_xml="# 周报\n第一段",
    )
    fake_xml = FetchResult(
        document_id="doc123",
        revision_id=5,
        content_xml="<title>周报</title><p>第一段</p>",
    )

    def fake_fetch(doc_ref: str, *, doc_format: str = "xml"):
        return fake_md if doc_format == "markdown" else fake_xml

    monkeypatch.setattr("backend.api.routes.fetch_doc", fake_fetch)

    resp = client.post(
        "/api/doc/load",
        json={"url": "https://example.feishu.cn/docx/fake"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == "doc123"
    assert body["revision_id"] == 5
    assert body["markdown"] == "# 周报\n第一段"
    assert body["block_count"] == 2


def test_load_doc_propagates_lark_error_as_502(monkeypatch):
    """fetch_doc 抛 LarkError 时,/api/doc/load 返回 502。"""
    from backend.lark.cli_wrapper import LarkError

    def raising_fetch(doc_ref: str, *, doc_format: str = "xml"):
        raise LarkError("文档不存在")

    monkeypatch.setattr("backend.api.routes.fetch_doc", raising_fetch)

    resp = client.post(
        "/api/doc/load",
        json={"url": "https://example.feishu.cn/docx/missing"},
    )
    assert resp.status_code == 502
    assert "文档不存在" in resp.json()["detail"]


def test_export_markdown_downloads_attachment():
    """/api/doc/export 返回 markdown 附件,带正确 Content-Disposition。"""
    resp = client.post(
        "/api/doc/export",
        json={"markdown": "# hi", "filename": "weekly.md"},
    )
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]
    assert "weekly.md" in resp.headers["content-disposition"]
    assert resp.text == "# hi"

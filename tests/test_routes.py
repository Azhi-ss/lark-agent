"""backend/api/routes.py 路由层测试。

用 FastAPI TestClient,mock lark fetch,覆盖:
- /api/health:健康检查返回 200 + 契约字段
- /api/doc/apply:LARK_WRITEBACK=0 时走模拟分支(不真正调用 lark-cli)
- /api/doc/load:mock fetch_doc 后返回 block_count
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.config import Settings, update_runtime_llm
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


# ===== LLM 设置端点 =====
# 运行时配置是全局单例,这里显式设已知值,避免被其它测试污染。


def _reset_llm(**kwargs):
    """把运行时 LLM 配置设为已知值,缺省字段填空串。"""
    update_runtime_llm(
        base_url=kwargs.get("base_url", ""),
        api_key=kwargs.get("api_key", ""),
        auth_token=kwargs.get("auth_token", ""),
        model=kwargs.get("model", "test-model"),
    )


def test_get_llm_settings_returns_contract_and_masks_secrets():
    """GET /api/settings/llm 返回 base_url/model 明文,api_key/auth_token 只回布尔。"""
    _reset_llm(base_url="https://proxy.example.com", api_key="sk-secret", model="m1")
    resp = client.get("/api/settings/llm")
    assert resp.status_code == 200
    body = resp.json()
    assert body["base_url"] == "https://proxy.example.com"
    assert body["model"] == "m1"
    assert body["has_api_key"] is True
    assert body["has_auth_token"] is False
    # 不应泄漏明文密钥
    assert "sk-secret" not in resp.text


def test_update_llm_settings_overwrites_base_url_and_model():
    """POST 更新 base_url/model,GET 立即反映。"""
    _reset_llm()
    resp = client.post(
        "/api/settings/llm",
        json={"base_url": "https://new-proxy.example.com", "model": "glm-5.2"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["base_url"] == "https://new-proxy.example.com"
    assert body["model"] == "glm-5.2"

    # 再 GET 确认持久(进程内)
    assert client.get("/api/settings/llm").json()["base_url"] == "https://new-proxy.example.com"


def test_update_llm_settings_none_fields_keep_old_secret():
    """密码框留空(传 None)时,原 api_key 保留,has_api_key 仍为 True。"""
    _reset_llm(api_key="sk-keep")
    resp = client.post(
        "/api/settings/llm",
        json={"base_url": "https://x.example.com"},  # 不传 api_key
    )
    assert resp.status_code == 200
    assert resp.json()["has_api_key"] is True  # 旧 key 仍在


def test_update_llm_settings_empty_string_clears_secret():
    """显式传空串表示清空该凭证,has_* 应变 False。"""
    _reset_llm(api_key="sk-keep", auth_token="tok-keep")
    resp = client.post(
        "/api/settings/llm",
        json={"api_key": "", "auth_token": ""},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_api_key"] is False
    assert body["has_auth_token"] is False


def test_health_reflects_runtime_model():
    """/api/health 的 model 取自运行时配置,改设置后 health 同步变化。"""
    _reset_llm(model="health-model-xyz")
    assert client.get("/api/health").json()["model"] == "health-model-xyz"

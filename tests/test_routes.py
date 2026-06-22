"""backend/api/routes.py 路由层测试。

用 FastAPI TestClient,mock lark fetch,覆盖:
- /api/health:健康检查返回 200 + 契约字段
- /api/doc/apply:LARK_WRITEBACK=0 时走模拟分支(不真正调用 lark-cli)
- /api/doc/load:mock fetch_doc 后返回 block_count
"""
from __future__ import annotations

import io
import zipfile

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


def test_apply_block_replace_passes_through_params_and_revision(monkeypatch):
    """edits 非空走 block_replace：update_doc 收到正确参数，revision_id 串行透传，响应结构正确。

    P2：edit 字段 content→xml，写回 doc_format=xml（单一真相源）。
    """
    monkeypatch.setattr(
        "backend.api.routes.settings",
        Settings(writeback_enabled=True),
    )
    calls: list[dict] = []

    def fake_update_doc(
        doc_ref, *, command, content="", pattern=None,
        block_id=None, doc_format="xml", revision_id=-1,
    ):
        calls.append(
            {
                "doc_ref": doc_ref,
                "command": command,
                "content": content,
                "pattern": pattern,
                "block_id": block_id,
                "doc_format": doc_format,
                "revision_id": revision_id,
            }
        )
        return {"document": {"revision_id": 13}}

    # 写前乐观锁校验：fetch_doc 返回的版本须与请求一致才放行
    def fake_fetch(doc_ref, *, doc_format="xml", detail="simple"):
        return FetchResult(document_id="fake", revision_id=12, content_xml="")

    monkeypatch.setattr("backend.api.routes.update_doc", fake_update_doc)
    monkeypatch.setattr("backend.api.routes.fetch_doc", fake_fetch)

    resp = client.post(
        "/api/doc/apply",
        json={
            "url": "https://example.feishu.cn/docx/fake",
            "revision_id": 12,
            "edits": [
                {"block_id": "blkcnA", "xml": "<p>改后A</p>"},
                {"block_id": "blkcnB", "xml": "<p>改后B</p>"},
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "block_replace"
    assert body["conflict"] is False
    assert body["final_revision_id"] == 13
    assert body["count"] == 2
    results = body["results"]
    assert len(results) == 2
    assert results[0]["block_id"] == "blkcnA"
    assert results[0]["ok"] is True
    assert results[0]["new_revision_id"] == 13

    # update_doc 被调两次，参数透传正确
    assert len(calls) == 2
    first = calls[0]
    assert first["command"] == "block_replace"
    assert first["doc_format"] == "xml"
    assert first["block_id"] == "blkcnA"
    assert first["content"] == "<p>改后A</p>"
    assert first["revision_id"] == 12  # 首次用加载时版本
    # 串行乐观锁：第二次用前一次返回的新版本
    assert calls[1]["revision_id"] == 13


def test_apply_block_replace_rejects_on_revision_conflict(monkeypatch):
    """写前校验：fetch_doc 返回的版本与请求不一致 → conflict，不调 update_doc。"""
    monkeypatch.setattr(
        "backend.api.routes.settings",
        Settings(writeback_enabled=True),
    )
    update_calls: list[dict] = []

    def fake_update_doc(*args, **kwargs):
        update_calls.append(kwargs)
        return {"document": {"revision_id": 999}}

    # 客户端持有 revision_id=12，但文档实际已被改到 15
    def fake_fetch(doc_ref, *, doc_format="xml", detail="simple"):
        return FetchResult(document_id="fake", revision_id=15, content_xml="")

    monkeypatch.setattr("backend.api.routes.update_doc", fake_update_doc)
    monkeypatch.setattr("backend.api.routes.fetch_doc", fake_fetch)

    resp = client.post(
        "/api/doc/apply",
        json={
            "url": "https://example.feishu.cn/docx/fake",
            "revision_id": 12,
            "edits": [{"block_id": "blkcnA", "xml": "<p>改后A</p>"}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["conflict"] is True
    assert body["mode"] == "block_replace"
    assert body["final_revision_id"] == 15  # 返回文档当前真实版本供前端提示
    assert body["count"] == 0
    assert update_calls == []  # 冲突时不应真正写回


def test_apply_empty_content_uses_block_delete(monkeypatch):
    """edits 中 xml 为空串时改用 block_delete（block_replace 不接受空 content）。

    P2：空 xml = 删整块 → block_delete（doc_format=xml）。
    """
    monkeypatch.setattr(
        "backend.api.routes.settings",
        Settings(writeback_enabled=True),
    )
    calls: list[dict] = []

    def fake_update_doc(
        doc_ref, *, command, content="", pattern=None,
        block_id=None, doc_format="xml", revision_id=-1,
    ):
        calls.append(
            {"command": command, "block_id": block_id, "content": content,
             "doc_format": doc_format}
        )
        return {"document": {"revision_id": 13}}

    def fake_fetch(doc_ref, *, doc_format="xml", detail="simple"):
        return FetchResult(document_id="fake", revision_id=12, content_xml="")

    monkeypatch.setattr("backend.api.routes.update_doc", fake_update_doc)
    monkeypatch.setattr("backend.api.routes.fetch_doc", fake_fetch)

    resp = client.post(
        "/api/doc/apply",
        json={
            "url": "https://example.feishu.cn/docx/fake",
            "revision_id": 12,
            "edits": [{"block_id": "blkcnA", "xml": ""}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    # 空 xml → block_delete，而非 block_replace；P2 用 doc_format=xml
    assert calls[0]["command"] == "block_delete"
    assert calls[0]["block_id"] == "blkcnA"
    assert calls[0]["doc_format"] == "xml"


def test_apply_falls_back_to_str_replace_when_only_replacements(monkeypatch):
    """请求只带 replacements（无 edits）时降级走 str_replace 路径（兼容旧调用）。"""
    monkeypatch.setattr(
        "backend.api.routes.settings",
        Settings(writeback_enabled=True),
    )
    calls: list[dict] = []

    def fake_update_doc(
        doc_ref, *, command, content="", pattern=None,
        block_id=None, doc_format="xml", revision_id=-1,
    ):
        calls.append(
            {
                "command": command,
                "pattern": pattern,
                "content": content,
                "doc_format": doc_format,
                "revision_id": revision_id,
            }
        )
        return {"document": {"revision_id": 13}}

    monkeypatch.setattr("backend.api.routes.update_doc", fake_update_doc)

    resp = client.post(
        "/api/doc/apply",
        json={
            "url": "https://example.feishu.cn/docx/fake",
            "replacements": [{"pattern": "旧", "content": "新", "reason": "测试"}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["count"] == 1
    assert len(calls) == 1
    assert calls[0]["command"] == "str_replace"
    assert calls[0]["pattern"] == "旧"
    assert calls[0]["content"] == "新"
    assert calls[0]["doc_format"] == "markdown"
    assert calls[0]["revision_id"] == -1  # 旧路径始终基于最新版本


def test_apply_block_replace_simulated_when_writeback_disabled(monkeypatch):
    """writeback 关闭且 edits 非空：返回 simulated=True，不调 update_doc。"""
    monkeypatch.setattr(
        "backend.api.routes.settings",
        Settings(writeback_enabled=False),
    )

    def fail_update_doc(*a, **kw):
        raise AssertionError("writeback 关闭时不应调用 update_doc")

    monkeypatch.setattr("backend.api.routes.update_doc", fail_update_doc)

    resp = client.post(
        "/api/doc/apply",
        json={
            "url": "https://example.feishu.cn/docx/fake",
            "revision_id": 12,
            "edits": [{"block_id": "blkcnA", "xml": "<p>改后A</p>"}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["simulated"] is True
    assert body["mode"] == "block_replace"
    assert body["conflict"] is False
    assert body["count"] == 1
    assert body["results"][0]["block_id"] == "blkcnA"
    assert body["results"][0]["ok"] is True


def test_load_doc_returns_block_count(monkeypatch):
    """mock fetch_doc 后,/api/doc/load 返回 block_count（P2：只 fetch xml）。"""
    fake_xml = FetchResult(
        document_id="doc123",
        revision_id=5,
        content_xml="<title>周报</title><p>第一段</p>",
    )

    def fake_fetch(doc_ref: str, *, doc_format: str = "xml", detail: str = "simple"):
        return fake_xml

    monkeypatch.setattr("backend.api.routes.fetch_doc", fake_fetch)

    resp = client.post(
        "/api/doc/load",
        json={"url": "https://example.feishu.cn/docx/fake"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == "doc123"
    assert body["revision_id"] == 5
    assert body["block_count"] == 2
    # P2：不再返回 markdown 整篇
    assert "markdown" not in body


def test_load_doc_returns_blocks_with_ids(monkeypatch):
    """/api/doc/load 返回 blocks 列表：with-ids 的 XML 解析后 block_id 正确、raw_xml 含 id。"""
    fake_xml = FetchResult(
        document_id="doc123",
        revision_id=5,
        content_xml='<title id="blkcnT">周报</title><p id="blkcnA">本周内容</p>',
    )

    def fake_fetch(doc_ref: str, *, doc_format: str = "xml", detail: str = "simple"):
        return fake_xml

    monkeypatch.setattr("backend.api.routes.fetch_doc", fake_fetch)

    resp = client.post(
        "/api/doc/load",
        json={"url": "https://example.feishu.cn/docx/fake"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "blocks" in body
    blocks = body["blocks"]
    assert len(blocks) == 2
    assert blocks[0]["block_id"] == "blkcnT"
    assert blocks[0]["kind"] == "title"
    assert blocks[1]["block_id"] == "blkcnA"
    assert blocks[1]["kind"] == "p"
    # P2：每块带 raw_xml（含 id 属性）
    assert 'id="blkcnA"' in blocks[1]["raw_xml"]


def test_load_doc_propagates_lark_error_as_502(monkeypatch):
    """fetch_doc 抛 LarkError 时,/api/doc/load 返回 502。"""
    from backend.lark.cli_wrapper import LarkError

    def raising_fetch(doc_ref: str, *, doc_format: str = "xml", detail: str = "simple"):
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


def test_export_remote_doc_as_markdown_attachment(monkeypatch):
    """/api/doc/export 支持按 url 拉取完整文档并导出为 markdown。"""
    fake_xml = FetchResult(
        document_id="doc123",
        revision_id=5,
        content_xml="<title>周报</title><h1>进展</h1><p>完成 A</p>",
    )
    calls: list[dict] = []

    def fake_fetch(doc_ref: str, *, doc_format: str = "xml", detail: str = "simple"):
        calls.append({"doc_ref": doc_ref, "doc_format": doc_format, "detail": detail})
        return fake_xml

    monkeypatch.setattr("backend.api.routes.fetch_doc", fake_fetch)

    resp = client.post(
        "/api/doc/export",
        json={
            "url": "https://example.feishu.cn/docx/fake",
            "format": "md",
            "filename": "weekly",
        },
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "weekly.md" in resp.headers["content-disposition"]
    assert resp.text == "# 周报\n\n# 进展\n\n完成 A"
    assert calls == [
        {
            "doc_ref": "https://example.feishu.cn/docx/fake",
            "doc_format": "xml",
            "detail": "with-ids",
        }
    ]


def test_export_remote_doc_as_docx_attachment(monkeypatch):
    """/api/doc/export 支持按 url 拉取完整文档并导出为真实 docx。"""
    fake_xml = FetchResult(
        document_id="doc123",
        revision_id=5,
        content_xml="<title>周报</title><h1>进展</h1><p>完成 A</p>",
    )

    def fake_fetch(doc_ref: str, *, doc_format: str = "xml", detail: str = "simple"):
        return fake_xml

    monkeypatch.setattr("backend.api.routes.fetch_doc", fake_fetch)

    resp = client.post(
        "/api/doc/export",
        json={
            "url": "https://example.feishu.cn/docx/fake",
            "format": "docx",
            "filename": "weekly",
        },
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "weekly.docx" in resp.headers["content-disposition"]
    assert resp.content.startswith(b"PK")
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        document_xml = zf.read("word/document.xml").decode("utf-8")
    assert "周报" in document_xml
    assert "进展" in document_xml
    assert "完成 A" in document_xml


def test_export_remote_doc_rejects_unsupported_format(monkeypatch):
    """/api/doc/export 对不支持的导出格式返回 400。"""
    resp = client.post(
        "/api/doc/export",
        json={
            "url": "https://example.feishu.cn/docx/fake",
            "format": "pdf",
            "filename": "weekly",
        },
    )

    assert resp.status_code == 400
    assert "format" in resp.json()["detail"]


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


def test_get_llm_settings_returns_plaintext_keys():
    """GET /api/settings/llm 返回 base_url/model/api_key/auth_token 明文。"""
    _reset_llm(base_url="https://proxy.example.com", api_key="sk-secret", model="m1")
    resp = client.get("/api/settings/llm")
    assert resp.status_code == 200
    body = resp.json()
    assert body["base_url"] == "https://proxy.example.com"
    assert body["model"] == "m1"
    assert body["api_key"] == "sk-secret"
    assert body["auth_token"] == ""


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
    """密码框留空(传 None)时,原 api_key 保留。"""
    _reset_llm(api_key="sk-keep")
    resp = client.post(
        "/api/settings/llm",
        json={"base_url": "https://x.example.com"},  # 不传 api_key
    )
    assert resp.status_code == 200
    assert resp.json()["api_key"] == "sk-keep"  # 旧 key 仍在


def test_update_llm_settings_empty_string_clears_secret():
    """显式传空串表示清空该凭证。"""
    _reset_llm(api_key="sk-keep", auth_token="tok-keep")
    resp = client.post(
        "/api/settings/llm",
        json={"api_key": "", "auth_token": ""},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["api_key"] == ""
    assert body["auth_token"] == ""


def test_health_reflects_runtime_model():
    """/api/health 的 model 取自运行时配置,改设置后 health 同步变化。"""
    _reset_llm(model="health-model-xyz")
    assert client.get("/api/health").json()["model"] == "health-model-xyz"


# ===== LLM 连接检测端点（mock anthropic，避免真实调用） =====


def _patch_anthropic(monkeypatch, *, create_side_effect=None):
    """mock anthropic.Anthropic 类，让其 messages.create 触发指定副作用。

    只替换 Anthropic 类本身，保留模块其余内容（异常类等）给 _classify_llm_error 用。
    """
    import anthropic

    class _FakeMessages:
        def __init__(self) -> None:
            self.create = lambda *a, **kw: None

    fake_messages = _FakeMessages()

    class _FakeClient:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.messages = fake_messages

    if create_side_effect is not None:
        fake_messages.create = create_side_effect  # type: ignore[assignment]
    monkeypatch.setattr(anthropic, "Anthropic", _FakeClient)


def test_llm_test_success_returns_ok_and_latency(monkeypatch):
    """检测成功:返回 ok=True + latency_ms。"""
    _patch_anthropic(monkeypatch)  # create 默认返回 None
    resp = client.post(
        "/api/settings/llm/test",
        json={"base_url": "https://x.example.com", "auth_token": "tok", "model": "m1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["latency_ms"] is not None
    assert body["latency_ms"] >= 0


def test_llm_test_failure_returns_ok_false(monkeypatch):
    """create 抛异常 → ok=False,带 error_type 与 detail。"""
    def raise_err(*a, **kw):
        raise RuntimeError("boom")

    _patch_anthropic(monkeypatch, create_side_effect=raise_err)
    resp = client.post(
        "/api/settings/llm/test",
        json={"base_url": "https://x.example.com", "api_key": "bad", "model": "m1"},
    )
    body = resp.json()
    assert body["ok"] is False
    assert body["error_type"] == "unknown"
    assert "boom" in body["detail"]


# ----- _classify_llm_error 分类逻辑单测(用真实异常类) -----


def _make_response(status: int):
    """构造真实 httpx.Response,供 anthropic APIStatusError 子类使用。"""
    import httpx

    return httpx.Response(status_code=status, request=httpx.Request("POST", "https://x"))


def test_classify_auth_error():
    import anthropic

    from backend.api.routes import _classify_llm_error

    etype, _ = _classify_llm_error(
        anthropic.AuthenticationError(message="bad key", response=_make_response(401), body=None)
    )
    assert etype == "auth"


def test_classify_model_not_found_error():
    import anthropic

    from backend.api.routes import _classify_llm_error

    etype, _ = _classify_llm_error(
        anthropic.NotFoundError(message="no model", response=_make_response(404), body=None)
    )
    assert etype == "model"


def test_classify_rate_limit_error():
    import anthropic

    from backend.api.routes import _classify_llm_error

    etype, _ = _classify_llm_error(
        anthropic.RateLimitError(message="slow down", response=_make_response(429), body=None)
    )
    assert etype == "rate_limit"


def test_classify_network_timeout_error():
    import anthropic

    from backend.api.routes import _classify_llm_error

    etype, _ = _classify_llm_error(anthropic.APITimeoutError(request=None))
    assert etype == "network"


def test_llm_test_does_not_persist_config(monkeypatch):
    """检测用的临时配置不落库:运行时配置应不受影响。"""
    _reset_llm(api_key="original-key", model="original-model")
    _patch_anthropic(monkeypatch)
    client.post(
        "/api/settings/llm/test",
        json={"base_url": "https://x.example.com", "api_key": "temp-key", "model": "temp-model"},
    )
    cfg = client.get("/api/settings/llm").json()
    assert cfg["api_key"] == "original-key"
    assert cfg["model"] == "original-model"

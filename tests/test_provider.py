from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

import pytest

from bugfix_agent.provider import DeepSeekProvider


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        body = b'{"choices":[{"message":{"content":"{\\"files\\":[\\"calc.py\\"],\\"reason\\":\\"inspect function\\"}"}}],"usage":{"prompt_tokens":42,"completion_tokens":12}}'
        status = 200
        request_body = None
        request_auth = None
        request_path = None
        reject_default_client = False

        def do_POST(self):
            if self.reject_default_client and self.headers.get('User-Agent', '').startswith('Python-urllib'):
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b'{"title":"Error 1010: Access denied","detail":"Client signature blocked","error_code":1010}')
                return
            type(self).request_body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            type(self).request_auth = self.headers.get("Authorization")
            type(self).request_path = self.path
            self.send_response(self.status)
            self.end_headers()
            self.wfile.write(self.body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}", Handler
    httpd.shutdown()
    httpd.server_close()
    thread.join()


def test_api_contract_and_usage_are_derived_from_http_response(server):
    url, handler = server
    provider = DeepSeekProvider(api_key="test-key", base_url=url)
    result = provider.complete("locator", {"issue": "broken", "inventory": {"calc.py": "add"}})
    assert result["files"] == ["calc.py"]
    assert provider.usage["prompt_tokens"] == 42
    assert provider.usage["completion_tokens"] == 12
    assert provider.usage["calls"] == 1
    assert handler.request_body["response_format"] == {"type": "json_object"}
    assert handler.request_auth == "Bearer test-key"
    assert handler.request_body["messages"][0]["role"] == "system"


@pytest.mark.parametrize("body", [b'{}', b'{"choices":[]}',
    b'{"choices":[{"message":{"content":"not json"}}]}',
    b'{"choices":[{"message":{"content":"[]"}}]}'])
def test_malformed_responses_fail_clearly(server, body):
    url, handler = server
    handler.body = body
    with pytest.raises(ValueError):
        DeepSeekProvider(api_key="test-key", base_url=url).complete("locator", {})


def test_api_error_does_not_leak_key_or_response_body(server):
    url, handler = server
    handler.status = 401
    handler.body = b'private-key-123'
    with pytest.raises(RuntimeError) as error:
        DeepSeekProvider(api_key="private-key-123", base_url=url).complete("locator", {})
    assert "401" in str(error.value)
    assert "private-key-123" not in str(error.value)


def test_custom_platform_environment_routes_request_and_model(server, monkeypatch):
    url, handler = server
    monkeypatch.setenv("DEEPSEEK_BASE_URL", url + "/v1/")
    monkeypatch.setenv("DEEPSEEK_MODEL", "platform-model-name")
    monkeypatch.setenv("DEEPSEEK_API_KEY", " platform-test-key \n")
    provider = DeepSeekProvider()
    assert provider.url == url + "/v1/chat/completions"
    result = provider.complete("locator", {})
    assert result["files"] == ["calc.py"]
    assert handler.request_path == "/v1/chat/completions"
    assert handler.request_body["model"] == "platform-model-name"
    assert handler.request_auth == "Bearer platform-test-key"


def test_explicit_endpoint_overrides_environment_and_accepts_full_path(server, monkeypatch):
    url, handler = server
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://unused.example/v1")
    provider = DeepSeekProvider(api_key="test", base_url=url + "/v1/chat/completions")
    assert provider.url == url + "/v1/chat/completions"
    provider.complete("locator", {})
    assert handler.request_path == "/v1/chat/completions"


@pytest.mark.parametrize("url", [
    "https://", "https://user:password@example.com/v1", "https://example.com/v1?key=private",
    "https://example.com/v1#key", "http://remote.example/v1", "https://example.com:invalid/v1",
])
def test_invalid_or_credential_bearing_endpoint_rejected(url):
    with pytest.raises(ValueError):
        DeepSeekProvider(api_key="test", base_url=url)


def test_default_official_endpoint_is_preserved(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    provider = DeepSeekProvider(api_key="test")
    assert provider.url == "https://api.deepseek.com/chat/completions"


def test_403_reports_platform_reason_with_secrets_redacted(server):
    url, handler = server
    handler.status = 403
    handler.body = json.dumps({"error": {"code": "group_denied", "message":
        "Group unavailable for private-test-key; Bearer other-secret; sk-another-secret"}}).encode()
    with pytest.raises(RuntimeError) as error:
        DeepSeekProvider(api_key="private-test-key", base_url=url).complete("locator", {})
    message = str(error.value)
    assert "group_denied" in message and "Group unavailable" in message
    assert "private-test-key" not in message
    assert "other-secret" not in message and "sk-another-secret" not in message
    assert "密钥无权限访问该模型" not in message


def test_html_403_is_not_reported_as_confirmed_model_permission_error(server):
    url, handler = server
    handler.status = 403
    handler.body = b'<html><body>blocked secret-data</body></html>'
    with pytest.raises(RuntimeError) as error:
        DeepSeekProvider(api_key="test", base_url=url).complete("locator", {})
    message = str(error.value)
    assert "403" in message and "未提供可解析的 JSON 错误说明" in message
    assert "secret-data" not in message
    assert "密钥无权限访问该模型" not in message


def test_identified_application_client_reaches_api(server):
    url, handler = server
    handler.reject_default_client = True
    result = DeepSeekProvider(api_key="test", base_url=url).complete("locator", {})
    assert result["files"] == ["calc.py"]


def test_gateway_problem_json_preserves_diagnostic_reason(server):
    url, handler = server
    handler.status = 403
    handler.body = json.dumps({"title": "Error 1010: Access denied",
        "detail": "Client signature blocked", "error_code": 1010}).encode()
    with pytest.raises(RuntimeError) as error:
        DeepSeekProvider(api_key="test", base_url=url).complete("locator", {})
    assert "1010" in str(error.value)
    assert "Client signature blocked" in str(error.value)

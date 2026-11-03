"""Configurable chat-completions JSON adapter and labeled fixture replay."""

import json
import os
from pathlib import Path
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from bugfix_agent.prompts import PROMPTS


def error_detail(response, secret: str) -> str:
    """Keep only bounded JSON error fields, never dump headers or raw bodies."""
    fallback = "平台未提供可解析的 JSON 错误说明"
    try:
        body = response.read(16_385)
        if len(body) > 16_384:
            return fallback
        data = json.loads(body)
        if not isinstance(data, dict):
            return fallback
        error = data.get("error", data)
        if isinstance(error, dict):
            parts = [error.get(field) for field in ("code", "error_code", "type", "title", "message", "detail")]
            detail = " / ".join(str(part) for part in parts if isinstance(part, (str, int)) and part)
        else:
            detail = error if isinstance(error, str) else ""
        if not detail:
            return fallback
        detail = detail.replace(secret, "[REDACTED]")
        detail = re.sub(r"(?i)\bBearer\s+[^\s\"',;<>]+", "Bearer [REDACTED]", detail)
        detail = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[REDACTED]", detail)
        return " ".join(detail.split())[:600]
    except (ValueError, OSError):
        return fallback


class DeepSeekProvider:
    mode = "live"

    def __init__(self, api_key=None, model=None, base_url=None, timeout=120):
        self._key = (api_key or os.environ.get("DEEPSEEK_API_KEY", "")).strip()
        if not self._key.strip():
            raise ValueError("未配置 DEEPSEEK_API_KEY。请在本机环境变量中设置密钥，或先运行 demo。")
        self.model = (model or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")).strip()
        if not self.model:
            raise ValueError("DEEPSEEK_MODEL 不能为空，请填写平台提供的模型名称。")
        base_url = (base_url if base_url is not None else os.environ.get(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com")).strip().rstrip("/")
        try:
            parsed = urlparse(base_url)
            parsed.port
            if (not parsed.hostname or parsed.username is not None or parsed.password is not None
                    or parsed.query or parsed.fragment or parsed.params
                    or any(char.isspace() for char in base_url)):
                raise ValueError("invalid endpoint")
        except ValueError:
            raise ValueError("DEEPSEEK_BASE_URL 必须是有效接口地址，不能包含账户、密钥、查询参数或片段。") from None
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}):
            raise ValueError("模型接口必须使用 HTTPS。")
        self.url = base_url if parsed.path.endswith("/chat/completions") else base_url + "/chat/completions"
        self.timeout = timeout
        self.usage = {"calls": 0, "responses": 0, "prompt_tokens": 0, "completion_tokens": 0, "usage_reported_calls": 0}

    def complete(self, role: str, context: dict) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": PROMPTS[role]},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": 4096,
            "stream": False,
        }
        request = Request(self.url, data=json.dumps(payload).encode("utf-8"), headers={
            "Authorization": f"Bearer {self._key}", "Content-Type": "application/json",
            "Accept": "application/json", "User-Agent": "BugFix-Agent/0.1",
        }, method="POST")
        self.usage["calls"] += 1
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read(2_000_001)
                if len(body) > 2_000_000:
                    raise ValueError("模型响应超过大小限制。")
        except HTTPError as exc:
            hints = {400: "请检查模型名称与 JSON 模式等参数是否受平台支持",
                     401: "请检查密钥是否属于当前接口平台", 402: "账户余额不足",
                     403: "请求被拒绝，可能涉及密钥分组、模型权限或平台访问策略，不能仅凭状态码确定原因",
                     404: "请检查接口路径（是否需要 /v1）及模型名称",
                     429: "请求受限，请稍后重试"}
            detail = error_detail(exc, self._key)
            exc.close()
            raise RuntimeError(f"模型接口 HTTP {exc.code}：{hints.get(exc.code, '接口请求失败')}。"
                               f" 平台错误说明（已脱敏）：{detail}") from None
        except (URLError, TimeoutError, socket.timeout):
            raise RuntimeError("模型接口网络连接失败或请求超时，请检查网络和接口地址。") from None
        try:
            envelope = json.loads(body)
            usage = envelope.get("usage", {})
            if (isinstance(usage, dict) and isinstance(usage.get("prompt_tokens"), int)
                    and isinstance(usage.get("completion_tokens"), int)):
                self.usage["prompt_tokens"] += usage["prompt_tokens"]
                self.usage["completion_tokens"] += usage["completion_tokens"]
                self.usage["usage_reported_calls"] += 1
            result = json.loads(envelope["choices"][0]["message"]["content"])
            if not isinstance(result, dict):
                raise ValueError("expected object")
            self.usage["responses"] += 1
            return result
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise ValueError("模型未返回有效 JSON 对象，请查看模型配置或重新运行。") from None


class ReplayProvider:
    """Hand-authored responses exercise the tools, NOT model intelligence."""

    mode = "replay"
    model = "预设响应 / 无模型调用"

    def __init__(self, path: Path):
        self.responses = json.loads(Path(path).read_text(encoding="utf-8"))
        self.usage = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "usage_reported_calls": 0}

    def complete(self, role: str, context: dict) -> dict:
        return json.loads(json.dumps(self.responses[role]))

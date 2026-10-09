"""百炼供应商：请求的形状（温度 0、结构化输出、超时、有限重试）、用量的读取、SDK 异常变成 E_LLM。

SDK 的客户端用记录请求的桩替换，所以不需要网络和密钥。
"""

from types import SimpleNamespace
from typing import ClassVar

import openai
import pytest

try:
    import httpx2 as httpx  # openai 新版本依赖的 HTTP 库
except ImportError:  # pragma: no cover - 旧版本的 openai 用 httpx
    import httpx

from pydantic import BaseModel

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.llm.client import StructuredClient
from reactor_agent.llm.providers import dashscope
from reactor_agent.llm.providers.dashscope import (
    CONNECT_TIMEOUT_S,
    MAX_NETWORK_RETRIES,
    DashScopeProvider,
)
from reactor_agent.spec.settings import LlmSettings

SETTINGS = LlmSettings(
    provider="dashscope",
    model="qwen-test",
    base_url="https://example.invalid/v1",
    api_key_env="DASHSCOPE_API_KEY",
    timeout_s=12.5,
)
SECRET = "sk-secret-value-123456"
URL = "https://example.invalid/v1/chat/completions"


class Answer(BaseModel):
    kind: str


def reply(text: str, prompt: int = 7, completion: int = 3) -> SimpleNamespace:
    message = SimpleNamespace(content=text)
    usage = SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


class FakeOpenAI:
    """记录构造参数和每次请求；按 outcome 返回回复或抛出异常。"""

    outcome: ClassVar[object] = None
    constructed: ClassVar[dict[str, object]] = {}
    requests: ClassVar[list[dict[str, object]]] = []

    def __init__(self, **kwargs: object) -> None:
        FakeOpenAI.constructed = kwargs
        FakeOpenAI.requests = []
        completions = SimpleNamespace(create=self._create)
        self.chat = SimpleNamespace(completions=completions)

    def _create(self, **kwargs: object) -> object:
        FakeOpenAI.requests.append(kwargs)
        if isinstance(FakeOpenAI.outcome, Exception):
            raise FakeOpenAI.outcome
        return FakeOpenAI.outcome


@pytest.fixture
def provider(monkeypatch) -> DashScopeProvider:
    monkeypatch.setattr(dashscope, "OpenAI", FakeOpenAI)
    FakeOpenAI.outcome = reply('{"kind": "a"}')
    return DashScopeProvider(SETTINGS, SECRET)


def status_error(code: int, body: object = None) -> openai.APIStatusError:
    request = httpx.Request("POST", URL)
    response = httpx.Response(code, request=request)
    return openai.APIStatusError("boom", response=response, body=body)


def test_the_client_is_built_with_the_configured_timeout_and_a_bounded_number_of_retries(provider):
    built = FakeOpenAI.constructed
    assert built["timeout"].read == 12.5 and built["max_retries"] == MAX_NETWORK_RETRIES
    assert built["timeout"].connect == CONNECT_TIMEOUT_S
    assert built["base_url"] == SETTINGS.base_url and built["api_key"] == SECRET
    assert 0 < MAX_NETWORK_RETRIES <= 3


def test_a_request_uses_temperature_zero_and_a_native_json_schema(provider):
    provider.generate("系统", "用户", {"type": "object"})
    [request] = FakeOpenAI.requests
    assert request["model"] == "qwen-test" and request["temperature"] == 0
    assert request["messages"] == [
        {"role": "system", "content": "系统"},
        {"role": "user", "content": "用户"},
    ]
    response_format = request["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["schema"] == {"type": "object"}
    assert response_format["json_schema"]["strict"] is True


def test_thinking_is_switched_off_because_it_makes_the_call_far_too_slow(provider):
    provider.generate("s", "u", {})
    assert FakeOpenAI.requests[0]["extra_body"] == {"enable_thinking": False}


def test_the_reply_text_and_the_usage_are_returned(provider):
    raw = provider.generate("s", "u", {})
    assert (raw.text, raw.prompt_tokens, raw.completion_tokens) == ('{"kind": "a"}', 7, 3)
    assert provider.model == "qwen-test"


def test_a_reply_without_usage_or_content_is_still_a_reply(provider):
    FakeOpenAI.outcome = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=None))], usage=None
    )
    raw = provider.generate("s", "u", {})
    assert (raw.text, raw.prompt_tokens, raw.completion_tokens) == ("", 0, 0)


@pytest.mark.parametrize("code", [400, 401, 404, 429, 500])
def test_an_http_error_becomes_an_llm_error_with_the_status_and_never_the_key(provider, code):
    FakeOpenAI.outcome = status_error(code, body={"message": "出错了"})
    with pytest.raises(ReactorAgentError) as caught:
        provider.generate("s", "u", {})
    assert caught.value.code is ErrorCode.LLM
    assert str(code) in caught.value.message and "出错了" in caught.value.message
    assert SECRET not in caught.value.message


def test_a_timeout_says_so(provider):
    FakeOpenAI.outcome = openai.APITimeoutError(request=httpx.Request("POST", URL))
    with pytest.raises(ReactorAgentError, match="超时") as caught:
        provider.generate("s", "u", {})
    assert caught.value.code is ErrorCode.LLM


def test_a_connection_failure_says_the_interface_cannot_be_reached(provider):
    FakeOpenAI.outcome = openai.APIConnectionError(request=httpx.Request("POST", URL))
    with pytest.raises(ReactorAgentError, match="连不上") as caught:
        provider.generate("s", "u", {})
    assert caught.value.code is ErrorCode.LLM


def test_the_provider_plugs_into_the_structured_client(provider):
    result = StructuredClient(provider).complete("系统", "用户", Answer)
    assert result.value == Answer(kind="a") and result.record.model == "qwen-test"
    assert result.record.attempts[0].prompt_tokens == 7

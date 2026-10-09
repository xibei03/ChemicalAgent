"""阿里云百炼（DashScope）的 Qwen 模型，通过 OpenAI 兼容接口用 openai SDK 调用。

这家供应商的差别全在这里：怎么要求结构化输出、温度、超时和网络重试用 SDK 自带的配置、
SDK 的各种异常怎么变成 E_LLM。密钥由调用方从环境变量读出来传入，这里不读环境，也不记录它。
"""

from collections.abc import Mapping

import openai
from openai import OpenAI
from openai.types.shared_params import ResponseFormatJSONSchema

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.llm.client import RawReply
from reactor_agent.spec.settings import LlmSettings

# 网络错误和 5xx、429 的重试由 SDK 自己做，次数有限，演示时网络不通也不会卡上几分钟。
MAX_NETWORK_RETRIES = 2
TEMPERATURE = 0
# Qwen3 默认开着思考：同一个选型请求，思考开着 90 秒还没有回完，关掉只要 7 秒（台账 L39）。
# 选型是读懂原文、按定义抽特征，不需要长链推理，所以关掉。
EXTRA_BODY: dict[str, object] = {"enable_thinking": False}
RESPONSE_NAME = "structured_output"
BODY_CHARS = 300


def _response_format(schema: Mapping[str, object]) -> ResponseFormatJSONSchema:
    """原生的结构化输出：按 JSON Schema 约束回复。"""
    return {
        "type": "json_schema",
        "json_schema": {"name": RESPONSE_NAME, "strict": True, "schema": dict(schema)},
    }


def _failure(error: openai.APIError) -> ReactorAgentError:
    """SDK 的异常变成 E_LLM，说明是什么类型的问题；消息里不会有密钥。"""
    if isinstance(error, openai.APIStatusError):
        body = str(error.body)[:BODY_CHARS]
        message = f"LLM 接口返回 {error.status_code}（{type(error).__name__}）：{body}"
    elif isinstance(error, openai.APITimeoutError):
        message = "LLM 接口超时，没有在规定的时间内回复"
    else:
        message = f"连不上 LLM 接口（{type(error).__name__}）：{error}"
    return ReactorAgentError(ErrorCode.LLM, message)


class DashScopeProvider:
    """ChatProvider 的百炼实现。"""

    def __init__(self, settings: LlmSettings, api_key: str) -> None:
        self._model = settings.model
        self._client = OpenAI(
            api_key=api_key,
            base_url=settings.base_url,
            timeout=settings.timeout_s,
            max_retries=MAX_NETWORK_RETRIES,
        )

    @property
    def model(self) -> str:
        """模型名。"""
        return self._model

    def generate(self, system: str, user: str, schema: Mapping[str, object]) -> RawReply:
        """用结构化输出问一次。"""
        try:
            reply = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=TEMPERATURE,
                response_format=_response_format(schema),
                extra_body=EXTRA_BODY,
            )
        except openai.APIError as error:
            raise _failure(error) from error
        usage = reply.usage
        return RawReply(
            text=reply.choices[0].message.content or "",
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
        )

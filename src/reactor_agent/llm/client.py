"""LLM 客户端的接口：给它系统提示、用户内容和一个 pydantic 模型类型，返回这个类型的实例和调用记录。

harness 只看见 LlmClient。各家供应商的差别（怎么要求结构化输出、怎么读回复和用量、怎么把网络错误
变成领域错误）都在 llm/providers/ 里，那里的类只实现 ChatProvider 的一个方法。

校验重问是这一层自己的约定：回复没有通过 pydantic 校验时，带着错误再问一次，仍不通过就抛 E_LLM。
客户端不写文件，也不写 Trace，每次调用都是无状态的。
"""

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.base import FrozenModel
from reactor_agent.spec.llm import LlmAttempt, LlmCallRecord

ModelT = TypeVar("ModelT", bound=BaseModel)
# 第一次问，加上校验不过时带着错误重问的一次。
MAX_ATTEMPTS = 2
MAX_PROBLEMS_SHOWN = 5
FAILURE_REPLY_CHARS = 400
CORRECTION_TEMPLATE = (
    "{user}\n\n---\n你上一次的回复没有通过校验。\n上一次的回复：\n{reply}\n"
    "校验发现的问题：\n{problem}\n请改正这些问题，重新输出完整的结果。"
)


class RawReply(FrozenModel):
    """供应商的一次回复：文字和用量。"""

    text: str
    prompt_tokens: int
    completion_tokens: int


class ChatProvider(Protocol):
    """一家供应商要实现的东西：用结构化输出问一次，拿回文字。网络和接口错误转成 E_LLM 抛出。"""

    @property
    def model(self) -> str:
        """模型名，写进调用记录。"""
        ...

    def generate(self, system: str, user: str, schema: Mapping[str, object]) -> RawReply:
        """发一次请求。schema 是期望输出的 JSON Schema，供应商决定怎么用它。"""
        ...


# 项目支持 Python 3.11，所以用 Generic，不用 3.12 才有的类型参数语法。
@dataclass(frozen=True)
class LlmReply(Generic[ModelT]):
    """校验过的输出，和这次调用的记录。"""

    value: ModelT
    record: LlmCallRecord


class LlmClient(Protocol):
    """harness 用的接口。测试里的桩是它的第二个实现。"""

    def complete(self, system: str, user: str, output: type[ModelT]) -> LlmReply[ModelT]:
        """问一次，返回 output 类型的实例。两次都不合法抛 E_LLM。"""
        ...


def _problems(error: ValidationError) -> str:
    shown = [
        f"- {'.'.join(str(part) for part in item['loc'])}：{item['msg']}" for item in error.errors()
    ]
    extra = len(shown) - MAX_PROBLEMS_SHOWN
    lines = shown[:MAX_PROBLEMS_SHOWN] + ([f"- 另有 {extra} 处"] if extra > 0 else [])
    return "\n".join(lines)


class StructuredClient:
    """在 ChatProvider 上加 pydantic 校验和一次带错误的重问。"""

    def __init__(self, provider: ChatProvider) -> None:
        self._provider = provider

    def complete(self, system: str, user: str, output: type[ModelT]) -> LlmReply[ModelT]:
        """问一次；回复没有通过校验就带着错误重问一次。"""
        schema = output.model_json_schema()
        attempts: list[LlmAttempt] = []
        content = user
        for _ in range(MAX_ATTEMPTS):
            started = time.monotonic()
            raw = self._provider.generate(system, content, schema)
            elapsed_ms = round((time.monotonic() - started) * 1000)
            try:
                value = output.model_validate_json(raw.text)
            except ValidationError as error:
                problem = _problems(error)
            else:
                attempts.append(self._attempt(content, raw, elapsed_ms, None))
                return LlmReply(
                    value,
                    LlmCallRecord(
                        model=self._provider.model, system_prompt=system, attempts=tuple(attempts)
                    ),
                )
            attempts.append(self._attempt(content, raw, elapsed_ms, problem))
            content = CORRECTION_TEMPLATE.format(user=user, reply=raw.text, problem=problem)
        details = {"最后一次的回复": raw.text[:FAILURE_REPLY_CHARS], "校验发现的问题": problem}
        message = f"LLM 的输出连续 {MAX_ATTEMPTS} 次没有通过 {output.__name__} 的校验"
        raise ReactorAgentError(ErrorCode.LLM, message, details)

    @staticmethod
    def _attempt(content: str, raw: RawReply, elapsed_ms: int, problem: str | None) -> LlmAttempt:
        return LlmAttempt(
            user_content=content,
            reply_text=raw.text,
            prompt_tokens=raw.prompt_tokens,
            completion_tokens=raw.completion_tokens,
            duration_ms=elapsed_ms,
            validation_error=problem,
        )

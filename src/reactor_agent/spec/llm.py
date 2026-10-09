"""LLM 调用的记录。客户端产出它，执行器把摘要写进 Trace、全文写进运行目录的 llm/ 子目录。

一次调用可能包含客户端内部的“校验不过，带着错误重问”，所以记录里是一串往返（LlmAttempt）。
记录里没有密钥：客户端从来不把密钥放进提示和回复。
"""

from reactor_agent.spec.base import FrozenModel
from reactor_agent.spec.enums import CallPoint


class LlmAttempt(FrozenModel):
    """一次往返：发出的内容、回复的全文、用量、耗时。validation_error 是这一次没通过校验的原因。"""

    user_content: str
    reply_text: str
    prompt_tokens: int
    completion_tokens: int
    duration_ms: int
    validation_error: str | None = None


class LlmCallRecord(FrozenModel):
    """一次调用的完整记录：模型名、系统提示和每次往返。"""

    model: str
    system_prompt: str
    attempts: tuple[LlmAttempt, ...]

    @property
    def total_tokens(self) -> int:
        """全部往返用掉的 token（提示加回复）。"""
        return sum(item.prompt_tokens + item.completion_tokens for item in self.attempts)

    @property
    def duration_ms(self) -> int:
        """全部往返的耗时。"""
        return sum(item.duration_ms for item in self.attempts)


class LlmCallSummary(FrozenModel):
    """Trace 里记的 LLM 调用摘要：调用点、模型、Skill 的名字和内容哈希、用量、往返次数。"""

    call_point: CallPoint
    model: str
    skill: str
    skill_hash: str
    prompt_tokens: int
    completion_tokens: int
    attempts: int


def summarize_call(
    call_point: CallPoint, skill: str, skill_hash: str, record: LlmCallRecord
) -> LlmCallSummary:
    """从完整的调用记录得到 Trace 里的摘要。"""
    return LlmCallSummary(
        call_point=call_point,
        model=record.model,
        skill=skill,
        skill_hash=skill_hash,
        prompt_tokens=sum(item.prompt_tokens for item in record.attempts),
        completion_tokens=sum(item.completion_tokens for item in record.attempts),
        attempts=len(record.attempts),
    )

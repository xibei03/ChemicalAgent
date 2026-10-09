"""LLM 客户端的桩：按脚本依次返回预设的结果（或者抛出预设的错误），并记录收到的提问。

只放在 tests/ 里。它实现 llm.client.LlmClient 的接口，所以是这个隔离边界的第二个实现。
"""

from collections.abc import Sequence

from pydantic import BaseModel

from reactor_agent.errors import ReactorAgentError
from reactor_agent.llm.client import LlmReply, ModelT
from reactor_agent.spec.llm import LlmAttempt, LlmCallRecord

MODEL_NAME = "stub-model"
PROMPT_TOKENS = 1000
COMPLETION_TOKENS = 200


class FakeLlm:
    """依次返回 replies 里的结果；用完之后再问就是测试写错了。"""

    def __init__(self, replies: Sequence[BaseModel | ReactorAgentError]) -> None:
        self._replies = list(replies)
        self.requests: list[tuple[str, str]] = []

    @property
    def calls(self) -> int:
        return len(self.requests)

    @property
    def remaining(self) -> int:
        """脚本里还没有被问到的回复个数。"""
        return len(self._replies)

    def complete(self, system: str, user: str, output: type[ModelT]) -> LlmReply[ModelT]:
        self.requests.append((system, user))
        reply = self._replies.pop(0)
        if isinstance(reply, ReactorAgentError):
            raise reply
        assert isinstance(reply, output), f"桩里的结果是 {type(reply).__name__}，要的是 {output}"
        attempt = LlmAttempt(
            user_content=user,
            reply_text=reply.model_dump_json(),
            prompt_tokens=PROMPT_TOKENS,
            completion_tokens=COMPLETION_TOKENS,
            duration_ms=1500,
        )
        record = LlmCallRecord(model=MODEL_NAME, system_prompt=system, attempts=(attempt,))
        return LlmReply(reply, record)

"""调用 LLM 的公共部分：调用、全文落盘、摘要进 Trace，失败了也留痕。

选型、写规格（以及之后的写解读）都经过这里，所以每次调用留下的东西一样：llm/ 下的全文，和 Trace 里
带模型名、Skill 名和内容哈希、用量的事件。
"""

from dataclasses import dataclass

from reactor_agent.llm.client import LlmClient, LlmError, ModelT
from reactor_agent.llm.prompts import Prompt
from reactor_agent.observability.trace import TraceWriter, llm_call_event
from reactor_agent.skill_loader import Skill
from reactor_agent.spec.enums import CallPoint
from reactor_agent.spec.llm import LlmCallRecord, summarize_call
from reactor_agent.state.models import TaskState
from reactor_agent.state.store import StateStore


@dataclass(frozen=True)
class LlmCaller:
    """一个任务里的 LLM 调用：客户端、存储和 Trace。"""

    llm: LlmClient
    store: StateStore
    trace: TraceWriter

    def ask(
        self,
        task: TaskState,
        call_point: CallPoint,
        skill: Skill,
        prompt: Prompt,
        output: type[ModelT],
    ) -> ModelT:
        """问一次，返回校验过的输出。校验两次都没通过时，回复全文也留下，排查时要看。"""
        try:
            reply = self.llm.complete(prompt.system, prompt.user, output)
        except LlmError as error:
            self._record(task, call_point, skill, error.record)
            raise
        self._record(task, call_point, skill, reply.record)
        return reply.value

    def _record(
        self, task: TaskState, call_point: CallPoint, skill: Skill, record: LlmCallRecord
    ) -> None:
        self.store.write_llm_log(task.task_id, call_point, record)
        summary = summarize_call(call_point, skill.name, skill.content_hash, record)
        event = llm_call_event(summary, record.duration_ms)
        self.trace.append(task.task_id, task.spec_hash, task.current_state, None, event)

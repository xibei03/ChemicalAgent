"""Trace：向 trace.jsonl 追加事件，每行一个 JSON，以及读回。

业务事件只进 Trace，不进 logging。事件模型是计划 §14.1 的子集（没有 run_id 和 skill，
那两项现在没有来源）。
"""

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

from pydantic import AwareDatetime, JsonValue

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.base import FrozenModel
from reactor_agent.spec.enums import CheckId, Checkpoint, EventType, TaskStatus, WorkflowState
from reactor_agent.spec.llm import LlmCallSummary
from reactor_agent.spec.loading import parse_model, read_utf8
from reactor_agent.spec.results import Issue
from reactor_agent.spec.selection import SelectionResult

TRACE_FILE = "trace.jsonl"


class EventBody(FrozenModel):
    """调用方说得出的那部分：发生了什么。时间、序号和所处的状态由 TraceWriter 补上。

    verdict 只有验证事件有：每项检查是否通过。llm 只有 LLM 调用事件有。
    """

    type: EventType
    name: str
    attempt: int | None = None
    input: JsonValue = None
    output: JsonValue = None
    verdict: Mapping[CheckId, bool] | None = None
    llm: LlmCallSummary | None = None
    duration_ms: int | None = None
    error: str | None = None


class TraceEvent(EventBody):
    """trace.jsonl 里的一行。state 是事件发生时的状态；任务到了终态，就是终态。

    spec_hash 在规格冻结之前（从文字描述开始的任务还在选型、写规格时）是 None。
    """

    ts: AwareDatetime
    task_id: str
    seq: int
    state: WorkflowState | TaskStatus
    case: str | None
    spec_hash: str | None


class TraceWriter:
    """向 runs/<task_id>/trace.jsonl 追加事件。一个 runs 目录一个实例，序号按任务各自计。"""

    def __init__(self, runs_dir: Path) -> None:
        self._runs_dir = runs_dir
        self._next_seq: dict[str, int] = {}

    def append(
        self,
        task_id: str,
        spec_hash: str | None,
        state: WorkflowState | TaskStatus,
        case: str | None,
        body: EventBody,
    ) -> TraceEvent:
        """追加一个事件并返回它。"""
        path = self._runs_dir / task_id / TRACE_FILE
        seq = self._next_seq.get(task_id)
        if seq is None:
            seq = len(read_events(path))
        event = TraceEvent(
            **body.model_dump(),
            ts=datetime.now().astimezone(),
            task_id=task_id,
            seq=seq,
            state=state,
            case=case,
            spec_hash=spec_hash,
        )
        try:
            with path.open("a", encoding="utf-8") as stream:
                stream.write(event.model_dump_json() + "\n")
        except OSError as error:
            raise ReactorAgentError(ErrorCode.IO, f"写不了 Trace {path}：{error}") from error
        self._next_seq[task_id] = seq + 1
        return event


def read_events(path: Path) -> list[TraceEvent]:
    """读 trace.jsonl 里的全部事件，按写入的顺序。文件还不存在是空列表。

    进程被中断时最后一行可能只写了一半，那一行忽略；其他位置的坏行是 E_SCHEMA，消息里有行号。
    """
    if not path.is_file():
        return []
    lines = read_utf8(path).splitlines()
    events = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            events.append(parse_model(TraceEvent, _loads(line), path.name))
        except ReactorAgentError as error:
            if number == len(lines):
                break
            raise ReactorAgentError(
                error.code, f"{path.name} 第 {number} 行不合法：{error.message}", error.details
            ) from error
    return events


def _loads(line: str) -> object:
    try:
        return json.loads(line)
    except json.JSONDecodeError as error:
        raise ReactorAgentError(ErrorCode.SCHEMA, f"不是合法的 JSON：{error}") from error


def llm_call_event(summary: LlmCallSummary, duration_ms: int) -> EventBody:
    """一次 LLM 调用的 Trace 事件，名字是调用点。"""
    return EventBody(
        type=EventType.LLM_CALL, name=summary.call_point.value, llm=summary, duration_ms=duration_ms
    )


def selection_saved_event(result: SelectionResult) -> EventBody:
    """选型结果保存的检查点事件，带结论、决定方式和被丢弃的依据（它们只在这里留痕）。"""
    return EventBody(
        type=EventType.CHECKPOINT,
        name=Checkpoint.SELECTION_SAVED.value,
        output={
            "reactor_type": None if result.reactor_type is None else result.reactor_type.value,
            "decision": result.decision.value,
            "dropped_evidence": [
                {"feature": quote.label, "text": quote.text} for quote in result.dropped_evidence
            ],
        },
    )


def spec_issues_event(issues: Sequence[Issue], rewrites_used: int) -> EventBody:
    """VALIDATE 没通过：问题清单和已经重写了几轮。"""
    return EventBody(
        type=EventType.VALIDATION,
        name="spec_issues",
        output={
            "rewrites_used": rewrites_used,
            "issues": [
                {
                    "code": issue.code.value,
                    "field_path": issue.field_path,
                    "message": issue.message,
                    "user_fixable": issue.user_fixable,
                }
                for issue in issues
            ],
        },
    )

"""Trace：向 trace.jsonl 追加事件，每行一个 JSON，以及读回。

业务事件只进 Trace，不进 logging。事件模型是计划 §14.1 的子集（没有 run_id 和 skill，
那两项现在没有来源）。
"""

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from pydantic import AwareDatetime, JsonValue

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.base import FrozenModel
from reactor_agent.spec.enums import CheckId, EventType, TaskStatus, WorkflowState
from reactor_agent.spec.loading import parse_model

TRACE_FILE = "trace.jsonl"


class EventBody(FrozenModel):
    """调用方说得出的那部分：发生了什么。时间、序号和所处的状态由 TraceWriter 补上。

    verdict 只有验证事件有：每项检查是否通过。
    """

    type: EventType
    name: str
    attempt: int | None = None
    input: JsonValue = None
    output: JsonValue = None
    verdict: Mapping[CheckId, bool] | None = None
    duration_ms: int | None = None
    error: str | None = None


class TraceEvent(EventBody):
    """trace.jsonl 里的一行。state 是事件发生时的状态；任务到了终态，就是终态。"""

    ts: AwareDatetime
    task_id: str
    seq: int
    state: WorkflowState | TaskStatus
    case: str | None
    spec_hash: str


class TraceWriter:
    """向 runs/<task_id>/trace.jsonl 追加事件。一个 runs 目录一个实例，序号按任务各自计。"""

    def __init__(self, runs_dir: Path) -> None:
        self._runs_dir = runs_dir
        self._next_seq: dict[str, int] = {}

    def append(
        self,
        task_id: str,
        spec_hash: str,
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
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ReactorAgentError(ErrorCode.IO, f"读不了 Trace {path}：{error}") from error
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

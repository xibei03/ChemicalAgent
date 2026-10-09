"""任务状态：一个任务的进展。

TaskState 是全系统唯一一份会被不断更新的数据。只有执行器改它，并且只通过这里的方法，
所以读这个文件就能知道“状态可以怎样变化”。状态文件只存摘要；完整的规格、计划和结果各自
写在 artifacts/ 下的文件里。
"""

from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from reactor_agent.errors import ErrorCode
from reactor_agent.spec.base import FrozenModel
from reactor_agent.spec.enums import (
    RecoveryAction,
    ResultStatus,
    TaskStatus,
    ToolName,
    WorkflowState,
)
from reactor_agent.spec.results import FailureReport
from reactor_agent.spec.selection import SelectionSummary

# 在这些状态里，事件和诊断要带上正在处理的工况名。
PER_CASE_STATES = frozenset({WorkflowState.SOLVE, WorkflowState.VERIFY})
UNKNOWN_VERSION = "未知"
SUCCESS_STATUSES = frozenset({TaskStatus.COMPLETE, TaskStatus.COMPLETE_WITH_WARNINGS})


class StepRecord(FrozenModel):
    """计划里做完的一步：编号、工具、用了几次尝试、对象发生了什么变化。失败的那一步记在错误记录里。"""

    number: int
    tool: ToolName
    attempts: int
    result_status: ResultStatus | None


class Position(FrozenModel):
    """任务现在在哪里：状态、工况序号和已完成的计划步骤。同一位置的失败共用重试次数。"""

    state: WorkflowState
    case_index: int
    cursor: int


class SessionInfo(FrozenModel):
    """HYSYS 会话和当前打开的 Case 文件。"""

    version: str
    process_id: int | None
    case_file: Path | None = None


class CaseSummary(FrozenModel):
    """一个工况的验证摘要：致命和警告级的检查各有几项没通过，以及保存的 .hsc。"""

    name: str
    fatal_failures: int
    warning_failures: int
    case_file: Path | None


class TaskError(FrozenModel):
    """一次失败和执行器的决定。tool 和 arguments 只有工具调用失败时才有。"""

    state: WorkflowState
    tool: str | None
    arguments: str | None
    code: ErrorCode
    message: str
    details: Mapping[str, str]
    action: RecoveryAction


class TaskState(BaseModel):
    """一个任务的进展。重试计数按“位置”算，位置变了就从零开始（见 position）。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    spec_file: Path | None = None
    spec_hash: str | None = None
    case_names: tuple[str, ...] = ()
    selection: SelectionSummary | None = None
    current_state: WorkflowState = WorkflowState.INIT
    status: TaskStatus | None = None
    steps: tuple[StepRecord, ...] = ()
    cursor: int = 0
    session: SessionInfo | None = None
    case_index: int = 0
    retry_position: Position | None = None
    retries_at_position: int = 0
    retries_total: int = 0
    rebuilds: int = 0
    cases: tuple[CaseSummary, ...] = ()
    errors: tuple[TaskError, ...] = ()

    @property
    def position(self) -> Position:
        """任务现在的位置。"""
        return Position(state=self.current_state, case_index=self.case_index, cursor=self.cursor)

    @property
    def current_case_name(self) -> str | None:
        """正在处理的工况名；不在逐工况的状态里是 None。"""
        if self.current_state not in PER_CASE_STATES:
            return None
        return self.case_names[self.case_index]

    @property
    def frozen_spec_hash(self) -> str:
        """冻结的规格的哈希。规格冻结之前（从文字描述开始的任务还在选型）取它是调用顺序的错误。"""
        if self.spec_hash is None:
            raise RuntimeError("规格还没有冻结")
        return self.spec_hash

    @property
    def simulator_version(self) -> str:
        """连接上的仿真软件版本。"""
        return self.session.version if self.session else UNKNOWN_VERSION

    def retries_here(self) -> int:
        """当前位置已经重试了几次。"""
        return self.retries_at_position if self.retry_position == self.position else 0

    def count_retry(self) -> None:
        """记一次重试：当前位置的次数加一，总次数加一。"""
        self.retries_at_position = self.retries_here() + 1
        self.retry_position = self.position
        self.retries_total += 1

    def enter(self, state: WorkflowState) -> None:
        """进入下一个状态。"""
        self.current_state = state

    def finish(self, status: TaskStatus) -> None:
        """任务进入终态。"""
        self.status = status

    def complete_step(
        self, number: int, tool: ToolName, result_status: ResultStatus | None
    ) -> None:
        """记录计划里一步做完了，游标前进到这一步。"""
        record = StepRecord(
            number=number, tool=tool, attempts=self.retries_here() + 1, result_status=result_status
        )
        self.steps = (*self.steps, record)
        self.cursor = number

    def record_selection(self, summary: SelectionSummary) -> None:
        """记录选型的结论：类型和它是怎么定的。完整的结果在 artifacts/selection.json。"""
        self.selection = summary

    def set_session(self, version: str, process_id: int | None) -> None:
        """记录连接上的 HYSYS。"""
        self.session = SessionInfo(version=version, process_id=process_id)

    def set_case_file(self, path: Path) -> None:
        """记录当前打开的 Case 文件（新建或另存之后）。还没有会话就有 Case 文件是调用顺序的错误。"""
        if self.session is None:
            raise RuntimeError("还没有 HYSYS 会话，不能记录 Case 文件")
        self.session = self.session.model_copy(update={"case_file": path})

    def record_case(self, summary: CaseSummary) -> None:
        """记录一个工况的验证摘要；同名的覆盖，位置不变。"""
        if any(item.name == summary.name for item in self.cases):
            self.cases = tuple(summary if i.name == summary.name else i for i in self.cases)
        else:
            self.cases = (*self.cases, summary)

    def next_case(self) -> None:
        """转到下一个工况。"""
        self.case_index += 1

    def record_error(self, error: TaskError) -> None:
        """记一次失败。"""
        self.errors = (*self.errors, error)

    def reset_for_rebuild(self) -> None:
        """干净重建：计划从头执行，已经算完的工况也重算，因为它们属于被丢弃的 Case。"""
        self.rebuilds += 1
        self.steps = ()
        self.cursor = 0
        self.case_index = 0
        self.cases = ()
        self.retry_position = None
        self.retries_at_position = 0
        if self.session is not None:
            self.session = self.session.model_copy(update={"case_file": None})

    def failure_report(self, trace_path: Path, spec_path: Path) -> FailureReport | None:
        """没有完成的任务的诊断，取最后一次失败；任务还在运行、已经完成或没有失败记录是 None。"""
        if self.status is None or self.status in SUCCESS_STATUSES or not self.errors:
            return None
        last = self.errors[-1]
        return FailureReport(
            task_id=self.task_id,
            status=self.status,
            state=last.state,
            tool=last.tool,
            arguments=last.arguments,
            code=last.code,
            message=last.message,
            details=last.details,
            retries=self.retries_total,
            rebuilds=self.rebuilds,
            trace_path=trace_path,
            case_path=self.session.case_file if self.session else None,
            spec_path=spec_path,
        )

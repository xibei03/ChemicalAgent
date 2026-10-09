"""执行器：一个任务从规格走到终态。

每次 step() 只推进一步：按当前状态在 _handlers 里找到处理函数，执行它，得到下一个状态
（或终态），保存。处理函数只做自己这个状态的事，不互相调用，出错一律抛 ReactorAgentError，
由 step() 交给 _recover 按错误码决定重试、重建还是中止。

重试就是留在当前状态：处理函数每次从游标处继续，所以重做的正好是失败的那一步。
终态只由 decide_outcome 给出，这里没有任何直接写入“完成”的路径。
"""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, JsonValue

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.harness.budgets import SOLVE_TIMEOUT_S
from reactor_agent.harness.recovery import decide
from reactor_agent.observability.trace import EventBody, TraceWriter
from reactor_agent.recipes.base import ReactorRecipe
from reactor_agent.spec.components import ComponentTable
from reactor_agent.spec.enums import (
    CaseMode,
    CheckSeverity,
    EventType,
    ReactorType,
    RecoveryAction,
    StepPhase,
    TaskStatus,
    ToolName,
    WorkflowState,
)
from reactor_agent.spec.model_spec import ModelSpec, OperatingCase, spec_hash
from reactor_agent.spec.plan import BuildPlan
from reactor_agent.spec.results import (
    CaseRecord,
    CheckContext,
    NormalizedResult,
    Provenance,
    RunResult,
)
from reactor_agent.spec.snapshot import ModelSnapshot
from reactor_agent.spec.tool_args import (
    CloseCaseArgs,
    ConnectArgs,
    EnsureCaseArgs,
    ReadSnapshotArgs,
    SaveCaseArgs,
    SolveArgs,
)
from reactor_agent.spec.tool_results import CaseData, ConnectData, SaveData, ToolError, ToolResult
from reactor_agent.state.models import CaseSummary, TaskError, TaskState
from reactor_agent.state.store import ArtifactName, StateStore, new_task_id
from reactor_agent.tools.registry import ToolExecutor
from reactor_agent.validation.checks import run_common_checks
from reactor_agent.validation.normalized import assemble_result, decide_outcome

DataT = TypeVar("DataT", bound=BaseModel)
Handler = Callable[[TaskState], WorkflowState | TaskStatus]
MAX_ARGUMENTS_CHARS = 400


@dataclass(frozen=True)
class Dependencies:
    """执行器用到的一切。由装配点（cli）创建，执行器自己不创建任何依赖。"""

    tools: ToolExecutor
    store: StateStore
    trace: TraceWriter
    recipes: Mapping[ReactorType, ReactorRecipe]
    components: ComponentTable


class ToolStepError(ReactorAgentError):
    """一次工具调用失败。比领域错误多带工具名和入参，诊断要用。"""

    def __init__(self, tool: ToolName, args: BaseModel, error: ToolError) -> None:
        super().__init__(error.code, error.message, error.details)
        self.tool = tool.value
        self.arguments = args.model_dump_json()[:MAX_ARGUMENTS_CHARS]


def _data(result: ToolResult, expected: type[DataT]) -> DataT:
    """成功的信封里这个工具自己的数据。类型不对是程序缺陷。"""
    if not isinstance(result.data, expected):
        raise TypeError(f"工具返回的数据应当是 {expected.__name__}，实际是 {result.data!r}")
    return result.data


class Engine:
    """按状态表推进任务。"""

    def __init__(self, deps: Dependencies) -> None:
        self._tools = deps.tools
        self._store = deps.store
        self._trace = deps.trace
        self._recipes = deps.recipes
        self._components = deps.components
        self._handlers: Mapping[WorkflowState, Handler] = {
            WorkflowState.INIT: self._init,
            WorkflowState.PLAN: self._plan,
            WorkflowState.PREFLIGHT: self._preflight,
            WorkflowState.BUILD_BASIS: self._build_basis,
            WorkflowState.BUILD_FLOWSHEET: self._build_flowsheet,
            WorkflowState.SOLVE: self._solve,
            WorkflowState.VERIFY: self._verify,
            WorkflowState.REPORT: self._report,
        }

    # ---- 对外的三样：创建任务、推进一步、反复推进 ----

    def create_task(self, spec: ModelSpec, spec_file: Path) -> TaskState:
        """生成任务标识，建运行目录，冻结规格，写下第一份状态。"""
        task = TaskState(
            task_id=new_task_id(datetime.now().astimezone()),
            spec_file=spec_file,
            spec_hash=spec_hash(spec),
            case_names=tuple(case.name for case in spec.cases),
        )
        self._store.create_run_dir(task.task_id)
        self._store.write_artifact(task.task_id, ArtifactName.MODEL_SPEC, spec)
        self._write_result(task, ())
        self._store.save(task)
        self._emit(task, EventBody(type=EventType.CHECKPOINT, name="spec_frozen"))
        return task

    def step(self, task: TaskState) -> None:
        """推进一步：执行当前状态的处理函数，迁移，保存。"""
        try:
            target = self._handlers[task.current_state](task)
        except ReactorAgentError as error:
            target = self._recover(task, error)
        self._move(task, target)
        self._store.save(task)

    def run(self, task: TaskState, stop_at: WorkflowState | None = None) -> TaskState:
        """反复推进，直到终态，或者到达 stop_at（到达时还没有执行那个状态）。"""
        while task.status is None and task.current_state is not stop_at:
            self.step(task)
        return task

    # ---- 状态的处理函数：返回下一个状态，或者终态 ----

    def _init(self, task: TaskState) -> WorkflowState:
        if spec_hash(self._spec(task)) != task.spec_hash:
            raise ReactorAgentError(ErrorCode.SCHEMA, "运行目录里冻结的规格与记录的哈希不一致")
        return WorkflowState.PLAN

    def _plan(self, task: TaskState) -> WorkflowState | TaskStatus:
        spec = self._spec(task)
        recipe = self._recipes.get(spec.reactor_type)
        if recipe is None:
            unsupported = ReactorAgentError(
                ErrorCode.UNSUPPORTED, f"还不支持 {spec.reactor_type.value} 反应器"
            )
            self._record_error(task, unsupported, RecoveryAction.ABORT)
            return TaskStatus.UNSUPPORTED
        issues = recipe.rules(spec, self._components)
        if issues:
            details = {issue.field_path: issue.message for issue in issues}
            raise ReactorAgentError(ErrorCode.RULE, f"规格有 {len(issues)} 处不合规", details)
        plan = recipe.compile(spec, self._components)
        self._store.write_artifact(task.task_id, ArtifactName.PLAN, plan)
        self._emit(task, EventBody(type=EventType.CHECKPOINT, name="plan_saved"))
        return WorkflowState.PREFLIGHT

    def _preflight(self, task: TaskState) -> WorkflowState:
        connected = _data(self._call(task, ToolName.SESSION_CONNECT, ConnectArgs()), ConnectData)
        task.set_session(connected.version, connected.process_id)
        working_file = self._store.run_dir(task.task_id) / f"working-{task.rebuilds + 1}.hsc"
        args = EnsureCaseArgs(path=working_file, mode=CaseMode.NEW)
        task.set_case_file(_data(self._call(task, ToolName.CASE_ENSURE, args), CaseData).path)
        return WorkflowState.BUILD_BASIS

    def _build_basis(self, task: TaskState) -> WorkflowState:
        self._run_steps(task, StepPhase.BASIS, None)
        return WorkflowState.BUILD_FLOWSHEET

    def _build_flowsheet(self, task: TaskState) -> WorkflowState:
        self._run_steps(task, StepPhase.FLOWSHEET, None)
        return WorkflowState.SOLVE

    def _solve(self, task: TaskState) -> WorkflowState:
        self._run_steps(task, StepPhase.CASE, task.case_names[task.case_index])
        self._call(task, ToolName.SOLVER_SOLVE, SolveArgs(timeout_s=SOLVE_TIMEOUT_S))
        return WorkflowState.VERIFY

    def _verify(self, task: TaskState) -> WorkflowState:
        spec = self._spec(task)
        case = spec.cases[task.case_index]
        read = self._call(task, ToolName.MODEL_READ_SNAPSHOT, ReadSnapshotArgs())
        snapshot = _data(read, ModelSnapshot)
        case_file = self._store.run_dir(task.task_id) / f"{case.name}.hsc"
        saved = _data(self._call(task, ToolName.CASE_SAVE, SaveCaseArgs(path=case_file)), SaveData)
        task.set_case_file(saved.path)
        result = self._assess(task, spec, case, snapshot, saved.path)
        self._record_case(task, result)
        fatal = result.failed(CheckSeverity.FATAL)
        if fatal:
            details = {check.check_id.value: check.message for check in fatal}
            message = f"{case.name}：{len(fatal)} 项致命检查未通过"
            raise ReactorAgentError(ErrorCode.VALIDATION_FATAL, message, details)
        if task.case_index + 1 < len(task.case_names):
            task.next_case()
            return WorkflowState.SOLVE
        return WorkflowState.REPORT

    def _assess(
        self,
        task: TaskState,
        spec: ModelSpec,
        case: OperatingCase,
        snapshot: ModelSnapshot,
        case_file: Path,
    ) -> NormalizedResult:
        """通用检查加这种反应器专有的检查，组装成这个工况的结果。"""
        context = CheckContext(
            spec=spec,
            case=case,
            plan=self._plan_artifact(task),
            components=self._components,
            snapshot=snapshot,
        )
        checks = (*run_common_checks(context), *self._recipes[spec.reactor_type].checks(context))
        provenance = Provenance(
            simulator_version=task.simulator_version,
            case_path=case_file,
            read_at=datetime.now(UTC),
            spec_hash=task.spec_hash,
        )
        return assemble_result(context, checks, provenance)

    def _report(self, task: TaskState) -> TaskStatus:
        cases = self._store.read_artifact(task.task_id, ArtifactName.RESULT, RunResult).cases
        return decide_outcome(task.case_names, cases)

    # ---- 调用工具的唯一入口 ----

    def _call(self, task: TaskState, tool: ToolName, args: BaseModel) -> ToolResult:
        """调用工具并记 Trace。失败时抛 ToolStepError，由 step() 交给 _recover。"""
        result = self._try_call(task, tool, args)
        if result.error is not None:
            raise ToolStepError(tool, args, result.error)
        return result

    def _try_call(self, task: TaskState, tool: ToolName, args: BaseModel) -> ToolResult:
        """调用工具并记 Trace，失败了也只是返回。收尾动作（关 Case、存 Case）用它。"""
        started = time.monotonic()
        result = self._tools.call(tool, args)
        failure = result.error
        body = EventBody(
            type=EventType.TOOL_CALL,
            name=tool.value,
            attempt=task.retries_here() + 1,
            input=args.model_dump(mode="json"),
            output={"ok": result.ok, "status": result.status},
            duration_ms=round((time.monotonic() - started) * 1000),
            error=None if failure is None else f"{failure.code.value}: {failure.message}",
        )
        self._emit(task, body)
        return result

    def _run_steps(self, task: TaskState, phase: StepPhase, case_name: str | None) -> None:
        """执行计划里这个阶段（和工况）尚未完成的步骤；每成功一步就推进游标并保存。"""
        for step in self._plan_artifact(task).steps:
            if step.number > task.cursor and step.phase is phase and step.case_name == case_name:
                result = self._call(task, step.tool, step.args)
                task.complete_step(step.number, step.tool, result.status)
                self._store.save(task)

    # ---- 出错之后 ----

    def _recover(self, task: TaskState, error: ReactorAgentError) -> WorkflowState | TaskStatus:
        """按错误码决定重试、重建或中止，记下来，返回下一个状态。"""
        action = decide(error.code, task.retries_here(), task.rebuilds)
        self._record_error(task, error, action)
        if action is RecoveryAction.RETRY:
            task.count_retry()
            return task.current_state
        if action is RecoveryAction.REBUILD:
            self._rebuild(task)
            return WorkflowState.PREFLIGHT
        if task.session is not None and task.session.case_file is not None:
            self._try_call(task, ToolName.CASE_SAVE, SaveCaseArgs())  # 留下现场，存不了就算了
        return TaskStatus.FAILED

    def _rebuild(self, task: TaskState) -> None:
        """丢弃当前的 Case，计划从头来。关闭失败不拦着：PREFLIGHT 会面对会话的真实状态。"""
        self._try_call(task, ToolName.CASE_CLOSE, CloseCaseArgs(save=False))
        task.reset_for_rebuild()
        self._write_result(task, ())

    # ---- 状态迁移、产物和 Trace ----

    def _move(self, task: TaskState, target: WorkflowState | TaskStatus) -> None:
        if isinstance(target, TaskStatus):
            self._finish(task, target)
        elif target is not task.current_state:
            task.enter(target)
            self._emit(task, EventBody(type=EventType.STATE_TRANSITION, name=target.value))

    def _finish(self, task: TaskState, status: TaskStatus) -> None:
        records = self._store.read_artifact(task.task_id, ArtifactName.RESULT, RunResult).cases
        self._store.write_artifact(
            task.task_id,
            ArtifactName.RESULT,
            RunResult(task_id=task.task_id, status=status, cases=records),
        )
        task.finish(status)
        self._emit(task, EventBody(type=EventType.STATE_TRANSITION, name=status.value))

    def _record_error(
        self, task: TaskState, error: ReactorAgentError, action: RecoveryAction
    ) -> None:
        """记下一次失败和决定：状态里一条错误记录，Trace 里一个错误事件和一个恢复事件。"""
        task.record_error(
            TaskError(
                state=task.current_state,
                tool=error.tool if isinstance(error, ToolStepError) else None,
                arguments=error.arguments if isinstance(error, ToolStepError) else None,
                code=error.code,
                message=error.message,
                details=error.details,
                action=action,
            )
        )
        failure = f"{error.code.value}: {error.message}"
        self._emit(task, EventBody(type=EventType.ERROR, name=error.code.value, error=failure))
        self._emit(task, EventBody(type=EventType.RECOVERY, name=action.value, error=failure))

    def _record_case(self, task: TaskState, result: NormalizedResult) -> None:
        fatal = result.failed(CheckSeverity.FATAL)
        warnings = result.failed(CheckSeverity.WARNING)
        task.record_case(
            CaseSummary(
                name=result.case_name,
                fatal_failures=len(fatal),
                warning_failures=len(warnings),
                case_file=result.provenance.case_path,
            )
        )
        records = self._store.read_artifact(task.task_id, ArtifactName.RESULT, RunResult).cases
        record = CaseRecord(case_name=result.case_name, result=result, case_file_saved=True)
        kept = tuple(r for r in records if r.case_name != result.case_name)
        self._write_result(task, (*kept, record))
        verdict: dict[str, JsonValue] = {c.check_id.value: c.passed for c in result.checks}
        self._emit(
            task, EventBody(type=EventType.VALIDATION, name=result.case_name, output=verdict)
        )
        self._emit(task, EventBody(type=EventType.CHECKPOINT, name="case_saved"))

    def _write_result(self, task: TaskState, cases: tuple[CaseRecord, ...]) -> None:
        run = RunResult(task_id=task.task_id, status=None, cases=cases)
        self._store.write_artifact(task.task_id, ArtifactName.RESULT, run)

    def _emit(self, task: TaskState, body: EventBody) -> None:
        state = task.status.value if task.status else task.current_state.value
        self._trace.append(task.task_id, task.spec_hash, state, task.current_case_name, body)

    def _spec(self, task: TaskState) -> ModelSpec:
        return self._store.read_artifact(task.task_id, ArtifactName.MODEL_SPEC, ModelSpec)

    def _plan_artifact(self, task: TaskState) -> BuildPlan:
        return self._store.read_artifact(task.task_id, ArtifactName.PLAN, BuildPlan)

"""执行器：状态路径、多工况、重试、干净重建、上限、不可恢复的错误、验证失败、不支持、停在指定状态。

工具用 tests/fake_tools.py 的桩，快照复用 1B 手算的正确快照，所以这里不需要 HYSYS。
"""

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from builders import (
    Scenario,
    component_table,
    conversion_scenario,
    equilibrium_scenario,
    gasification_scenario,
)
from fake_tools import FakeTools
from reactor_agent.errors import ErrorCode
from reactor_agent.harness.budgets import MAX_REBUILDS
from reactor_agent.harness.engine import Dependencies, Engine
from reactor_agent.harness.recovery import POLICIES
from reactor_agent.observability.trace import TRACE_FILE, TraceEvent, TraceWriter, read_events
from reactor_agent.recipes import RECIPES
from reactor_agent.spec.enums import (
    Checkpoint,
    CheckSeverity,
    EventType,
    RecoveryAction,
    TaskStatus,
    ToolName,
    WorkflowState,
)
from reactor_agent.spec.plan import BuildPlan
from reactor_agent.spec.results import Issue, RunResult, make_issue
from reactor_agent.state.models import TaskState
from reactor_agent.state.store import ArtifactName, StateStore

BEFORE_THE_CASES = ["PLAN", "PREFLIGHT", "BUILD_BASIS", "BUILD_FLOWSHEET"]
AFTER_THE_CASES = ["REPORT", "complete"]
RETRYABLE = ErrorCode.NOT_FOUND
MAX_RETRIES = POLICIES[RETRYABLE].retries
MAX_CALLS_IN_A_STATE = 2
# 每个场景的全部工况各一份正确的快照（工厂函数，每次现造）。
SCENARIO_SETS: Mapping[str, Callable[[], list[Scenario]]] = {
    "conversion": lambda: [conversion_scenario()],
    "equilibrium": lambda: [equilibrium_scenario("T710"), equilibrium_scenario("T600")],
    "gasification": lambda: [gasification_scenario()],
}


class Run:
    """一次执行：任务、存储和桩。"""

    def __init__(self, task: TaskState, store: StateStore, tools: FakeTools) -> None:
        self.task = task
        self.store = store
        self.tools = tools

    @property
    def events(self) -> list[TraceEvent]:
        return read_events(self.store.run_dir(self.task.task_id) / TRACE_FILE)

    def transitions(self) -> list[str]:
        return [e.name for e in self.events if e.type is EventType.STATE_TRANSITION]

    def result(self) -> RunResult:
        return self.store.read_artifact(self.task.task_id, ArtifactName.RESULT, RunResult)

    def saved_as(self) -> list[Path | None]:
        """case.save 的每次调用写到哪里；None 是原地保存。"""
        return [args.path for args in self.tools.args_of(ToolName.CASE_SAVE)]


def engine_for(
    tmp_path: Path, tools: FakeTools, recipes: Mapping | None = None
) -> tuple[Engine, StateStore]:
    store = StateStore(tmp_path)
    deps = Dependencies(
        tools=tools,
        store=store,
        trace=TraceWriter(tmp_path),
        recipes=RECIPES if recipes is None else recipes,
        components=component_table(),
    )
    return Engine(deps), store


def execute(
    tmp_path: Path,
    scenarios: Sequence[Scenario],
    failures: Mapping[ToolName, Sequence[ErrorCode | None]] | None = None,
    always: Mapping[ToolName, ErrorCode] | None = None,
) -> Run:
    """用这些工况的快照把一个任务跑到终态。"""
    tools = FakeTools([s.snapshot for s in scenarios], failures, always)
    engine, store = engine_for(tmp_path, tools)
    task = engine.create_task(scenarios[0].spec, Path("spec.yaml"))
    engine.run(task)
    return Run(task, store, tools)


def expected_tools(scenario: Scenario) -> list[ToolName]:
    """正常路径上工具被调用的顺序：连接、新建 Case、计划里的建模步骤，然后每个工况。"""
    plan: BuildPlan = scenario.plan
    tools = [ToolName.SESSION_CONNECT, ToolName.CASE_ENSURE]
    tools += [step.tool for step in plan.steps if step.case_name is None]
    for case in scenario.spec.cases:
        tools += [step.tool for step in plan.case_steps(case.name)]
        tools += [ToolName.SOLVER_SOLVE, ToolName.MODEL_READ_SNAPSHOT, ToolName.CASE_SAVE]
    return tools


@pytest.fixture(params=sorted(SCENARIO_SETS))
def scenarios(request: pytest.FixtureRequest) -> list[Scenario]:
    return SCENARIO_SETS[request.param]()


def test_normal_path_calls_tools_in_plan_order_and_completes(scenarios, tmp_path):
    run = execute(tmp_path, scenarios)
    assert run.task.status is TaskStatus.COMPLETE
    assert run.tools.tools_called == expected_tools(scenarios[0])
    per_case = ["SOLVE", "VERIFY"] * len(scenarios[0].spec.cases)
    assert run.transitions() == [*BEFORE_THE_CASES, *per_case, *AFTER_THE_CASES]
    assert run.task.cursor == len(scenarios[0].plan.steps)
    checkpoints = [e.name for e in run.events if e.type is EventType.CHECKPOINT]
    saved_cases = [Checkpoint.CASE_SAVED] * len(scenarios[0].spec.cases)
    assert checkpoints == [
        Checkpoint.SPEC_FROZEN,
        Checkpoint.PLAN_SAVED,
        *saved_cases,
        Checkpoint.RESULT_SAVED,
    ]
    assert run.store.load(run.task.task_id) == run.task


def test_run_directory_holds_state_trace_and_artifacts(conversion, tmp_path):
    run = execute(tmp_path, [conversion])
    directory = run.store.run_dir(run.task.task_id)
    assert (directory / "state.json").is_file()
    assert (directory / TRACE_FILE).is_file()
    for name in ArtifactName:
        assert run.store.artifact_path(run.task.task_id, name).is_file()
    assert not list(directory.rglob("*.tmp"))


def test_the_working_case_is_kept_apart_from_the_case_files_of_the_operating_cases(
    conversion, tmp_path
):
    run = execute(tmp_path, [conversion])
    (created,) = run.tools.args_of(ToolName.CASE_ENSURE)
    assert created.path == run.store.work_dir(run.task.task_id) / "working-1.hsc"
    assert run.saved_as() == [run.store.run_dir(run.task.task_id) / "base.hsc"]


def test_each_operating_case_has_its_own_solve_snapshot_save_and_result(tmp_path):
    scenarios = SCENARIO_SETS["equilibrium"]()
    run = execute(tmp_path, scenarios)
    assert run.task.status is TaskStatus.COMPLETE
    assert [args.value for args in run.tools.args_of(ToolName.FLOWSHEET_SET_SPEC)] == [710, 600]
    assert run.tools.tools_called.count(ToolName.SOLVER_SOLVE) == 2
    assert [path.name for path in run.saved_as()] == ["T710.hsc", "T600.hsc"]
    result = run.result()
    assert [record.case_name for record in result.cases] == ["T710", "T600"]
    assert all(record.case_file_saved and record.result for record in result.cases)
    assert result.status is TaskStatus.COMPLETE
    assert [c.name for c in run.task.cases] == ["T710", "T600"]


def test_a_retryable_failure_is_retried_and_the_task_completes(conversion, tmp_path):
    run = execute(tmp_path, [conversion], failures={ToolName.FLOWSHEET_ENSURE_REACTOR: [RETRYABLE]})
    assert run.task.status is TaskStatus.COMPLETE
    assert len(run.tools.args_of(ToolName.FLOWSHEET_ENSURE_REACTOR)) == 2
    assert run.task.retries_total == 1
    assert run.task.rebuilds == 0
    attempts = {record.tool: record.attempts for record in run.task.steps}
    assert attempts[ToolName.FLOWSHEET_ENSURE_REACTOR] == 2
    assert [e.attempt for e in run.events if e.name == "flowsheet.ensure_reactor"] == [1, 2]


@pytest.mark.parametrize(
    ("tool", "code"),
    [
        (ToolName.SOLVER_SOLVE, ErrorCode.NOT_CONVERGED),
        (ToolName.SOLVER_SOLVE, ErrorCode.TIMEOUT),
        (ToolName.MODEL_READ_SNAPSHOT, ErrorCode.TIMEOUT),
        (ToolName.CASE_SAVE, ErrorCode.IO),
        (ToolName.CASE_ENSURE, ErrorCode.CASE_OPEN),
        (ToolName.SESSION_CONNECT, ErrorCode.CONNECT_FAILED),
    ],
)
def test_a_failure_while_solving_verifying_or_preflighting_is_retried_then_succeeds(
    conversion, tmp_path, tool, code
):
    run = execute(tmp_path, [conversion], failures={tool: [code]})
    assert run.task.status is TaskStatus.COMPLETE
    assert run.task.retries_total == 1
    assert run.task.rebuilds == 0
    assert run.tools.tools_called.count(tool) == expected_tools(conversion).count(tool) + 1


def test_a_failure_after_the_single_retry_goes_on_to_a_rebuild(conversion, tmp_path):
    failures = {ToolName.SOLVER_SOLVE: [ErrorCode.NOT_CONVERGED] * 2}
    run = execute(tmp_path, [conversion], failures=failures)
    assert run.task.status is TaskStatus.COMPLETE
    assert (run.task.retries_total, run.task.rebuilds) == (1, 1)


def test_retries_are_used_up_then_the_case_is_rebuilt_with_a_new_file_name(conversion, tmp_path):
    failures = {ToolName.FLOWSHEET_ENSURE_STREAM: [RETRYABLE] * (MAX_RETRIES + 1)}
    run = execute(tmp_path, [conversion], failures=failures)
    assert run.task.status is TaskStatus.COMPLETE
    assert run.task.rebuilds == 1
    assert run.task.retries_total == MAX_RETRIES
    files = [args.path.name for args in run.tools.args_of(ToolName.CASE_ENSURE)]
    assert files == ["working-1.hsc", "working-2.hsc"]
    closes = run.tools.args_of(ToolName.CASE_CLOSE)
    assert [args.save for args in closes] == [False]
    assert run.tools.tools_called.count(ToolName.BASIS_ENSURE_THERMO) == 2  # 计划从头执行
    recoveries = [e.name for e in run.events if e.type is EventType.RECOVERY]
    assert recoveries == ["retry", "retry", "rebuild"]
    assert run.transitions().count("PREFLIGHT") == 2


def test_the_calls_that_clean_up_are_not_numbered_as_attempts(conversion, tmp_path):
    failures = {ToolName.FLOWSHEET_ENSURE_STREAM: [RETRYABLE] * (MAX_RETRIES + 1)}
    run = execute(tmp_path, [conversion], failures=failures)
    (closing,) = [e for e in run.events if e.name == ToolName.CASE_CLOSE]
    assert closing.attempt is None
    always = {ToolName.FLOWSHEET_ENSURE_STREAM: RETRYABLE}
    aborted = execute(tmp_path / "aborted", [conversion], always=always)
    preserving = [e for e in aborted.events if e.name == ToolName.CASE_SAVE]
    assert [e.attempt for e in preserving] == [None]


def test_a_conflict_rebuilds_without_retrying(conversion, tmp_path):
    failures = {ToolName.FLOWSHEET_ENSURE_STREAM: [ErrorCode.CONFLICT]}
    run = execute(tmp_path, [conversion], failures=failures)
    assert run.task.status is TaskStatus.COMPLETE
    assert run.task.retries_total == 0
    assert run.task.rebuilds == 1


def test_a_failing_close_does_not_stop_a_rebuild(conversion, tmp_path):
    run = execute(
        tmp_path,
        [conversion],
        failures={ToolName.FLOWSHEET_ENSURE_STREAM: [ErrorCode.CONFLICT]},
        always={ToolName.CASE_CLOSE: ErrorCode.IO},
    )
    assert run.task.status is TaskStatus.COMPLETE
    assert run.task.rebuilds == 1


def test_failures_at_different_positions_do_not_add_up_to_a_rebuild(conversion, tmp_path):
    failures = {
        ToolName.FLOWSHEET_ENSURE_STREAM: [RETRYABLE, RETRYABLE],
        ToolName.FLOWSHEET_ENSURE_REACTOR: [RETRYABLE, RETRYABLE],
    }
    run = execute(tmp_path, [conversion], failures=failures)
    assert run.task.status is TaskStatus.COMPLETE
    assert (run.task.retries_total, run.task.rebuilds) == (4, 0)


def test_a_rebuild_in_the_second_case_recomputes_both_cases(tmp_path):
    scenarios = SCENARIO_SETS["equilibrium"]()
    failures = {ToolName.SOLVER_SOLVE: [None, ErrorCode.CONFLICT]}
    run = execute(tmp_path, scenarios, failures=failures)
    assert run.task.status is TaskStatus.COMPLETE
    assert run.task.rebuilds == 1
    assert [record.case_name for record in run.result().cases] == ["T710", "T600"]
    assert [path.name for path in run.saved_as()] == ["T710.hsc", "T710.hsc", "T600.hsc"]


@pytest.mark.parametrize("failing_tool", sorted(set(expected_tools(conversion_scenario()))))
def test_a_persistent_failure_anywhere_ends_failed_after_a_bounded_number_of_calls(
    conversion, tmp_path, failing_tool
):
    normal = expected_tools(conversion)
    run = execute(tmp_path, [conversion], always={failing_tool: RETRYABLE})
    assert run.task.status is TaskStatus.FAILED
    assert run.task.errors[-1].code is RETRYABLE
    assert run.task.errors[-1].action is RecoveryAction.ABORT
    assert run.task.rebuilds == MAX_REBUILDS
    assert run.task.retries_total == MAX_RETRIES * (1 + MAX_REBUILDS)
    # 每一轮：正常路径走一遍，再加上每次重试重做的调用（重试从游标处继续，但一个状态的处理函数
    # 里最多有两个调用，比如 VERIFY 的读快照和另存，重试时都要重做）；重建和中止各有一个收尾的调用
    bound = (len(normal) + MAX_RETRIES * MAX_CALLS_IN_A_STATE) * (1 + MAX_REBUILDS) + 2
    assert len(run.tools.calls) <= bound
    assert run.result().status is TaskStatus.FAILED


def test_an_unrecoverable_error_aborts_at_once_and_keeps_the_case_for_inspection(
    conversion, tmp_path
):
    code = ErrorCode.COMPONENT_NOT_FOUND
    run = execute(tmp_path, [conversion], always={ToolName.BASIS_ENSURE_THERMO: code})
    assert run.task.status is TaskStatus.FAILED
    assert run.tools.tools_called.count(ToolName.BASIS_ENSURE_THERMO) == 1
    assert ToolName.CASE_CLOSE not in run.tools.tools_called
    failed_file = run.store.work_dir(run.task.task_id) / "failed.hsc"
    assert run.saved_as() == [failed_file]  # 另存到专用的文件，不是原地保存
    report = run.task.failure_report(Path("trace.jsonl"), Path("model_spec.json"))
    assert report is not None
    assert (report.code, report.tool) == (code, "basis.ensure_thermo")
    assert report.state is WorkflowState.BUILD_BASIS
    assert "components" in (report.arguments or "")
    assert report.details == {"CRV-100": "under_specified"}
    assert report.case_path == failed_file


def test_aborting_in_a_later_case_never_overwrites_the_file_of_an_earlier_case(tmp_path):
    scenarios = SCENARIO_SETS["equilibrium"]()
    failures = {ToolName.SOLVER_SOLVE: [None, ErrorCode.COM_DISCONNECTED]}
    run = execute(tmp_path, scenarios, failures=failures)
    assert run.task.status is TaskStatus.FAILED
    run_dir = run.store.run_dir(run.task.task_id)
    failed_file = run.store.work_dir(run.task.task_id) / "failed.hsc"
    assert run.saved_as() == [run_dir / "T710.hsc", failed_file]
    first = run.result().cases[0]
    assert first.case_name == "T710" and first.result is not None
    assert first.result.provenance.case_path == run_dir / "T710.hsc"


def test_a_model_that_does_not_solve_is_rebuilt_once_and_then_completes(conversion, tmp_path):
    failures = {ToolName.SOLVER_SOLVE: [ErrorCode.NOT_SOLVED]}
    run = execute(tmp_path, [conversion], failures=failures)
    assert run.task.status is TaskStatus.COMPLETE
    assert (run.task.retries_total, run.task.rebuilds) == (0, 1)  # 不重试，直接重建
    assert run.tools.tools_called.count(ToolName.SOLVER_SOLVE) == 2
    files = [args.path.name for args in run.tools.args_of(ToolName.CASE_ENSURE)]
    assert files == ["working-1.hsc", "working-2.hsc"]
    recoveries = [e.name for e in run.events if e.type is EventType.RECOVERY]
    assert recoveries == ["rebuild"]


def test_a_model_that_still_does_not_solve_after_the_rebuild_aborts_with_the_object_states(
    conversion, tmp_path
):
    run = execute(tmp_path, [conversion], always={ToolName.SOLVER_SOLVE: ErrorCode.NOT_SOLVED})
    assert run.task.status is TaskStatus.FAILED
    assert (run.task.retries_total, run.task.rebuilds) == (0, 1)
    assert run.tools.tools_called.count(ToolName.SOLVER_SOLVE) == 2  # 重建前后各一次
    last = run.task.errors[-1]
    assert (last.code, last.action) == (ErrorCode.NOT_SOLVED, RecoveryAction.ABORT)
    report = run.task.failure_report(Path("trace.jsonl"), Path("model_spec.json"))
    assert report is not None and report.details == {"CRV-100": "under_specified"}


def test_a_failing_save_at_abort_does_not_hide_the_original_error(conversion, tmp_path):
    code = ErrorCode.COMPONENT_NOT_FOUND
    always = {ToolName.BASIS_ENSURE_THERMO: code, ToolName.CASE_SAVE: ErrorCode.IO}
    run = execute(tmp_path, [conversion], always=always)
    assert run.task.status is TaskStatus.FAILED
    assert run.task.errors[-1].code is code
    report = run.task.failure_report(Path("trace.jsonl"), Path("model_spec.json"))
    assert report is not None and report.case_path is not None
    assert report.case_path.name == "working-1.hsc"


def test_a_lost_session_is_not_retried(conversion, tmp_path):
    code = ErrorCode.COM_DISCONNECTED
    run = execute(tmp_path, [conversion], always={ToolName.SOLVER_SOLVE: code})
    assert run.task.status is TaskStatus.FAILED
    assert run.tools.tools_called.count(ToolName.SOLVER_SOLVE) == 1
    assert run.task.errors[-1].code is code


def test_a_fatal_check_failure_never_ends_complete(conversion, tmp_path):
    broken = conversion.with_component("Vap", "Benzene", molar_flow_kmol_h=None)
    run = execute(tmp_path, [broken])
    assert run.task.status is TaskStatus.FAILED
    assert run.task.errors[-1].code is ErrorCode.VALIDATION_FATAL
    assert "V5" in run.task.errors[-1].details
    # 读快照重检一次，然后重建，重建后再读一次，再重检一次：2 次重试机会共 4 次读取
    assert run.tools.tools_called.count(ToolName.MODEL_READ_SNAPSHOT) == 4
    failed = run.result().cases[-1].result
    assert failed is not None and failed.failed(CheckSeverity.FATAL)
    assert run.task.cases[-1].fatal_failures > 0


def test_a_snapshot_that_fails_the_checks_once_is_read_again_and_then_completes(
    conversion, tmp_path
):
    broken = conversion.with_component("Vap", "Benzene", molar_flow_kmol_h=None)
    tools = FakeTools([conversion.snapshot], reads=[broken.snapshot, conversion.snapshot])
    engine, store = engine_for(tmp_path, tools)
    task = engine.create_task(conversion.spec, Path("spec.yaml"))
    engine.run(task)
    assert task.status is TaskStatus.COMPLETE
    assert (task.retries_total, task.rebuilds) == (1, 0)
    assert tools.tools_called.count(ToolName.SOLVER_SOLVE) == 1  # 重试只重读，不重新求解
    assert tools.tools_called.count(ToolName.MODEL_READ_SNAPSHOT) == 2
    events = read_events(store.run_dir(task.task_id) / TRACE_FILE)
    reads = [e for e in events if e.name == ToolName.MODEL_READ_SNAPSHOT]
    assert [e.attempt for e in reads] == [1, 2]
    (record,) = store.read_artifact(task.task_id, ArtifactName.RESULT, RunResult).cases
    assert record.result is not None and not record.result.failed(CheckSeverity.FATAL)


class Rejecting:
    """规则永远不通过的 Recipe。只有 rules 会被调用。"""

    def __init__(self, issues: tuple[Issue, ...]) -> None:
        self._issues = issues

    def rules(self, spec, components) -> tuple[Issue, ...]:
        return self._issues


def reject_with(conversion, tmp_path, *issues: Issue):
    recipes = {conversion.spec.reactor_type: Rejecting(issues)}
    tools = FakeTools([conversion.snapshot])
    engine, _ = engine_for(tmp_path, tools, recipes)
    task = engine.create_task(conversion.spec, Path("spec.yaml"))
    engine.run(task)
    return task, tools


def test_a_rule_failure_stops_before_any_tool_is_called(conversion, tmp_path):
    issue = make_issue(ErrorCode.RULE, "feeds[0]", "进料不合规")
    task, tools = reject_with(conversion, tmp_path, issue)
    assert task.status is TaskStatus.FAILED
    assert tools.calls == []
    assert task.errors[-1].code is ErrorCode.RULE
    assert task.errors[-1].details == {"feeds[0]": "进料不合规"}


def test_every_rule_issue_is_kept_even_when_several_are_about_the_same_field(conversion, tmp_path):
    task, _ = reject_with(
        conversion,
        tmp_path,
        make_issue(ErrorCode.RULE, "components", "缺 CO"),
        make_issue(ErrorCode.RULE, "feeds", "没有水"),
        make_issue(ErrorCode.RULE, "components", "缺氢气"),
    )
    error = task.errors[-1]
    assert "3 处" in error.message
    assert error.details == {"components": "缺 CO；缺氢气", "feeds": "没有水"}


def test_a_rule_that_says_unsupported_ends_unsupported_not_failed(conversion, tmp_path):
    task, tools = reject_with(
        conversion,
        tmp_path,
        make_issue(ErrorCode.RULE, "feeds", "进料不合规"),
        make_issue(ErrorCode.UNSUPPORTED, "reactions", "不支持串联反应"),
    )
    assert task.status is TaskStatus.UNSUPPORTED
    assert task.errors[-1].code is ErrorCode.UNSUPPORTED
    assert tools.calls == []


def test_a_reactor_type_without_a_recipe_is_unsupported_and_calls_nothing(conversion, tmp_path):
    tools = FakeTools([conversion.snapshot])
    engine, store = engine_for(tmp_path, tools, recipes={})
    task = engine.create_task(conversion.spec, Path("spec.yaml"))
    engine.run(task)
    assert task.status is TaskStatus.UNSUPPORTED
    assert tools.calls == []
    assert task.errors[-1].code is ErrorCode.UNSUPPORTED
    assert task.errors[-1].action is RecoveryAction.ABORT
    result = store.read_artifact(task.task_id, ArtifactName.RESULT, RunResult)
    assert result.status is TaskStatus.UNSUPPORTED


def test_a_backend_that_cannot_build_it_ends_unsupported_and_keeps_the_case(conversion, tmp_path):
    always = {ToolName.BASIS_ENSURE_REACTION: ErrorCode.UNSUPPORTED}
    run = execute(tmp_path, [conversion], always=always)
    assert run.task.status is TaskStatus.UNSUPPORTED
    assert run.tools.tools_called.count(ToolName.BASIS_ENSURE_REACTION) == 1
    assert run.saved_as() == [run.store.work_dir(run.task.task_id) / "failed.hsc"]


def test_run_stops_at_the_requested_state_and_can_continue_from_the_saved_file(
    conversion, tmp_path
):
    tools = FakeTools([conversion.snapshot])
    engine, store = engine_for(tmp_path, tools)
    task = engine.create_task(conversion.spec, Path("spec.yaml"))
    engine.run(task, stop_at=WorkflowState.PREFLIGHT)
    assert task.current_state is WorkflowState.PREFLIGHT
    assert task.status is None
    assert tools.calls == []
    reloaded = store.load(task.task_id)
    assert reloaded == task
    engine.run(reloaded)
    assert reloaded.status is TaskStatus.COMPLETE


def test_a_tampered_frozen_spec_is_refused(conversion, tmp_path):
    tools = FakeTools([conversion.snapshot])
    engine, store = engine_for(tmp_path, tools)
    task = engine.create_task(conversion.spec, Path("spec.yaml"))
    path = store.artifact_path(task.task_id, ArtifactName.MODEL_SPEC)
    path.write_text(path.read_text(encoding="utf-8").replace("380.0", "381.0"), encoding="utf-8")
    engine.run(task)
    assert task.status is TaskStatus.FAILED
    assert task.errors[-1].code is ErrorCode.SCHEMA
    assert tools.calls == []


def test_trace_events_are_numbered_in_order_and_carry_the_state(scenarios, tmp_path):
    run = execute(tmp_path, scenarios)
    events = run.events
    assert [e.seq for e in events] == list(range(len(events)))
    calls = [e for e in events if e.type is EventType.TOOL_CALL]
    assert len(calls) == len(run.tools.calls)
    assert {e.state.value for e in calls} == {
        "PREFLIGHT",
        "BUILD_BASIS",
        "BUILD_FLOWSHEET",
        "SOLVE",
        "VERIFY",
    }
    assert all(e.spec_hash == run.task.spec_hash for e in events)


def test_the_verdict_event_records_every_check(conversion, tmp_path):
    run = execute(tmp_path, [conversion])
    (verdict,) = [e for e in run.events if e.type is EventType.VALIDATION]
    assert verdict.verdict is not None and all(verdict.verdict.values())
    assert {check.value for check in verdict.verdict} >= {f"V{n}" for n in range(1, 9)}

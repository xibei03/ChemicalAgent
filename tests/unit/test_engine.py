"""执行器：状态路径、多工况、重试、干净重建、上限、不可恢复的错误、验证失败、不支持、停在指定状态。

工具用 tests/fake_tools.py 的桩，快照复用 1B 手算的正确快照，所以这里不需要 HYSYS。
"""

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from builders import Scenario, component_table, equilibrium_scenario
from fake_tools import FakeTools
from reactor_agent.errors import ErrorCode
from reactor_agent.harness.engine import Dependencies, Engine
from reactor_agent.observability.trace import TRACE_FILE, TraceEvent, TraceWriter, read_events
from reactor_agent.recipes import RECIPES
from reactor_agent.spec.enums import EventType, RecoveryAction, TaskStatus, ToolName, WorkflowState
from reactor_agent.spec.plan import BuildPlan
from reactor_agent.spec.results import Issue, RunResult, make_issue
from reactor_agent.state.models import TaskState
from reactor_agent.state.store import ArtifactName, StateStore

BEFORE_THE_CASES = ["PLAN", "PREFLIGHT", "BUILD_BASIS", "BUILD_FLOWSHEET"]
AFTER_THE_CASES = ["REPORT", "complete"]
RETRYABLE = ErrorCode.NOT_FOUND
MAX_RETRIES = 2
MAX_REBUILDS = 1


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


@pytest.fixture(params=["conversion", "equilibrium", "gasification"])
def scenarios(request: pytest.FixtureRequest) -> list[Scenario]:
    """一个场景的全部工况各一份正确的快照。"""
    first: Scenario = request.getfixturevalue(request.param)
    return (
        [equilibrium_scenario(case.name) for case in first.spec.cases]
        if (request.param == "equilibrium")
        else [first]
    )


def test_normal_path_calls_tools_in_plan_order_and_completes(scenarios, tmp_path):
    run = execute(tmp_path, scenarios)
    assert run.task.status is TaskStatus.COMPLETE
    assert run.tools.tools_called == expected_tools(scenarios[0])
    per_case = ["SOLVE", "VERIFY"] * len(scenarios[0].spec.cases)
    assert run.transitions() == [*BEFORE_THE_CASES, *per_case, *AFTER_THE_CASES]
    assert run.task.cursor == len(scenarios[0].plan.steps)
    checkpoints = [e.name for e in run.events if e.type is EventType.CHECKPOINT]
    saved_cases = ["case_saved"] * len(scenarios[0].spec.cases)
    assert checkpoints == ["spec_frozen", "plan_saved", *saved_cases, "result_saved"]
    assert run.store.load(run.task.task_id) == run.task


def test_run_directory_holds_state_trace_and_artifacts(conversion, tmp_path):
    run = execute(tmp_path, [conversion])
    directory = run.store.run_dir(run.task.task_id)
    assert (directory / "state.json").is_file()
    assert (directory / TRACE_FILE).is_file()
    for name in ArtifactName:
        assert run.store.artifact_path(run.task.task_id, name).is_file()
    assert not list(directory.rglob("*.tmp"))


def test_each_operating_case_has_its_own_solve_snapshot_save_and_result(tmp_path):
    scenarios = [equilibrium_scenario("T710"), equilibrium_scenario("T600")]
    run = execute(tmp_path, scenarios)
    assert run.task.status is TaskStatus.COMPLETE
    assert [args.value for args in run.tools.args_of(ToolName.FLOWSHEET_SET_SPEC)] == [710, 600]
    assert run.tools.tools_called.count(ToolName.SOLVER_SOLVE) == 2
    saves = [args.path.name for args in run.tools.args_of(ToolName.CASE_SAVE)]
    assert saves == ["T710.hsc", "T600.hsc"]
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


def test_a_conflict_rebuilds_without_retrying(conversion, tmp_path):
    run = execute(
        tmp_path, [conversion], failures={ToolName.FLOWSHEET_ENSURE_STREAM: [ErrorCode.CONFLICT]}
    )
    assert run.task.status is TaskStatus.COMPLETE
    assert run.task.retries_total == 0
    assert run.task.rebuilds == 1


def test_a_rebuild_in_the_second_case_recomputes_both_cases(tmp_path):
    scenarios = [equilibrium_scenario("T710"), equilibrium_scenario("T600")]
    failures = {ToolName.SOLVER_SOLVE: [None, ErrorCode.CONFLICT]}
    run = execute(tmp_path, scenarios, failures=failures)
    assert run.task.status is TaskStatus.COMPLETE
    assert run.task.rebuilds == 1
    assert [record.case_name for record in run.result().cases] == ["T710", "T600"]
    saves = [args.path.name for args in run.tools.args_of(ToolName.CASE_SAVE)]
    assert saves == ["T710.hsc", "T710.hsc", "T600.hsc"]


def test_persistent_failure_ends_failed_after_a_bounded_number_of_calls(conversion, tmp_path):
    run = execute(tmp_path, [conversion], always={ToolName.FLOWSHEET_ENSURE_STREAM: RETRYABLE})
    assert run.task.status is TaskStatus.FAILED
    bound = len(conversion.plan.steps) * (1 + MAX_RETRIES) * (1 + MAX_REBUILDS) + 10
    assert len(run.tools.calls) <= bound
    assert run.tools.tools_called.count(ToolName.FLOWSHEET_ENSURE_STREAM) == 2 * (1 + MAX_RETRIES)
    assert (run.task.retries_total, run.task.rebuilds) == (MAX_RETRIES * 2, 1)
    assert run.result().status is TaskStatus.FAILED
    assert run.task.errors[-1].code is RETRYABLE
    assert run.task.errors[-1].action is RecoveryAction.ABORT


def test_an_unrecoverable_error_aborts_at_once_and_keeps_the_case(conversion, tmp_path):
    code = ErrorCode.COMPONENT_NOT_FOUND
    run = execute(tmp_path, [conversion], always={ToolName.BASIS_ENSURE_THERMO: code})
    assert run.task.status is TaskStatus.FAILED
    assert run.tools.tools_called.count(ToolName.BASIS_ENSURE_THERMO) == 1
    assert ToolName.CASE_CLOSE not in run.tools.tools_called
    assert run.tools.tools_called[-1] is ToolName.CASE_SAVE  # 中止时留下现场
    report = run.task.failure_report(Path("trace.jsonl"), Path("model_spec.json"))
    assert report is not None
    assert (report.code, report.tool, report.state) == (
        code,
        "basis.ensure_thermo",
        WorkflowState.BUILD_BASIS,
    )
    assert "components" in (report.arguments or "")
    assert report.details == {"CRV-100": "under_specified"}
    assert report.case_path is not None and report.case_path.name == "working-1.hsc"


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
    assert failed is not None and failed.failed(failed.checks[0].severity)
    assert run.task.cases[-1].fatal_failures > 0


def test_a_flaky_snapshot_that_checks_out_on_reread_completes(conversion, tmp_path):
    broken = conversion.with_component("Vap", "Benzene", molar_flow_kmol_h=None)
    tools = FakeTools([broken.snapshot])
    engine, _ = engine_for(tmp_path, tools)
    task = engine.create_task(conversion.spec, Path("spec.yaml"))
    engine.run(task, stop_at=WorkflowState.VERIFY)
    tools = FakeTools([conversion.snapshot])  # 第二次读到的是好的
    engine, _ = engine_for(tmp_path, tools)
    engine.run(task)
    assert task.status is TaskStatus.COMPLETE


def test_a_rule_failure_stops_before_any_tool_is_called(conversion, tmp_path):
    class Rejecting:
        def rules(self, spec, components) -> tuple[Issue, ...]:
            return (make_issue(ErrorCode.RULE, "feeds[0]", "进料不合规"),)

    recipes = {conversion.spec.reactor_type: Rejecting()}
    tools = FakeTools([conversion.snapshot])
    engine, _ = engine_for(tmp_path, tools, recipes)
    task = engine.create_task(conversion.spec, Path("spec.yaml"))
    engine.run(task)
    assert task.status is TaskStatus.FAILED
    assert tools.calls == []
    assert task.errors[-1].code is ErrorCode.RULE
    assert task.errors[-1].details == {"feeds[0]": "进料不合规"}


def test_a_reactor_type_without_a_recipe_is_unsupported_and_calls_nothing(conversion, tmp_path):
    tools = FakeTools([conversion.snapshot])
    engine, store = engine_for(tmp_path, tools, recipes={})
    task = engine.create_task(conversion.spec, Path("spec.yaml"))
    engine.run(task)
    assert task.status is TaskStatus.UNSUPPORTED
    assert tools.calls == []
    assert task.errors[-1].code is ErrorCode.UNSUPPORTED
    result = store.read_artifact(task.task_id, ArtifactName.RESULT, RunResult)
    assert result.status is TaskStatus.UNSUPPORTED


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
    assert {e.state for e in calls} == {
        "PREFLIGHT",
        "BUILD_BASIS",
        "BUILD_FLOWSHEET",
        "SOLVE",
        "VERIFY",
    }
    assert all(e.spec_hash == run.task.spec_hash for e in events)

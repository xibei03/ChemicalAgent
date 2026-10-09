"""执行器在真实 HYSYS 上的验收（闸门 G1）：三份规格各自跑到完成，连续 3 次一致，没有多余的对象，
干净重建真的发生过。

整个测试会话共用一个 HYSYS 连接（conftest 的 executor）。每次运行结束后，活动的 Case 是最后一个工况
另存的文件，测试用 close_the_case 夹具把它关掉，不保存。
"""

from dataclasses import dataclass
from pathlib import Path

import pytest
from references import REFERENCES, SPEC_NAMES, YIELD_RANGE_PERCENT

from builders import GOLDEN, component_table
from reactor_agent.errors import ErrorCode
from reactor_agent.harness.engine import Dependencies, Engine
from reactor_agent.observability.render import render_timeline
from reactor_agent.observability.trace import TRACE_FILE, TraceWriter, read_events
from reactor_agent.recipes import RECIPES
from reactor_agent.spec.enums import CaseMode, EventType, MetricKind, TaskStatus, ToolName
from reactor_agent.spec.model_spec import ModelSpec, load_model_spec
from reactor_agent.spec.plan import (
    BuildPlan,
    energy_stream_names,
    material_stream_names,
    system_vapour_outlets,
)
from reactor_agent.spec.results import COMMON_CHECK_IDS, RunResult
from reactor_agent.spec.snapshot import ModelSnapshot
from reactor_agent.spec.tool_args import (
    CloseCaseArgs,
    EnsureCaseArgs,
    EnsureReactionArgs,
    EnsureReactionSetArgs,
    EnsureReactorArgs,
    EnsureStreamArgs,
    ReadSnapshotArgs,
)
from reactor_agent.spec.tool_results import ToolResult
from reactor_agent.state.models import TaskState
from reactor_agent.state.store import ArtifactName, StateStore
from reactor_agent.tools.registry import ToolExecutor

pytestmark = pytest.mark.hysys

REPEATS = 3
REPEAT_TOLERANCE = 1e-4
REPEAT_FLOOR = 1e-9
TEMPERATURE_OFFSET_C = 25.0


@dataclass
class Execution:
    """一次真实运行：任务、存储和规格。"""

    task: TaskState
    store: StateStore
    spec: ModelSpec

    def result(self) -> RunResult:
        return self.store.read_artifact(self.task.task_id, ArtifactName.RESULT, RunResult)

    def plan(self) -> BuildPlan:
        return self.store.read_artifact(self.task.task_id, ArtifactName.PLAN, BuildPlan)

    @property
    def run_dir(self) -> Path:
        return self.store.run_dir(self.task.task_id)


def execute(tools: ToolExecutor, name: str, runs_dir: Path) -> Execution:
    spec = load_model_spec(GOLDEN / f"{name}.yaml")
    store = StateStore(runs_dir)
    deps = Dependencies(
        tools=tools,
        store=store,
        trace=TraceWriter(runs_dir),
        recipes=RECIPES,
        components=component_table(),
    )
    engine = Engine(deps)
    task = engine.create_task(spec, GOLDEN / f"{name}.yaml")
    engine.run(task)
    return Execution(task, store, spec)


@pytest.fixture
def close_the_case(executor):
    """测试结束时关闭活动的 Case，不保存；整个会话共用一个 HYSYS 连接。"""
    yield lambda: executor.call(ToolName.CASE_CLOSE, CloseCaseArgs(save=False))
    executor.call(ToolName.CASE_CLOSE, CloseCaseArgs(save=False))


def the_snapshot(executor: ToolExecutor) -> ModelSnapshot:
    result = executor.call(ToolName.MODEL_READ_SNAPSHOT, ReadSnapshotArgs())
    assert result.ok, result.error
    assert isinstance(result.data, ModelSnapshot)
    return result.data


def assert_object_counts_match_the_plan(executor: ToolExecutor, plan: BuildPlan) -> None:
    """Case 里的对象数量与计划一致：没有多余的物流、反应、反应集或反应器。"""
    snapshot = the_snapshot(executor)
    assert sorted(s.name for s in snapshot.streams) == sorted(material_stream_names(plan))
    assert sorted(s.name for s in snapshot.energy_streams) == sorted(energy_stream_names(plan))
    assert sorted(r.name for r in snapshot.reactions) == sorted(
        a.name for a in plan.args_of(EnsureReactionArgs)
    )
    assert sorted(s.name for s in snapshot.reaction_sets) == sorted(
        a.name for a in plan.args_of(EnsureReactionSetArgs)
    )
    assert sorted(r.name for r in snapshot.reactors) == sorted(
        a.name for a in plan.args_of(EnsureReactorArgs)
    )


def assert_the_run_directory_is_complete(execution: Execution) -> None:
    directory = execution.run_dir
    assert (directory / "state.json").is_file()
    assert (directory / TRACE_FILE).stat().st_size > 0
    for name in ArtifactName:
        assert execution.store.artifact_path(execution.task.task_id, name).is_file(), name
    for case in execution.spec.cases:
        saved = directory / f"{case.name}.hsc"
        assert saved.is_file() and saved.stat().st_size > 0, saved


def assert_each_saved_case_holds_its_own_state(
    executor: ToolExecutor, execution: Execution
) -> None:
    """重新打开每个工况另存的 .hsc：已求解，出口温度是这个工况的，不是最后一个工况的。"""
    plan = execution.plan()
    for case in execution.spec.cases:
        executor.call(ToolName.CASE_CLOSE, CloseCaseArgs(save=False))
        path = execution.run_dir / f"{case.name}.hsc"
        opened = executor.call(ToolName.CASE_ENSURE, EnsureCaseArgs(path=path, mode=CaseMode.OPEN))
        assert opened.ok, opened.error
        snapshot = the_snapshot(executor)
        assert snapshot.solve.solved, case.name
        if case.outlet_temperature_c is not None:
            for name in system_vapour_outlets(plan):
                outlet = snapshot.stream(name)
                assert outlet is not None
                assert outlet.temperature_c == pytest.approx(case.outlet_temperature_c, abs=0.1)


def assert_matches_the_references(name: str, execution: Execution) -> None:
    result = execution.result()
    for record in result.cases:
        assert record.result is not None and record.case_file_saved
        checks = {c.check_id: c for c in record.result.checks}
        assert set(COMMON_CHECK_IDS) <= set(checks)
        assert all(c.passed for c in checks.values()), [c.message for c in checks.values()]
        stream_name, fractions, tolerance = REFERENCES[name][record.case_name]
        outlet = next(s for s in record.result.outlets if s.name == stream_name)
        for component in outlet.components:
            if component.name in fractions:
                assert component.mole_fraction == pytest.approx(
                    fractions[component.name], abs=tolerance
                ), (name, record.case_name, component.name)
    if name in YIELD_RANGE_PERCENT:
        low, high = YIELD_RANGE_PERCENT[name]
        metrics = [m for r in result.cases if r.result for m in r.result.metrics]
        yields = [m.value for m in metrics if m.request.kind is MetricKind.YIELD]
        assert yields and all(low <= value <= high for value in yields), yields


def outlet_numbers(execution: Execution) -> dict[tuple[str, str, str], tuple[float, float]]:
    """出料里每个组分的（摩尔分率，摩尔流量），键是（工况，出料，组分）。"""
    numbers = {}
    for record in execution.result().cases:
        assert record.result is not None
        for outlet in record.result.outlets:
            for item in outlet.components:
                key = (record.case_name, outlet.name, item.name)
                numbers[key] = (item.mole_fraction or 0.0, item.molar_flow_kmol_h or 0.0)
    return numbers


@pytest.mark.parametrize("name", SPEC_NAMES)
def test_each_golden_spec_runs_to_complete_three_times_with_the_same_results(
    executor, tmp_path, close_the_case, name
):
    executions = []
    for _ in range(REPEATS):
        execution = execute(executor, name, tmp_path / "runs")
        assert execution.task.status is TaskStatus.COMPLETE, execution.task.errors
        assert_the_run_directory_is_complete(execution)
        assert_matches_the_references(name, execution)
        assert_object_counts_match_the_plan(executor, execution.plan())
        if not executions:
            assert_each_saved_case_holds_its_own_state(executor, execution)
        executions.append(execution)
        close_the_case()
    first = outlet_numbers(executions[0])
    for later in executions[1:]:
        for key, (fraction, flow) in outlet_numbers(later).items():
            expected_fraction, expected_flow = first[key]
            assert fraction == pytest.approx(
                expected_fraction, rel=REPEAT_TOLERANCE, abs=REPEAT_FLOOR
            ), key
            assert flow == pytest.approx(expected_flow, rel=REPEAT_TOLERANCE, abs=REPEAT_FLOOR), key


class ConflictOnce(ToolExecutor):
    """测试专用的包装：在计划第一次创建进料物流之前，先建一股同名但温度不同的，只注入一次。"""

    def __init__(self, inner: ToolExecutor) -> None:
        super().__init__({})
        self._inner = inner
        self.injected = False

    def call(self, name: str, args: object) -> ToolResult:
        if not self.injected and name == ToolName.FLOWSHEET_ENSURE_STREAM:
            assert isinstance(args, EnsureStreamArgs) and args.conditions is not None
            self.injected = True
            warmer = args.conditions.model_copy(
                update={"temperature_c": args.conditions.temperature_c + TEMPERATURE_OFFSET_C}
            )
            planted = self._inner.call(name, args.model_copy(update={"conditions": warmer}))
            assert planted.ok, planted.error
        return self._inner.call(name, args)


def test_a_conflicting_object_triggers_exactly_one_clean_rebuild_and_the_task_still_completes(
    executor, tmp_path, close_the_case
):
    tools = ConflictOnce(executor)
    execution = execute(tools, "toluene_conversion", tmp_path / "runs")
    assert tools.injected
    assert execution.task.status is TaskStatus.COMPLETE, execution.task.errors
    events = read_events(execution.run_dir / TRACE_FILE)
    recoveries = [e for e in events if e.type is EventType.RECOVERY]
    assert [e.name for e in recoveries] == ["rebuild"]
    assert (recoveries[0].error or "").startswith("E_CONFLICT")
    assert execution.task.rebuilds == 1
    case_files = [
        e.input["path"]
        for e in events
        if e.name == ToolName.CASE_ENSURE and isinstance(e.input, dict)
    ]
    assert len(case_files) == 2 and case_files[0] != case_files[1]
    assert_object_counts_match_the_plan(executor, execution.plan())
    assert_the_run_directory_is_complete(execution)
    assert_matches_the_references("toluene_conversion", execution)
    timeline = render_timeline(events)
    assert "rebuild (E_CONFLICT)" in timeline and timeline.rstrip().endswith("complete")


class FailSecondSolve(ToolExecutor):
    """测试专用的包装：第二次求解直接返回 E_NOT_SOLVED（不真的调用），其余照常。"""

    def __init__(self, inner: ToolExecutor) -> None:
        super().__init__({})
        self._inner = inner
        self._solves = 0

    def call(self, name: str, args: object) -> ToolResult:
        if name == ToolName.SOLVER_SOLVE:
            self._solves += 1
            if self._solves == 2:
                return ToolResult.failure(ErrorCode.NOT_SOLVED, "测试注入的失败", {"ERV-100": "x"})
        return self._inner.call(name, args)


def outlet_temperature_in(executor: ToolExecutor, execution: Execution, path: Path) -> float:
    """关掉活动的 Case，重新打开 path，读气相出料的温度。"""
    executor.call(ToolName.CASE_CLOSE, CloseCaseArgs(save=False))
    opened = executor.call(ToolName.CASE_ENSURE, EnsureCaseArgs(path=path, mode=CaseMode.OPEN))
    assert opened.ok, opened.error
    (name,) = system_vapour_outlets(execution.plan())
    outlet = the_snapshot(executor).stream(name)
    assert outlet is not None and outlet.temperature_c is not None
    return outlet.temperature_c


def test_an_abort_in_the_second_case_keeps_the_first_cases_file_and_saves_the_failure_apart(
    executor, tmp_path, close_the_case
):
    execution = execute(FailSecondSolve(executor), "smr_equilibrium", tmp_path / "runs")
    assert execution.task.status is TaskStatus.FAILED
    assert execution.task.errors[-1].code is ErrorCode.NOT_SOLVED
    first, failed = execution.run_dir / "T710.hsc", execution.run_dir / "work" / "failed.hsc"
    assert failed.is_file() and failed.stat().st_size > 0
    report = execution.task.failure_report(execution.run_dir / TRACE_FILE, first)
    assert report is not None and report.case_path == failed
    # 第一个工况的文件还是 710 °C 的状态；现场是第二个工况改了规定、还没解出来的状态（600 °C）
    assert outlet_temperature_in(executor, execution, first) == pytest.approx(710.0, abs=0.1)
    assert outlet_temperature_in(executor, execution, failed) == pytest.approx(600.0, abs=0.1)

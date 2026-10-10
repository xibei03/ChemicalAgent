"""SPECIFY 和 VALIDATE：一次通过、重写后通过、轮数用完（NEEDS_INPUT、FAILED、UNSUPPORTED）、
缺关键信息时不重写直接结束，以及上下文、产物和 Trace 的内容。

LLM 用 tests/fake_llm.py 的桩；Skill、单位表、组分表、Recipe 都是真正在用的，所以这里同时检查了
“Skill 的加载 + 字段说明 + 规范化 + 规则 + 编排”这一整条链。
"""

from pathlib import Path

from fake_llm import FakeLlm
from reactor_agent import cli
from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.harness.budgets import MAX_SPEC_REWRITES
from reactor_agent.observability.trace import TRACE_FILE, read_events
from reactor_agent.spec.enums import (
    CallPoint,
    Checkpoint,
    EventType,
    ReactorType,
    TaskStatus,
    WorkflowState,
)
from reactor_agent.spec.model_spec import ModelSpec, load_model_spec, spec_hash
from reactor_agent.spec.results import SpecIssues
from reactor_agent.spec.selection import FeatureName as F
from reactor_agent.spec.task_spec import ConversionTaskSpec, MissingField, MissingItem
from reactor_agent.state.models import TaskState
from reactor_agent.state.store import ArtifactName, StateStore
from selection_builders import evidence_text, make_draft, make_features
from task_builders import composition, conversion_reaction, conversion_task, feed, q, split

FEATURES = make_features(F.CONVERSION_DATA_GIVEN, F.REACTION_DEFINED)
TEXT = evidence_text(FEATURES) + "。进料 10000 kg/h，380 ℃，2.5 MPa，转化率 50%。"
DRAFT = make_draft(FEATURES, ReactorType.CONVERSION)


def conversion_with(percent: float) -> ConversionTaskSpec:
    isomers = split(1, ("p-xylene", 24), ("m-xylene", 52), ("o-xylene", 24))
    reaction = conversion_reaction(
        (("toluene", 2),), (("benzene", 1),), "toluene", q(percent, "%"), (isomers,)
    )
    return conversion_task(reactions=(reaction,))


def without_flow() -> ConversionTaskSpec:
    """流量没有给、也没有假设：规范化的问题，不是用户的问题，重写能解决。"""
    first = conversion_task().feeds[0].model_copy(update={"flow": None})
    return conversion_task(feeds=(first,))


CHAIN_TEXT = TEXT + "CO、水、CO2、氢气的摩尔比 1:1:1:4。"


def chained() -> ConversionTaskSpec:
    """CO2 既是第一个反应的产物，又是第二个反应的基准：Recipe 说不支持串联的转化反应。"""
    shift = conversion_reaction(
        (("CO", 1), ("water", 1)), (("CO2", 1), ("hydrogen", 1)), "CO", q(50, "%")
    )
    methanation = conversion_reaction(
        (("CO2", 1), ("hydrogen", 4)), (("methane", 1), ("water", 2)), "CO2", q(50, "%")
    )
    mix = composition(("CO", 1.0), ("water", 1.0), ("CO2", 1.0), ("hydrogen", 4.0))
    return conversion_task(
        feeds=(feed(q(380, "℃"), q(10000, "kg/h"), mix),), reactions=(shift, methanation)
    )


class Run:
    def __init__(
        self, tmp_path: Path, replies: list, stop_at: WorkflowState | None, text: str = TEXT
    ) -> None:
        self.llm = FakeLlm(replies)
        built = cli.build_text_run(self.llm, tmp_path)
        self.store: StateStore = built.store
        self.task: TaskState = built.selector.create_task(text)
        built.engine.run(self.task, stop_at=stop_at)

    @property
    def run_dir(self) -> Path:
        return self.store.run_dir(self.task.task_id)

    @property
    def events(self):
        return read_events(self.run_dir / TRACE_FILE)

    def issues(self) -> SpecIssues:
        return self.store.read_artifact(self.task.task_id, ArtifactName.SPEC_ISSUES, SpecIssues)


def specify(tmp_path: Path, *tasks, stop_at=WorkflowState.PREFLIGHT, text: str = TEXT) -> Run:
    return Run(tmp_path, [DRAFT, *tasks], stop_at, text)


# ---- 一次通过 ----


def test_a_valid_task_spec_is_frozen_and_the_task_moves_on_to_the_plan(tmp_path):
    run = specify(tmp_path, conversion_task())
    assert run.task.current_state is WorkflowState.PREFLIGHT and run.task.status is None
    spec = run.store.read_artifact(run.task.task_id, ArtifactName.MODEL_SPEC, ModelSpec)
    assert spec.reactor_type is ReactorType.CONVERSION and spec.feeds[0].pressure_bar == 25.0
    assert run.task.spec_hash and run.task.case_names == ("基准工况",)
    assert run.task.spec_file == run.store.artifact_path(run.task.task_id, ArtifactName.MODEL_SPEC)
    assert run.task.spec_rewrites == 0 and run.llm.calls == 2
    assert (run.run_dir / "artifacts" / "task_spec.json").is_file()
    assert not (run.run_dir / "artifacts" / "spec_issues.json").exists()


def test_the_checkpoints_and_the_llm_call_are_in_the_trace(tmp_path):
    run = specify(tmp_path, conversion_task())
    names = [e.name for e in run.events if e.type is EventType.CHECKPOINT]
    assert names == [
        Checkpoint.INPUT_SAVED,
        Checkpoint.SELECTION_SAVED,
        Checkpoint.TASK_SPEC_SAVED,
        Checkpoint.SPEC_FROZEN,
        Checkpoint.PLAN_SAVED,
    ]
    calls = [e for e in run.events if e.type is EventType.LLM_CALL]
    assert [c.name for c in calls] == [CallPoint.SELECT, CallPoint.SPECIFY]
    assert calls[1].llm is not None and calls[1].llm.skill == "reactor-modeling"
    assert (run.run_dir / "llm" / "specify-1.json").is_file()
    assert run.events[-1].spec_hash == run.task.spec_hash


def test_the_context_has_the_skill_the_type_reference_the_field_guide_and_the_names(tmp_path):
    run = specify(tmp_path, conversion_task())
    system, user = run.llm.requests[1]
    assert "把描述写成 TaskSpec" in system and "转化反应器的建模要点" in system
    assert "平衡反应器的建模要点" not in system and "Gibbs 反应器的建模要点" not in system
    assert "### FeedTask" in system and "原文里的数值，照抄" in system
    assert "| 规范名 | 分子式 |" in system and "| Methane |" in system
    assert TEXT in user and "选型结论（系统已经确定，不能改）：Conversion" in user


# ---- 重写 ----


def test_a_rewrite_gets_the_previous_task_spec_and_the_issues_and_then_passes(tmp_path):
    run = specify(tmp_path, without_flow(), conversion_task())
    assert run.task.current_state is WorkflowState.PREFLIGHT
    assert run.task.spec_rewrites == 1 and run.llm.calls == 3
    _, first_user = run.llm.requests[1]
    _, rewrite_user = run.llm.requests[2]
    assert "你上一次写的 TaskSpec" not in first_user
    assert "你上一次写的 TaskSpec" in rewrite_user and "feeds[0].flow" in rewrite_user
    assert "不要替用户改" in rewrite_user and TEXT in rewrite_user
    issues = [e for e in run.events if e.name == "spec_issues"]
    assert len(issues) == 1 and isinstance(issues[0].output, dict)
    assert issues[0].output["rewrites_used"] == 0
    assert run.issues().rewrites_used == 0 and run.issues().issues[0].field_path == "feeds[0].flow"


def test_the_issue_list_is_saved_for_the_next_round_and_in_the_trace(tmp_path):
    run = specify(tmp_path, without_flow(), conversion_task())
    sent = next(e for e in run.events if e.name == "spec_issues")
    assert sent.state is WorkflowState.VALIDATE


# ---- 轮数用完 ----


def test_problems_that_are_not_the_users_end_in_failed_after_the_rewrites(tmp_path):
    run = specify(tmp_path, *[without_flow()] * (MAX_SPEC_REWRITES + 1))
    assert run.task.status is TaskStatus.FAILED
    assert run.task.spec_rewrites == MAX_SPEC_REWRITES
    assert run.llm.calls == 1 + MAX_SPEC_REWRITES + 1
    assert run.task.errors[-1].code is ErrorCode.RULE
    assert "feeds[0].flow" in run.task.errors[-1].details


def test_problems_in_what_the_user_gave_end_in_needs_input_after_the_rewrites(tmp_path):
    run = specify(tmp_path, *[conversion_with(120.0)] * (MAX_SPEC_REWRITES + 1))
    assert run.task.status is TaskStatus.NEEDS_INPUT
    assert run.llm.calls == 1 + MAX_SPEC_REWRITES + 1
    details = run.task.errors[-1].details
    assert (
        "reactions[0].conversion_percent" in details
        and "120" in details["reactions[0].conversion_percent"]
    )
    assert run.task.current_state is WorkflowState.VALIDATE


def test_something_the_system_cannot_do_ends_in_unsupported(tmp_path):
    run = specify(tmp_path, *[chained()] * (MAX_SPEC_REWRITES + 1), text=CHAIN_TEXT)
    assert run.task.status is TaskStatus.UNSUPPORTED
    assert run.task.errors[-1].code is ErrorCode.UNSUPPORTED


def test_a_second_attempt_that_fixes_the_problem_stops_the_rewriting(tmp_path):
    run = specify(tmp_path, conversion_with(120.0), conversion_with(120.0), conversion_task())
    assert run.task.status is None and run.task.spec_rewrites == 2
    assert run.task.current_state is WorkflowState.PREFLIGHT


# ---- 缺失的关键信息：不重写 ----


def test_declared_missing_key_information_ends_in_needs_input_without_a_rewrite(tmp_path):
    first = conversion_task().feeds[0].model_copy(update={"temperature": None})
    missing = MissingItem(
        field=MissingField.FEED_TEMPERATURE, feed_index=0, description="没有给出进料温度"
    )
    task = conversion_task(feeds=(first,), missing=(missing,))
    run = specify(tmp_path, task)
    assert run.task.status is TaskStatus.NEEDS_INPUT
    assert run.llm.calls == 2 and run.task.spec_rewrites == 0
    assert run.task.errors[-1].details == {
        "feeds[0].temperature_c": "缺少关键信息：没有给出进料温度"
    }


def test_a_declared_missing_flow_does_not_stop_the_task(tmp_path):
    missing = MissingItem(field=MissingField.FEED_FLOW, feed_index=0, description="没有给流量")
    run = specify(tmp_path, conversion_task(missing=(missing,)))
    assert run.task.current_state is WorkflowState.PREFLIGHT


# ---- 出错 ----


def test_an_llm_failure_in_specify_is_recorded_and_ends_the_task(tmp_path):
    run = specify(tmp_path, ReactorAgentError(ErrorCode.LLM, "网络不通"))
    assert run.task.status is TaskStatus.FAILED
    assert (
        run.task.errors[-1].code is ErrorCode.LLM
        and run.task.current_state is WorkflowState.SPECIFY
    )


def test_the_frozen_spec_hash_is_the_hash_of_the_saved_file(tmp_path):
    run = specify(tmp_path, conversion_task())
    assert run.task.spec_file is not None
    assert spec_hash(load_model_spec(run.task.spec_file)) == run.task.spec_hash


def test_a_feed_with_no_pressure_anywhere_is_a_missing_pressure_problem(tmp_path):
    task = conversion_task(
        reactor_pressure=None, feeds=(feed(q(380, "℃"), q(10000, "kg/h"), "toluene"),)
    )
    run = specify(tmp_path, *[task] * (MAX_SPEC_REWRITES + 1))
    assert run.task.status is TaskStatus.NEEDS_INPUT
    assert "feeds[0].pressure_bar" in run.task.errors[-1].details


def test_the_timeline_shows_the_spec_issues_and_the_llm_calls(tmp_path):
    from reactor_agent.observability.render import render_timeline

    run = specify(tmp_path, without_flow(), conversion_task())
    text = render_timeline(run.events)
    assert "规格有 1 个问题（已重写 0 轮）" in text
    assert "LLM specify" in text and "LLM select" in text


def test_a_needs_input_task_prints_what_to_supply_and_not_retries(tmp_path):
    from reactor_agent.observability.render import render_failure

    run = specify(tmp_path, *[conversion_with(120.0)] * (MAX_SPEC_REWRITES + 1))
    report = run.task.failure_report(
        run.run_dir / "trace.jsonl",
        run.store.artifact_path(run.task.task_id, ArtifactName.MODEL_SPEC),
    )
    assert report is not None
    text = render_failure(report)
    assert "需要你补充或确认" in text and "reactions[0].conversion_percent" in text
    assert "重试" not in text and "没有替你改动" in text

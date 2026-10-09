"""SELECT 状态：一致、重问后一致、始终不一致、不是反应过程、选出的类型没有 Recipe 五条路径，
以及依据不是原文、LLM 出错、重问次数的上限、留下的产物和 Trace。

LLM 用 tests/fake_llm.py 的桩，规则表和 Skill 用 skills/ 下真正的那一份，所以这里同时检查了
“Skill 的规则表 + 规则检查 + 编排”这一整条链。
"""

from pathlib import Path

import pytest

from builders import component_table
from fake_llm import COMPLETION_TOKENS, MODEL_NAME, PROMPT_TOKENS, FakeLlm
from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.harness.budgets import MAX_SELECTION_REASKS
from reactor_agent.harness.engine import Dependencies, Engine
from reactor_agent.harness.selection import SELECTION_SKILL, Selector
from reactor_agent.observability.trace import TRACE_FILE, TraceWriter, read_events
from reactor_agent.recipes import RECIPES
from reactor_agent.skill_loader import load_skill
from reactor_agent.spec.enums import (
    Checkpoint,
    EventType,
    ReactorType,
    RecoveryAction,
    TaskStatus,
    WorkflowState,
)
from reactor_agent.spec.selection import Decision, FeedPhase, Flag, SelectionResult
from reactor_agent.spec.selection import FeatureName as F
from reactor_agent.state.models import TaskState
from reactor_agent.state.store import ArtifactName, StateStore
from reactor_agent.tools.registry import ToolExecutor
from selection_builders import evidence_text, make_draft, make_features

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
EQUILIBRIUM, GIBBS, CONVERSION = ReactorType.EQUILIBRIUM, ReactorType.GIBBS, ReactorType.CONVERSION
PFR = ReactorType.PFR


class Run:
    """一次选型：任务、存储和桩。"""

    def __init__(self, task: TaskState, store: StateStore, llm: FakeLlm) -> None:
        self.task = task
        self.store = store
        self.llm = llm

    @property
    def run_dir(self) -> Path:
        return self.store.run_dir(self.task.task_id)

    @property
    def events(self):
        return read_events(self.run_dir / TRACE_FILE)

    def result(self) -> SelectionResult:
        return self.store.read_artifact(self.task.task_id, ArtifactName.SELECTION, SelectionResult)


def select(tmp_path: Path, features, replies, text: str | None = None) -> Run:
    """用这些回复跑到 SELECT 之后停下（SPECIFY 还没有处理函数）。text 默认是特征里的全部依据。"""
    llm = FakeLlm(replies)
    store = StateStore(tmp_path)
    trace = TraceWriter(tmp_path)
    selector = Selector(llm, store, trace, RECIPES, SKILLS_DIR)
    deps = Dependencies(
        tools=ToolExecutor({}),
        store=store,
        trace=trace,
        recipes=RECIPES,
        components=component_table(),
        select=selector.run,
    )
    engine = Engine(deps)
    task = selector.create_task(evidence_text(features) if text is None else text)
    engine.run(task, stop_at=WorkflowState.SPECIFY)
    return Run(task, store, llm)


EQUILIBRIUM_FEATURES = make_features(F.REACTION_DEFINED)


def test_agreement_on_the_first_answer_needs_one_call_and_moves_to_specify(tmp_path):
    run = select(tmp_path, EQUILIBRIUM_FEATURES, [make_draft(EQUILIBRIUM_FEATURES, EQUILIBRIUM)])
    assert run.llm.calls == 1
    assert run.task.status is None and run.task.current_state is WorkflowState.SPECIFY
    assert run.task.selection.reactor_type is EQUILIBRIUM
    assert run.task.selection.decision is Decision.AGREED
    assert run.result().decision is Decision.AGREED


def test_a_disagreement_is_asked_again_once_with_the_feedback_and_then_agrees(tmp_path):
    first = make_draft(EQUILIBRIUM_FEATURES, GIBBS)
    second = make_draft(EQUILIBRIUM_FEATURES, EQUILIBRIUM)
    run = select(tmp_path, EQUILIBRIUM_FEATURES, [first, second])
    assert run.llm.calls == 2
    reask = run.llm.requests[1][1]
    assert "你推荐的是 Gibbs" in reask and "Equilibrium" in reask and "命中第二层第 5 条" in reask
    assert first.model_dump_json() in reask
    assert run.result().decision is Decision.AGREED_AFTER_REASK
    assert run.result().reactor_type is EQUILIBRIUM


def test_a_disagreement_that_survives_the_second_ask_is_resolved_by_the_rules(tmp_path):
    drafts = [make_draft(EQUILIBRIUM_FEATURES, GIBBS)] * 2
    run = select(tmp_path, EQUILIBRIUM_FEATURES, drafts)
    result = run.result()
    assert run.llm.calls == 1 + MAX_SELECTION_REASKS
    assert result.reactor_type is EQUILIBRIUM and result.decision is Decision.RULES_PREVAILED
    assert result.llm_recommendation is GIBBS
    gibbs = next(item for item in result.alternatives if item.reactor_type is GIBBS)
    assert gibbs.recommended_by_llm
    assert run.task.selection.decision is Decision.RULES_PREVAILED
    assert run.task.current_state is WorkflowState.SPECIFY and run.task.status is None


def test_the_rule_side_explanation_matches_the_final_type_even_when_the_llm_is_overruled(tmp_path):
    drafts = [make_draft(EQUILIBRIUM_FEATURES, GIBBS)] * 2
    notes = "\n".join(select(tmp_path, EQUILIBRIUM_FEATURES, drafts).result().rule_notes)
    assert "命中第二层第 5 条" in notes and "选 Equilibrium" in notes and "Gibbs" in notes


def test_there_is_never_a_third_ask(tmp_path):
    drafts = [make_draft(EQUILIBRIUM_FEATURES, GIBBS)] * 3
    run = select(tmp_path, EQUILIBRIUM_FEATURES, drafts)
    assert run.llm.calls == 2 and len(drafts) - run.llm.calls == 1


def test_a_request_that_is_not_a_reaction_ends_unsupported_with_the_selection_saved(tmp_path):
    features = make_features(reaction_process=False)
    run = select(tmp_path, features, [make_draft(features, None)], text="请模拟一座精馏塔")
    assert run.task.status is TaskStatus.UNSUPPORTED
    assert run.result().reactor_type is None and run.result().decision is Decision.AGREED
    assert run.task.errors[-1].code is ErrorCode.UNSUPPORTED
    assert "不是反应过程" in run.task.errors[-1].message
    assert run.task.errors[-1].action is RecoveryAction.ABORT


def test_a_type_without_a_recipe_ends_unsupported_and_names_the_type(tmp_path):
    features = make_features(F.KINETICS_GIVEN, F.DIMENSIONS_GIVEN, phase=FeedPhase.GAS)
    run = select(tmp_path, features, [make_draft(features, PFR)])
    assert run.task.status is TaskStatus.UNSUPPORTED
    assert run.result().reactor_type is PFR and run.task.selection.reactor_type is PFR
    assert "PFR" in run.task.errors[-1].message


def test_the_unsupported_decision_follows_the_recipe_registry_not_a_hard_coded_list(tmp_path):
    features = make_features(F.CONVERSION_DATA_GIVEN)
    llm = FakeLlm([make_draft(features, CONVERSION)])
    store, trace = StateStore(tmp_path), TraceWriter(tmp_path)
    selector = Selector(llm, store, trace, {}, SKILLS_DIR)
    task = selector.create_task(evidence_text(features))
    with pytest.raises(ReactorAgentError) as caught:
        selector.run(task)
    assert caught.value.code is ErrorCode.UNSUPPORTED and "Conversion" in caught.value.message


def test_evidence_that_is_not_in_the_text_triggers_the_ask_and_a_fixed_answer_is_accepted(tmp_path):
    good = make_draft(EQUILIBRIUM_FEATURES, EQUILIBRIUM)
    bad_features = EQUILIBRIUM_FEATURES.model_copy(
        update={"reaction_defined": Flag(value=True, evidence="原文里没有的话")}
    )
    run = select(tmp_path, EQUILIBRIUM_FEATURES, [make_draft(bad_features, EQUILIBRIUM), good])
    assert run.llm.calls == 2
    assert "原文里没有的话" in run.llm.requests[1][1] and "找不到原话" in run.llm.requests[1][1]
    result = run.result()
    assert result.decision is Decision.AGREED_AFTER_REASK and result.dropped_evidence == ()


def test_evidence_that_is_still_not_in_the_text_is_dropped_and_recorded_in_the_trace(tmp_path):
    bad = EQUILIBRIUM_FEATURES.model_copy(
        update={"reaction_defined": Flag(value=True, evidence="原文里没有的话")}
    )
    run = select(tmp_path, EQUILIBRIUM_FEATURES, [make_draft(bad, EQUILIBRIUM)] * 2)
    result = run.result()
    assert result.reactor_type is EQUILIBRIUM and result.decision is Decision.AGREED_AFTER_REASK
    assert result.features.reaction_defined == Flag(value=True, evidence=None)
    assert result.dropped_evidence == ("原文里没有的话",)
    saved = next(e for e in run.events if e.name == Checkpoint.SELECTION_SAVED.value)
    assert saved.output["dropped_evidence"] == ["原文里没有的话"]


def test_the_original_text_is_stored_and_the_prompt_keeps_it_apart_from_the_instructions(tmp_path):
    run = select(tmp_path, EQUILIBRIUM_FEATURES, [make_draft(EQUILIBRIUM_FEATURES, EQUILIBRIUM)])
    text = evidence_text(EQUILIBRIUM_FEATURES)
    assert run.store.read_input(run.task.task_id) == text
    system, user = run.llm.requests[0]
    assert text in user and text not in system


def test_the_calls_leave_full_logs_and_trace_summaries_with_skill_name_and_hash(tmp_path):
    drafts = [
        make_draft(EQUILIBRIUM_FEATURES, GIBBS),
        make_draft(EQUILIBRIUM_FEATURES, EQUILIBRIUM),
    ]
    run = select(tmp_path, EQUILIBRIUM_FEATURES, drafts)
    logs = sorted(path.name for path in (run.run_dir / "llm").iterdir())
    assert logs == ["select-1.json", "select-2.json"]
    skill = load_skill(SKILLS_DIR, SELECTION_SKILL)
    calls = [e for e in run.events if e.type is EventType.LLM_CALL]
    assert len(calls) == 2
    summary = calls[0].llm
    assert (summary.call_point, summary.model) == ("select", MODEL_NAME)
    assert (summary.skill, summary.skill_hash) == (skill.name, skill.content_hash)
    assert (summary.prompt_tokens, summary.completion_tokens) == (PROMPT_TOKENS, COMPLETION_TOKENS)
    assert calls[0].duration_ms == 1500


def test_the_trace_of_a_text_task_has_no_spec_hash_until_a_spec_is_frozen(tmp_path):
    run = select(tmp_path, EQUILIBRIUM_FEATURES, [make_draft(EQUILIBRIUM_FEATURES, EQUILIBRIUM)])
    names = [e.name for e in run.events]
    assert names[0] == Checkpoint.INPUT_SAVED.value
    assert {e.spec_hash for e in run.events} == {None}
    assert run.task.spec_hash is None and run.task.spec_file is None
    with pytest.raises(RuntimeError):
        _ = run.task.frozen_spec_hash


def test_an_llm_failure_ends_failed_without_a_retry_and_without_a_selection(tmp_path):
    error = ReactorAgentError(ErrorCode.LLM, "网络不通")
    run = select(tmp_path, EQUILIBRIUM_FEATURES, [error])
    assert run.task.status is TaskStatus.FAILED and run.llm.calls == 1
    assert run.task.errors[-1].code is ErrorCode.LLM
    assert not run.store.artifact_path(run.task.task_id, ArtifactName.SELECTION).is_file()
    assert run.task.selection is None


def test_the_state_file_of_a_stopped_text_task_can_be_read_back(tmp_path):
    run = select(tmp_path, EQUILIBRIUM_FEATURES, [make_draft(EQUILIBRIUM_FEATURES, EQUILIBRIUM)])
    loaded = run.store.load(run.task.task_id)
    assert loaded == run.task
    assert loaded.current_state is WorkflowState.SPECIFY and loaded.selection is not None

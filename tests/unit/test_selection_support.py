"""选型周边的小件：上下文组装、运行目录里的输入和 LLM 日志、Trace 的 LLM 事件、选型结果的渲染。"""

from datetime import datetime
from pathlib import Path

import pytest

from fake_llm import MODEL_NAME
from reactor_agent.harness.context import SELECTION_REFERENCES, reask_content, selection_prompt
from reactor_agent.observability.render import render_selection, render_timeline
from reactor_agent.observability.trace import (
    EventBody,
    TraceWriter,
    llm_call_event,
    read_events,
    selection_saved_event,
)
from reactor_agent.skill_loader import list_files, load_skill, read_file
from reactor_agent.spec.enums import EventType, ReactorType, WorkflowState
from reactor_agent.spec.llm import LlmAttempt, LlmCallRecord, summarize_call
from reactor_agent.spec.selection import FeatureName as F
from reactor_agent.spec.selection import FeedPhase
from reactor_agent.spec.selection_rules import assess, build_result, reask_feedback
from reactor_agent.state.store import StateStore
from selection_builders import evidence_text, load_rules, make_draft, make_features

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
EQUILIBRIUM, GIBBS = ReactorType.EQUILIBRIUM, ReactorType.GIBBS
FEATURES = make_features(F.REACTION_DEFINED)
TEXT = evidence_text(FEATURES)


def attempt(text: str = "回复", tokens: int = 10) -> LlmAttempt:
    return LlmAttempt(
        user_content="问",
        reply_text=text,
        prompt_tokens=tokens,
        completion_tokens=tokens,
        duration_ms=500,
    )


# ---------- 上下文 ----------


def test_the_prompt_puts_instructions_in_system_and_the_users_text_in_user():
    skill = load_skill(SKILLS_DIR, "reactor-selection")
    prompt = selection_prompt("系统提示正文", skill, "用户的原文")
    assert prompt.system.startswith("系统提示正文")
    assert skill.body in prompt.system
    for name in SELECTION_REFERENCES:
        assert read_file(skill, "references", name) in prompt.system
    for name in list_files(skill, "examples"):
        assert read_file(skill, "examples", name) in prompt.system
    assert "用户的原文" in prompt.user and "用户的原文" not in prompt.system


def test_the_references_are_the_files_the_skill_actually_has():
    skill = load_skill(SKILLS_DIR, "reactor-selection")
    assert set(SELECTION_REFERENCES) == set(list_files(skill, "references"))


def test_the_reask_keeps_the_original_prompt_the_previous_output_and_the_feedback():
    skill = load_skill(SKILLS_DIR, "reactor-selection")
    prompt = selection_prompt("系统", skill, TEXT)
    draft = make_draft(FEATURES, GIBBS)
    feedback = reask_feedback(draft, assess(draft, TEXT, load_rules()))
    content = reask_content(prompt, draft, feedback)
    assert content.startswith(prompt.user) and draft.model_dump_json() in content
    assert feedback in content and "重新核对每个特征" in content


def test_the_feedback_names_both_sides_of_a_disagreement_and_lists_the_rule_steps():
    draft = make_draft(FEATURES, GIBBS)
    feedback = reask_feedback(draft, assess(draft, TEXT, load_rules()))
    assert "你推荐的是 Gibbs" in feedback and "推出的结论是 Equilibrium" in feedback
    assert "命中第二层第 5 条" in feedback


def test_the_feedback_for_a_non_reaction_says_so_in_words():
    draft = make_draft(make_features(reaction_process=False), GIBBS)
    feedback = reask_feedback(draft, assess(draft, "x", load_rules()))
    assert "不是反应过程" in feedback


def test_the_feedback_lists_each_evidence_that_is_not_in_the_text_and_numbers_the_problems():
    draft = make_draft(FEATURES, GIBBS)
    feedback = reask_feedback(draft, assess(draft, "没有依据", load_rules()))
    assert feedback.startswith("1. ") and "\n2. " in feedback
    assert "“原文reaction_defined”" in feedback and "改成“否”" in feedback


# ---------- 运行目录 ----------


def test_the_input_text_round_trips_and_leaves_no_temporary_file(tmp_path):
    store = StateStore(tmp_path)
    task_id = store.new_run(datetime.now().astimezone())
    store.write_input(task_id, "一段描述\n第二行")
    assert store.read_input(task_id) == "一段描述\n第二行"
    assert not list(tmp_path.rglob("*.tmp"))


def test_llm_logs_are_numbered_per_call_point_and_hold_the_full_exchange(tmp_path):
    store = StateStore(tmp_path)
    task_id = store.new_run(datetime.now().astimezone())
    record = LlmCallRecord(model=MODEL_NAME, system_prompt="系统", attempts=(attempt("回复全文"),))
    first = store.write_llm_log(task_id, "select", record)
    second = store.write_llm_log(task_id, "select", record)
    other = store.write_llm_log(task_id, "specify", record)
    assert [p.name for p in (first, second, other)] == [
        "select-1.json",
        "select-2.json",
        "specify-1.json",
    ]
    saved = LlmCallRecord.model_validate_json(first.read_text(encoding="utf-8"))
    assert saved == record and saved.attempts[0].reply_text == "回复全文"


# ---------- Trace 与时间线 ----------


def summary(attempts: int = 1):
    record = LlmCallRecord(model=MODEL_NAME, system_prompt="系统", attempts=(attempt(),) * attempts)
    return summarize_call("select", "reactor-selection", "abc123", record), record


def test_the_summary_adds_up_the_tokens_of_all_attempts():
    call, record = summary(attempts=2)
    assert (call.prompt_tokens, call.completion_tokens, call.attempts) == (20, 20, 2)
    assert record.total_tokens == 40 and record.duration_ms == 1000


def test_an_llm_event_round_trips_through_the_trace_file(tmp_path):
    (tmp_path / "t1").mkdir()
    call, record = summary()
    TraceWriter(tmp_path).append("t1", None, WorkflowState.SELECT, None, llm_call_event(call, 1234))
    [event] = read_events(tmp_path / "t1" / "trace.jsonl")
    assert event.type is EventType.LLM_CALL and event.name == "select"
    assert event.llm == call and event.duration_ms == 1234 and event.spec_hash is None
    assert record.model == event.llm.model


def test_the_timeline_shows_the_llm_call_with_model_tokens_time_and_rerun_count(tmp_path):
    (tmp_path / "t1").mkdir()
    writer = TraceWriter(tmp_path)
    call, _ = summary(attempts=2)
    writer.append("t1", None, WorkflowState.SELECT, None, llm_call_event(call, 2500))
    text = render_timeline(read_events(tmp_path / "t1" / "trace.jsonl"))
    assert "LLM select（stub-model，40 tokens，2.5 秒，校验重问 1 次）" in text
    assert "SELECT" in text and "规格哈希" not in text


def test_the_selection_saved_event_records_type_decision_and_dropped_evidence():
    draft = make_draft(FEATURES, GIBBS)
    result = build_result(draft, "没有依据", assess(draft, "没有依据", load_rules()), reasked=True)
    event = selection_saved_event(result)
    assert isinstance(event, EventBody) and event.name == "selection_saved"
    assert event.output["reactor_type"] == "equilibrium"
    assert event.output["decision"] == "rules_prevailed"
    assert set(event.output["dropped_evidence"]) == {
        "原文reaction_defined",
        "原文is_reaction_process",
    }


# ---------- 渲染 ----------


def settle(features, recommended, text=None, *, reasked=False):
    draft = make_draft(features, recommended, {ReactorType.GIBBS: "Gibbs 优先级更低"})
    body = evidence_text(features) if text is None else text
    return build_result(draft, body, assess(draft, body, load_rules()), reasked=reasked)


def test_an_agreed_selection_shows_conclusion_rule_steps_llm_reason_evidence_and_alternatives():
    text = render_selection(settle(FEATURES, EQUILIBRIUM))
    assert text.startswith("选型结论：Equilibrium（规则的推导与 LLM 的推荐一致）")
    assert "规则的推导：" in text and "LLM 的理由：测试用的理由" in text
    assert "原文依据：" in text and "[反应已明确] “原文reaction_defined”" in text
    assert "备选类型：" in text and "Gibbs（能建）：Gibbs 优先级更低" in text
    assert "PFR（不能建）：缺少必要输入：给出了动力学参数" in text


def test_an_overruled_selection_shows_the_rule_conclusion_and_what_the_llm_said():
    text = render_selection(settle(FEATURES, GIBBS))
    assert text.startswith("选型结论：Equilibrium（规则的推导与 LLM 的推荐不一致，采用规则的结论）")
    assert "LLM 曾推荐 Gibbs（理由：测试用的理由），规则没有采纳。" in text
    assert "LLM 的理由：" not in text


def test_a_selection_after_a_second_ask_says_so():
    text = render_selection(settle(FEATURES, EQUILIBRIUM, reasked=True))
    assert "对照原文重新核对特征之后" in text


def test_a_non_reaction_has_no_alternatives_and_says_no_conclusion():
    features = make_features(reaction_process=False)
    text = render_selection(settle(features, None))
    assert text.startswith("选型结论：无（这不是反应过程的模拟请求）")
    assert "备选类型" not in text and "原文依据" not in text


def test_dropped_evidence_is_listed_at_the_end():
    text = render_selection(settle(FEATURES, EQUILIBRIUM, text="没有依据"))
    assert "已丢弃的依据（在原文里找不到原话）：" in text
    assert text.index("已丢弃的依据") > text.index("备选类型")


def test_a_kinetic_result_mentions_the_missing_size_in_the_rule_steps():
    features = make_features(F.KINETICS_GIVEN, phase=FeedPhase.GAS)
    draft = make_draft(features, ReactorType.PFR)
    result = build_result(
        draft,
        evidence_text(features),
        assess(draft, evidence_text(features), load_rules()),
        reasked=False,
    )
    assert "设备尺寸" in render_selection(result)


@pytest.mark.parametrize("recommended", [EQUILIBRIUM, GIBBS])
def test_the_rendering_never_prints_json_or_enum_reprs(recommended):
    text = render_selection(settle(FEATURES, recommended))
    assert "ReactorType" not in text and "{" not in text and "Decision." not in text

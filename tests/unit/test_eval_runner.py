"""评测运行器：用例能读、单次运行收集得对、汇总和门槛、报告的内容。

LLM 用桩，所以这里测的是评测自己的逻辑，不是模型的表现。
"""

from pathlib import Path

import pytest
import run_evals
from scoring import (
    MAX_WRONG,
    EvalCase,
    RunRecord,
    case_passes,
    feature_matches,
    load_cases,
    render_report,
    summarize,
    type_correct,
)

from fake_llm import FakeLlm
from reactor_agent.cli import SKILLS_DIR
from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.harness.selection import SELECTION_SKILL
from reactor_agent.skill_loader import load_rules, load_skill
from reactor_agent.spec.enums import ReactorType
from reactor_agent.spec.selection import Decision, SelectionResult, SelectionRules
from reactor_agent.spec.selection import FeatureName as F
from selection_builders import cite, make_draft, make_features

CASES_DIR = Path(__file__).resolve().parents[2] / "evals" / "cases"
CASES = {case.id: case for case in load_cases(CASES_DIR)}
EQUILIBRIUM, GIBBS, CONVERSION = ReactorType.EQUILIBRIUM, ReactorType.GIBBS, ReactorType.CONVERSION
RULES = load_rules(load_skill(SKILLS_DIR, SELECTION_SKILL), SelectionRules)


def test_every_case_file_loads_and_scenarios_come_first():
    cases = load_cases(CASES_DIR)
    assert len(cases) == 29
    assert [c.id for c in cases[:3]] == ["L1-S1", "L1-S2", "L1-S3"]
    assert all(c.is_scenario for c in cases[:3]) and not any(c.is_scenario for c in cases[3:])


def test_expected_features_use_only_known_names_and_values(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "id: x\npurpose: p\ninput: i\nexpected:\n  reactor: gibbs\n"
        "  features:\n    nonsense: true\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="nonsense"):
        load_cases(tmp_path)


def test_the_expected_reactor_none_means_no_reactor():
    assert CASES["L1-X5"].expected.reactor is None
    assert CASES["L1-S3"].expected.reactor is GIBBS


def run(case_id: str, replies, tmp_path) -> RunRecord:
    return run_evals.run_one(FakeLlm(replies), CASES[case_id], 1, tmp_path, RULES)


def equilibrium_draft(case_id: str, recommended=EQUILIBRIUM):
    features = cite(make_features(F.REACTION_DEFINED), CASES[case_id].input)
    return make_draft(features, recommended)


def test_a_run_collects_the_final_type_the_first_answer_and_the_usage(tmp_path):
    record = run("L1-E2", [equilibrium_draft("L1-E2")], tmp_path)
    assert record.final_type is EQUILIBRIUM and type_correct(CASES["L1-E2"], record)
    assert record.has_first_answer and record.first_recommendation is EQUILIBRIUM
    assert record.first_rule_type is EQUILIBRIUM
    assert record.tokens == 1200 and not record.reasked and record.error is None
    assert record.selection.decision is Decision.AGREED


def test_a_run_keeps_the_first_answer_even_when_a_second_ask_corrected_it(tmp_path):
    wrong_first = equilibrium_draft("L1-E2", recommended=GIBBS)
    record = run("L1-E2", [wrong_first, equilibrium_draft("L1-E2")], tmp_path)
    assert record.first_recommendation is GIBBS and record.first_rule_type is EQUILIBRIUM
    assert record.final_type is EQUILIBRIUM and record.reasked and record.tokens == 2400
    assert record.selection.decision is Decision.AGREED_AFTER_REASK


def test_a_wrong_llm_answer_the_rules_overrule_counts_as_a_correct_final_type(tmp_path):
    record = run("L1-E2", [equilibrium_draft("L1-E2", GIBBS)] * 2, tmp_path)
    assert record.first_recommendation is GIBBS and record.final_type is EQUILIBRIUM
    assert type_correct(CASES["L1-E2"], record)


def test_a_run_without_a_selection_is_incorrect_and_carries_the_error(tmp_path):
    record = run("L1-E2", [ReactorAgentError(ErrorCode.LLM, "网络不通")], tmp_path)
    assert record.selection is None and not record.has_first_answer
    assert not type_correct(CASES["L1-E2"], record) and record.error == "网络不通"


def test_a_non_reaction_case_is_correct_only_when_no_type_comes_out(tmp_path):
    features = cite(make_features(reaction_process=False), "请模拟")
    record = run("L1-X5", [make_draft(features, None)], tmp_path)
    assert record.final_type is None and type_correct(CASES["L1-X5"], record)


def test_key_features_are_compared_with_the_final_result(tmp_path):
    record = run("L1-E2", [equilibrium_draft("L1-E2")], tmp_path)
    matched, total = feature_matches(CASES["L1-E2"], record)
    assert total == 4 and matched == 3  # 相态抽成了 unknown，其余三个一致


def selection_of(final: ReactorType | None) -> SelectionResult:
    return SelectionResult(
        reactor_type=final,
        decision=Decision.AGREED,
        rule_notes=("说明",),
        llm_recommendation=final,
        llm_rationale="理由",
        features=make_features(),
        alternatives=(),
    )


def record_of(case_id: str, final, repeat: int = 1, first=None) -> RunRecord:
    return RunRecord(
        case_id=case_id,
        repeat=repeat,
        selection=selection_of(final),
        first_recommendation=first,
        first_rule_type=first,
        has_first_answer=True,
        error=None,
        tokens=0,
        seconds=0.0,
        reasked=False,
    )


def all_correct(cases: list[EvalCase]) -> list[RunRecord]:
    return [
        record_of(case.id, case.expected.reactor, repeat)
        for case in cases
        for repeat in range(1, case.repeats + 1)
    ]


def test_the_gate_passes_when_the_scenarios_are_all_right_and_one_other_case_is_wrong():
    cases = list(CASES.values())
    records = [
        record_of("L1-K1", CONVERSION) if r.case_id == "L1-K1" else r for r in all_correct(cases)
    ]
    summary = summarize(cases, records)
    assert summary.gate_passed and summary.other_wrong_cases == MAX_WRONG
    assert summary.scenario_correct == summary.scenario_runs == 15


def test_the_gate_fails_with_two_wrong_other_cases():
    cases = list(CASES.values())
    wrong = {"L1-K1", "L1-K2"}
    records = [
        record_of(r.case_id, CONVERSION) if r.case_id in wrong else r for r in all_correct(cases)
    ]
    summary = summarize(cases, records)
    assert not summary.gate_passed and summary.other_wrong_cases == 2


def test_the_gate_fails_if_a_single_scenario_run_is_wrong():
    cases = list(CASES.values())
    records = all_correct(cases)
    index = next(i for i, r in enumerate(records) if r.case_id == "L1-S3" and r.repeat == 4)
    records[index] = record_of("L1-S3", CONVERSION, repeat=4)
    summary = summarize(cases, records)
    assert not summary.gate_passed and summary.scenario_correct == 14


def test_the_legal_rate_counts_runs_that_reached_a_selection():
    cases = [CASES["L1-E2"], CASES["L1-E3"]]
    broken = record_of("L1-E3", EQUILIBRIUM).model_copy(update={"selection": None})
    summary = summarize(cases, [record_of("L1-E2", EQUILIBRIUM), broken])
    assert summary.legal_rate == 0.5


def test_the_llm_first_accuracy_and_the_final_accuracy_are_reported_separately():
    cases = [CASES["L1-E2"], CASES["L1-E3"]]
    records = [
        record_of("L1-E2", EQUILIBRIUM, first=GIBBS),
        record_of("L1-E3", EQUILIBRIUM, first=EQUILIBRIUM),
    ]
    summary = summarize(cases, records)
    assert summary.llm_first_accuracy == 0.5 and summary.final_accuracy == 1.0


def test_repeat_consistency_counts_cases_whose_runs_all_agree():
    cases = [CASES["L1-S1"]]
    same = [record_of("L1-S1", EQUILIBRIUM, n) for n in range(1, 6)]
    differing = [*same[:4], record_of("L1-S1", GIBBS, 5)]
    assert summarize(cases, same).consistent_cases == 1
    assert summarize(cases, differing).consistent_cases == 0
    assert not case_passes(CASES["L1-S1"], differing)


def test_the_report_has_the_numbers_the_metadata_and_the_wrong_runs():
    cases = [CASES["L1-E2"], CASES["L1-K1"]]
    records = [record_of("L1-E2", EQUILIBRIUM), record_of("L1-K1", GIBBS)]
    report = render_report(cases, records, {"模型": "stub-model", "提交": "abc123"})
    assert "- 模型：stub-model" in report and "- 提交：abc123" in report
    assert "## 汇总：" in report and "LLM 第一次推荐的类型准确率" in report
    assert "| L1-E2 | Equilibrium | ✓Equilibrium |" in report
    assert "| L1-K1 | PFR | ✗Gibbs |" in report and "**未通过**" in report
    assert "### L1-K1（第 1 次）" in report and "期望 PFR，得到 Gibbs" in report

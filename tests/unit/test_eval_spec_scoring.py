"""规格评测的打分：期望参数和黄金规格一致、能发现每一类不一致、假设一一对应、病态输入的判定。

纯函数，不需要 LLM。期望参数读自 evals/cases/ 下真正的用例文件，所以这里也检查了“用例里写的期望
与手写的黄金规格在用户给出的量上一致”。
"""

from pathlib import Path

import pytest
import yaml
from scoring import Expected
from spec_scoring import (
    ExpectedIssue,
    ExpectedParams,
    IssueKey,
    SpecRecord,
    judge_issues,
    missing_assumptions,
    score_params,
)

from builders import golden_spec
from reactor_agent.errors import ErrorCode
from reactor_agent.spec.enums import HeatMode, ReactorType, TaskStatus
from reactor_agent.spec.model_spec import ModelSpec
from reactor_agent.spec.normalize import normalize
from reactor_agent.spec.task_spec import AssumptionField, AssumptionTask, YieldMetricTask
from task_builders import components, conversion_task, gibbs_task, smr_task, units

CASES_DIR = Path(__file__).resolve().parents[2] / "evals" / "cases"


def expected_of(case_id: str) -> Expected:
    data = yaml.safe_load((CASES_DIR / f"{case_id}.yaml").read_text(encoding="utf-8"))
    return Expected.model_validate(data["expected"])


def params_of(case_id: str) -> ExpectedParams:
    params = expected_of(case_id).params
    assert params is not None
    return params


def spec_from(task, reactor_type) -> ModelSpec:
    spec = normalize(task, reactor_type, components(), units()).spec
    assert spec is not None
    return spec


GOLDEN = {"L1-S1": "smr_equilibrium", "L1-S2": "toluene_conversion", "L1-S3": "slurry_gibbs"}


@pytest.mark.parametrize("case_id", sorted(GOLDEN))
def test_the_expected_parameters_in_the_case_files_match_the_hand_written_golden_specs(case_id):
    score = score_params(params_of(case_id), golden_spec(GOLDEN[case_id]))
    assert score.misses == () and score.matched == score.total > 0


def test_the_ideal_task_specs_normalize_to_what_the_case_files_expect():
    split = AssumptionTask(
        field=AssumptionField.REACTIONS, statement="二甲苯按 24:52:24 分配", rationale="平衡分布"
    )
    scenario_1 = spec_from(smr_task(), ReactorType.EQUILIBRIUM)
    scenario_2 = spec_from(conversion_task(assumptions=(split,)), ReactorType.CONVERSION)
    yield_co = YieldMetricTask(product="CO", reference_component="coal")
    scenario_3 = spec_from(gibbs_task(yield_metrics=(yield_co,)), ReactorType.GIBBS)
    for case_id, spec in (("L1-S1", scenario_1), ("L1-S2", scenario_2), ("L1-S3", scenario_3)):
        expected = expected_of(case_id)
        assert expected.params is not None
        assert score_params(expected.params, spec).misses == (), case_id
    assert missing_assumptions(expected_of("L1-S1").assumed, scenario_1) == ()
    assert missing_assumptions(expected_of("L1-S2").assumed, scenario_2) == ()
    # 场景 3 还要登记“没有氧气进料”：理想的 LLM 写一条针对 feeds 的假设
    no_oxygen = AssumptionTask(
        field=AssumptionField.FEEDS, statement="进料里没有氧气", rationale="题面如此"
    )
    proxy = AssumptionTask(
        field=AssumptionField.FEEDS, statement="煤按碳处理", rationale="灰分不考虑"
    )
    with_both = spec_from(
        gibbs_task(yield_metrics=(yield_co,), assumptions=(proxy, no_oxygen)), ReactorType.GIBBS
    )
    assert missing_assumptions(expected_of("L1-S3").assumed, with_both) == ()
    assert missing_assumptions(expected_of("L1-S3").assumed, scenario_3)  # 少了一条


# ---- 能发现每一类不一致 ----


def changed(spec: ModelSpec, edit) -> ModelSpec:
    data = spec.model_dump(mode="json")
    edit(data)
    return ModelSpec.model_validate(data)


def test_a_wrong_temperature_is_a_miss_and_the_rest_still_count():
    wrong = changed(
        golden_spec("smr_equilibrium"), lambda d: d["feeds"][0].update(temperature_c=500.0)
    )
    score = score_params(params_of("L1-S1"), wrong)
    assert score.misses == ("feeds[0].temperature_c",) and score.matched == score.total - 1


def test_the_tolerance_is_relative_one_part_in_a_thousand():
    near = changed(
        golden_spec("smr_equilibrium"), lambda d: d["feeds"][0].update(pressure_bar=13.51)
    )
    assert score_params(params_of("L1-S1"), near).misses == ()
    far = changed(golden_spec("smr_equilibrium"), lambda d: d["feeds"][0].update(pressure_bar=13.6))
    assert "feeds[0].pressure_bar" in score_params(params_of("L1-S1"), far).misses


def test_a_missing_spec_misses_everything():
    score = score_params(params_of("L1-S2"), None)
    assert score.matched == 0 and score.total > 0


def test_isomer_coefficients_are_compared_only_by_their_sum():
    def reshuffle(data):
        coefficients = data["reactions"][0]["stoichiometry"]
        for term in coefficients:
            if term["component"] == "p-Xylene":
                term["coefficient"] = 0.5
            if term["component"] == "m-Xylene":
                term["coefficient"] = 0.3
            if term["component"] == "o-Xylene":
                term["coefficient"] = 0.2

    spec = changed(golden_spec("toluene_conversion"), reshuffle)
    assert score_params(params_of("L1-S2"), spec).misses == ()

    def lose_one(data):
        data["reactions"][0]["stoichiometry"][2]["coefficient"] = 0.1

    lost = changed(golden_spec("toluene_conversion"), lose_one)
    assert any("sum(" in label for label in score_params(params_of("L1-S2"), lost).misses)


def test_reactions_are_matched_by_their_components_not_by_position():
    reversed_order = changed(golden_spec("smr_equilibrium"), lambda d: d["reactions"].reverse())
    assert score_params(params_of("L1-S1"), reversed_order).misses == ()


def test_a_different_heat_mode_or_case_count_is_a_miss():
    spec = golden_spec("smr_equilibrium")
    one_case = changed(spec, lambda d: d["cases"].pop())
    assert "cases 的个数" in score_params(params_of("L1-S1"), one_case).misses
    expected = ExpectedParams(heat_mode=HeatMode.ADIABATIC)
    assert score_params(expected, spec).misses == ("heat_mode",)


# ---- 假设一一对应 ----


def test_every_expected_field_needs_its_own_assumption():
    spec = golden_spec("slurry_gibbs")  # 假设里有 feeds[0].composition、molar_flow、pressure_bar 等
    assert missing_assumptions(["feeds[0].pressure_bar"], spec) == ()
    assert missing_assumptions(["feeds[0].pressure_bar", "feeds[0].pressure_bar"], spec) == (
        "feeds[0].pressure_bar",
    )


def test_a_container_assumption_covers_the_fields_under_it_once():
    spec = golden_spec("slurry_gibbs")
    data = spec.model_dump(mode="json")
    data["assumptions"] = [{"id": "A1", "field_path": "feeds", "value": "x", "reason": "y"}]
    only_container = ModelSpec.model_validate(data)
    assert missing_assumptions(["feeds[0].composition"], only_container) == ()
    assert missing_assumptions(
        ["feeds[0].composition", "feeds[0].pressure_bar"], only_container
    ) == ("feeds[0].pressure_bar",)


# ---- 病态输入 ----


def record(status, paths, first, spec=None) -> SpecRecord:
    return SpecRecord(
        status=status,
        spec=spec,
        rewrites=2,
        first_issues=tuple(IssueKey(code=c, field_path=p) for c, p in first),
        final_paths=tuple(paths),
    )


WANTED = [ExpectedIssue(code=ErrorCode.RULE, field_path="feeds[0].pressure_bar")]
FINAL = [TaskStatus.NEEDS_INPUT]
FIRST = [(ErrorCode.RULE, "feeds[0].pressure_bar")]


def test_a_blocked_input_with_the_right_issue_and_reason_passes():
    verdict = judge_issues(
        WANTED, FINAL, record(TaskStatus.NEEDS_INPUT, ["feeds[0].pressure_bar"], FIRST)
    )
    assert verdict.passed


def test_the_first_issue_list_must_have_the_expected_code_and_field():
    wrong_code = [(ErrorCode.SCHEMA, "feeds[0].pressure_bar")]
    wrong_field = [(ErrorCode.RULE, "feeds[0].temperature_c")]
    for first in (wrong_code, wrong_field, []):
        verdict = judge_issues(
            WANTED, FINAL, record(TaskStatus.NEEDS_INPUT, ["feeds[0].pressure_bar"], first)
        )
        assert not verdict.first_ok and verdict.final_ok


def test_silently_building_a_model_is_a_failure_even_with_the_right_first_issue():
    spec = golden_spec("toluene_conversion")
    verdict = judge_issues(WANTED, FINAL, record(None, [], FIRST, spec))
    assert verdict.first_ok and not verdict.final_ok


def test_the_final_state_and_the_reason_must_match():
    wrong_state = record(TaskStatus.UNSUPPORTED, ["feeds[0].pressure_bar"], FIRST)
    assert not judge_issues(WANTED, FINAL, wrong_state).final_ok
    wrong_reason = record(TaskStatus.NEEDS_INPUT, ["feeds[0].temperature_c"], FIRST)
    assert not judge_issues(WANTED, FINAL, wrong_reason).final_ok


def test_an_empty_expected_field_matches_any_field():
    wanted = [ExpectedIssue(code=ErrorCode.COMPONENT_NOT_FOUND, field_path="")]
    first = [(ErrorCode.COMPONENT_NOT_FOUND, "reactions[0].reactants[0].component")]
    verdict = judge_issues(
        wanted,
        FINAL,
        record(TaskStatus.NEEDS_INPUT, ["reactions[0].reactants[0].component"], first),
    )
    assert verdict.passed


def test_the_pathological_case_files_load_with_their_expected_issues():
    for case_id in ("L1-X1", "L1-X1b", "L1-X2", "L1-X3", "L1-X4"):
        expected = expected_of(case_id)
        assert expected.issues and expected.final == (TaskStatus.NEEDS_INPUT,)
        assert expected.params is None

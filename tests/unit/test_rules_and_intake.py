"""通用业务规则、抄写检查和 intake 的串联：每条规则一个通过和一个不通过的用例。

规格用黄金规格和 TaskSpec 构造函数得到；规则都是纯函数，不需要 HYSYS 和 LLM。
"""

import pytest

from builders import component_table, golden_spec
from reactor_agent.errors import ErrorCode
from reactor_agent.spec.enums import ReactorType
from reactor_agent.spec.intake import intake
from reactor_agent.spec.model_spec import ModelSpec
from reactor_agent.spec.results import Issue, make_issue
from reactor_agent.spec.rules import (
    general_rules,
    reaction_balance_issues,
    undeclared_default_issues,
    volume_flow_issues,
)
from reactor_agent.spec.transcription import numbers_in, transcription_issues
from task_builders import (
    components,
    composition,
    conversion_reaction,
    conversion_task,
    feed,
    gibbs_task,
    pressure,
    q,
    units,
)

TABLE = component_table()
CONVERSION = ReactorType.CONVERSION


def unbalanced_spec() -> ModelSpec:
    data = golden_spec("toluene_conversion").model_dump(mode="json")
    data["assumptions"] = []
    data["reactions"][0]["stoichiometry"][1]["coefficient"] = 2.0
    return ModelSpec.model_validate(data)


# ---- 元素守恒 ----


def test_the_golden_reactions_conserve_every_element():
    for name in ("smr_equilibrium", "toluene_conversion"):
        assert reaction_balance_issues(golden_spec(name), TABLE) == ()


def test_a_reaction_that_does_not_conserve_an_element_is_a_user_fixable_rule_problem():
    (issue,) = reaction_balance_issues(unbalanced_spec(), TABLE)
    assert issue.code is ErrorCode.RULE and issue.user_fixable
    assert issue.field_path == "reactions[0].stoichiometry"
    assert "C 净增" in issue.message and "H 净增" in issue.message


def test_fractional_isomer_coefficients_still_conserve():
    assert reaction_balance_issues(golden_spec("toluene_conversion"), TABLE) == ()


# ---- 默认值都有假设 ----


def test_a_defaulted_field_without_an_assumption_is_an_error():
    spec = golden_spec("toluene_conversion")
    assert undeclared_default_issues(spec, ["pressure_drop_bar", "heat_mode"]) == ()
    (issue,) = undeclared_default_issues(spec, ["feeds[0].mass_flow_kg_h"])
    assert issue.code is ErrorCode.RULE and issue.field_path == "feeds[0].mass_flow_kg_h"


def test_a_field_is_covered_by_an_assumption_on_the_container_that_holds_it():
    spec = golden_spec("slurry_gibbs")
    assert undeclared_default_issues(spec, ["feeds[0].composition"]) == ()


# ---- 气体体积单位用于含固体或液体的进料 ----


def test_a_volume_flow_of_a_slurry_needs_an_ambiguity_assumption():
    spec = golden_spec("slurry_gibbs")  # 黄金规格里有“80000 Nm3/h 按总摩尔流量理解”的假设
    assert volume_flow_issues(spec, TABLE, [0]) == ()
    data = spec.model_dump(mode="json")
    data["assumptions"] = [a for a in data["assumptions"] if a["id"] != "A3-2"]
    (issue,) = volume_flow_issues(ModelSpec.model_validate(data), TABLE, [0])
    assert issue.code is ErrorCode.RULE and issue.field_path == "feeds[0].molar_flow_kmol_h"


def test_a_volume_flow_of_a_gas_needs_no_assumption():
    spec = golden_spec("smr_equilibrium")
    data = spec.model_dump(mode="json")
    data["feeds"][0]["composition"] = [{"component": "CO", "mole_fraction": 1.0}]
    data["assumptions"] = []
    assert volume_flow_issues(ModelSpec.model_validate(data), TABLE, [0]) == ()


def test_general_rules_collects_all_three_kinds():
    spec = unbalanced_spec()
    found = general_rules(spec, TABLE, ["feeds[0].mass_flow_kg_h"], [])
    assert {i.code for i in found} == {ErrorCode.RULE} and len(found) == 2


# ---- 抄写检查 ----


def test_numbers_are_found_after_width_folding_and_thousands_separators():
    found = numbers_in("流量 10,000 kg/h，２.５MPa，转化率50%，C₇H₈")
    assert {10000.0, 2.5, 50.0, 7.0, 8.0} <= set(found)


TEXT = "进料 10000 kg/h，380 ℃，2.5 MPa，转化率 50%。"


def test_a_value_that_is_in_the_text_passes():
    assert transcription_issues(conversion_task(), TEXT) == ()


def test_a_converted_value_is_found_missing():
    task = conversion_task(reactor_pressure=pressure(25.0, "MPa"))  # 25 不在原文里
    (issue,) = transcription_issues(task, TEXT)
    assert issue.code is ErrorCode.SCHEMA and "25" in issue.message
    assert issue.field_path == "reactor_pressure" and not issue.user_fixable


def test_an_assumed_value_is_not_checked_against_the_text():
    task = conversion_task()
    assumed = task.feeds[0].model_copy(update={"flow": q(123456, "kg/h", assumed="自定")})
    assert transcription_issues(task.model_copy(update={"feeds": (assumed,)}), TEXT) == ()


def test_the_check_is_skipped_when_the_text_has_no_arabic_digits():
    assert transcription_issues(conversion_task(), "进料一万公斤每小时，温度三百八十摄氏度") == ()


def test_a_single_component_amount_of_one_is_not_looked_for_in_the_text():
    task = gibbs_task().model_copy(update={})
    mix = composition(("coal", 1.0))
    single = task.feeds[0].model_copy(update={"composition": mix})
    swapped = task.model_copy(update={"feeds": (single,)})
    assert transcription_issues(swapped, "压力 40 bar，40 ℃，1400 度，80000 Nm3/h") == ()


def test_a_remainder_the_llm_computed_itself_is_found_missing():
    mix = composition(("coal", 62.0), ("water", 38.0))
    mixed = gibbs_task().feeds[0].model_copy(update={"composition": mix})
    task = gibbs_task().model_copy(update={"feeds": (mixed,)})
    paths = [i.field_path for i in transcription_issues(task, "浓度 62%，其余是水，40 bar，40 ℃")]
    assert "feeds[0].composition.items[1]" in paths


def test_a_conversion_in_the_reaction_is_checked_too():
    reaction = conversion_reaction((("toluene", 2),), (("benzene", 1),), "toluene", q(55, "%"))
    paths = [
        i.field_path for i in transcription_issues(conversion_task(reactions=(reaction,)), TEXT)
    ]
    assert paths == ["reactions[0].conversion_percent"]


# ---- intake 的串联 ----


def intake_of(task, text=TEXT, rules=lambda _spec: ()):
    return intake(task, text, CONVERSION, (components(), units()), rules)


def test_a_good_task_spec_is_taken_in_and_the_reactor_rules_are_the_last_word():
    taken = intake_of(conversion_task())
    assert taken.spec is not None and taken.issues == ()
    reject: Issue = make_issue(ErrorCode.RULE, "heat_mode", "这种反应器不支持")
    refused = intake_of(conversion_task(), rules=lambda _spec: (reject,))
    assert refused.spec is None and refused.issues == (reject,)


def test_the_reactor_rules_are_not_run_when_an_earlier_step_found_problems():
    calls = []

    def spy(spec):
        calls.append(spec)
        return ()

    bad = conversion_task(feeds=(feed(q(380, "华氏"), q(10000, "kg/h"), "toluene"),))
    taken = intake_of(bad, rules=spy)
    assert taken.spec is None and taken.issues and not calls


def test_transcription_problems_come_first_and_stop_the_later_steps():
    bad = conversion_task(reactor_pressure=pressure(25.0, "MPa"))
    taken = intake_of(bad)
    assert taken.spec is None and taken.issues[0].code is ErrorCode.SCHEMA


@pytest.mark.parametrize("name", ["smr_equilibrium", "slurry_gibbs", "toluene_conversion"])
def test_the_golden_specs_pass_the_general_rules(name):
    spec = golden_spec(name)
    assert general_rules(spec, TABLE, [], []) == ()

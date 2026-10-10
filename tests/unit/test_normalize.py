"""规范化：TaskSpec → ModelSpec 的换算、默认值的登记，和每一类问题。

TaskSpec 用 tests/task_builders.py 里“理想的 LLM 会写出的”那几份，需要时改其中一个字段，所以每个
用例只说明一件事。组分表和单位表读的是 config/ 下真正在用的那两份。
"""

import math

import pytest

from reactor_agent.errors import ErrorCode
from reactor_agent.spec.enums import (
    HeatMode,
    KeqSource,
    PressureBasis,
    PropertyPackage,
    ReactorType,
)
from reactor_agent.spec.model_spec import ModelSpec, is_assumed
from reactor_agent.spec.normalize import Normalized, normalize
from reactor_agent.spec.results import Issue
from reactor_agent.spec.task_spec import (
    AssumptionField,
    AssumptionTask,
    CaseTask,
    ConversionMetricTask,
    MissingField,
    MissingItem,
    Source,
    TaskSpec,
    blocking_missing,
)
from task_builders import (
    components,
    composition,
    conversion_reaction,
    conversion_task,
    equilibrium_reaction,
    equilibrium_task,
    gibbs_task,
    pressure,
    q,
    smr_task,
    split,
    units,
)

CONVERSION, EQUILIBRIUM, GIBBS = ReactorType.CONVERSION, ReactorType.EQUILIBRIUM, ReactorType.GIBBS


def run(task: TaskSpec) -> Normalized:
    kind = {"ConversionTaskSpec": CONVERSION, "EquilibriumTaskSpec": EQUILIBRIUM}.get(
        type(task).__name__, GIBBS
    )
    return normalize(task, kind, components(), units())


def spec_of(task: TaskSpec) -> ModelSpec:
    result = run(task)
    assert result.spec is not None, [i.message for i in result.issues]
    return result.spec


def issues_of(task: TaskSpec) -> tuple[Issue, ...]:
    result = run(task)
    assert result.spec is None and result.issues
    return result.issues


def only_issue(task: TaskSpec) -> Issue:
    (issue,) = issues_of(task)
    return issue


def with_feed(task: TaskSpec, **changes: object) -> TaskSpec:
    first = task.feeds[0].model_copy(update=changes)
    return task.model_copy(update={"feeds": (first, *task.feeds[1:])})


def assumed_paths(spec: ModelSpec) -> set[str]:
    return {item.field_path for item in spec.assumptions}


# ---- 换算 ----


def test_pressure_flow_and_split_products_are_converted_to_canonical_values():
    spec = spec_of(conversion_task())
    feed_spec = spec.feeds[0]
    assert math.isclose(feed_spec.pressure_bar, 25.0)
    assert feed_spec.mass_flow_kg_h == pytest.approx(10000.0)
    assert feed_spec.molar_flow_kmol_h is None
    coefficients = {t.component: t.coefficient for t in spec.reactions[0].stoichiometry}
    assert coefficients["Toluene"] == pytest.approx(-2.0)
    assert coefficients["Benzene"] == pytest.approx(1.0)
    assert math.isclose(coefficients["p-Xylene"], 0.24)
    assert math.isclose(coefficients["m-Xylene"], 0.52)
    assert math.isclose(coefficients["o-Xylene"], 0.24)


def test_a_standard_volume_flow_of_a_slurry_becomes_a_molar_flow_with_a_noted_assumption():
    result = run(gibbs_task())
    spec = result.spec
    assert spec is not None
    feed_spec = spec.feeds[0]
    assert math.isclose(feed_spec.molar_flow_kmol_h or 0, 3569.2, rel_tol=1e-4)
    fractions = {c.component: c.mole_fraction for c in feed_spec.composition}
    assert math.isclose(fractions["Carbon"], 0.7099, abs_tol=1e-4)
    assert math.isclose(fractions["H2O"], 0.2901, abs_tol=1e-4)
    assert result.volume_feeds == (0,) and is_assumed(spec, "feeds[0].molar_flow_kmol_h")


def test_the_candidate_products_join_the_component_table_for_a_gibbs_reactor():
    spec = spec_of(gibbs_task())
    assert spec.components == ("Carbon", "H2O", "CO", "Hydrogen", "CO2", "Methane")
    assert spec.reactor_type is GIBBS and spec.reactions == ()


def test_a_gauge_pressure_is_converted_to_absolute_without_a_basis_assumption():
    gauge = pressure(1.0, "MPa", PressureBasis.GAUGE)
    spec = spec_of(with_feed(conversion_task(reactor_pressure=None), pressure=gauge))
    assert math.isclose(spec.feeds[0].pressure_bar, 11.01325)
    assert not [a for a in spec.assumptions if "绝压" in a.reason]


def test_a_basis_the_unit_carries_wins_over_the_basis_the_llm_filled_in():
    contradicting = pressure(10.0, "barg", PressureBasis.ABSOLUTE)
    spec = spec_of(conversion_task(reactor_pressure=contradicting))
    assert math.isclose(spec.feeds[0].pressure_bar, 11.01325)


def test_an_unstated_basis_is_assumed_once_per_pressure_even_when_the_drop_is_derived():
    task = with_feed(
        conversion_task(reactor_pressure=pressure(15.0, "bar")), pressure=pressure(20.0, "bar")
    )
    spec = spec_of(task)
    basis = [a for a in spec.assumptions if "绝压" in a.reason]
    assert sorted(a.field_path for a in basis) == ["feeds[0].pressure_bar", "pressure_drop_bar"]
    assert len({a.field_path for a in spec.assumptions}) == len(spec.assumptions)


def test_the_lowest_feed_pressure_gives_the_pressure_drop():
    task = conversion_task(reactor_pressure=pressure(10.0, "bar"))
    second = task.feeds[0].model_copy(update={"name": "第二股", "pressure": pressure(30.0, "bar")})
    first = task.feeds[0].model_copy(update={"pressure": pressure(25.0, "bar")})
    spec = spec_of(task.model_copy(update={"feeds": (second, first)}))
    assert math.isclose(spec.pressure_drop_bar, 15.0)


def test_a_feed_below_the_reactor_pressure_is_a_problem_even_when_it_is_not_the_first():
    task = conversion_task(reactor_pressure=pressure(20.0, "bar"))
    high = task.feeds[0].model_copy(update={"pressure": pressure(30.0, "bar")})
    low = task.feeds[0].model_copy(update={"name": "低压", "pressure": pressure(5.0, "bar")})
    issue = only_issue(task.model_copy(update={"feeds": (high, low)}))
    assert issue.field_path == "pressure_drop_bar" and "5 bar" in issue.message


def test_a_reactor_pressure_with_an_unknown_unit_is_reported_on_the_reactor_pressure():
    task = with_feed(
        conversion_task(reactor_pressure=pressure(2.0, "furlong")), pressure=pressure(20.0, "bar")
    )
    issue = only_issue(task)
    assert issue.code is ErrorCode.SCHEMA and issue.field_path == "reactor_pressure"


def test_a_pressure_drop_that_leaves_no_outlet_pressure_is_a_user_fixable_problem():
    issue = only_issue(conversion_task(pressure_drop=q(30.0, "bar")))
    assert issue.code is ErrorCode.RULE and issue.user_fixable
    assert issue.field_path == "pressure_drop_bar" and "出口压力" in issue.message


def test_a_zero_share_isomer_is_left_out_of_the_reaction():
    reaction = conversion_reaction(
        (("toluene", 2),),
        (("benzene", 1),),
        "toluene",
        q(50, "%"),
        (split(1, ("p-xylene", 50), ("m-xylene", 50), ("o-xylene", 0)),),
    )
    spec = spec_of(conversion_task(reactions=(reaction,)))
    coefficients = {t.component: t.coefficient for t in spec.reactions[0].stoichiometry}
    assert "o-Xylene" not in coefficients
    assert math.isclose(coefficients["p-Xylene"], 0.5)
    assert math.isclose(coefficients["m-Xylene"], 0.5)


def test_a_pressure_unit_that_carries_its_own_basis_needs_no_assumption():
    spec = spec_of(conversion_task(reactor_pressure=pressure(10.0, "barg")))
    assert math.isclose(spec.feeds[0].pressure_bar, 11.01325)


def test_a_feed_pressure_and_a_lower_reactor_pressure_give_the_pressure_drop():
    task = with_feed(conversion_task(), pressure=pressure(20.0, "bar"))
    spec = spec_of(task.model_copy(update={"reactor_pressure": pressure(15.0, "bar")}))
    assert math.isclose(spec.feeds[0].pressure_bar, 20.0)
    assert math.isclose(spec.pressure_drop_bar, 5.0)


def test_a_reactor_pressure_above_the_feed_pressure_is_a_user_fixable_problem():
    task = with_feed(conversion_task(), pressure=pressure(10.0, "bar"))
    issue = only_issue(task.model_copy(update={"reactor_pressure": pressure(15.0, "bar")}))
    assert issue.code is ErrorCode.RULE and issue.user_fixable
    assert issue.field_path == "pressure_drop_bar"


def test_a_given_pressure_drop_is_used_and_not_an_assumption():
    spec = spec_of(conversion_task(pressure_drop=q(0.5, "bar")))
    assert math.isclose(spec.pressure_drop_bar, 0.5)
    assert "pressure_drop_bar" not in assumed_paths(spec)


def test_a_given_equilibrium_constant_is_a_fixed_k_reaction():
    reaction = equilibrium_reaction((("CO", 1), ("water", 1)), (("CO2", 1), ("hydrogen", 1)), 4.5)
    spec = spec_of(equilibrium_task(reactions=(reaction,)))
    assert spec.reactions[0].keq_source is KeqSource.FIXED_K
    assert spec.reactions[0].equilibrium_constant == pytest.approx(4.5)


# ---- 默认值都登记成假设 ----

DEFAULTS = {
    "feeds[0].pressure_bar": "压力基准、取操作压力",
    "pressure_drop_bar": "压降",
    "heat_mode": "热模式",
    "property_package": "物性包",
    "reactions[0].keq_source": "Keq 的来源",
}


@pytest.mark.parametrize(
    ("task", "path"),
    [
        (conversion_task(), "feeds[0].pressure_bar"),
        (conversion_task(), "pressure_drop_bar"),
        (conversion_task(), "heat_mode"),
        (conversion_task(), "property_package"),
        (equilibrium_task(), "reactions[0].keq_source"),
    ],
    ids=list(DEFAULTS.values()),
)
def test_every_defaulted_field_has_an_assumption(task, path):
    result = run(task)
    assert result.spec is not None and path in result.defaulted_fields
    assert is_assumed(result.spec, path)


def test_every_field_that_took_a_default_is_assumed_for_all_three_systems():
    for task in (conversion_task(), smr_task(), gibbs_task()):
        result = run(task)
        assert result.spec is not None
        assert all(is_assumed(result.spec, path) for path in result.defaulted_fields)


def test_adiabatic_is_not_an_assumption_when_the_text_says_so():
    spec = spec_of(conversion_task(adiabatic_stated=True))
    assert spec.heat_mode is HeatMode.ADIABATIC and "heat_mode" not in assumed_paths(spec)


def test_an_assumed_flow_and_declared_assumptions_are_registered_with_their_reasons():
    task = smr_task(
        assumptions=(
            AssumptionTask(field=AssumptionField.FEEDS, statement="只有两种原料", rationale="题面"),
        )
    )
    spec = spec_of(task)
    by_path = {a.field_path: a for a in spec.assumptions if a.field_path != "feeds[0].pressure_bar"}
    assert by_path["feeds[0].molar_flow_kmol_h"].reason == "取一个中等规模"
    assert by_path["feeds"].value == "只有两种原料" and by_path["feeds"].reason == "题面"
    ids = [a.id for a in spec.assumptions]
    assert ids == [f"A{n}" for n in range(1, len(ids) + 1)]


def test_the_property_package_defaults_to_peng_robinson_and_the_default_is_an_assumption():
    spec = spec_of(conversion_task())
    assert spec.property_package is PropertyPackage.PENG_ROBINSON
    assert "property_package" in assumed_paths(spec)


@pytest.mark.parametrize(
    "written",
    [
        "Peng-Robinson",
        "peng robinson",
        "Peng–Robinson",  # en dash
        "Peng-Robinson EOS",
        "Peng-Robinson 方程",
        "Peng Robinson equation of state",
        "PR",
        "PR 状态方程",
        "彭罗宾逊",
    ],
)
def test_the_ways_of_writing_peng_robinson_are_the_same_package_and_need_no_assumption(written):
    spec = spec_of(conversion_task(property_package=written))
    assert spec.property_package is PropertyPackage.PENG_ROBINSON
    assert "property_package" not in assumed_paths(spec)


# ---- 问题 ----


def test_an_unknown_unit_is_a_user_fixable_schema_problem_and_is_not_guessed():
    issue = only_issue(with_feed(conversion_task(), temperature=q(380, "华氏")))
    assert issue.code is ErrorCode.SCHEMA and issue.user_fixable
    assert issue.field_path == "feeds[0].temperature_c" and "华氏" in issue.message


def test_an_unknown_component_names_the_closest_candidates():
    issue = only_issue(with_feed(conversion_task(), pure_component="toluen"))
    assert issue.code is ErrorCode.COMPONENT_NOT_FOUND and issue.user_fixable
    assert "Toluene" in issue.message and issue.field_path == "feeds[0].composition.pure_component"


def test_a_component_nothing_like_the_table_lists_what_the_table_has():
    issue = only_issue(with_feed(conversion_task(), pure_component="unobtainium"))
    assert "组分表里有" in issue.message and "Methane" in issue.message


@pytest.mark.parametrize(
    ("task", "path"),
    [
        (with_feed(conversion_task(), temperature=q(380, "℃", assumed="常见值")), "temperature_c"),
        (conversion_task(reactor_pressure=pressure(2.5, "MPa", assumed="常见值")), "pressure_bar"),
        (
            conversion_task(
                reactions=(
                    conversion_reaction(
                        (("toluene", 2),), (("benzene", 1),), "toluene", q(50, "%", assumed="常见")
                    ),
                )
            ),
            "conversion_percent",
        ),
        (
            conversion_task(
                cases=(
                    CaseTask(name="基准", outlet_temperature=q(400, "℃", assumed="x"), duty=None),
                )
            ),
            "outlet_temperature_c",
        ),
    ],
    ids=["进料温度", "压力", "转化率", "出口温度"],
)
def test_filling_a_non_assumable_quantity_as_an_assumption_is_a_problem(task, path):
    issue = only_issue(task)
    assert issue.code is ErrorCode.RULE and issue.user_fixable
    assert issue.field_path.endswith(path) and "不可以假设" in issue.message


def test_an_assumed_composition_is_a_problem():
    mix = composition(("methane", 1.0), ("water", 2.0)).model_copy(
        update={"source": Source.ASSUMED, "rationale": "猜的"}
    )
    issue = only_issue(with_feed(equilibrium_task(), composition=mix, pure_component=None))
    assert issue.code is ErrorCode.RULE and "不可以假设" in issue.message


@pytest.mark.parametrize("percent", [120.0, 0.0, -5.0])
def test_a_conversion_outside_zero_to_one_hundred_is_reported_with_the_given_value(percent):
    reaction = conversion_reaction((("toluene", 2),), (("benzene", 1),), "toluene", q(percent, "%"))
    issue = only_issue(conversion_task(reactions=(reaction,)))
    assert issue.code is ErrorCode.RULE and issue.user_fixable
    assert issue.field_path == "reactions[0].conversion_percent"
    assert f"{percent:g} %" in issue.message


def test_missing_required_values_are_each_a_user_fixable_problem():
    task = with_feed(
        conversion_task(reactor_pressure=None),
        temperature=None,
        composition=None,
        pure_component=None,
    )
    found = {(i.code, i.field_path) for i in issues_of(task) if i.user_fixable}
    assert (ErrorCode.RULE, "feeds[0].temperature_c") in found
    assert (ErrorCode.RULE, "feeds[0].pressure_bar") in found
    assert (ErrorCode.RULE, "feeds[0].composition") in found


def test_a_missing_conversion_is_a_user_fixable_problem():
    reaction = conversion_reaction((("toluene", 2),), (("benzene", 1),), "toluene", None)
    issue = only_issue(conversion_task(reactions=(reaction,)))
    assert issue.field_path == "reactions[0].conversion_percent" and issue.user_fixable


def test_a_missing_flow_is_not_user_fixable_because_it_can_be_assumed():
    issue = only_issue(with_feed(conversion_task(), flow=None))
    assert issue.code is ErrorCode.SCHEMA and not issue.user_fixable
    assert issue.field_path == "feeds[0].flow"


def test_declared_missing_information_is_reported_at_the_field_but_not_a_missing_flow():
    declared = (
        MissingItem(field=MissingField.FEED_TEMPERATURE, feed_index=0, description="没有给温度"),
        MissingItem(field=MissingField.FEED_FLOW, feed_index=0, description="没有给流量"),
    )
    result = run(
        with_feed(conversion_task(), temperature=None).model_copy(update={"missing": declared})
    )
    paths = [i.field_path for i in result.issues]
    assert paths.count("feeds[0].temperature_c") == 1
    assert "没有给温度" in result.issues[0].message and "feeds[0].flow" not in paths


def test_cases_that_are_specified_differently_are_a_schema_problem():
    cases = (
        CaseTask(name="A", outlet_temperature=q(500, "℃"), duty=None),
        CaseTask(name="B", outlet_temperature=None, duty=None),
    )
    issue = only_issue(conversion_task(cases=cases))
    assert issue.code is ErrorCode.SCHEMA and issue.field_path == "cases"


def test_a_case_with_both_an_outlet_temperature_and_a_duty_is_a_schema_problem():
    cases = (CaseTask(name="A", outlet_temperature=q(500, "℃"), duty=q(10, "kW")),)
    assert only_issue(conversion_task(cases=cases)).field_path == "cases"


def test_a_duty_case_gives_the_specified_duty_mode():
    cases = (CaseTask(name="A", outlet_temperature=None, duty=q(2, "MW")),)
    spec = spec_of(conversion_task(cases=cases))
    assert spec.heat_mode is HeatMode.SPECIFIED_DUTY
    assert spec.cases[0].duty_kw == pytest.approx(2000.0)


@pytest.mark.parametrize("written", ["SRK", "Soave-Redlich-Kwong", "PRSV", "NRTL"])
def test_an_unsupported_property_package_is_reported_for_the_user_to_confirm(written):
    issue = only_issue(conversion_task(property_package=written))
    assert issue.code is ErrorCode.RULE and issue.user_fixable
    assert issue.field_path == "property_package" and written in issue.message


def test_adiabatic_stated_together_with_an_outlet_temperature_is_a_conflict_not_a_guess():
    cases = (CaseTask(name="A", outlet_temperature=q(500, "℃"), duty=None),)
    issue = only_issue(conversion_task(adiabatic_stated=True, cases=cases))
    assert issue.code is ErrorCode.SCHEMA and issue.field_path == "cases"
    assert "绝热" in issue.message


def test_no_feeds_and_no_reactions_are_problems():
    paths = {i.field_path for i in issues_of(conversion_task(feeds=(), reactions=()))}
    assert {"feeds", "reactions"} <= paths


def test_a_non_positive_coefficient_is_a_schema_problem():
    reaction = conversion_reaction((("toluene", -2),), (("benzene", 1),), "toluene", q(50, "%"))
    issue = only_issue(conversion_task(reactions=(reaction,)))
    assert issue.code is ErrorCode.SCHEMA and "reactants[0].coefficient" in issue.field_path


def test_modelspec_validation_errors_become_issues_instead_of_exceptions():
    cases = (CaseTask(name="T:700", outlet_temperature=q(700, "℃"), duty=None),)
    issue = only_issue(conversion_task(cases=cases))
    assert issue.code is ErrorCode.SCHEMA and issue.field_path.startswith("cases[0]")


def test_a_metric_on_a_component_that_is_not_in_the_system_is_reported():
    task = conversion_task(conversion_metrics=(ConversionMetricTask(component="CO"),))
    issue = only_issue(task)
    assert issue.field_path.startswith("metrics[0]") and "不在 components" in issue.message


def test_every_unknown_component_in_the_metrics_is_reported_on_its_own_path():
    metrics = (
        ConversionMetricTask(component="unobtainium"),
        ConversionMetricTask(component="toluene"),
        ConversionMetricTask(component="mystery"),
    )
    found = issues_of(conversion_task(conversion_metrics=metrics))
    paths = [i.field_path for i in found if i.code is ErrorCode.COMPONENT_NOT_FOUND]
    assert paths == ["conversion_metrics[0].component", "conversion_metrics[2].component"]


def test_reactor_type_comes_from_the_caller_and_the_spec_carries_it():
    for task, kind in ((conversion_task(), CONVERSION), (smr_task(), EQUILIBRIUM)):
        spec = normalize(task, kind, components(), units()).spec
        assert spec is not None and spec.reactor_type is kind


# ---- 声明缺失，字段却已经填了：自相矛盾，不当作要用户补充的信息 ----


def declared(field: MissingField) -> tuple[MissingItem, ...]:
    return (MissingItem(field=field, feed_index=0, description="声明缺失"),)


def no_conversion() -> TaskSpec:
    reaction = conversion_reaction((("toluene", 2),), (("benzene", 1),), "toluene", None)
    return conversion_task(reactions=(reaction,))


ABSENT = [
    (with_feed(conversion_task(), temperature=None), MissingField.FEED_TEMPERATURE),
    (with_feed(conversion_task(reactor_pressure=None), pressure=None), MissingField.FEED_PRESSURE),
    (
        with_feed(conversion_task(), pure_component=None, composition=None),
        MissingField.FEED_COMPOSITION,
    ),
    (with_feed(gibbs_task(), composition=None), MissingField.FEED_COMPOSITION),
    (no_conversion(), MissingField.CONVERSION),
    (conversion_task(reactions=()), MissingField.REACTIONS),
    (equilibrium_task(reactions=()), MissingField.REACTIONS),
    (conversion_task(), MissingField.OTHER),
]
PRESENT = [
    (conversion_task(), MissingField.FEED_TEMPERATURE),
    (conversion_task(), MissingField.FEED_PRESSURE),
    (conversion_task(), MissingField.FEED_COMPOSITION),
    (conversion_task(), MissingField.CONVERSION),
    (conversion_task(), MissingField.REACTIONS),
    (gibbs_task(), MissingField.REACTIONS),  # Gibbs 反应器没有反应式，不算缺
    (gibbs_task(), MissingField.CONVERSION),  # 也没有转化率
    (equilibrium_task(), MissingField.CONVERSION),
]


@pytest.mark.parametrize(("task", "field"), ABSENT)
def test_declared_missing_counts_when_the_field_is_really_absent(task, field):
    declared_task = task.model_copy(update={"missing": declared(field)})
    assert blocking_missing(declared_task)


@pytest.mark.parametrize(("task", "field"), PRESENT)
def test_declared_missing_is_ignored_when_the_field_is_filled_in(task, field):
    declared_task = task.model_copy(update={"missing": declared(field)})
    assert not blocking_missing(declared_task)


def test_an_empty_composition_with_a_declared_missing_is_sent_back_not_asked_of_the_user():
    empty = composition(("methane", 1.0)).model_copy(update={"items": ()})
    task = with_feed(smr_task(), composition=empty, pure_component=None)
    task = task.model_copy(update={"missing": declared(MissingField.FEED_COMPOSITION)})
    issue = only_issue(task)
    assert issue.field_path == "feeds[0].composition" and "没有任何组分" in issue.message
    assert "缺少关键信息" not in issue.message

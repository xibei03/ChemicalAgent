"""结果检查 V1 至 V7：正确的模型全部通过；每次改坏一处，失败的检查集合与预期一致。

一处破坏可能让不止一项检查失败（比如一个量读不到，V5 和 V7 都会失败），所以预期写成
“破坏 → 应当失败的检查集合”的表。
"""

from dataclasses import replace

import pytest
from pydantic import ValidationError

from builders import (
    conversion_scenario,
    equilibrium_scenario,
    gasification_scenario,
    golden_data,
    spec_from,
)
from reactor_agent.recipes import recipe_for
from reactor_agent.spec.enums import CheckId, CheckSeverity, KeqSource, ObjectState
from reactor_agent.spec.model_spec import OperatingCase
from reactor_agent.spec.plan import system_feed_names, system_outlet_names
from reactor_agent.spec.snapshot import EnergyStreamSnapshot
from reactor_agent.validation.checks import COMMON_CHECKS, run_common_checks
from reactor_agent.validation.conservation import relative_error

V1, V2, V3, V4 = CheckId.SOLVED, CheckId.STRUCTURE, CheckId.FEEDS, CheckId.SPECIFICATIONS
V5, V6, V7 = CheckId.OUTPUTS, CheckId.PHYSICAL, CheckId.CONSERVATION
CONVERSION_CHECK, FIXED_K_CHECK = CheckId.CONVERSION_SPECIFIED, CheckId.FIXED_K_SATISFIED
# 蒸汽重整场景的出口：CO 350、H2O 1950、CO2 200、H2 1850 kmol/h，所以 CO + H2O <=> CO2 + H2
# 的反应商是 200 * 1850 / (350 * 1950)。
SHIFT_QUOTIENT = (200 * 1850) / (350 * 1950)


def all_checks(scenario):
    recipe = recipe_for(scenario.spec.reactor_type)
    return (*run_common_checks(scenario.context), *recipe.checks(scenario.context))


def failed_ids(scenario):
    return {check.check_id for check in all_checks(scenario) if not check.passed}


def result_of(scenario, check_id):
    return next(c for c in all_checks(scenario) if c.check_id is check_id)


def passes(scenario, check_id):
    return result_of(scenario, check_id).passed


def solve_with(scenario, **changes):
    return scenario.with_snapshot(solve=scenario.snapshot.solve.model_copy(update=changes))


def reactors_not_solved(scenario):
    objects = tuple(
        o.model_copy(update={"state": ObjectState.NOT_SOLVED}) if o.type_name == "reactor" else o
        for o in scenario.snapshot.solve.objects
    )
    return solve_with(scenario, objects=objects)


def scaled_mass(scenario, stream, factor):
    mass = scenario.snapshot.stream(stream).mass_flow_kg_h
    return scenario.with_stream(stream, mass_flow_kg_h=mass * factor)


def with_reaction_as_fixed_k(scenario):
    first = scenario.snapshot.reactions[0]
    update = {"keq_source": KeqSource.FIXED_K, "equilibrium_constant": 1.0}
    changed = first.model_copy(update={"definition": first.definition.model_copy(update=update)})
    return scenario.with_snapshot(reactions=(changed, *scenario.snapshot.reactions[1:]))


def with_reaction_sets_detached(scenario):
    detached = tuple(
        x.model_copy(update={"attached_to_fluid_package": False})
        for x in scenario.snapshot.reaction_sets
    )
    return scenario.with_snapshot(reaction_sets=detached)


def with_feed_composition_changed(scenario):
    changed = scenario.with_component("Feed", "Methane", mole_fraction=0.3)
    return changed.with_component("Feed", "H2O", mole_fraction=0.7)


def with_carbon_moved_to_carbon_dioxide(scenario):
    # 一氧化碳少 100，二氧化碳多 100：碳守恒，氧不守恒。物流内部的数跟着重算，仍然一致
    return scenario.with_flows("Vap", CO=250.0, CO2=300.0)


def with_feed_flows_changed(scenario):
    return scenario.with_flows("Feed", Methane=1100.0)


def with_water_lost(scenario):
    return scenario.with_flows("Vap", H2O=1852.5)


def with_scaled_component_mass(scenario):
    monoxide = scenario.snapshot.stream("Vap").components[2]
    assert monoxide.name == "CO"
    return scenario.with_component("Vap", "CO", mass_flow_kg_h=monoxide.mass_flow_kg_h * 1.05)


def with_unknown_duty(scenario):
    return scenario.with_snapshot(
        energy_streams=(EnergyStreamSnapshot(name="Q-100", duty_kw=None),)
    )


def with_other_components_in_the_fluid_package(scenario):
    thermo = scenario.snapshot.thermo
    return scenario.with_snapshot(
        thermo=thermo.model_copy(update={"components": thermo.components[:-1]})
    )


def with_case_temperature(scenario, temperature_c):
    """规格里的第一个工况（连同当前工况）改成另一个出口温度，快照和计划不变。"""
    data = golden_data("smr_equilibrium")
    data["cases"][0]["outlet_temperature_c"] = temperature_c
    spec = spec_from(data)
    return scenario.with_spec(spec, spec.cases[0])


def without_case_steps(scenario):
    steps = tuple(step for step in scenario.plan.steps if step.case_name is None)
    return replace(scenario, plan=scenario.plan.model_copy(update={"steps": steps}))


def with_fixed_k(constant):
    data = golden_data("smr_equilibrium")
    data["reactions"][1].update(keq_source="fixed_k", equilibrium_constant=constant)
    return equilibrium_scenario(spec=spec_from(data))


class TestCorrectModels:
    def test_every_check_passes_on_a_correct_model(self, scenario):
        assert failed_ids(scenario) == set()

    def test_common_checks_are_v1_to_v7_in_order(self, scenario):
        found = [check.check_id for check in run_common_checks(scenario.context)]
        assert found == [V1, V2, V3, V4, V5, V6, V7]
        assert len(COMMON_CHECKS) == 7

    def test_checks_are_fatal_and_say_what_they_expected(self, scenario):
        for check in all_checks(scenario):
            assert check.severity is CheckSeverity.FATAL
            assert check.expected
            assert check.message

    def test_the_second_case_of_a_multi_case_spec_also_passes(self):
        assert failed_ids(equilibrium_scenario("T600")) == set()


BREAKS = [
    pytest.param(
        equilibrium_scenario, lambda s: solve_with(s, is_solving=True), {V1}, id="solver running"
    ),
    pytest.param(equilibrium_scenario, reactors_not_solved, {V1}, id="reactor not solved"),
    pytest.param(
        equilibrium_scenario, lambda s: s.without_stream("Liq"), {V2, V5, V7}, id="outlet missing"
    ),
    pytest.param(
        equilibrium_scenario, lambda s: s.without_stream("Feed"), {V2, V3, V7}, id="feed missing"
    ),
    pytest.param(
        equilibrium_scenario, lambda s: s.with_snapshot(energy_streams=()), {V2}, id="no energy"
    ),
    pytest.param(
        equilibrium_scenario, lambda s: s.with_snapshot(thermo=None), {V2}, id="no fluid package"
    ),
    pytest.param(equilibrium_scenario, with_reaction_as_fixed_k, {V2}, id="reaction differs"),
    pytest.param(equilibrium_scenario, with_reaction_sets_detached, {V2}, id="set not attached"),
    pytest.param(
        equilibrium_scenario,
        lambda s: s.with_snapshot(reactions=s.snapshot.reactions[:1]),
        {V2},
        id="reaction missing",
    ),
    pytest.param(
        equilibrium_scenario, lambda s: s.with_snapshot(reaction_sets=()), {V2}, id="set missing"
    ),
    pytest.param(
        equilibrium_scenario,
        with_other_components_in_the_fluid_package,
        {V2},
        id="fluid package has other components",
    ),
    pytest.param(
        equilibrium_scenario,
        lambda s: s.with_reactor(0, vapour_product="Liq"),
        {V2},
        id="reactor wired to another product",
    ),
    pytest.param(
        equilibrium_scenario,
        lambda s: s.with_stream("Feed", temperature_c=530.0),
        {V3},
        id="feed temperature differs",
    ),
    pytest.param(
        equilibrium_scenario,
        with_feed_composition_changed,
        {V3, V6},
        id="feed fractions differ from the flows",
    ),
    pytest.param(equilibrium_scenario, with_feed_flows_changed, {V3, V7}, id="feed flows differ"),
    pytest.param(
        equilibrium_scenario,
        lambda s: s.with_stream("Vap", temperature_c=711.0),
        {V4},
        id="outlet temperature off",
    ),
    pytest.param(
        equilibrium_scenario,
        lambda s: s.with_reactor(0, pressure_drop_bar=0.5),
        {V4},
        id="pressure drop differs",
    ),
    pytest.param(
        equilibrium_scenario,
        lambda s: s.with_stream("Vap", temperature_c=None),
        {V4, V5},
        id="outlet temperature unknown",
    ),
    pytest.param(
        equilibrium_scenario,
        lambda s: s.with_component("Vap", "CO", molar_flow_kmol_h=None),
        {V5, V7},
        id="a flow unknown",
    ),
    pytest.param(equilibrium_scenario, with_unknown_duty, {V5}, id="duty unknown"),
    pytest.param(
        equilibrium_scenario,
        lambda s: s.with_component("Vap", "CO", mole_fraction=None),
        {V5},
        id="a fraction unknown",
    ),
    pytest.param(
        equilibrium_scenario,
        lambda s: s.with_component("Vap", "Methane", mole_fraction=0.20),
        {V6},
        id="fractions do not add up",
    ),
    pytest.param(
        equilibrium_scenario,
        lambda s: s.with_component("Vap", "CO", mole_fraction=-0.05),
        {V6},
        id="negative fraction",
    ),
    pytest.param(
        equilibrium_scenario,
        lambda s: s.with_component("Vap", "CO", molar_flow_kmol_h=-5.0),
        {V6, V7},
        id="negative flow",
    ),
    pytest.param(
        equilibrium_scenario,
        lambda s: scaled_mass(s, "Vap", 1.01),
        {V6, V7},
        id="total mass of an outlet off",
    ),
    pytest.param(equilibrium_scenario, with_water_lost, {V7}, id="mass and hydrogen lost"),
    pytest.param(
        equilibrium_scenario, with_carbon_moved_to_carbon_dioxide, {V7}, id="element not conserved"
    ),
    pytest.param(
        equilibrium_scenario,
        lambda s: s.with_stream("Vap", molar_flow_kmol_h=5040.0),
        {V6},
        id="total molar flow does not match the components",
    ),
    pytest.param(
        equilibrium_scenario,
        with_scaled_component_mass,
        {V6},
        id="component mass does not match moles times molecular weight",
    ),
    pytest.param(
        equilibrium_scenario,
        lambda s: s.with_component("Liq", "Methane", molar_flow_kmol_h=0.05),
        {V6},
        id="flow inside an empty stream",
    ),
    pytest.param(
        conversion_scenario,
        lambda s: s.without_stream("Vap"),
        {V2, V5, V7, CONVERSION_CHECK},
        id="conversion: product missing",
    ),
    pytest.param(
        lambda: conversion_scenario(converted=0.45), lambda s: s, {CONVERSION_CHECK}, id="45%"
    ),
    pytest.param(
        lambda: conversion_scenario(converted=0.55), lambda s: s, {CONVERSION_CHECK}, id="55%"
    ),
    pytest.param(
        gasification_scenario,
        lambda s: s.with_flows("Liq-1", Carbon=0.0),
        {V7},
        id="solid carbon lost",
    ),
    pytest.param(
        gasification_scenario,
        lambda s: s.with_flows("Vap-1", H2O=100.0),
        {CONVERSION_CHECK},
        id="water left unconverted",
    ),
    pytest.param(
        gasification_scenario,
        lambda s: s.without_stream("Vap-1"),
        {V2, V4, CONVERSION_CHECK},
        id="intermediate stream missing",
    ),
]


@pytest.mark.parametrize(("make", "break_it", "expected"), BREAKS)
def test_each_break_fails_exactly_the_expected_checks(make, break_it, expected):
    assert failed_ids(break_it(make())) == expected


class TestSolved:
    def test_v1_passes_when_everything_is_solved(self, equilibrium):
        assert passes(equilibrium, V1)

    def test_v1_names_the_object_that_is_not_solved(self, equilibrium):
        result = result_of(reactors_not_solved(equilibrium), V1)
        assert not result.passed
        assert "ERV-100" in result.actual

    def test_v1_ignores_whether_the_values_exist(self, equilibrium):
        assert passes(equilibrium.with_stream("Vap", temperature_c=None), V1)

    def test_a_flowsheet_without_objects_is_not_solved(self, equilibrium):
        assert not passes(solve_with(equilibrium, objects=()), V1)


class TestStructure:
    def test_v2_lists_every_missing_object(self, equilibrium):
        result = result_of(equilibrium.without_stream("Liq").with_snapshot(reactors=()), V2)
        assert not result.passed
        assert "Liq" in result.actual
        assert "ERV-100" in result.actual

    def test_v2_expects_the_objects_the_plan_names(self, gasification):
        result = result_of(gasification.without_stream("Vap-1"), V2)
        assert result.actual.startswith("物流 Vap-1")


class TestFeeds:
    def test_v3_accepts_a_small_readback_error(self, equilibrium):
        # 温度相对误差约 2e-5，在 1e-4 之内
        assert passes(equilibrium.with_stream("Feed", temperature_c=520.01), V3)

    def test_v3_rejects_an_error_above_the_tolerance(self, equilibrium):
        assert not passes(equilibrium.with_stream("Feed", temperature_c=521.0), V3)

    def test_v3_compares_against_the_spec_and_not_against_the_plan(self, equilibrium):
        data = golden_data("smr_equilibrium")
        data["feeds"][0]["pressure_bar"] = 20.0
        assert not passes(equilibrium.with_spec(spec_from(data)), V3)

    def test_v3_fails_when_the_spec_has_more_feeds_than_the_plan(self, equilibrium):
        data = golden_data("smr_equilibrium")
        data["feeds"] = [data["feeds"][0], {**data["feeds"][0], "name": "Second"}]
        result = result_of(equilibrium.with_spec(spec_from(data)), V3)
        assert not result.passed
        assert "股进料" in result.actual


class TestSpecifications:
    def test_v4_accepts_the_outlet_temperature_within_a_tenth_of_a_degree(self, equilibrium):
        assert passes(equilibrium.with_stream("Vap", temperature_c=710.05), V4)

    def test_v4_rejects_a_temperature_off_by_more_than_that(self, equilibrium):
        assert not passes(equilibrium.with_stream("Vap", temperature_c=710.2), V4)

    def test_v4_follows_the_current_case(self):
        cold = equilibrium_scenario("T600")
        assert passes(cold, V4)
        assert not passes(cold.with_stream("Vap", temperature_c=710.0), V4)

    def test_v4_checks_both_reactors_of_the_two_stage_model(self, gasification):
        assert not passes(gasification.with_stream("Vap-1", temperature_c=1300.0), V4)
        assert not passes(gasification.with_stream("Vap-2", temperature_c=1300.0), V4)

    def test_v4_checks_the_duty_when_the_case_specifies_one(self):
        data = golden_data("smr_equilibrium")
        data.update(heat_mode="specified_duty", cases=[{"name": "q", "duty_kw": 39989.0}])
        scenario = equilibrium_scenario("q", spec_from(data))
        assert passes(scenario, V4)
        other = scenario.with_snapshot(
            energy_streams=(EnergyStreamSnapshot(name="Q-100", duty_kw=39990.0),)
        )
        assert not passes(other, V4)

    def test_v4_does_not_require_a_temperature_for_an_adiabatic_reactor(self, conversion):
        assert passes(conversion.with_stream("Vap", temperature_c=900.0), V4)

    def test_v4_compares_the_total_pressure_drop_of_all_reactors_with_the_spec(self):
        data = golden_data("slurry_gibbs")
        data["pressure_drop_bar"] = 0.5
        scenario = gasification_scenario(spec_from(data))
        assert passes(scenario.with_reactor(0, pressure_drop_bar=0.5), V4)
        assert not passes(scenario.with_reactor(1, pressure_drop_bar=0.3), V4)


class TestOutputs:
    def test_v5_passes_when_every_outlet_has_its_values(self, conversion):
        assert passes(conversion, V5)

    def test_v5_does_not_ask_an_empty_outlet_for_a_composition(self, conversion):
        assert conversion.snapshot.stream("Liq").molar_flow_kmol_h == 0.0
        assert passes(conversion.with_component("Liq", "Toluene", mole_fraction=None), V5)

    def test_v5_asks_a_flowing_outlet_for_every_component(self, conversion):
        assert not passes(conversion.with_component("Vap", "Benzene", mass_flow_kg_h=None), V5)

    def test_v5_asks_every_outlet_for_its_state_and_total_flow(self, conversion):
        for field in ("temperature_c", "pressure_bar", "molar_flow_kmol_h", "mass_flow_kg_h"):
            assert not passes(conversion.with_stream("Liq", **{field: None}), V5), field

    def test_v5_does_not_look_at_the_intermediate_stream(self, gasification):
        assert passes(gasification.with_stream("Vap-1", temperature_c=None), V5)


class TestPhysical:
    def test_v6_accepts_fractions_that_add_up_within_the_tolerance(self, equilibrium):
        co = equilibrium.snapshot.stream("Vap").components[2]
        assert co.name == "CO"
        shifted = equilibrium.with_component("Vap", "CO", mole_fraction=co.mole_fraction + 5e-7)
        assert passes(shifted, V6)

    def test_v6_rejects_fractions_that_miss_one_by_more(self, equilibrium):
        co = equilibrium.snapshot.stream("Vap").components[2]
        shifted = equilibrium.with_component("Vap", "CO", mole_fraction=co.mole_fraction + 5e-6)
        assert not passes(shifted, V6)

    def test_v6_accepts_a_tiny_negative_value_from_numerical_noise(self, equilibrium):
        assert passes(equilibrium.with_component("Liq", "CO2", molar_flow_kmol_h=-1e-12), V6)

    def test_v6_says_which_total_the_components_do_not_add_up_to(self, equilibrium):
        result = result_of(equilibrium.with_stream("Vap", molar_flow_kmol_h=5040.0), V6)
        assert "各组分摩尔流量之和" in result.actual

    def test_v6_compares_component_masses_with_the_molecular_weights_of_the_table(
        self, equilibrium
    ):
        result = result_of(with_scaled_component_mass(equilibrium), V6)
        assert "分子量" in result.actual

    def test_v6_accepts_the_small_molecular_weight_differences_between_tables(self, equilibrium):
        scaled = equilibrium
        for item in equilibrium.snapshot.stream("Vap").components:
            scaled = scaled.with_component(
                "Vap", item.name, mass_flow_kg_h=item.mass_flow_kg_h * 1.0005
            )
        mass = equilibrium.snapshot.stream("Vap").mass_flow_kg_h
        assert passes(scaled.with_stream("Vap", mass_flow_kg_h=mass * 1.0005), V6)

    def test_v6_rejects_larger_molecular_weight_differences(self, equilibrium):
        scaled = equilibrium
        for item in equilibrium.snapshot.stream("Vap").components:
            scaled = scaled.with_component(
                "Vap", item.name, mass_flow_kg_h=item.mass_flow_kg_h * 1.002
            )
        mass = equilibrium.snapshot.stream("Vap").mass_flow_kg_h
        assert not passes(scaled.with_stream("Vap", mass_flow_kg_h=mass * 1.002), V6)

    def test_v6_checks_that_the_fractions_are_the_shares_of_the_flows(self, equilibrium):
        co = equilibrium.snapshot.stream("Vap").components[2]
        fractions_off = equilibrium.with_component(
            "Vap", "CO", mole_fraction=co.mole_fraction + 0.01
        )
        assert "流量占比" in result_of(fractions_off, V6).actual

    def test_v6_checks_the_streams_that_have_no_flow_for_stray_component_flows(self, equilibrium):
        stray = equilibrium.with_component("Liq", "Methane", molar_flow_kmol_h=0.05)
        assert "各组分摩尔流量之和" in result_of(stray, V6).actual

    def test_v6_does_not_ask_an_empty_stream_for_fractions_that_add_up(self, conversion):
        assert conversion.snapshot.stream("Liq").molar_flow_kmol_h == 0.0
        assert passes(conversion, V6)

    def test_v6_also_looks_at_the_intermediate_stream(self, gasification):
        assert not passes(gasification.with_component("Vap-1", "CO", mole_fraction=0.9), V6)


class TestConservation:
    def test_v7_accepts_a_balance_error_inside_the_tolerance(self, equilibrium):
        # 多出 0.2 kmol/h 水：质量多 3.6 kg/h（5.6e-5，在 1e-4 之内），氢、氧也在 1e-3 之内
        assert passes(equilibrium.with_flows("Vap", H2O=1950.2), V7)

    def test_v7_rejects_a_mass_error_outside_the_tolerance(self, equilibrium):
        # 多出 0.5 kmol/h 水：质量多 9 kg/h（1.4e-4），元素误差仍在 1e-3 之内，所以是质量检查失败
        result = result_of(equilibrium.with_flows("Vap", H2O=1950.5), V7)
        assert not result.passed
        assert "总质量" in result.actual
        assert "元素" not in result.actual

    def test_v7_accepts_a_small_hydrogen_error(self, equilibrium):
        # 多出 1 kmol/h 氢气：质量 3e-5，氢原子 2e-4
        assert passes(equilibrium.with_flows("Vap", Hydrogen=1851.0), V7)

    def test_v7_rejects_a_larger_hydrogen_error(self, equilibrium):
        assert not passes(equilibrium.with_flows("Vap", Hydrogen=1900.0), V7)

    def test_v7_counts_the_solid_in_the_liquid_outlet(self, gasification):
        assert passes(gasification, V7)
        assert not passes(gasification.without_stream("Liq-1"), V7)

    def test_v7_names_the_elements_that_are_off(self, equilibrium):
        result = result_of(equilibrium.with_flows("Vap", CO2=300.0), V7)
        assert "元素 C" in result.actual
        assert "元素 O" in result.actual
        assert "元素 H" not in result.actual

    def test_v7_cannot_balance_what_it_cannot_read(self, equilibrium):
        broken = equilibrium.with_stream("Vap", mass_flow_kg_h=None)
        assert "无法核算" in result_of(broken, V7).actual


class TestFixedKCheck:
    def test_a_reaction_quotient_equal_to_k_passes(self):
        assert passes(with_fixed_k(SHIFT_QUOTIENT), FIXED_K_CHECK)

    def test_a_different_k_fails_only_this_check(self):
        scenario = with_fixed_k(0.6)
        assert failed_ids(scenario) == {FIXED_K_CHECK}
        assert "0.6" in result_of(scenario, FIXED_K_CHECK).expected

    def test_a_reactant_that_has_disappeared_fails(self):
        scenario = with_fixed_k(SHIFT_QUOTIENT).with_component("Vap", "CO", mole_fraction=0.0)
        assert not passes(scenario, FIXED_K_CHECK)

    def test_there_is_no_such_check_when_k_comes_from_gibbs_energy(self, equilibrium):
        assert FIXED_K_CHECK not in {check.check_id for check in all_checks(equilibrium)}


STREAM_TOTALS = ("molar_flow_kmol_h", "mass_flow_kg_h")
COMPONENT_FIELDS = ("mole_fraction", "molar_flow_kmol_h", "mass_flow_kg_h")
STATE_FIELDS = ("temperature_c", "pressure_bar")


def changed_value(value):
    """把一个数改大 5%；原来是 0 的量改成 0.05。"""
    return value * 1.05 if value else 0.05


def outlets_with_flow(scenario):
    names = [s.name for s in scenario.snapshot.streams if s.name in outlet_names(scenario)]
    return [
        scenario.snapshot.stream(n) for n in names if scenario.snapshot.stream(n).molar_flow_kmol_h
    ]


def outlet_names(scenario):
    return set(system_outlet_names(scenario.plan))


class TestNothingInAnOutletIsLeftUnchecked:
    """报告会展示出料的总量和各组分的量。其中任何一个数不对，都应该有一项检查发现。"""

    def test_a_wrong_total_in_a_flowing_outlet_is_noticed(self, scenario):
        for stream in outlets_with_flow(scenario):
            for field in STREAM_TOTALS:
                broken = scenario.with_stream(
                    stream.name, **{field: changed_value(getattr(stream, field))}
                )
                assert failed_ids(broken), (stream.name, field)

    def test_a_wrong_component_value_in_a_flowing_outlet_is_noticed(self, scenario):
        for stream in outlets_with_flow(scenario):
            for item in stream.components:
                for field in COMPONENT_FIELDS:
                    new = changed_value(getattr(item, field))
                    broken = scenario.with_component(stream.name, item.name, **{field: new})
                    assert failed_ids(broken), (stream.name, item.name, field)

    def test_a_missing_value_in_an_outlet_is_noticed(self, scenario):
        for name in outlet_names(scenario):
            stream = scenario.snapshot.stream(name)
            for field in (*STATE_FIELDS, *STREAM_TOTALS):
                assert failed_ids(scenario.with_stream(name, **{field: None})), (name, field)
            if not stream.molar_flow_kmol_h:
                continue
            for item in stream.components:
                for field in COMPONENT_FIELDS:
                    broken = scenario.with_component(name, item.name, **{field: None})
                    assert failed_ids(broken), (name, item.name, field)

    def test_a_wrong_component_value_in_a_feed_is_noticed(self, scenario):
        feed = scenario.snapshot.stream(system_feed_names(scenario.plan)[0])
        for item in feed.components:
            for field in COMPONENT_FIELDS:
                new = changed_value(getattr(item, field))
                broken = scenario.with_component(feed.name, item.name, **{field: new})
                assert failed_ids(broken), (feed.name, item.name, field)


class TestChecksComeFromTheSpecAndNotFromThePlan:
    """计划是 Recipe 编译出来的。编译错了，结果再和计划一致也是错的模型，所以期望值取自规格。"""

    def test_v4_fails_when_the_spec_wants_another_temperature_than_the_model_has(self, equilibrium):
        assert passes(equilibrium, V4)
        assert not passes(with_case_temperature(equilibrium, 800.0), V4)

    def test_v4_does_not_need_the_case_steps_of_the_plan(self, equilibrium):
        without_steps = without_case_steps(equilibrium)
        assert passes(without_steps, V4)
        assert not passes(without_steps.with_stream("Vap", temperature_c=650.0), V4)

    def test_a_context_needs_a_case_that_the_spec_has(self, equilibrium):
        stranger = OperatingCase(name="typo", outlet_temperature_c=999.0)
        with pytest.raises(ValidationError, match="不是规格里的工况"):
            _ = replace(equilibrium, case=stranger).context

    def test_v2_fails_when_the_plan_has_another_reaction_than_the_spec(self, equilibrium):
        data = golden_data("smr_equilibrium")
        data["reactions"][1]["stoichiometry"][2]["coefficient"] = 2.0
        result = result_of(equilibrium.with_spec(spec_from(data)), V2)
        assert not result.passed
        assert "第 2 个反应" in result.actual

    def test_v2_fails_when_the_spec_has_more_reactions_than_the_plan(self, equilibrium):
        data = golden_data("smr_equilibrium")
        data["reactions"].append(data["reactions"][0])
        result = result_of(equilibrium.with_spec(spec_from(data)), V2)
        assert "第 3 个反应在计划里不存在" in result.actual

    def test_v2_fails_when_the_plan_has_another_fluid_package_than_the_spec(self, equilibrium):
        data = golden_data("smr_equilibrium")
        data["components"] = list(reversed(data["components"]))
        assert not passes(equilibrium.with_spec(spec_from(data)), V2)

    def test_the_synthesised_reaction_of_the_two_stage_model_is_not_in_the_spec(self, gasification):
        assert gasification.spec.reactions == ()
        assert passes(gasification, V2)


class TestToleranceBoundaries:
    def test_conversion_within_a_tenth_of_a_percentage_point_passes(self):
        assert passes(conversion_scenario(converted=0.5005), CONVERSION_CHECK)

    def test_conversion_beyond_a_tenth_of_a_percentage_point_fails(self):
        assert not passes(conversion_scenario(converted=0.502), CONVERSION_CHECK)

    def test_a_fixed_k_within_the_tolerance_passes(self):
        assert passes(with_fixed_k(SHIFT_QUOTIENT * 1.0005), FIXED_K_CHECK)

    def test_a_fixed_k_beyond_the_tolerance_fails(self):
        assert not passes(with_fixed_k(SHIFT_QUOTIENT * 1.005), FIXED_K_CHECK)


class TestRelativeError:
    def test_it_is_relative_to_the_larger_of_the_two_quantities(self):
        assert relative_error(100.0, 99.0) == pytest.approx(0.01)
        assert relative_error(99.0, 100.0) == pytest.approx(0.01)

    def test_quantities_that_are_both_close_to_zero_have_no_error(self):
        assert relative_error(0.0, 0.0) == 0.0
        assert relative_error(1e-12, 3e-12) == 0.0

    def test_an_element_that_appears_from_nowhere_is_a_full_error(self):
        assert relative_error(0.0, 5.0) == pytest.approx(1.0)

    @pytest.mark.parametrize(("fed", "left"), [(None, 1.0), (1.0, None), (None, None)])
    def test_an_unreadable_quantity_has_no_error_to_report(self, fed, left):
        assert relative_error(fed, left) is None

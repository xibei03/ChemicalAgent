"""Recipe：编译出的计划与计划 §17 的构建表一致，每条规则有违反它的用例，注册表查不到时返回 None。"""

import json

import pytest

from builders import component_table, golden_data, golden_spec, spec_from
from reactor_agent.backends.hysys_com.reactor_kinds import REACTOR_KINDS
from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.recipes import RECIPES, recipe_for
from reactor_agent.recipes.conversion import HEAT_MODES as CONVERSION_HEAT_MODES
from reactor_agent.recipes.equilibrium import HEAT_MODES as EQUILIBRIUM_HEAT_MODES
from reactor_agent.recipes.gibbs import HEAT_MODES as GIBBS_HEAT_MODES
from reactor_agent.recipes.gibbs import TWO_STAGE_HEAT_MODES
from reactor_agent.spec.components import ComponentEntry, ComponentTable
from reactor_agent.spec.enums import (
    ComponentPhase,
    HeatMode,
    KeqSource,
    ReactionKind,
    ReactionPhase,
    ReactorType,
    SpecVariable,
    ToolName,
)
from reactor_agent.spec.tool_args import (
    EnsureReactionArgs,
    EnsureReactionSetArgs,
    EnsureReactorArgs,
    EnsureStreamArgs,
    EnsureThermoArgs,
    SetSpecArgs,
)


def compiled(spec):
    return recipe_for(spec.reactor_type).compile(spec, component_table())


def issues_of(data, table=None):
    spec = spec_from(data)
    return recipe_for(spec.reactor_type).rules(spec, table or component_table())


def where(issues):
    return [(issue.code, issue.field_path) for issue in issues]


def outline(plan):
    """（工具，对象名）的清单。"""
    return [
        (step.tool, getattr(step.args, "name", getattr(step.args, "object_name", None)))
        for step in plan.steps
    ]


def reactor(plan, name):
    return next(a for a in plan.args_of(EnsureReactorArgs) if a.name == name)


def as_gibbs(data, **changes):
    """蒸汽重整的规格改成 Gibbs 反应器：没有反应式，也就没有针对反应式的假设。"""
    kept = [a for a in data["assumptions"] if not a["field_path"].startswith("reactions")]
    return {**data, "reactor_type": "gibbs", "reactions": [], "assumptions": kept, **changes}


def stripped(data, **changes):
    """去掉指标和假设再改字段：它们引用的组分和字段路径会随着改动失效，而这里不关心它们。"""
    return {**data, "metrics": [], "assumptions": [], **changes}


def renamed(data, old, new):
    """把规格里出现的某个组分名全部换成另一个写法。"""
    return json.loads(json.dumps(data).replace(old, new))


class TestEquilibriumPlan:
    def test_steps_follow_the_build_table_without_connect_and_new_case(self):
        plan = compiled(golden_spec("smr_equilibrium"))
        assert outline(plan) == [
            (ToolName.BASIS_ENSURE_THERMO, None),
            (ToolName.BASIS_ENSURE_REACTION, "Rxn-1"),
            (ToolName.BASIS_ENSURE_REACTION, "Rxn-2"),
            (ToolName.BASIS_ENSURE_REACTION_SET, "RxnSet-1"),
            (ToolName.FLOWSHEET_ENSURE_STREAM, "Feed"),
            (ToolName.FLOWSHEET_ENSURE_STREAM, "Vap"),
            (ToolName.FLOWSHEET_ENSURE_STREAM, "Liq"),
            (ToolName.FLOWSHEET_ENSURE_STREAM, "Q-100"),
            (ToolName.FLOWSHEET_ENSURE_REACTOR, "ERV-100"),
            (ToolName.FLOWSHEET_SET_SPEC, "ERV-100"),
            (ToolName.FLOWSHEET_SET_SPEC, "ERV-100"),
        ]

    def test_key_arguments_come_from_the_spec(self):
        spec = golden_spec("smr_equilibrium")
        plan = compiled(spec)
        thermo = plan.args_of(EnsureThermoArgs)[0]
        assert thermo.components == spec.components
        assert thermo.property_package is spec.property_package
        first, second = plan.args_of(EnsureReactionArgs)
        assert [first.reaction, second.reaction] == list(spec.reactions)
        assert plan.args_of(EnsureReactionSetArgs)[0].reactions == ("Rxn-1", "Rxn-2")
        feed = plan.args_of(EnsureStreamArgs)[0].conditions
        assert feed.temperature_c == 520.0
        assert feed.pressure_bar == 13.5
        assert feed.molar_flow_kmol_h == 3700.0

    def test_feed_arguments_do_not_carry_the_label_of_the_spec(self):
        feed = compiled(golden_spec("smr_equilibrium")).args_of(EnsureStreamArgs)[0].conditions
        assert "name" not in feed.model_dump()

    def test_reactor_is_wired_to_the_streams_and_the_reaction_set(self):
        erv = reactor(compiled(golden_spec("smr_equilibrium")), "ERV-100")
        assert erv.reactor_type is ReactorType.EQUILIBRIUM
        assert erv.feeds == ("Feed",)
        assert (erv.vapour_product, erv.liquid_product) == ("Vap", "Liq")
        assert erv.energy_stream == "Q-100"
        assert erv.reaction_set == "RxnSet-1"
        assert erv.pressure_drop_bar == 0.0
        assert erv.heat_mode is HeatMode.SPECIFIED_OUTLET_TEMPERATURE

    def test_every_case_gets_its_own_outlet_temperature(self):
        plan = compiled(golden_spec("smr_equilibrium"))
        assert [(s.case_name, s.args.variable, s.args.value) for s in plan.steps[-2:]] == [
            ("T710", SpecVariable.OUTLET_TEMPERATURE_C, 710.0),
            ("T600", SpecVariable.OUTLET_TEMPERATURE_C, 600.0),
        ]

    def test_cases_only_change_values_and_never_create_objects(self):
        plan = compiled(golden_spec("smr_equilibrium"))
        assert all(isinstance(s.args, SetSpecArgs) for s in plan.steps if s.case_name)

    def test_specified_duty_writes_the_duty_of_the_case(self):
        data = golden_data("smr_equilibrium")
        data.update(heat_mode="specified_duty", cases=[{"name": "q", "duty_kw": 40000.0}])
        plan = compiled(spec_from(data))
        (step,) = plan.case_steps("q")
        assert (step.args.variable, step.args.value) == (SpecVariable.DUTY_KW, 40000.0)
        assert reactor(plan, "ERV-100").energy_stream == "Q-100"

    def test_adiabatic_reactor_has_no_energy_stream_and_no_case_steps(self):
        data = golden_data("smr_equilibrium")
        data.update(heat_mode="adiabatic", cases=[{"name": "base"}])
        plan = compiled(spec_from(data))
        assert reactor(plan, "ERV-100").energy_stream is None
        assert "Q-100" not in [name for _, name in outline(plan)]
        assert plan.case_steps("base") == ()

    def test_several_feeds_are_numbered_and_all_go_to_the_reactor(self):
        data = golden_data("smr_equilibrium")
        steam = {**data["feeds"][0], "name": "Steam", "molar_flow_kmol_h": 2700.0}
        steam["composition"] = [{"component": "H2O", "mole_fraction": 1.0}]
        data["feeds"] = [
            {
                **data["feeds"][0],
                "molar_flow_kmol_h": 1000.0,
                "composition": [{"component": "Methane", "mole_fraction": 1.0}],
            },
            steam,
        ]
        plan = compiled(spec_from(data))
        assert [s.name for s in plan.args_of(EnsureStreamArgs)[:2]] == ["Feed", "Feed-2"]
        assert reactor(plan, "ERV-100").feeds == ("Feed", "Feed-2")

    def test_the_same_spec_always_gives_the_same_plan(self):
        spec = golden_spec("smr_equilibrium")
        assert compiled(spec) == compiled(spec)

    def test_metrics_and_assumptions_do_not_change_the_plan(self):
        data = golden_data("smr_equilibrium")
        bare = compiled(spec_from({**data, "metrics": [], "assumptions": []}))
        assert bare == compiled(golden_spec("smr_equilibrium"))


class TestConversionPlan:
    def test_steps_follow_the_build_table_without_connect_and_new_case(self):
        plan = compiled(golden_spec("toluene_conversion"))
        assert outline(plan) == [
            (ToolName.BASIS_ENSURE_THERMO, None),
            (ToolName.BASIS_ENSURE_REACTION, "Rxn-1"),
            (ToolName.BASIS_ENSURE_REACTION_SET, "RxnSet-1"),
            (ToolName.FLOWSHEET_ENSURE_STREAM, "Feed"),
            (ToolName.FLOWSHEET_ENSURE_STREAM, "Vap"),
            (ToolName.FLOWSHEET_ENSURE_STREAM, "Liq"),
            (ToolName.FLOWSHEET_ENSURE_REACTOR, "CRV-100"),
        ]

    def test_the_fractional_stoichiometry_stays_in_one_reaction(self):
        spec = golden_spec("toluene_conversion")
        (reaction,) = compiled(spec).args_of(EnsureReactionArgs)
        assert reaction.reaction == spec.reactions[0]
        assert reaction.reaction.base_component == "Toluene"
        assert reaction.reaction.conversion_percent == 50.0

    def test_adiabatic_reactor_has_no_energy_stream_and_the_case_has_no_steps(self):
        plan = compiled(golden_spec("toluene_conversion"))
        crv = reactor(plan, "CRV-100")
        assert crv.reactor_type is ReactorType.CONVERSION
        assert (crv.energy_stream, crv.heat_mode) == (None, HeatMode.ADIABATIC)
        assert crv.reaction_set == "RxnSet-1"
        assert plan.case_steps("base") == ()

    def test_feed_is_given_as_mass_flow_when_the_spec_says_so(self):
        feed = compiled(golden_spec("toluene_conversion")).args_of(EnsureStreamArgs)[0].conditions
        assert (feed.mass_flow_kg_h, feed.molar_flow_kmol_h) == (10000.0, None)


class TestGibbsPlan:
    def test_solid_carbon_is_compiled_into_a_conversion_reactor_and_a_gibbs_reactor(self):
        plan = compiled(golden_spec("slurry_gibbs"))
        assert outline(plan) == [
            (ToolName.BASIS_ENSURE_THERMO, None),
            (ToolName.BASIS_ENSURE_REACTION, "Rxn-1"),
            (ToolName.BASIS_ENSURE_REACTION_SET, "RxnSet-1"),
            (ToolName.FLOWSHEET_ENSURE_STREAM, "Feed"),
            (ToolName.FLOWSHEET_ENSURE_STREAM, "Vap-1"),
            (ToolName.FLOWSHEET_ENSURE_STREAM, "Liq-1"),
            (ToolName.FLOWSHEET_ENSURE_STREAM, "Q-1"),
            (ToolName.FLOWSHEET_ENSURE_REACTOR, "CRV-100"),
            (ToolName.FLOWSHEET_ENSURE_STREAM, "Vap-2"),
            (ToolName.FLOWSHEET_ENSURE_STREAM, "Liq-2"),
            (ToolName.FLOWSHEET_ENSURE_STREAM, "Q-2"),
            (ToolName.FLOWSHEET_ENSURE_REACTOR, "GBR-100"),
            (ToolName.FLOWSHEET_SET_SPEC, "CRV-100"),
            (ToolName.FLOWSHEET_SET_SPEC, "GBR-100"),
        ]

    def test_first_stage_turns_the_limiting_reactant_completely_into_syngas(self):
        (reaction,) = compiled(golden_spec("slurry_gibbs")).args_of(EnsureReactionArgs)
        gasification = reaction.reaction
        assert {t.component: t.coefficient for t in gasification.stoichiometry} == {
            "Carbon": -1.0,
            "H2O": -1.0,
            "CO": 1.0,
            "Hydrogen": 1.0,
        }
        assert gasification.base_component == "H2O"
        assert gasification.conversion_percent == 100.0
        assert gasification.phase is ReactionPhase.COMBINED

    def test_the_gas_of_the_first_stage_is_the_feed_of_the_gibbs_reactor(self):
        plan = compiled(golden_spec("slurry_gibbs"))
        first, second = reactor(plan, "CRV-100"), reactor(plan, "GBR-100")
        assert (first.reactor_type, first.feeds) == (ReactorType.CONVERSION, ("Feed",))
        assert (first.vapour_product, first.liquid_product) == ("Vap-1", "Liq-1")
        assert (first.energy_stream, first.reaction_set) == ("Q-1", "RxnSet-1")
        assert (second.reactor_type, second.feeds) == (ReactorType.GIBBS, ("Vap-1",))
        assert (second.vapour_product, second.liquid_product) == ("Vap-2", "Liq-2")
        assert (second.energy_stream, second.reaction_set) == ("Q-2", None)

    def test_both_reactors_are_held_at_the_outlet_temperature_of_the_case(self):
        plan = compiled(golden_spec("slurry_gibbs"))
        assert [(s.args.object_name, s.args.value) for s in plan.case_steps("base")] == [
            ("CRV-100", 1400.0),
            ("GBR-100", 1400.0),
        ]

    def test_the_pressure_drop_is_taken_once_by_the_first_stage(self):
        data = golden_data("slurry_gibbs")
        plan = compiled(spec_from({**data, "pressure_drop_bar": 0.5}))
        assert reactor(plan, "CRV-100").pressure_drop_bar == 0.5
        assert reactor(plan, "GBR-100").pressure_drop_bar == 0.0

    @pytest.mark.parametrize(
        ("carbon", "water", "base"), [(0.71, 0.29, "H2O"), (0.2, 0.8, "Carbon"), (0.5, 0.5, "H2O")]
    )
    def test_the_reactant_with_fewer_moles_is_the_base_component(self, carbon, water, base):
        data = golden_data("slurry_gibbs")
        data["feeds"][0]["composition"] = [
            {"component": "Carbon", "mole_fraction": carbon},
            {"component": "H2O", "mole_fraction": water},
        ]
        plan = compiled(spec_from(data))
        assert plan.args_of(EnsureReactionArgs)[0].reaction.base_component == base

    @pytest.mark.parametrize(
        ("carbon_kg_h", "water_kg_h", "base"), [(500.0, 1000.0, "Carbon"), (1000.0, 1000.0, "H2O")]
    )
    def test_mass_flows_are_converted_to_moles_before_comparing(
        self, carbon_kg_h, water_kg_h, base
    ):
        data = golden_data("slurry_gibbs")
        feed = {k: v for k, v in data["feeds"][0].items() if k != "molar_flow_kmol_h"}
        carbon = {**feed, "name": "Coal", "mass_flow_kg_h": carbon_kg_h}
        carbon["composition"] = [{"component": "Carbon", "mole_fraction": 1.0}]
        water = {**feed, "name": "Water", "mass_flow_kg_h": water_kg_h}
        water["composition"] = [{"component": "H2O", "mole_fraction": 1.0}]
        data["feeds"] = [carbon, water]
        plan = compiled(spec_from(data))
        assert plan.args_of(EnsureReactionArgs)[0].reaction.base_component == base
        assert reactor(plan, "CRV-100").feeds == ("Feed", "Feed-2")

    def test_compiling_a_spec_that_did_not_pass_the_rules_is_an_error(self):
        data = stripped(golden_data("slurry_gibbs"), components=["Carbon", "H2O", "CO2"])
        with pytest.raises(ReactorAgentError) as caught:
            compiled(spec_from(data))
        assert caught.value.code is ErrorCode.RULE

    def test_gas_only_feed_gets_a_single_gibbs_reactor_without_reactions(self):
        plan = compiled(spec_from(as_gibbs(golden_data("smr_equilibrium"))))
        assert outline(plan) == [
            (ToolName.BASIS_ENSURE_THERMO, None),
            (ToolName.FLOWSHEET_ENSURE_STREAM, "Feed"),
            (ToolName.FLOWSHEET_ENSURE_STREAM, "Vap"),
            (ToolName.FLOWSHEET_ENSURE_STREAM, "Liq"),
            (ToolName.FLOWSHEET_ENSURE_STREAM, "Q-100"),
            (ToolName.FLOWSHEET_ENSURE_REACTOR, "GBR-100"),
            (ToolName.FLOWSHEET_SET_SPEC, "GBR-100"),
            (ToolName.FLOWSHEET_SET_SPEC, "GBR-100"),
        ]
        gbr = reactor(plan, "GBR-100")
        assert (gbr.reactor_type, gbr.reaction_set) == (ReactorType.GIBBS, None)

    def test_gas_only_gibbs_reactor_may_be_adiabatic(self):
        data = as_gibbs(
            golden_data("smr_equilibrium"), heat_mode="adiabatic", cases=[{"name": "b"}]
        )
        plan = compiled(spec_from(data))
        assert reactor(plan, "GBR-100").energy_stream is None


class TestRulesCommonToAllReactors:
    def test_the_golden_specs_have_no_issues(self):
        for name in ("smr_equilibrium", "toluene_conversion", "slurry_gibbs"):
            assert issues_of(golden_data(name)) == (), name

    def test_unknown_component_is_reported_at_its_position(self):
        data = json.loads(
            json.dumps(golden_data("smr_equilibrium")).replace("Methane", "Unobtainium")
        )
        issues = issues_of(data)
        assert where(issues) == [(ErrorCode.COMPONENT_NOT_FOUND, "components[0]")]
        assert "Unobtainium" in issues[0].message

    def test_alias_is_not_accepted_in_place_of_the_canonical_name(self):
        data = renamed(golden_data("smr_equilibrium"), "Methane", "甲烷")
        (issue,) = issues_of(data)
        assert issue.code is ErrorCode.COMPONENT_NOT_FOUND
        assert "Methane" in issue.message

    def test_reaction_that_does_not_conserve_elements_is_reported_with_the_elements(self):
        data = golden_data("smr_equilibrium")
        data["reactions"][0]["stoichiometry"][2]["coefficient"] = 2.0
        (issue,) = issues_of(data)
        assert (issue.code, issue.field_path) == (
            ErrorCode.REACTION_INVALID,
            "reactions[0].stoichiometry",
        )
        assert "C" in issue.message
        assert "O" in issue.message

    def test_rounded_coefficients_within_the_tolerance_are_accepted(self):
        data = golden_data("toluene_conversion")
        data["reactions"][0]["stoichiometry"][2]["coefficient"] = 0.2401
        assert issues_of(data) == ()

    def test_issues_say_whether_the_user_has_to_fix_them(self):
        data = golden_data("smr_equilibrium")
        data["reactions"][0]["stoichiometry"][2]["coefficient"] = 2.0
        assert issues_of(data)[0].user_fixable is False


class TestConversionRules:
    def test_a_reaction_is_required(self):
        (issue,) = issues_of(stripped(golden_data("toluene_conversion"), reactions=[]))
        assert (issue.code, issue.field_path, issue.user_fixable) == (
            ErrorCode.RULE,
            "reactions",
            True,
        )

    def test_equilibrium_reactions_do_not_fit_a_conversion_reactor(self):
        data = {**golden_data("smr_equilibrium"), "reactor_type": "conversion"}
        assert where(issues_of(data)) == [
            (ErrorCode.SET_INCOMPATIBLE, "reactions[0]"),
            (ErrorCode.SET_INCOMPATIBLE, "reactions[1]"),
        ]

    @pytest.mark.parametrize(("second", "ok"), [(50.0, True), (50.5, False)])
    def test_parallel_conversions_of_one_base_component_add_up_to_at_most_100(self, second, ok):
        data = golden_data("toluene_conversion")
        data["reactions"][0]["conversion_percent"] = 50.0
        data["reactions"].append({**data["reactions"][0], "conversion_percent": second})
        issues = issues_of(data)
        assert (issues == ()) is ok
        assert ok or where(issues) == [(ErrorCode.RULE, "reactions")]
        assert ok or issues[0].user_fixable

    def test_base_component_may_not_appear_in_a_reaction_of_another_base(self):
        data = golden_data("toluene_conversion")
        data["reactions"].append(
            {
                "kind": "conversion",
                "stoichiometry": [
                    {"component": "m-Xylene", "coefficient": -1.0},
                    {"component": "p-Xylene", "coefficient": 1.0},
                ],
                "base_component": "m-Xylene",
                "conversion_percent": 30.0,
            }
        )
        (issue,) = issues_of(data)
        assert (issue.code, issue.field_path) == (ErrorCode.UNSUPPORTED, "reactions[0]")
        assert "m-Xylene" in issue.message

    def test_specified_duty_has_not_been_verified_for_a_conversion_reactor(self):
        data = golden_data("toluene_conversion")
        data.update(heat_mode="specified_duty", cases=[{"name": "base", "duty_kw": 100.0}])
        assert where(issues_of(data)) == [(ErrorCode.UNSUPPORTED, "heat_mode")]

    def test_outlet_temperature_is_accepted(self):
        data = golden_data("toluene_conversion")
        data.update(heat_mode="specified_outlet_temperature")
        data["cases"] = [{"name": "base", "outlet_temperature_c": 400.0}]
        assert issues_of(data) == ()


class TestEquilibriumRules:
    def test_a_reaction_is_required(self):
        data = stripped(golden_data("smr_equilibrium"), reactions=[])
        assert where(issues_of(data)) == [(ErrorCode.RULE, "reactions")]

    def test_conversion_reactions_do_not_fit_an_equilibrium_reactor(self):
        data = {**golden_data("toluene_conversion"), "reactor_type": "equilibrium"}
        assert where(issues_of(data)) == [(ErrorCode.SET_INCOMPATIBLE, "reactions[0]")]

    def test_all_three_heat_modes_are_accepted(self):
        data = golden_data("smr_equilibrium")
        data.update(heat_mode="specified_duty", cases=[{"name": "q", "duty_kw": 1.0e4}])
        assert issues_of(data) == ()
        data.update(heat_mode="adiabatic", cases=[{"name": "base"}])
        assert issues_of(data) == ()


class TestGibbsRules:
    def test_gas_only_feed_needs_nothing_but_the_components(self):
        assert issues_of(as_gibbs(golden_data("smr_equilibrium"))) == ()

    def test_reactions_are_not_used_by_a_gibbs_reactor(self):
        data = {**golden_data("smr_equilibrium"), "reactor_type": "gibbs"}
        assert where(issues_of(data)) == [(ErrorCode.SET_INCOMPATIBLE, "reactions")]

    def test_specified_duty_has_not_been_verified_for_a_gibbs_reactor(self):
        data = as_gibbs(golden_data("smr_equilibrium"), heat_mode="specified_duty")
        data["cases"] = [{"name": "q", "duty_kw": 1.0e4}]
        assert where(issues_of(data)) == [(ErrorCode.UNSUPPORTED, "heat_mode")]

    def test_every_element_of_the_feed_needs_a_non_solid_component_to_go_to(self):
        data = stripped(golden_data("slurry_gibbs"), components=["Carbon", "H2O"])
        issues = issues_of(data)
        coverage = issues[0]
        assert (coverage.code, coverage.field_path) == (ErrorCode.RULE, "components")
        assert "C" in coverage.message
        # 两段式还需要 CO 和氢气作为气化的产物
        assert [i.field_path for i in issues[1:]] == ["components", "components"]

    def test_a_solid_that_is_not_in_the_feed_cannot_be_a_product(self):
        data = as_gibbs(golden_data("smr_equilibrium"))
        data["components"] = [*data["components"], "Carbon"]
        (issue,) = issues_of(data)
        assert (issue.code, issue.field_path) == (ErrorCode.UNSUPPORTED, "components[5]")
        assert "Carbon" in issue.message

    def test_solid_carbon_needs_both_syngas_components(self):
        data = golden_data("slurry_gibbs")
        data["components"] = ["Carbon", "H2O", "CO", "CO2", "Methane"]
        (issue,) = issues_of(data)
        assert issue.code is ErrorCode.RULE
        assert "H2" in issue.message

    def test_solid_carbon_feed_may_only_contain_carbon_and_water(self):
        data = golden_data("slurry_gibbs")
        data["feeds"][0]["composition"] = [
            {"component": "Carbon", "mole_fraction": 0.6},
            {"component": "H2O", "mole_fraction": 0.3},
            {"component": "CO2", "mole_fraction": 0.1},
        ]
        (issue,) = issues_of(data)
        assert (issue.code, issue.field_path) == (ErrorCode.UNSUPPORTED, "feeds")

    def test_solid_carbon_without_water_cannot_be_gasified(self):
        data = golden_data("slurry_gibbs")
        data["feeds"][0]["composition"] = [{"component": "Carbon", "mole_fraction": 1.0}]
        (issue,) = issues_of(data)
        assert (issue.code, issue.field_path, issue.user_fixable) == (ErrorCode.RULE, "feeds", True)
        assert "水" in issue.message

    def test_other_solids_are_not_supported(self):
        sulfur = ComponentEntry(
            name="Sulfur",
            formula="S",
            molecular_weight_kg_per_kmol=32.06,
            phase=ComponentPhase.SOLID,
        )
        table = ComponentTable(components=(*component_table().components, sulfur))
        data = stripped(golden_data("slurry_gibbs"), components=["Sulfur", "H2O", "CO", "Hydrogen"])
        data["feeds"][0]["composition"] = [
            {"component": "Sulfur", "mole_fraction": 0.5},
            {"component": "H2O", "mole_fraction": 0.5},
        ]
        assert (ErrorCode.UNSUPPORTED, "feeds") in where(issues_of(data, table))

    def test_the_two_stage_model_is_only_verified_with_a_specified_outlet_temperature(self):
        data = golden_data("slurry_gibbs")
        data.update(heat_mode="adiabatic", cases=[{"name": "base"}])
        (issue,) = issues_of(data)
        assert (issue.code, issue.field_path) == (ErrorCode.UNSUPPORTED, "heat_mode")
        assert "两段式" in issue.message


class TestRegistry:
    def test_the_three_supported_types_have_a_recipe(self):
        assert set(RECIPES) == {ReactorType.CONVERSION, ReactorType.EQUILIBRIUM, ReactorType.GIBBS}

    @pytest.mark.parametrize("reactor_type", [ReactorType.PFR, ReactorType.CSTR])
    def test_types_without_a_recipe_give_none(self, reactor_type):
        assert recipe_for(reactor_type) is None

    def test_heat_modes_agree_with_what_the_backend_has_verified(self):
        assert REACTOR_KINDS[ReactorType.CONVERSION].heat_modes == CONVERSION_HEAT_MODES
        assert REACTOR_KINDS[ReactorType.EQUILIBRIUM].heat_modes == EQUILIBRIUM_HEAT_MODES
        assert REACTOR_KINDS[ReactorType.GIBBS].heat_modes == GIBBS_HEAT_MODES
        assert TWO_STAGE_HEAT_MODES <= GIBBS_HEAT_MODES

    def test_reaction_kinds_agree_with_what_the_backend_accepts(self):
        # 转化、平衡反应器的规则只放行 Backend 支持的那一种反应
        assert REACTOR_KINDS[ReactorType.CONVERSION].reaction_kind is ReactionKind.CONVERSION
        assert REACTOR_KINDS[ReactorType.EQUILIBRIUM].reaction_kind is ReactionKind.EQUILIBRIUM
        assert REACTOR_KINDS[ReactorType.GIBBS].reaction_kind is None

    def test_fixed_k_is_compiled_like_any_other_equilibrium_reaction(self):
        data = golden_data("smr_equilibrium")
        data["reactions"][1].update(keq_source="fixed_k", equilibrium_constant=0.54)
        plan = compiled(spec_from(data))
        second = plan.args_of(EnsureReactionArgs)[1].reaction
        assert (second.keq_source, second.equilibrium_constant) == (KeqSource.FIXED_K, 0.54)

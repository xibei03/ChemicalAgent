"""BuildPlan：步骤的一致性、按入参类型装配、系统进出料的推导。"""

import pytest
from pydantic import ValidationError

from builders import conversion_scenario, gasification_scenario
from reactor_agent.spec.enums import (
    HeatMode,
    PropertyPackage,
    ReactorType,
    SpecVariable,
    StepPhase,
    StreamKind,
    ToolName,
)
from reactor_agent.spec.plan import (
    BuildPlan,
    BuildStep,
    CaseSpecs,
    assemble_plan,
    energy_stream_names,
    material_stream_names,
    system_feed_names,
    system_liquid_outlets,
    system_outlet_names,
    system_vapour_outlets,
)
from reactor_agent.spec.tool_args import (
    CompositionEntry,
    EnsureReactorArgs,
    EnsureStreamArgs,
    EnsureThermoArgs,
    FeedConditions,
    SetSpecArgs,
)


def thermo():
    return EnsureThermoArgs(components=("Methane",), property_package=PropertyPackage.PENG_ROBINSON)


def feed(name="Feed"):
    conditions = FeedConditions(
        temperature_c=25.0,
        pressure_bar=1.0,
        composition=(CompositionEntry(component="Methane", mole_fraction=1.0),),
        molar_flow_kmol_h=10.0,
    )
    return EnsureStreamArgs(name=name, conditions=conditions)


def outlet(name):
    return EnsureStreamArgs(name=name)


def energy(name="Q-100"):
    return EnsureStreamArgs(name=name, kind=StreamKind.ENERGY)


def reactor(name, feeds, vapour, liquid, energy_stream=None):
    return EnsureReactorArgs(
        name=name,
        reactor_type=ReactorType.GIBBS,
        feeds=feeds,
        vapour_product=vapour,
        liquid_product=liquid,
        energy_stream=energy_stream,
        heat_mode=HeatMode.ADIABATIC if energy_stream is None else HeatMode.SPECIFIED_DUTY,
    )


def outlet_temperature(reactor_name, value):
    return SetSpecArgs(
        object_name=reactor_name, variable=SpecVariable.OUTLET_TEMPERATURE_C, value=value
    )


def step(number, args, tool, phase, case_name=None):
    return BuildStep(number=number, tool=tool, args=args, phase=phase, case_name=case_name)


THERMO_STEP = (ToolName.BASIS_ENSURE_THERMO, StepPhase.BASIS)
STREAM_STEP = (ToolName.FLOWSHEET_ENSURE_STREAM, StepPhase.FLOWSHEET)
SPEC_STEP = (ToolName.FLOWSHEET_SET_SPEC, StepPhase.CASE)


class TestAssembly:
    def test_tool_phase_and_numbers_come_from_the_kind_of_args(self):
        cases = [CaseSpecs("base", (outlet_temperature("R", 700.0),))]
        plan = assemble_plan([thermo()], [feed(), outlet("Vap")], cases)
        assert [(s.number, s.tool, s.phase, s.case_name) for s in plan.steps] == [
            (1, ToolName.BASIS_ENSURE_THERMO, StepPhase.BASIS, None),
            (2, ToolName.FLOWSHEET_ENSURE_STREAM, StepPhase.FLOWSHEET, None),
            (3, ToolName.FLOWSHEET_ENSURE_STREAM, StepPhase.FLOWSHEET, None),
            (4, ToolName.FLOWSHEET_SET_SPEC, StepPhase.CASE, "base"),
        ]

    def test_cases_keep_the_order_they_were_given_in(self):
        cases = [
            CaseSpecs("hot", (outlet_temperature("R", 800.0),)),
            CaseSpecs("cold", (outlet_temperature("R", 500.0),)),
        ]
        plan = assemble_plan([thermo()], [feed()], cases)
        assert [s.case_name for s in plan.steps[2:]] == ["hot", "cold"]
        assert [s.args.value for s in plan.case_steps("cold")] == [500.0]

    def test_a_case_without_steps_has_no_case_steps(self):
        plan = assemble_plan([thermo()], [feed()], [CaseSpecs("base", ())])
        assert plan.case_steps("base") == ()

    def test_args_of_returns_one_kind_in_plan_order(self):
        plan = assemble_plan([thermo()], [feed("A"), outlet("B"), feed("C")], [])
        assert [a.name for a in plan.args_of(EnsureStreamArgs)] == ["A", "B", "C"]
        assert plan.args_of(SetSpecArgs) == ()

    def test_plan_survives_a_json_round_trip(self, scenario):
        again = BuildPlan.model_validate_json(scenario.plan.model_dump_json())
        assert again == scenario.plan


class TestConsistency:
    def test_tool_that_does_not_belong_to_the_args_is_rejected(self):
        with pytest.raises(ValidationError, match="不是"):
            step(1, thermo(), ToolName.FLOWSHEET_ENSURE_STREAM, StepPhase.BASIS)

    def test_phase_that_does_not_belong_to_the_tool_is_rejected(self):
        with pytest.raises(ValidationError, match="不是"):
            step(1, feed(), ToolName.FLOWSHEET_ENSURE_STREAM, StepPhase.BASIS)

    def test_only_case_steps_carry_a_case_name(self):
        with pytest.raises(ValidationError, match="工况名"):
            step(1, thermo(), *THERMO_STEP, case_name="base")
        with pytest.raises(ValidationError, match="工况名"):
            step(1, outlet_temperature("R", 700.0), *SPEC_STEP)

    def test_numbers_must_start_at_one_and_count_up(self):
        first = step(2, thermo(), *THERMO_STEP)
        with pytest.raises(ValidationError, match="编号"):
            BuildPlan(steps=(first,))
        second = step(1, feed(), *STREAM_STEP)
        with pytest.raises(ValidationError, match="编号"):
            BuildPlan(steps=(second, step(3, outlet("Vap"), *STREAM_STEP)))

    def test_phases_must_come_in_order(self):
        flowsheet = step(1, feed(), *STREAM_STEP)
        basis = step(2, thermo(), *THERMO_STEP)
        with pytest.raises(ValidationError, match="顺序"):
            BuildPlan(steps=(flowsheet, basis))

    def test_a_plan_needs_at_least_one_step(self):
        with pytest.raises(ValidationError):
            BuildPlan(steps=())

    def test_steps_that_are_not_modelling_steps_are_rejected(self):
        # 求解、读快照这类动作由执行器直接调用，不能出现在计划里
        with pytest.raises(ValidationError):
            BuildStep.model_validate(
                {"number": 1, "tool": "solver.solve", "args": {}, "phase": "case", "case_name": "x"}
            )


class TestSystemStreams:
    def test_single_reactor_plan_has_one_feed_and_both_products_as_outlets(self):
        plan = conversion_scenario().plan
        assert system_feed_names(plan) == ("Feed",)
        assert system_vapour_outlets(plan) == ("Vap",)
        assert system_liquid_outlets(plan) == ("Liq",)
        assert system_outlet_names(plan) == ("Vap", "Liq")

    def test_stream_that_feeds_another_reactor_is_not_an_outlet(self):
        plan = gasification_scenario().plan
        assert system_vapour_outlets(plan) == ("Vap-2",)
        assert system_liquid_outlets(plan) == ("Liq-1", "Liq-2")
        assert "Vap-1" not in system_outlet_names(plan)
        assert "Vap-1" in material_stream_names(plan)

    def test_every_stream_with_conditions_is_a_feed_in_plan_order(self):
        plan = assemble_plan(
            [thermo()],
            [feed("Feed"), feed("Feed-2"), outlet("Vap"), outlet("Liq"), energy("Q-1")],
            [],
        )
        assert system_feed_names(plan) == ("Feed", "Feed-2")
        assert material_stream_names(plan) == ("Feed", "Feed-2", "Vap", "Liq")
        assert energy_stream_names(plan) == ("Q-1",)

    def test_a_plan_without_a_reactor_has_no_outlets(self):
        plan = assemble_plan([thermo()], [feed()], [])
        assert system_outlet_names(plan) == ()

    def test_energy_streams_follow_the_reactors_that_use_them(self):
        plan = gasification_scenario().plan
        assert energy_stream_names(plan) == ("Q-1", "Q-2")
        assert energy_stream_names(conversion_scenario().plan) == ()

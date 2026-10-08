"""工具契约在真实 HYSYS 上的行为：冲突、非法连接、缺规定、Case 的生命周期、快照里没有哨兵数。"""

import math

import pytest
from hysys_models import (
    SNAPSHOT,
    SOLVE,
    TOLUENE_COMPONENTS,
    composition,
    conversion_model,
    energy,
    equilibrium_model,
    feed,
    fractions_of,
    reaction,
    reaction_set,
    reactor,
    steam_feed_conditions,
    stream,
    stream_of,
    terms,
    thermo,
)
from steps import run_steps

from reactor_agent.errors import ErrorCode
from reactor_agent.spec.enums import (
    CaseMode,
    HeatMode,
    PropertyPackage,
    ReactorType,
    ResultStatus,
    SpecVariable,
    ToolName,
)
from reactor_agent.spec.snapshot import ModelSnapshot
from reactor_agent.spec.tool_args import (
    CloseCaseArgs,
    ConnectArgs,
    ConversionReaction,
    EnsureCaseArgs,
    EquilibriumReaction,
    FeedConditions,
    ReadSnapshotArgs,
    SaveCaseArgs,
    SetSpecArgs,
    SolveArgs,
)

pytestmark = pytest.mark.hysys

SENTINEL = -32767.0


def fail_with(executor, step):
    """执行一个应当失败的步骤，返回错误。"""
    result = executor.call(step.tool, step.args)
    assert not result.ok, f"{step.tool} 本该失败"
    return result.error


def numbers_in(value):
    """递归取出一个 dump 里的全部数字。"""
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield float(value)
    elif isinstance(value, dict):
        for item in value.values():
            yield from numbers_in(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from numbers_in(item)


class TestSessionAndCase:
    def test_connect_reports_version_and_the_process_it_launched(self, executor, backend):
        result = executor.call(ToolName.SESSION_CONNECT, ConnectArgs(visible=False))
        assert result.ok
        assert result.status is ResultStatus.UNCHANGED
        assert backend.is_running()
        assert "Version 15" in result.data.version
        assert result.data.process_id is not None
        assert result.data.reused_instance is False

    def test_case_ensure_is_reentrant_and_refuses_a_second_case(
        self, executor, fresh_case, tmp_path
    ):
        again = executor.call(ToolName.CASE_ENSURE, EnsureCaseArgs(path=fresh_case))
        assert again.ok
        assert again.status is ResultStatus.UNCHANGED
        other = executor.call(ToolName.CASE_ENSURE, EnsureCaseArgs(path=tmp_path / "other.hsc"))
        assert other.error.code is ErrorCode.CONFLICT

    def test_new_case_refuses_an_existing_file_and_missing_directory(
        self, executor, fresh_case, tmp_path
    ):
        executor.call(ToolName.CASE_CLOSE, CloseCaseArgs(save=False))
        taken = executor.call(ToolName.CASE_ENSURE, EnsureCaseArgs(path=fresh_case))
        assert taken.error.code is ErrorCode.CONFLICT
        missing = tmp_path / "no_such_dir" / "model.hsc"
        result = executor.call(ToolName.CASE_ENSURE, EnsureCaseArgs(path=missing))
        assert result.error.code is ErrorCode.IO
        assert result.error.retryable

    def test_save_close_and_reopen_keep_the_solved_model(self, executor, fresh_case):
        results = run_steps(executor, conversion_model())
        saved = executor.call(ToolName.CASE_SAVE, SaveCaseArgs())
        assert saved.ok
        assert saved.data.size_bytes > 0
        closed = executor.call(ToolName.CASE_CLOSE, CloseCaseArgs(save=False))
        assert closed.data.path == saved.data.path
        reopened = executor.call(
            ToolName.CASE_ENSURE, EnsureCaseArgs(path=fresh_case, mode=CaseMode.OPEN)
        )
        assert reopened.ok
        snapshot = executor.call(ToolName.MODEL_READ_SNAPSHOT, ReadSnapshotArgs()).data
        assert snapshot.solve.solved
        assert fractions_of(stream_of(snapshot, "Vap")) == fractions_of(
            stream_of(results[-1].data, "Vap")
        )

    def test_opening_a_missing_file_fails_before_touching_hysys(self, executor, case_path):
        result = executor.call(
            ToolName.CASE_ENSURE, EnsureCaseArgs(path=case_path, mode=CaseMode.OPEN)
        )
        assert result.error.code is ErrorCode.IO

    def test_tools_that_need_a_case_say_so(self, executor):
        executor.call(ToolName.CASE_CLOSE, CloseCaseArgs(save=False))
        result = executor.call(ToolName.MODEL_READ_SNAPSHOT, ReadSnapshotArgs())
        assert result.error.code is ErrorCode.NOT_FOUND
        closed_again = executor.call(ToolName.CASE_CLOSE, CloseCaseArgs(save=False))
        assert closed_again.ok
        assert closed_again.status is ResultStatus.UNCHANGED


class TestBasis:
    def test_unknown_component_is_a_component_error(self, executor, fresh_case):
        step = thermo("Methane", "Watr")
        error = fail_with(executor, step)
        assert error.code is ErrorCode.COMPONENT_NOT_FOUND
        assert not error.retryable

    def test_component_name_must_be_the_canonical_one(self, executor, fresh_case):
        error = fail_with(executor, thermo("methane"))
        assert error.code is ErrorCode.COMPONENT_NOT_FOUND
        assert error.details["canonical"] == "Methane"

    def test_different_thermo_on_an_existing_basis_is_a_conflict(self, executor, fresh_case):
        run_steps(executor, [thermo(*TOLUENE_COMPONENTS)])
        error = fail_with(executor, thermo("Toluene", "Benzene"))
        assert error.code is ErrorCode.CONFLICT

    def test_flowsheet_tools_need_the_basis_to_be_finished_first(self, executor, fresh_case):
        error = fail_with(executor, stream("Feed"))
        assert error.code is ErrorCode.BASIS_LOCKED

    def test_reaction_with_a_component_outside_the_basis_is_rejected(self, executor, fresh_case):
        run_steps(executor, [thermo("Methane", "H2O")])
        wrong = ConversionReaction(
            stoichiometry=terms(("Methane", -1.0), ("CO", 1.0)),
            base_component="Methane",
            conversion_percent=50.0,
        )
        assert fail_with(executor, reaction("Rxn-1", wrong)).code is ErrorCode.COMPONENT_NOT_FOUND

    def test_unbalanced_reaction_is_invalid(self, executor, fresh_case):
        run_steps(executor, [thermo("Methane", "H2O", "CO", "Hydrogen")])
        unbalanced = EquilibriumReaction(
            stoichiometry=terms(("Methane", -1.0), ("H2O", -1.0), ("CO", 1.0), ("Hydrogen", 2.0))
        )
        assert fail_with(executor, reaction("Rxn-1", unbalanced)).code is ErrorCode.REACTION_INVALID

    def test_reaction_set_needs_existing_reactions(self, executor, fresh_case):
        run_steps(executor, [thermo(*TOLUENE_COMPONENTS)])
        assert fail_with(executor, reaction_set("RxnSet-1", "Nope")).code is ErrorCode.NOT_FOUND

    def test_different_stoichiometry_for_an_existing_reaction_is_a_conflict(
        self, executor, fresh_case
    ):
        steps = conversion_model()
        run_steps(executor, steps[:3])
        other = ConversionReaction(
            stoichiometry=terms(
                ("Toluene", -2.0), ("Benzene", 1.0), ("p-Xylene", 0.5), ("m-Xylene", 0.5)
            ),
            base_component="Toluene",
            conversion_percent=50.0,
        )
        assert fail_with(executor, reaction("Rxn-1", other)).code is ErrorCode.CONFLICT


class TestFlowsheet:
    def test_stream_with_other_conditions_is_a_conflict_and_is_not_modified(
        self, executor, fresh_case
    ):
        steps = conversion_model()
        run_steps(executor, steps[:4])
        hotter = FeedConditions(
            temperature_c=400.0,
            pressure_bar=25.0,
            composition=composition(Toluene=1.0),
            mass_flow_kg_h=10000.0,
        )
        error = fail_with(executor, feed("Feed", hotter))
        assert error.code is ErrorCode.CONFLICT
        assert "温度" in error.details["differences"]
        snapshot = executor.call(ToolName.MODEL_READ_SNAPSHOT, ReadSnapshotArgs()).data
        assert stream_of(snapshot, "Feed").temperature_c == pytest.approx(380.0)

    def test_stream_with_unknown_component_is_rejected(self, executor, fresh_case):
        run_steps(executor, [thermo("Toluene")])
        conditions = FeedConditions(
            temperature_c=380.0,
            pressure_bar=25.0,
            composition=composition(Benzene=1.0),
            mass_flow_kg_h=1000.0,
        )
        error = fail_with(executor, feed("Feed", conditions))
        assert error.code is ErrorCode.COMPONENT_NOT_FOUND

    def test_reactor_needs_existing_streams(self, executor, fresh_case):
        steps = conversion_model()
        run_steps(executor, steps[:3])
        bad = reactor(
            name="CRV-100",
            reactor_type=ReactorType.CONVERSION,
            feeds=("Feed",),
            vapour_product="Vap",
            liquid_product="Liq",
            reaction_set="RxnSet-1",
            heat_mode=HeatMode.ADIABATIC,
        )
        assert fail_with(executor, bad).code is ErrorCode.NOT_FOUND

    def test_equilibrium_reaction_set_cannot_be_attached_to_a_conversion_reactor(
        self, executor, backend, fresh_case
    ):
        run_steps(executor, equilibrium_model((710.0,))[:7])
        wrong = reactor(
            name="CRV-100",
            reactor_type=ReactorType.CONVERSION,
            feeds=("Feed",),
            vapour_product="Vap",
            liquid_product="Liq",
            reaction_set="RxnSet-1",
            heat_mode=HeatMode.ADIABATIC,
        )
        assert fail_with(executor, wrong).code is ErrorCode.SET_INCOMPATIBLE
        assert backend.dialog_messages() == ()

    def test_same_name_with_another_reactor_type_is_a_conflict_and_never_calls_add(
        self, executor, backend, fresh_case
    ):
        run_steps(executor, conversion_model())
        as_gibbs = reactor(
            name="CRV-100",
            reactor_type=ReactorType.GIBBS,
            feeds=("Feed",),
            vapour_product="Vap",
            liquid_product="Liq",
            heat_mode=HeatMode.ADIABATIC,
        )
        assert fail_with(executor, as_gibbs).code is ErrorCode.CONFLICT
        assert backend.dialog_messages() == ()

    def test_pfr_and_cstr_are_not_supported_yet(self, executor, fresh_case):
        run_steps(executor, conversion_model()[:3])
        for reactor_type in (ReactorType.PFR, ReactorType.CSTR):
            step = reactor(
                name="PFR-100",
                reactor_type=reactor_type,
                feeds=("Feed",),
                vapour_product="Vap",
                liquid_product="Liq",
                heat_mode=HeatMode.ADIABATIC,
            )
            assert fail_with(executor, step).code is ErrorCode.UNSUPPORTED

    def test_duty_cannot_be_specified_on_a_gibbs_reactor_yet(self, executor, fresh_case):
        run_steps(executor, equilibrium_model((710.0,))[:3])
        step = reactor(
            name="GBR-100",
            reactor_type=ReactorType.GIBBS,
            feeds=("Feed",),
            vapour_product="Vap",
            liquid_product="Liq",
            energy_stream="Q-100",
            heat_mode=HeatMode.SPECIFIED_DUTY,
        )
        assert fail_with(executor, step).code is ErrorCode.UNSUPPORTED

    def test_outlet_temperature_of_an_adiabatic_reactor_cannot_be_specified(
        self, executor, fresh_case
    ):
        run_steps(executor, conversion_model())
        spec = SetSpecArgs(
            object_name="CRV-100", variable=SpecVariable.OUTLET_TEMPERATURE_C, value=500.0
        )
        result = executor.call(ToolName.FLOWSHEET_SET_SPEC, spec)
        assert result.error.code is ErrorCode.RULE

    def test_set_spec_on_a_missing_reactor_or_unconnected_duty_is_reported(
        self, executor, fresh_case
    ):
        run_steps(executor, conversion_model())
        missing = SetSpecArgs(
            object_name="Nope", variable=SpecVariable.OUTLET_TEMPERATURE_C, value=500.0
        )
        assert executor.call(ToolName.FLOWSHEET_SET_SPEC, missing).error.code is ErrorCode.NOT_FOUND
        no_energy = SetSpecArgs(object_name="CRV-100", variable=SpecVariable.DUTY_KW, value=1.0)
        assert executor.call(ToolName.FLOWSHEET_SET_SPEC, no_energy).error.code is ErrorCode.RULE

    def test_duty_can_be_specified_instead_of_the_outlet_temperature(self, executor, fresh_case):
        results = run_steps(executor, equilibrium_model((710.0,)))
        duty_kw = results[-1].data.energy_streams[0].duty_kw
        # 另建一台同样的反应器（物流只能属于一台反应器，所以进出料另起），规定热负荷，
        # 出口温度应当回到 710 °C（台账 L22）。
        run_steps(
            executor,
            [
                feed("Feed-2", steam_feed_conditions()),
                stream("Vap-2"),
                stream("Liq-2"),
                energy("Q-200"),
                reactor(
                    name="ERV-200",
                    reactor_type=ReactorType.EQUILIBRIUM,
                    feeds=("Feed-2",),
                    vapour_product="Vap-2",
                    liquid_product="Liq-2",
                    energy_stream="Q-200",
                    reaction_set="RxnSet-1",
                    heat_mode=HeatMode.SPECIFIED_DUTY,
                ),
            ],
        )
        spec = SetSpecArgs(object_name="ERV-200", variable=SpecVariable.DUTY_KW, value=duty_kw)
        assert executor.call(ToolName.FLOWSHEET_SET_SPEC, spec).ok
        snapshot = run_steps(executor, [SOLVE, SNAPSHOT])[-1].data
        assert stream_of(snapshot, "Vap-2").temperature_c == pytest.approx(710.0, abs=0.05)


class TestSolveAndSnapshot:
    def test_model_whose_feed_has_no_specification_is_not_solved(self, executor, fresh_case):
        run_steps(executor, conversion_model()[:3])
        run_steps(
            executor,
            [
                stream("Feed"),
                stream("Vap"),
                stream("Liq"),
                reactor(
                    name="CRV-100",
                    reactor_type=ReactorType.CONVERSION,
                    feeds=("Feed",),
                    vapour_product="Vap",
                    liquid_product="Liq",
                    reaction_set="RxnSet-1",
                    heat_mode=HeatMode.ADIABATIC,
                ),
            ],
        )
        result = executor.call(ToolName.SOLVER_SOLVE, SolveArgs())
        assert not result.ok
        assert result.error.code is ErrorCode.NOT_SOLVED
        assert "CRV-100" in result.error.details
        assert not result.error.retryable

    def test_solved_model_reports_every_object_ok(self, executor, fresh_case):
        run_steps(executor, conversion_model())
        result = executor.call(ToolName.SOLVER_SOLVE, SolveArgs(timeout_s=30.0))
        assert result.ok
        assert result.data.status.solved
        assert {item.name for item in result.data.status.objects} == {
            "Feed",
            "Vap",
            "Liq",
            "CRV-100",
        }

    def test_snapshot_never_contains_the_hysys_null_sentinel(self, executor, fresh_case):
        results = run_steps(executor, conversion_model())
        snapshot = results[-1].data
        assert isinstance(snapshot, ModelSnapshot)
        liquid = stream_of(snapshot, "Liq")
        assert liquid.molar_flow_kmol_h is None or abs(liquid.molar_flow_kmol_h) < 1e-6
        for number in numbers_in(snapshot.model_dump(mode="json")):
            assert not math.isclose(number, SENTINEL, abs_tol=1.0), number

    def test_snapshot_of_a_half_built_model_has_none_for_unknown_values(self, executor, fresh_case):
        run_steps(executor, [thermo("Toluene", "Benzene"), stream("Mystery")])
        snapshot = executor.call(ToolName.MODEL_READ_SNAPSHOT, ReadSnapshotArgs()).data
        mystery = stream_of(snapshot, "Mystery")
        assert mystery.temperature_c is None
        assert mystery.molar_flow_kmol_h is None
        assert all(item.mole_fraction is None for item in mystery.components)
        assert not snapshot.solve.solved
        assert snapshot.thermo.property_package is PropertyPackage.PENG_ROBINSON
        for number in numbers_in(snapshot.model_dump(mode="json")):
            assert not math.isclose(number, SENTINEL, abs_tol=1.0), number

    def test_snapshot_describes_the_model_that_was_built(self, executor, fresh_case):
        snapshot = run_steps(executor, equilibrium_model((710.0,)))[-1].data
        assert [c.name for c in snapshot.thermo.components] == [
            "Methane",
            "H2O",
            "CO",
            "CO2",
            "Hydrogen",
        ]
        assert {r.name for r in snapshot.reactions} == {"Rxn-1", "Rxn-2"}
        assert snapshot.reaction_sets[0].reactions == ("Rxn-1", "Rxn-2")
        assert snapshot.reaction_sets[0].attached_to_fluid_package
        reactor_snapshot = snapshot.reactors[0]
        assert reactor_snapshot.reactor_type is ReactorType.EQUILIBRIUM
        assert reactor_snapshot.feeds == ("Feed",)
        assert reactor_snapshot.energy_stream == "Q-100"
        assert reactor_snapshot.pressure_drop_bar == pytest.approx(0.0)
        assert snapshot.thermo.components[4].formula
        carbon_free = [c for c in snapshot.thermo.components if c.is_solid]
        assert carbon_free == []

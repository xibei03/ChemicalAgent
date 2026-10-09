"""归一化结果：出料、干基组成、热负荷、V8；任务结局的判定。"""

import pytest

from builders import equilibrium_scenario, provenance
from reactor_agent.recipes import recipe_for
from reactor_agent.spec.enums import CheckId, CheckSeverity, TaskStatus
from reactor_agent.spec.results import CaseRecord, CheckResult, NormalizedResult
from reactor_agent.spec.snapshot import EnergyStreamSnapshot
from reactor_agent.validation.checks import run_common_checks
from reactor_agent.validation.normalized import assemble_result, decide_outcome, requested_check


def result_for(scenario) -> NormalizedResult:
    recipe = recipe_for(scenario.spec.reactor_type)
    checks = (*run_common_checks(scenario.context), *recipe.checks(scenario.context))
    return assemble_result(scenario.context, checks, provenance())


def outlet(result, name):
    return next(item for item in result.outlets if item.name == name)


def component(stream, name):
    return next(item for item in stream.components if item.name == name)


class TestAssembly:
    def test_the_result_carries_case_assumptions_and_provenance(self, equilibrium):
        result = result_for(equilibrium)
        assert result.case_name == "T710"
        assert result.assumptions == equilibrium.spec.assumptions
        assert result.provenance == provenance()

    def test_outlets_are_the_system_outlets_in_plan_order(
        self, conversion, equilibrium, gasification
    ):
        assert [o.name for o in result_for(conversion).outlets] == ["Vap", "Liq"]
        assert [o.name for o in result_for(equilibrium).outlets] == ["Vap", "Liq"]
        assert [o.name for o in result_for(gasification).outlets] == ["Vap-2", "Liq-1", "Liq-2"]

    def test_an_outlet_keeps_its_state_flows_and_composition(self, equilibrium):
        vapour = outlet(result_for(equilibrium), "Vap")
        assert (vapour.temperature_c, vapour.pressure_bar) == (710.0, 13.5)
        assert vapour.molar_flow_kmol_h == pytest.approx(4800.0)
        carbon_monoxide = component(vapour, "CO")
        assert carbon_monoxide.mole_fraction == pytest.approx(350 / 4800)
        assert carbon_monoxide.molar_flow_kmol_h == pytest.approx(350.0)
        assert carbon_monoxide.mass_flow_kg_h == pytest.approx(350 * 28.010)

    def test_a_missing_outlet_is_left_out_and_not_invented(self, equilibrium):
        result = result_for(equilibrium.without_stream("Liq"))
        assert [o.name for o in result.outlets] == ["Vap"]

    def test_the_result_survives_a_json_round_trip(self, scenario):
        result = result_for(scenario)
        assert NormalizedResult.model_validate_json(result.model_dump_json()) == result


class TestDryBasis:
    def test_water_is_taken_out_of_the_gas_outlet(self, equilibrium):
        vapour = outlet(result_for(equilibrium), "Vap")
        # 出口 4800 kmol/h，水 1950，干基 2850
        assert component(vapour, "Hydrogen").dry_mole_fraction == pytest.approx(1850 / 2850)
        assert component(vapour, "Methane").dry_mole_fraction == pytest.approx(450 / 2850)
        assert component(vapour, "CO").dry_mole_fraction == pytest.approx(350 / 2850)
        assert component(vapour, "CO2").dry_mole_fraction == pytest.approx(200 / 2850)
        assert component(vapour, "H2O").dry_mole_fraction is None

    def test_the_dry_fractions_add_up_to_one(self, equilibrium):
        vapour = outlet(result_for(equilibrium), "Vap")
        total = sum(c.dry_mole_fraction or 0.0 for c in vapour.components)
        assert total == pytest.approx(1.0)

    def test_an_outlet_without_water_has_the_same_dry_and_wet_composition(self, conversion):
        vapour = outlet(result_for(conversion), "Vap")
        for item in vapour.components:
            assert item.dry_mole_fraction == pytest.approx(item.mole_fraction)

    def test_only_gas_outlets_get_a_dry_basis(self, gasification):
        result = result_for(gasification)
        assert all(c.dry_mole_fraction is None for c in outlet(result, "Liq-1").components)
        assert any(c.dry_mole_fraction is not None for c in outlet(result, "Vap-2").components)

    def test_the_dry_basis_is_always_given_without_being_requested(self, equilibrium):
        assert equilibrium.spec.metrics  # 规格里没有任何一项指标是干基
        assert component(outlet(result_for(equilibrium), "Vap"), "CO").dry_mole_fraction

    def test_an_empty_gas_stream_has_no_dry_basis_and_does_not_divide_by_zero(self, conversion):
        empty = tuple(
            c.model_copy(
                update={"molar_flow_kmol_h": 0.0, "mass_flow_kg_h": 0.0, "mole_fraction": 0.0}
            )
            for c in conversion.snapshot.stream("Vap").components
        )
        result = result_for(conversion.with_stream("Vap", components=empty, molar_flow_kmol_h=0.0))
        assert all(c.dry_mole_fraction is None for c in outlet(result, "Vap").components)

    def test_a_flow_that_cannot_be_read_gives_no_dry_basis(self, equilibrium):
        broken = equilibrium.with_component("Vap", "CO", molar_flow_kmol_h=None)
        assert all(
            c.dry_mole_fraction is None for c in outlet(result_for(broken), "Vap").components
        )


class TestDuty:
    def test_the_duty_is_the_sum_of_the_energy_streams(self, equilibrium, gasification):
        assert result_for(equilibrium).duty_kw == pytest.approx(39989.0)
        assert result_for(gasification).duty_kw == pytest.approx(60000.0 + 25000.0)

    def test_an_adiabatic_reactor_exchanges_no_heat(self, conversion):
        assert result_for(conversion).duty_kw == 0.0

    def test_an_unreadable_duty_is_none_and_not_zero(self, equilibrium):
        broken = equilibrium.with_snapshot(
            energy_streams=(EnergyStreamSnapshot(name="Q-100", duty_kw=None),)
        )
        assert result_for(broken).duty_kw is None


class TestRequestedCheck:
    def test_v8_passes_when_every_requested_metric_has_a_value(self, equilibrium):
        result = result_for(equilibrium)
        last = result.checks[-1]
        assert last.check_id is CheckId.REQUESTED
        assert last.passed
        assert last.severity is CheckSeverity.FATAL

    def test_v8_fails_and_names_the_metric_that_has_no_value(self, equilibrium):
        broken = equilibrium.with_component("Vap", "CO", molar_flow_kmol_h=0.0)
        last = result_for(broken).checks[-1]
        assert not last.passed
        assert "Hydrogen/CO" in last.actual

    def test_v8_passes_when_nothing_was_requested(self, conversion):
        assert result_for(conversion).metrics == ()
        assert result_for(conversion).checks[-1].passed

    def test_v8_is_added_after_the_checks_that_were_passed_in(self, equilibrium):
        ids = [check.check_id for check in result_for(equilibrium).checks]
        assert ids[:7] == [CheckId(f"V{n}") for n in range(1, 8)]
        assert ids[7] is CheckId.REQUESTED

    def test_requested_check_on_its_own(self, equilibrium):
        metrics = result_for(equilibrium).metrics
        assert requested_check(metrics).passed
        none_valued = tuple(m.model_copy(update={"value": None}) for m in metrics)
        assert not requested_check(none_valued).passed


def warning():
    return CheckResult(
        check_id=CheckId.CONSERVATION,
        passed=False,
        severity=CheckSeverity.WARNING,
        expected="x",
        actual="y",
        message="z",
    )


def record(scenario, saved=True, extra_check=None, name=None):
    result = result_for(scenario)
    if extra_check is not None:
        result = result.model_copy(update={"checks": (*result.checks, extra_check)})
    return CaseRecord(case_name=name or result.case_name, result=result, case_file_saved=saved)


class TestOutcome:
    def test_all_checks_passing_and_the_file_saved_is_complete(self, equilibrium):
        assert decide_outcome(["T710"], [record(equilibrium)]) is TaskStatus.COMPLETE

    def test_only_warnings_give_complete_with_warnings(self, equilibrium):
        records = [record(equilibrium, extra_check=warning())]
        assert decide_outcome(["T710"], records) is TaskStatus.COMPLETE_WITH_WARNINGS

    def test_a_failed_fatal_check_is_a_failure(self, equilibrium):
        broken = equilibrium.with_stream("Vap", temperature_c=711.0)
        assert decide_outcome(["T710"], [record(broken)]) is TaskStatus.FAILED

    def test_a_fatal_failure_wins_over_a_warning(self, equilibrium):
        broken = equilibrium.with_stream("Vap", temperature_c=711.0)
        records = [record(broken, extra_check=warning())]
        assert decide_outcome(["T710"], records) is TaskStatus.FAILED

    def test_a_case_without_a_result_is_a_failure(self, equilibrium):
        records = [CaseRecord(case_name="T710", result=None, case_file_saved=True)]
        assert decide_outcome(["T710"], records) is TaskStatus.FAILED

    def test_a_case_without_a_record_is_a_failure(self, equilibrium):
        assert decide_outcome(["T710", "T600"], [record(equilibrium)]) is TaskStatus.FAILED

    def test_a_case_file_that_was_not_saved_is_a_failure(self, equilibrium):
        assert decide_outcome(["T710"], [record(equilibrium, saved=False)]) is TaskStatus.FAILED

    def test_every_case_has_to_be_complete(self):
        hot, cold = equilibrium_scenario("T710"), equilibrium_scenario("T600")
        names = ["T710", "T600"]
        assert decide_outcome(names, [record(hot), record(cold)]) is TaskStatus.COMPLETE
        bad = cold.with_stream("Vap", temperature_c=650.0)
        assert decide_outcome(names, [record(hot), record(bad)]) is TaskStatus.FAILED
        assert decide_outcome(names, [record(hot), record(cold, saved=False)]) is TaskStatus.FAILED

    def test_records_of_cases_the_spec_does_not_have_are_ignored(self, equilibrium):
        extra = record(equilibrium, name="other")
        assert decide_outcome(["T710"], [record(equilibrium), extra]) is TaskStatus.COMPLETE

    def test_the_outcome_only_ever_depends_on_the_first_three_statuses(self, equilibrium):
        possible = {
            decide_outcome(["T710"], [record(equilibrium)]),
            decide_outcome(["T710"], []),
            decide_outcome(["T710"], [record(equilibrium, extra_check=warning())]),
        }
        assert possible <= {
            TaskStatus.COMPLETE,
            TaskStatus.COMPLETE_WITH_WARNINGS,
            TaskStatus.FAILED,
        }

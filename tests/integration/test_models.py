"""三个模型都只通过工具建成，结果与参照值的偏差在容差内；每个 ensure 再调一次是“未改变”。"""

import pytest
from hysys_models import (
    CARBON_AMOUNT_TOLERANCE,
    CARBON_MOLE_FRACTION,
    CO_YIELD_RANGE,
    CONVERSION_FRACTIONS,
    CONVERSION_TOLERANCE,
    EQUILIBRIUM_REFERENCE,
    EQUILIBRIUM_TOLERANCE,
    FIXED_K_FRACTIONS,
    FIXED_K_TOLERANCE,
    GAS_FRACTION_TOLERANCE,
    GASIFICATION_FEED_KMOL_H,
    REFERENCE_GAS_FRACTIONS,
    REFERENCE_UNREACTED_CARBON_KMOL_H,
    conversion_model,
    equilibrium_model,
    fixed_k_model,
    fractions_of,
    gasification_model,
    gibbs_gas_model,
    molar_flows_of,
    stream_of,
)
from steps import run_steps

from reactor_agent.spec.enums import ResultStatus
from reactor_agent.spec.snapshot import ModelSnapshot

pytestmark = pytest.mark.hysys


def snapshots(results) -> list[ModelSnapshot]:
    return [r.data for r in results if r.data is not None and isinstance(r.data, ModelSnapshot)]


def test_conversion_reactor_matches_the_analytic_solution(executor, fresh_case):
    results = run_steps(executor, conversion_model())
    snapshot = snapshots(results)[-1]
    assert snapshot.solve.solved
    outlet = fractions_of(stream_of(snapshot, "Vap"))
    for name, expected in CONVERSION_FRACTIONS.items():
        assert outlet[name] == pytest.approx(expected, abs=CONVERSION_TOLERANCE), name
    feed = stream_of(snapshot, "Feed")
    assert feed.molar_flow_kmol_h == pytest.approx(10000.0 / 92.14, rel=1e-3)
    assert stream_of(snapshot, "Vap").mass_flow_kg_h == pytest.approx(10000.0, rel=1e-4)


@pytest.mark.parametrize("temperature_c", sorted(EQUILIBRIUM_REFERENCE))
def test_equilibrium_reactor_matches_the_reference_at_each_outlet_temperature(
    executor, fresh_case, temperature_c
):
    results = run_steps(executor, equilibrium_model((temperature_c,)))
    snapshot = snapshots(results)[-1]
    assert snapshot.solve.solved
    expected_fractions, expected_flow = EQUILIBRIUM_REFERENCE[temperature_c]
    outlet = stream_of(snapshot, "Vap")
    assert outlet.temperature_c == pytest.approx(temperature_c, abs=1e-6)
    for name, expected in expected_fractions.items():
        assert fractions_of(outlet)[name] == pytest.approx(expected, abs=EQUILIBRIUM_TOLERANCE)
    assert outlet.molar_flow_kmol_h == pytest.approx(expected_flow, rel=0.02)
    assert next(item.duty_kw for item in snapshot.energy_streams) > 0.0


def test_equilibrium_reactor_can_move_between_outlet_temperatures_and_back(executor, fresh_case):
    results = run_steps(executor, equilibrium_model((710.0, 600.0, 710.0)))
    first, second, third = snapshots(results)
    assert fractions_of(stream_of(first, "Vap")) != fractions_of(stream_of(second, "Vap"))
    again = fractions_of(stream_of(third, "Vap"))
    for name, value in fractions_of(stream_of(first, "Vap")).items():
        assert again[name] == pytest.approx(value, abs=1e-6)


def test_gibbs_reactor_without_carbon_agrees_with_the_equilibrium_reference(executor, fresh_case):
    snapshot = snapshots(run_steps(executor, gibbs_gas_model(710.0)))[-1]
    assert snapshot.solve.solved
    expected_fractions, expected_flow = EQUILIBRIUM_REFERENCE[710.0]
    outlet = stream_of(snapshot, "Vap")
    for name, expected in expected_fractions.items():
        assert fractions_of(outlet)[name] == pytest.approx(expected, abs=EQUILIBRIUM_TOLERANCE)
    assert outlet.molar_flow_kmol_h == pytest.approx(expected_flow, rel=0.02)
    assert snapshot.reactors[0].reaction_set is None


def test_fixed_equilibrium_constant_gives_the_mass_action_composition(executor, fresh_case):
    snapshot = snapshots(run_steps(executor, fixed_k_model()))[-1]
    assert snapshot.solve.solved
    outlet = fractions_of(stream_of(snapshot, "Vap"))
    for name, expected in FIXED_K_FRACTIONS.items():
        assert outlet[name] == pytest.approx(expected, abs=FIXED_K_TOLERANCE), name


def test_gibbs_reactor_with_solid_carbon_gives_the_reference_co_yield(executor, fresh_case):
    results = run_steps(executor, gasification_model())
    snapshot = snapshots(results)[-1]
    assert snapshot.solve.solved
    gas = stream_of(snapshot, "Gas-2")
    assert gas.temperature_c == pytest.approx(1400.0, abs=1e-6)
    carbon_in = GASIFICATION_FEED_KMOL_H * CARBON_MOLE_FRACTION
    co_yield = molar_flows_of(gas)["CO"] / carbon_in
    assert CO_YIELD_RANGE[0] <= co_yield <= CO_YIELD_RANGE[1], co_yield
    for name, expected in REFERENCE_GAS_FRACTIONS.items():
        assert fractions_of(gas)[name] == pytest.approx(expected, abs=GAS_FRACTION_TOLERANCE)
    unreacted = molar_flows_of(stream_of(snapshot, "Carbon-1"))["Carbon"]
    assert unreacted == pytest.approx(
        REFERENCE_UNREACTED_CARBON_KMOL_H, rel=CARBON_AMOUNT_TOLERANCE
    )


def single_temperature_equilibrium_model():
    return equilibrium_model((710.0,))


@pytest.mark.parametrize(
    "model",
    [conversion_model, single_temperature_equilibrium_model, gasification_model],
    ids=lambda m: m.__name__,
)
def test_every_ensure_called_again_is_unchanged_and_creates_nothing(executor, fresh_case, model):
    steps = model()
    first = run_steps(executor, steps)
    second = run_steps(executor, steps)
    assert ResultStatus.CREATED in {r.status for r in first}
    assert {r.status for r in second} == {ResultStatus.UNCHANGED}
    before, after = snapshots(first)[-1], snapshots(second)[-1]
    assert len(after.streams) == len(before.streams)
    assert len(after.energy_streams) == len(before.energy_streams)
    assert len(after.reactions) == len(before.reactions)
    assert len(after.reaction_sets) == len(before.reaction_sets)
    assert len(after.reactors) == len(before.reactors)

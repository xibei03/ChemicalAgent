"""单位换算和组成归一化：每一类换算至少一个用例，并且包含提示词里给出的具体数。

纯函数，不需要 HYSYS 和 LLM。单位表读的是 config/units.yaml 本身，所以检查的就是真正在用的那张表。
"""

import math
from pathlib import Path

import pytest

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.composition import CompositionError, mole_fractions
from reactor_agent.spec.enums import PressureBasis
from reactor_agent.spec.task_spec import AmountScale, CompositionBasis
from reactor_agent.spec.units import (
    FlowKind,
    UnitEntry,
    UnitTable,
    load_unit_table,
    pressure_unit_basis,
    to_conversion_percent,
    to_duty_kw,
    to_flow,
    to_pressure_bar,
    to_temperature_c,
    unit_key,
)
from task_builders import components, composition, units

TABLE = units()
ABSOLUTE, GAUGE = PressureBasis.ABSOLUTE, PressureBasis.GAUGE


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (520, "℃", 520.0),
        (710, "°C", 710.0),
        (40, "摄氏度", 40.0),
        (1400, "度", 1400.0),
        (300, "K", 26.85),
        (212, "°F", 100.0),
    ],
)
def test_temperatures_become_celsius(value, unit, expected):
    celsius = to_temperature_c(TABLE, value, unit)
    assert celsius is not None and math.isclose(celsius, expected, abs_tol=1e-6)


def test_zero_kelvin_is_converted_not_mistaken_for_a_missing_value():
    celsius = to_temperature_c(TABLE, 0.0, "K")
    assert celsius is not None and math.isclose(celsius, -273.15)


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (13.5, "bar", 13.5),
        (2.5, "MPa", 25.0),
        (101.325, "kPa", 1.01325),
        (1, "atm", 1.01325),
        (200000, "Pa", 2.0),
    ],
)
def test_absolute_pressures_become_bar(value, unit, expected):
    bar = to_pressure_bar(TABLE, value, unit, ABSOLUTE)
    assert bar is not None and math.isclose(bar, expected, rel_tol=1e-9)


def test_a_gauge_pressure_gets_one_atmosphere_added():
    bar = to_pressure_bar(TABLE, 1.0, "MPa", GAUGE)
    assert bar is not None and math.isclose(bar, 11.01325)


def test_a_unit_can_carry_its_own_pressure_basis():
    assert pressure_unit_basis(TABLE, "barg") is GAUGE
    assert pressure_unit_basis(TABLE, "bara") is ABSOLUTE
    assert pressure_unit_basis(TABLE, "bar") is PressureBasis.UNSTATED
    assert pressure_unit_basis(TABLE, "furlong") is None


@pytest.mark.parametrize(
    ("value", "unit", "kind", "expected"),
    [
        (1000, "kmol/h", FlowKind.MOLAR, 1000.0),
        (10000, "kg/h", FlowKind.MASS, 10000.0),
        (30, "t/h", FlowKind.MASS, 30000.0),
        (80000, "Nm3/h", FlowKind.STANDARD_VOLUME, 3569.2),
        (80000, "Nm³/h", FlowKind.STANDARD_VOLUME, 3569.2),
    ],
)
def test_flows_become_kmol_per_hour_or_kg_per_hour(value, unit, kind, expected):
    flow = to_flow(TABLE, value, unit)
    assert flow is not None and flow.kind is kind
    assert math.isclose(flow.value, expected, rel_tol=1e-4)


@pytest.mark.parametrize("unit", ["桶/天", "gal/min", "", "kmol"])
def test_an_unknown_unit_is_none_not_a_guess(unit):
    assert to_flow(TABLE, 1.0, unit) is None


def test_duty_and_conversion_units():
    assert to_duty_kw(TABLE, 85, "MW") == 85000.0
    assert to_conversion_percent(TABLE, 50, "%") == 50.0
    assert to_conversion_percent(TABLE, 0.5, "fraction") == 50.0
    assert to_conversion_percent(TABLE, 0.5, "") == 50.0


def test_unit_spelling_is_compared_after_width_folding_but_keeps_the_case():
    assert unit_key("Nm³ / h") == unit_key("Nm3/h") and unit_key("℃") == unit_key("°C")
    assert unit_key("mW") != unit_key("MW")


def test_a_unit_in_another_case_is_accepted_when_only_one_unit_matches():
    flow = to_flow(TABLE, 80000, "NM3/H")
    assert flow is not None and flow.kind is FlowKind.STANDARD_VOLUME
    assert to_pressure_bar(TABLE, 2.5, "mpa", ABSOLUTE) == 25.0


def table_with(**groups: tuple[UnitEntry, ...]) -> UnitTable:
    """真实的单位表，换掉其中几类单位，重新校验。"""
    return UnitTable.model_validate({**TABLE.model_dump(), **groups})


def test_a_case_difference_that_changes_the_meaning_is_never_guessed():
    milli = UnitEntry(names=("mW",), factor=1e-6)
    table = table_with(duty_kw=(*TABLE.duty_kw, milli))
    assert to_duty_kw(table, 1.0, "MW") == 1000.0
    assert to_duty_kw(table, 1.0, "mW") == pytest.approx(1e-6)
    assert to_duty_kw(table, 1.0, "mw") is None


@pytest.mark.parametrize(
    "group", ["temperature_c", "pressure_bar", "molar_flow_kmol_h", "duty_kw", "conversion_percent"]
)
def test_a_spelling_that_belongs_to_two_conversions_is_rejected(group):
    entries = getattr(TABLE, group)
    repeated = UnitEntry(names=(entries[0].names[0],), factor=7.0)
    with pytest.raises(ValueError, match="重复"):
        table_with(**{group: (*entries, repeated)})


def test_a_spelling_used_by_two_kinds_of_flow_is_rejected():
    taken = TABLE.molar_flow_kmol_h[0].names[0]
    mass = (*TABLE.mass_flow_kg_h, UnitEntry(names=(taken,), factor=1.0))
    with pytest.raises(ValueError, match="重复"):
        table_with(mass_flow_kg_h=mass)


def test_the_same_spelling_in_width_variants_counts_as_a_duplicate():
    repeated = UnitEntry(names=("°C",), factor=1.0)
    with pytest.raises(ValueError, match="重复"):
        table_with(
            temperature_c=(*TABLE.temperature_c, UnitEntry(names=("℃",), factor=2.0), repeated)
        )


def test_a_missing_unit_file_is_an_io_error(tmp_path: Path):
    with pytest.raises(ReactorAgentError) as caught:
        load_unit_table(tmp_path / "nope.yaml")
    assert caught.value.code is ErrorCode.IO


# ---- 组成 ----

TABLE_C = components()


def fractions(*items, basis=CompositionBasis.MOLE, scale=AmountScale.RATIO):
    task = composition(*items, basis=basis, scale=scale)
    return mole_fractions(task, [name for name, _ in items], TABLE_C)


def test_a_mole_ratio_is_normalized():
    result = fractions(("Methane", 1.0), ("H2O", 2.7))
    assert math.isclose(result.fractions["Methane"], 0.2703, abs_tol=1e-4)
    assert math.isclose(result.fractions["H2O"], 0.7297, abs_tol=1e-4)


def test_a_mass_percent_with_a_remainder_becomes_mole_fractions():
    result = fractions(
        ("Carbon", 62.0), ("H2O", None), basis=CompositionBasis.MASS, scale=AmountScale.PERCENT
    )
    assert math.isclose(result.fractions["Carbon"], 0.7099, abs_tol=1e-4)
    assert math.isclose(result.fractions["H2O"], 0.2901, abs_tol=1e-4)
    assert not result.notes


def test_mole_fractions_given_as_decimals_are_kept():
    result = fractions(("CO", 0.25), ("Hydrogen", 0.75), scale=AmountScale.FRACTION)
    assert result.fractions == {"CO": 0.25, "Hydrogen": 0.75}


def test_percentages_that_are_a_little_off_are_normalized_and_noted():
    result = fractions(("CO", 33.3), ("Hydrogen", 33.3), ("CO2", 33.3), scale=AmountScale.PERCENT)
    assert math.isclose(sum(result.fractions.values()), 1.0)
    assert result.notes and "归一化" in result.notes[0]


def test_percentages_that_are_far_off_are_a_user_fixable_problem():
    with pytest.raises(CompositionError) as caught:
        fractions(("CO", 60.0), ("Hydrogen", 30.0), scale=AmountScale.PERCENT)
    assert caught.value.user_fixable and "应当是 100" in str(caught.value)


def test_a_remainder_that_is_used_up_is_a_user_fixable_problem():
    with pytest.raises(CompositionError) as caught:
        fractions(("CO", 100.0), ("Hydrogen", None), scale=AmountScale.PERCENT)
    assert caught.value.user_fixable


def test_a_remainder_is_not_allowed_with_a_ratio():
    with pytest.raises(CompositionError, match="余量"):
        fractions(("CO", 1.0), ("Hydrogen", None), scale=AmountScale.RATIO)


def test_a_negative_share_is_rejected():
    with pytest.raises(CompositionError, match="负"):
        fractions(("CO", -1.0), ("Hydrogen", 2.0))


def test_a_volume_basis_is_a_mole_basis_for_gases_and_an_error_otherwise():
    result = fractions(("CO", 1.0), ("Hydrogen", 1.0), basis=CompositionBasis.VOLUME)
    assert result.fractions == {"CO": 0.5, "Hydrogen": 0.5} and "理想气体" in result.notes[0]
    with pytest.raises(CompositionError, match="液体或固体"):
        fractions(("CO", 1.0), ("H2O", 1.0), basis=CompositionBasis.VOLUME)


def test_duplicate_components_and_empty_compositions_are_rejected():
    with pytest.raises(CompositionError, match="重复"):
        mole_fractions(composition(("CO", 1.0), ("CO", 2.0)), ["CO", "CO"], TABLE_C)
    with pytest.raises(CompositionError, match="没有任何组分"):
        mole_fractions(composition(), [], TABLE_C)

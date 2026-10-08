"""读写带单位的变量：规范单位、空值哨兵转 None、数组变量逐项处理。"""

import pytest

from reactor_agent.backends.hysys_com.variables import (
    NULL_VALUE,
    Quantity,
    read_fractions,
    read_plain,
    read_quantities,
    read_quantity,
    write_fractions,
    write_quantity,
)


class FakeVariable:
    """只实现 Backend 用到的成员：IsKnown、GetValue、SetValue、GetValues、Values。"""

    def __init__(self, value=NULL_VALUE, known=True, values=(), flags=None):
        self.value, self.IsKnown, self.Values = value, known, values
        if flags is not None:
            self.IsKnown = flags
        self.written = []

    def GetValue(self, unit):
        self.unit = unit
        return self.value

    def SetValue(self, value, unit):
        self.written.append((value, unit))

    def GetValues(self, unit):
        self.unit = unit
        return self.Values


def test_unknown_variable_reads_as_none_not_as_the_sentinel():
    variable = FakeVariable(value=NULL_VALUE, known=False)
    assert read_quantity(variable, Quantity.TEMPERATURE) is None


def test_known_variable_is_read_in_the_unit_hysys_understands():
    variable = FakeVariable(value=380.0)
    assert read_quantity(variable, Quantity.TEMPERATURE) == 380.0
    assert variable.unit == "C"
    read_quantity(variable, Quantity.MOLAR_FLOW)
    assert variable.unit == "kgmole/h"


def test_pressure_drop_is_converted_between_kpa_and_bar():
    variable = FakeVariable(value=50.0)
    assert read_quantity(variable, Quantity.PRESSURE_DROP) == pytest.approx(0.5)
    write_quantity(variable, 0.5, Quantity.PRESSURE_DROP)
    assert variable.written == [(pytest.approx(50.0), "kPa")]


def test_write_uses_the_canonical_unit_for_pressure_and_power():
    variable = FakeVariable()
    write_quantity(variable, 13.5, Quantity.PRESSURE)
    write_quantity(variable, 100.0, Quantity.POWER)
    assert variable.written == [(13.5, "bar"), (100.0, "kW")]


def test_array_variable_marks_only_the_unknown_entries_as_none():
    variable = FakeVariable(values=(10.0, NULL_VALUE, 3.0), flags=(True, False, True))
    assert read_quantities(variable, Quantity.MASS_FLOW) == (10.0, None, 3.0)
    assert variable.unit == "kg/h"


def test_array_variable_with_a_single_flag_applies_it_to_every_entry():
    variable = FakeVariable(values=(0.5, 0.5), flags=False)
    assert read_fractions(variable) == (None, None)


def test_fractions_are_read_and_written_without_units():
    variable = FakeVariable(values=(0.25, 0.75), flags=(True, True))
    assert read_fractions(variable) == (0.25, 0.75)
    write_fractions(variable, (0.4, 0.6))
    assert variable.Values == (0.4, 0.6)


@pytest.mark.parametrize(("raw", "expected"), [(NULL_VALUE, None), (0.0, 0.0), (1.0, 1.0)])
def test_plain_members_turn_the_sentinel_into_none(raw, expected):
    assert read_plain(raw) == expected


def test_a_value_close_to_the_sentinel_is_the_sentinel():
    assert read_plain(-32767.0000001) is None

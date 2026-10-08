"""读写带单位的变量：单位字符串和空值哨兵只出现在这个文件里。

HYSYS 的变量用 GetValue(unit) 和 SetValue(value, unit) 读写；没有值的变量读出 -32767.0（台账 H22），
所以读之前先看 IsKnown。离开这个文件，物理量一律是规范单位（°C、bar、kmol/h、kg/h、kW）的
float，或者 None。
"""

import math
from enum import Enum
from typing import Any

NULL_VALUE = -32767.0
NULL_TOLERANCE = 1.0


class Quantity(Enum):
    """物理量的种类：HYSYS 里用的单位，以及换算到规范单位要乘的系数。"""

    TEMPERATURE = ("C", 1.0)
    PRESSURE = ("bar", 1.0)
    # 压降的单位 kPa 验证过，bar 没有；规范单位是 bar。
    PRESSURE_DROP = ("kPa", 0.01)
    # kgmole/h 数值上等于 kmol/h，HYSYS 不认 kmol/h（台账 H29）。
    MOLAR_FLOW = ("kgmole/h", 1.0)
    MASS_FLOW = ("kg/h", 1.0)
    POWER = ("kW", 1.0)

    @property
    def unit(self) -> str:
        """HYSYS 的单位字符串。"""
        return str(self.value[0])

    @property
    def factor(self) -> float:
        """HYSYS 单位的数值乘以它得到规范单位的数值。"""
        return float(self.value[1])


def read_plain(value: Any) -> float | None:
    """读没有 IsKnown 的双精度成员（如 VapourFractionValue）：空值哨兵转成 None。"""
    number = float(value)
    return None if math.isclose(number, NULL_VALUE, abs_tol=NULL_TOLERANCE) else number


def read_quantity(variable: Any, quantity: Quantity) -> float | None:
    """读一个变量，换算成规范单位；没有值返回 None。"""
    if not bool(variable.IsKnown):
        return None
    return float(variable.GetValue(quantity.unit)) * quantity.factor


def write_quantity(variable: Any, value: float, quantity: Quantity) -> None:
    """把规范单位的值写进变量。"""
    variable.SetValue(value / quantity.factor, quantity.unit)


def _known_flags(variable: Any, count: int) -> tuple[bool, ...]:
    """数组变量的 IsKnown 是逐项的元组；个别成员给单个布尔值，这里统一成逐项。"""
    flags = variable.IsKnown
    if isinstance(flags, bool):
        return (flags,) * count
    return tuple(bool(flag) for flag in flags)


def read_quantities(variable: Any, quantity: Quantity) -> tuple[float | None, ...]:
    """读数组变量（按组分的流量），逐项换算成规范单位；没有值的项是 None。"""
    values = tuple(variable.GetValues(quantity.unit))
    flags = _known_flags(variable, len(values))
    return tuple(
        float(value) * quantity.factor if known else None
        for value, known in zip(values, flags, strict=True)
    )


def read_fractions(variable: Any) -> tuple[float | None, ...]:
    """读无量纲的数组变量（摩尔分率）；没有值的项是 None。"""
    values = tuple(variable.Values)
    flags = _known_flags(variable, len(values))
    return tuple(
        float(value) if known else None for value, known in zip(values, flags, strict=True)
    )


def write_fractions(variable: Any, fractions: tuple[float, ...]) -> None:
    """写无量纲的数组变量。长度必须等于组分数，HYSYS 会把和归一化（台账 H14）。"""
    variable.Values = fractions

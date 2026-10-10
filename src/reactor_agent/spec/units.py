"""单位表和换算：原文里的单位写法 → 规范单位。

表在 config/units.yaml。不认识的单位换算返回 None，由调用方变成一个问题，这里不猜。
文件路径由调用方传入，这里不猜路径。
"""

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, model_validator

from reactor_agent.spec.base import FrozenModel
from reactor_agent.spec.enums import PressureBasis
from reactor_agent.spec.loading import parse_model, read_document


def unit_key(text: str) -> str:
    """单位写法比较前的规范化：全角半角统一（℃ 变成 °C，Nm³ 变成 Nm3），去掉空白。区分大小写。"""
    return "".join(unicodedata.normalize("NFKC", text).split())


class UnitEntry(FrozenModel):
    """一组同义的写法，和换算到规范单位的系数：规范值 = 值 × factor + offset。"""

    names: tuple[str, ...]
    factor: Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
    offset: float = 0.0
    basis: PressureBasis = PressureBasis.UNSTATED


class UnitTable(FrozenModel):
    """config/units.yaml 的全部内容。同一类单位里，一个写法（区分大小写）只能指向一个换算。"""

    standard_molar_volume_nm3_per_kmol: Annotated[float, Field(gt=0.0)]
    atmosphere_bar: Annotated[float, Field(gt=0.0)]
    temperature_c: tuple[UnitEntry, ...]
    pressure_bar: tuple[UnitEntry, ...]
    molar_flow_kmol_h: tuple[UnitEntry, ...]
    mass_flow_kg_h: tuple[UnitEntry, ...]
    standard_volume_flow_nm3_h: tuple[UnitEntry, ...]
    duty_kw: tuple[UnitEntry, ...]
    conversion_percent: tuple[UnitEntry, ...]

    @model_validator(mode="after")
    def _names_are_unambiguous(self) -> Self:
        flows = (*self.molar_flow_kmol_h, *self.mass_flow_kg_h, *self.standard_volume_flow_nm3_h)
        groups = (
            self.temperature_c,
            self.pressure_bar,
            flows,
            self.duty_kw,
            self.conversion_percent,
        )
        for group in groups:
            keys = [unit_key(name) for entry in group for name in entry.names]
            if len(set(keys)) != len(keys):
                raise ValueError("单位表里有写法重复，换算不唯一")
        return self


class FlowKind(StrEnum):
    """流量的单位属于哪一类。标准体积流量要按理想气体换算，单独登记假设。"""

    MOLAR = "molar"
    MASS = "mass"
    STANDARD_VOLUME = "standard_volume"


@dataclass(frozen=True)
class FlowValue:
    """换算后的流量：摩尔流量和标准体积流量是 kmol/h，质量流量是 kg/h。"""

    kind: FlowKind
    value: float


def _find(entries: Sequence[UnitEntry], unit: str) -> UnitEntry | None:
    """先按写法原样找；找不到再不分大小写找，而且只在没有歧义时采用（mW 和 MW 差 10^9，不能猜）。"""
    key = unit_key(unit)
    exact = [e for e in entries if key in {unit_key(n) for n in e.names}]
    if exact:
        return exact[0]
    folded = [e for e in entries if key.casefold() in {unit_key(n).casefold() for n in e.names}]
    return folded[0] if len(folded) == 1 else None


def _convert(entries: Sequence[UnitEntry], value: float, unit: str) -> float | None:
    entry = _find(entries, unit)
    return None if entry is None else value * entry.factor + entry.offset


def to_temperature_c(table: UnitTable, value: float, unit: str) -> float | None:
    """温度换算成 °C。"""
    return _convert(table.temperature_c, value, unit)


def to_duty_kw(table: UnitTable, value: float, unit: str) -> float | None:
    """热负荷换算成 kW。"""
    return _convert(table.duty_kw, value, unit)


def to_conversion_percent(table: UnitTable, value: float, unit: str) -> float | None:
    """转化率换算成百分数。"""
    return _convert(table.conversion_percent, value, unit)


def pressure_unit_basis(table: UnitTable, unit: str) -> PressureBasis | None:
    """压力单位自带的基准（barg 是表压，atm 是绝压，bar 没有）。不认识的单位是 None。"""
    entry = _find(table.pressure_bar, unit)
    return None if entry is None else entry.basis


def to_pressure_bar(
    table: UnitTable, value: float, unit: str, basis: PressureBasis
) -> float | None:
    """压力换算成绝压 bar。basis 是表压时加一个标准大气压；调用方保证它不是 UNSTATED。"""
    entry = _find(table.pressure_bar, unit)
    if entry is None:
        return None
    bar = value * entry.factor
    return bar + table.atmosphere_bar if basis is PressureBasis.GAUGE else bar


def to_flow(table: UnitTable, value: float, unit: str) -> FlowValue | None:
    """流量换算：摩尔流量 kmol/h，质量流量 kg/h，标准体积流量按标准摩尔体积换算成 kmol/h。"""
    if (molar := _convert(table.molar_flow_kmol_h, value, unit)) is not None:
        return FlowValue(FlowKind.MOLAR, molar)
    if (mass := _convert(table.mass_flow_kg_h, value, unit)) is not None:
        return FlowValue(FlowKind.MASS, mass)
    volume = _convert(table.standard_volume_flow_nm3_h, value, unit)
    if volume is None:
        return None
    return FlowValue(FlowKind.STANDARD_VOLUME, volume / table.standard_molar_volume_nm3_per_kmol)


def load_unit_table(path: Path) -> UnitTable:
    """从 YAML 文件加载单位表。文件读不了是 E_IO，内容不合法是 E_SCHEMA。"""
    return parse_model(UnitTable, read_document(path), path.name)

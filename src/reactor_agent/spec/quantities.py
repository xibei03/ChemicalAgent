"""TaskSpec 里的名字和物理量 → 规范名和规范单位。进料、反应、工况的规范化共用。

每个函数要么返回规范的值，要么在 Notes 里记一个问题并返回 None。不认识的组分和单位不猜；
LLM 把不可以假设的量填成“假设”是问题；用户给的数值超出范围也保持原值，作为问题报告。
"""

from collections.abc import Callable
from dataclasses import dataclass

from reactor_agent.errors import ErrorCode
from reactor_agent.spec.components import closest_names, resolve_component
from reactor_agent.spec.enums import PressureBasis
from reactor_agent.spec.notes import Context
from reactor_agent.spec.task_spec import PressureQuantity, Quantity, Source
from reactor_agent.spec.tool_args import ABSOLUTE_ZERO_C
from reactor_agent.spec.units import (
    UnitTable,
    pressure_unit_basis,
    to_conversion_percent,
    to_duty_kw,
    to_pressure_bar,
    to_temperature_c,
)

Convert = Callable[[UnitTable, float, str], float | None]


@dataclass(frozen=True)
class QuantityKind:
    """一类物理量：叫什么、怎么换算、换算后必须大于几（没有下限是 None）。"""

    label: str
    convert: Convert
    lower: float | None


TEMPERATURE = QuantityKind("温度", to_temperature_c, ABSOLUTE_ZERO_C)
DUTY = QuantityKind("热负荷", to_duty_kw, None)
CONVERSION = QuantityKind("转化率", to_conversion_percent, 0.0)
MAX_CONVERSION_PERCENT = 100.0


def resolve_name(ctx: Context, text: str, path: str) -> str | None:
    """组分名解析成规范名；解析不了记一个问题，带上最接近的候选，没有候选就列出组分表。"""
    entry = resolve_component(ctx.table, text)
    if entry is not None:
        return entry.name
    close = closest_names(ctx.table, text)
    known = "、".join(entry.name for entry in ctx.table.components)
    hint = f"最接近的候选：{'、'.join(close)}" if close else f"组分表里有：{known}"
    ctx.notes.problem(
        ErrorCode.COMPONENT_NOT_FOUND,
        path,
        f"组分 {text!r} 不在组分表里。{hint}",
        user_fixable=True,
    )
    return None


def _assumed(ctx: Context, label: str, path: str) -> None:
    message = f"{label}不可以假设：原文没有给就写 null，并列进 missing"
    ctx.notes.problem(ErrorCode.RULE, path, message, user_fixable=True)


def convert_value(ctx: Context, quantity: Quantity, path: str, kind: QuantityKind) -> float | None:
    """物理量换算成规范单位。是假设、单位不认识、超出范围，都记成问题。"""
    if quantity.source is Source.ASSUMED:
        _assumed(ctx, kind.label, path)
        return None
    value = kind.convert(ctx.units, quantity.value, quantity.unit)
    if value is None:
        message = f"{kind.label}的单位 {quantity.unit!r} 不认识"
        ctx.notes.problem(ErrorCode.SCHEMA, path, message, user_fixable=True)
        return None
    if kind.lower is not None and value <= kind.lower:
        given = f"{quantity.value:g} {quantity.unit}".strip()
        message = f"{kind.label} {given} 超出了合理范围（要大于 {kind.lower:g}）"
        ctx.notes.problem(ErrorCode.RULE, path, message, user_fixable=True)
        return None
    return value


def convert_pressure(ctx: Context, quantity: PressureQuantity, path: str) -> float | None:
    """压力换算成绝压 bar。原文没有说明基准（单位也不带）时按绝压，并登记假设。"""
    if quantity.source is Source.ASSUMED:
        _assumed(ctx, "压力", path)
        return None
    unit_basis = pressure_unit_basis(ctx.units, quantity.unit)
    if unit_basis is None:
        message = f"压力的单位 {quantity.unit!r} 不认识"
        ctx.notes.problem(ErrorCode.SCHEMA, path, message, user_fixable=True)
        return None
    basis = quantity.basis if quantity.basis is not PressureBasis.UNSTATED else unit_basis
    if basis is PressureBasis.UNSTATED:
        reason = "原文没有说明压力是绝压还是表压，按绝压"
        basis = ctx.notes.default(path, PressureBasis.ABSOLUTE, reason)
    bar = to_pressure_bar(ctx.units, quantity.value, quantity.unit, basis)
    if bar is None or bar <= 0:
        message = f"压力 {quantity.value:g} {quantity.unit} 换算后不是正数"
        ctx.notes.problem(ErrorCode.RULE, path, message, user_fixable=True)
        return None
    return bar

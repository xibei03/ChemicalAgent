"""进料的规范化：温度、压力、流量、组成。

压力：这股进料自己的；原文只给了一个不属于某股进料的压力（操作压力）时，进料压力取它并登记假设。
流量：摩尔、质量或标准体积流量，标准体积流量按标准摩尔体积折算；气体体积单位用于含固体或液体的
进料时，登记一条歧义假设。组成：换成摩尔分率。规格里的进料是字典，由 ModelSpec 统一校验。
"""

from collections.abc import Mapping
from dataclasses import dataclass

from reactor_agent.errors import ErrorCode
from reactor_agent.spec.composition import CompositionError, MoleComposition, mole_fractions
from reactor_agent.spec.enums import ComponentPhase
from reactor_agent.spec.notes import Context
from reactor_agent.spec.quantities import TEMPERATURE, convert_pressure, convert_value, resolve_name
from reactor_agent.spec.task_spec import FeedTask, PressureQuantity, Source
from reactor_agent.spec.units import FlowKind, to_flow


@dataclass(frozen=True)
class FeedData:
    """一股进料的规格（字典，最后由 ModelSpec 校验）、它用到的组分和换算后的进料压力。"""

    spec: dict[str, object]
    components: tuple[str, ...]
    pressure_bar: float


@dataclass(frozen=True)
class FlowSpec:
    """换算后的流量：规格里的字段名（摩尔流量或质量流量）和规范值。"""

    field: str
    value: float


def _feed_pressure(
    ctx: Context, index: int, own: PressureQuantity | None, shared: PressureQuantity | None
) -> float | None:
    """进料压力：这股进料自己的；没有就取原文给的操作压力，并登记假设。"""
    path = f"feeds[{index}].pressure_bar"
    given = own or shared
    if given is None:
        ctx.notes.problem(ErrorCode.RULE, path, "进料压力没有给出", user_fixable=True)
        return None
    bar = convert_pressure(ctx, given, path, assume_at=path)
    if bar is None or own is not None:
        return bar
    reason = "原文只给了一个不属于某股进料的压力（操作压力），进料压力取它"
    return ctx.notes.default(path, bar, reason)


def _composition(ctx: Context, feed: FeedTask, path: str) -> MoleComposition | None:
    """进料组成换成摩尔分率。缺失、假设、组分解析失败和份额不对都是问题。"""
    task = feed.composition
    if feed.pure_component is not None and task is None:
        name = resolve_name(ctx, feed.pure_component, f"{path}.pure_component")
        return None if name is None else MoleComposition({name: 1.0}, ())
    if feed.pure_component is not None:
        message = "进料是纯物质就写 pure_component，composition 写 null；有几种物质才写 composition"
        ctx.notes.problem(ErrorCode.SCHEMA, path, message)
        return None
    if task is None:
        ctx.notes.problem(ErrorCode.RULE, path, "进料组成没有给出", user_fixable=True)
        return None
    if task.source is Source.ASSUMED:
        message = "组成不可以假设：原文没有给就写 null，并列进 missing"
        ctx.notes.problem(ErrorCode.RULE, path, message, user_fixable=True)
        return None
    resolved = [
        resolve_name(ctx, item.component, f"{path}.items[{k}]") for k, item in enumerate(task.items)
    ]
    names = [name for name in resolved if name is not None]
    if len(names) != len(resolved):
        return None
    try:
        result = mole_fractions(task, names, ctx.table)
    except CompositionError as error:
        ctx.notes.problem(ErrorCode.RULE, path, str(error), user_fixable=error.user_fixable)
        return None
    for note in result.notes:
        ctx.notes.declare(path, note, "换算组成时的处理，各项数值照原文")
    return result


def _has_non_gas(ctx: Context, names: Mapping[str, float]) -> bool:
    phases = {entry.name: entry.phase for entry in ctx.table.components}
    return any(phases[name] is not ComponentPhase.GAS for name in names)


def _flow(
    ctx: Context, index: int, feed: FeedTask, composition: MoleComposition
) -> FlowSpec | None:
    """进料流量换算成规格里的字段和规范值。没有给、单位不认识、不是正数都是问题。"""
    path = f"feeds[{index}].flow"
    quantity = feed.flow
    if quantity is None:
        message = "流量没有给出，也没有给出假设值：原文没有给时由你给一个取值，source 写 assumed"
        ctx.notes.problem(ErrorCode.SCHEMA, path, message)
        return None
    converted = to_flow(ctx.units, quantity.value, quantity.unit)
    if converted is None or converted.value <= 0:
        message = f"流量 {quantity.value:g} {quantity.unit} 的单位不认识，或者不是正数"
        ctx.notes.problem(ErrorCode.SCHEMA, path, message, user_fixable=True)
        return None
    name = "mass_flow_kg_h" if converted.kind is FlowKind.MASS else "molar_flow_kmol_h"
    target = f"feeds[{index}].{name}"
    given = f"{quantity.value:g} {quantity.unit}"
    if quantity.source is Source.ASSUMED:
        ctx.notes.declare(target, given, quantity.rationale or "")
    if converted.kind is FlowKind.STANDARD_VOLUME:
        ctx.notes.volume_feeds.append(index)
        if _has_non_gas(ctx, composition.fractions):
            reason = "Nm3/h 是气体体积单位，进料含固体或液体，按标准状态下的理想气体折算成摩尔流量"
            ctx.notes.declare(target, f"{given}按摩尔流量理解", reason)
    return FlowSpec(name, converted.value)


def _feed(
    ctx: Context, index: int, feed: FeedTask, shared: PressureQuantity | None
) -> FeedData | None:
    """一股进料的规格。有任何一项出了问题就是 None，问题已经记在 Notes 里。"""
    base = f"feeds[{index}]"
    temperature = None
    if feed.temperature is None:
        ctx.notes.problem(
            ErrorCode.RULE, f"{base}.temperature_c", "进料温度没有给出", user_fixable=True
        )
    else:
        temperature = convert_value(ctx, feed.temperature, f"{base}.temperature_c", TEMPERATURE)
    pressure = _feed_pressure(ctx, index, feed.pressure, shared)
    composition = _composition(ctx, feed, f"{base}.composition")
    flow = None if composition is None else _flow(ctx, index, feed, composition)
    if temperature is None or pressure is None or composition is None or flow is None:
        return None
    spec: dict[str, object] = {
        "name": feed.name,
        "temperature_c": temperature,
        "pressure_bar": pressure,
        "composition": [
            {"component": name, "mole_fraction": fraction}
            for name, fraction in composition.fractions.items()
        ],
        flow.field: flow.value,
    }
    return FeedData(spec, tuple(composition.fractions), pressure)


def normalize_feeds(
    ctx: Context, feeds: tuple[FeedTask, ...], shared: PressureQuantity | None
) -> list[FeedData]:
    """全部进料的规格。没有进料是一个问题；出了问题的进料不出现在结果里。"""
    if not feeds:
        ctx.notes.problem(ErrorCode.RULE, "feeds", "没有进料", user_fixable=True)
    built = [_feed(ctx, index, feed, shared) for index, feed in enumerate(feeds)]
    return [item for item in built if item is not None]

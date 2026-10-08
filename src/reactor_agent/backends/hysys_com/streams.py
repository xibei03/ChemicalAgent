"""物料流和能流。

写入顺序没有要求：T、P、组成写完闪蒸就完成，流量最后写（台账 H13、H14）。HYSYS 不校验取值（组成被
静默归一化，负流量照收），校验在入参模型里做，这里写完读回。MaterialStreams.Add 同名返回已有的那一股
（H12），但仍然先查：已有的要和期望比较，不一致是冲突。
"""

from typing import Any

from reactor_agent.backends.hysys_com.com_errors import com_call, read_optional
from reactor_agent.backends.hysys_com.lookup import find_by_name
from reactor_agent.backends.hysys_com.thermo import component_names
from reactor_agent.backends.hysys_com.variables import (
    Quantity,
    read_fractions,
    read_plain,
    read_quantities,
    read_quantity,
    write_fractions,
    write_quantity,
)
from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.enums import ResultStatus, StreamKind
from reactor_agent.spec.matching import require_match, stream_differences
from reactor_agent.spec.snapshot import EnergyStreamSnapshot, StreamComponent, StreamSnapshot
from reactor_agent.spec.tool_args import EnsureStreamArgs, FeedConditions
from reactor_agent.spec.tool_results import Outcome, StreamData


def read_stream(stream: Any, components: tuple[str, ...]) -> StreamSnapshot:
    """读一股物料流：温度、压力、流量、相分率和按组分的量。读不到的值是 None。"""
    with com_call(ErrorCode.NOT_FOUND, "读取物流"):
        fractions = read_fractions(stream.ComponentMolarFraction)
        molar_flows = read_quantities(stream.ComponentMolarFlow, Quantity.MOLAR_FLOW)
        mass_flows = read_quantities(stream.ComponentMassFlow, Quantity.MASS_FLOW)
        return StreamSnapshot(
            name=str(stream.name),
            temperature_c=read_quantity(stream.Temperature, Quantity.TEMPERATURE),
            pressure_bar=read_quantity(stream.Pressure, Quantity.PRESSURE),
            molar_flow_kmol_h=read_quantity(stream.MolarFlow, Quantity.MOLAR_FLOW),
            mass_flow_kg_h=read_quantity(stream.MassFlow, Quantity.MASS_FLOW),
            # 组成写入之前读相分率会抛 com_error（台账 H14），当作还没有值。
            vapour_fraction=read_optional(lambda: read_plain(stream.VapourFractionValue)),
            heavy_liquid_fraction=read_optional(
                lambda: read_plain(stream.HeavyLiquidFractionValue)
            ),
            components=tuple(
                StreamComponent(
                    name=name, mole_fraction=fraction, molar_flow_kmol_h=flow, mass_flow_kg_h=mass
                )
                for name, fraction, flow, mass in zip(
                    components, fractions, molar_flows, mass_flows, strict=True
                )
            ),
        )


def read_energy_stream(stream: Any) -> EnergyStreamSnapshot:
    """读一股能流的热负荷（吸热为正）。"""
    with com_call(ErrorCode.NOT_FOUND, "读取能流"):
        return EnergyStreamSnapshot(
            name=str(stream.name), duty_kw=read_quantity(stream.HeatFlow, Quantity.POWER)
        )


def _write_conditions(stream: Any, order: tuple[str, ...], conditions: FeedConditions) -> None:
    write_quantity(stream.Temperature, conditions.temperature_c, Quantity.TEMPERATURE)
    write_quantity(stream.Pressure, conditions.pressure_bar, Quantity.PRESSURE)
    amounts = {entry.component: entry.mole_fraction for entry in conditions.composition}
    write_fractions(stream.ComponentMolarFraction, tuple(amounts.get(name, 0.0) for name in order))
    if conditions.molar_flow_kmol_h is not None:
        write_quantity(stream.MolarFlow, conditions.molar_flow_kmol_h, Quantity.MOLAR_FLOW)
    elif conditions.mass_flow_kg_h is not None:
        write_quantity(stream.MassFlow, conditions.mass_flow_kg_h, Quantity.MASS_FLOW)


def _check_components(conditions: FeedConditions, order: tuple[str, ...]) -> None:
    unknown = sorted({entry.component for entry in conditions.composition} - set(order))
    if unknown:
        raise ReactorAgentError(
            ErrorCode.COMPONENT_NOT_FOUND,
            f"组成里的组分不在组分表里：{unknown}",
            {"components": ", ".join(unknown)},
        )


def _create(case: Any, collection: Any, args: EnsureStreamArgs) -> None:
    subject = f"物流 {args.name}"
    with com_call(ErrorCode.READBACK_MISMATCH, f"创建{subject}"):
        stream = collection.Add(args.name)
    if args.conditions is None:
        return
    order = component_names(case)
    _check_components(args.conditions, order)
    with com_call(ErrorCode.READBACK_MISMATCH, f"写入{subject}"):
        _write_conditions(stream, order, args.conditions)
    differences = stream_differences(read_stream(stream, order), args.conditions)
    require_match(ErrorCode.READBACK_MISMATCH, subject, differences)


def ensure_stream(case: Any, flowsheet: Any, args: EnsureStreamArgs) -> Outcome[StreamData]:
    """确保物流或能流存在。给了规定时，规定值读回一致；已有同名对象只确认，不一致是冲突。"""
    is_material = args.kind is StreamKind.MATERIAL
    collection = flowsheet.MaterialStreams if is_material else flowsheet.EnergyStreams
    other = flowsheet.EnergyStreams if is_material else flowsheet.MaterialStreams
    if find_by_name(other, args.name, "另一种流") is not None:
        raise ReactorAgentError(ErrorCode.CONFLICT, f"已经有同名的另一种流：{args.name}")
    data = StreamData(name=args.name, kind=args.kind)
    existing = find_by_name(collection, args.name, "物流")
    if existing is None:
        _create(case, collection, args)
        return Outcome(ResultStatus.CREATED, data)
    if args.conditions is not None:
        snapshot = read_stream(existing, component_names(case))
        differences = stream_differences(snapshot, args.conditions)
        require_match(ErrorCode.CONFLICT, f"物流 {args.name}", differences)
    return Outcome(ResultStatus.UNCHANGED, data)

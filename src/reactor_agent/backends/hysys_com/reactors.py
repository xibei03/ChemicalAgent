"""反应器：创建、连接、读回，以及工况变量（出口温度、热负荷）的规定。

连接顺序固定为进料、能流、气相出料、液相出料、反应集：Gibbs 反应器先接出料后接能流会弹出
绝热警告（台账 L24）。同名的 Operations.Add 不能依赖 HYSYS 的行为，同名不同类型会弹窗并可能使
进程崩溃（L26），所以创建之前先按名字查，名字已存在时绝不调用 Add。出口温度规定在气相出料
物流上（台账 H16）。
"""

from collections.abc import Callable
from typing import Any

from reactor_agent.backends.hysys_com.com_errors import com_call, read_optional
from reactor_agent.backends.hysys_com.lookup import find_by_name, names_of, reaction_manager_of
from reactor_agent.backends.hysys_com.reactions import reaction_set_kinds
from reactor_agent.backends.hysys_com.reactor_kinds import ReactorKind, kind_of, reactor_type_of
from reactor_agent.backends.hysys_com.variables import Quantity, read_quantity, write_quantity
from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.enums import ResultStatus, SpecVariable
from reactor_agent.spec.matching import reactor_differences, require_match, values_close
from reactor_agent.spec.snapshot import ReactorSnapshot
from reactor_agent.spec.tool_args import EnsureReactorArgs, SetSpecArgs
from reactor_agent.spec.tool_results import Outcome, ReactorData, SetSpecData

# 变量的 State：1 是规定值，0 是计算值（台账 H18）。
SPECIFIED_STATE = 1

# 每个可规定的变量：怎么从反应器找到它，以及它的物理量。出口温度在气相出料上，热负荷在能流上。
SPEC_TARGETS: dict[SpecVariable, tuple[Callable[[Any], Any], Quantity]] = {
    SpecVariable.OUTLET_TEMPERATURE_C: (
        lambda reactor: reactor.VapourProduct.Temperature,
        Quantity.TEMPERATURE,
    ),
    SpecVariable.DUTY_KW: (lambda reactor: reactor.EnergyStream.HeatFlow, Quantity.POWER),
}


def read_reactor(operation: Any) -> ReactorSnapshot | None:
    """读一台反应器的类型和连接；这个操作不是三种反应器之一时是 None。"""
    with com_call(ErrorCode.NOT_FOUND, "读取反应器"):
        reactor_type = reactor_type_of(str(operation.TypeName))
        if reactor_type is None:
            return None
        # 没有连接的引用，HYSYS 读取时抛 COM 异常，而不是返回空（台账 H16）。
        return ReactorSnapshot(
            name=str(operation.name),
            reactor_type=reactor_type,
            feeds=tuple(str(name) for name in operation.Feeds.Names),
            vapour_product=read_optional(lambda: str(operation.VapourProduct.name)),
            liquid_product=read_optional(lambda: str(operation.LiquidProduct.name)),
            energy_stream=read_optional(lambda: str(operation.EnergyStream.name)),
            reaction_set=read_optional(lambda: str(operation.ReactionSet.name)),
            pressure_drop_bar=read_quantity(operation.PressureDrop, Quantity.PRESSURE_DROP),
        )


def _check_streams_exist(flowsheet: Any, args: EnsureReactorArgs) -> None:
    material = set(names_of(flowsheet.MaterialStreams, "物流"))
    energy = set(names_of(flowsheet.EnergyStreams, "能流"))
    missing = [
        name
        for name in (*args.feeds, args.vapour_product, args.liquid_product)
        if name not in material
    ]
    if args.energy_stream is not None and args.energy_stream not in energy:
        missing.append(args.energy_stream)
    if missing:
        raise ReactorAgentError(
            ErrorCode.NOT_FOUND,
            f"反应器 {args.name} 连接的物流还没有创建：{missing}",
            {"streams": ", ".join(missing)},
        )


def check_reaction_set(case: Any, kind: ReactorKind, args: EnsureReactorArgs) -> None:
    """反应集的反应类型必须与反应器匹配，否则 HYSYS 会弹模态对话框并且不挂上（台账 H23）。"""
    wanted = args.reaction_set
    if kind.reaction_kind is None:
        if wanted is not None:
            raise ReactorAgentError(
                ErrorCode.SET_INCOMPATIBLE, f"{args.reactor_type.value} 反应器不挂反应集"
            )
        return
    if wanted is None:
        raise ReactorAgentError(
            ErrorCode.SET_INCOMPATIBLE, f"{args.reactor_type.value} 反应器需要反应集"
        )
    kinds = reaction_set_kinds(case, wanted)
    if kinds is None:
        raise ReactorAgentError(ErrorCode.NOT_FOUND, f"反应集 {wanted} 还没有创建")
    if kinds != {kind.reaction_kind}:
        raise ReactorAgentError(
            ErrorCode.SET_INCOMPATIBLE,
            f"反应集 {wanted} 的反应类型 {sorted(k.value for k in kinds)} "
            f"与 {args.reactor_type.value} 反应器不兼容",
        )


def _connect(case: Any, flowsheet: Any, kind: ReactorKind, args: EnsureReactorArgs) -> Any:
    streams, energy_streams = flowsheet.MaterialStreams, flowsheet.EnergyStreams
    with com_call(ErrorCode.CONNECT_FAILED, f"创建并连接反应器 {args.name}"):
        reactor = flowsheet.Operations.Add(args.name, kind.operation_type)
        for feed in args.feeds:
            reactor.Feeds.Add(streams.Item(feed))
        if args.energy_stream is not None:
            reactor.EnergyStream = energy_streams.Item(args.energy_stream)
        reactor.VapourProduct = streams.Item(args.vapour_product)
        reactor.LiquidProduct = streams.Item(args.liquid_product)
        if args.reaction_set is not None:
            sets = reaction_manager_of(case).ReactionSets
            reactor.ReactionSet = sets.Item(args.reaction_set)
        write_quantity(reactor.PressureDrop, args.pressure_drop_bar, Quantity.PRESSURE_DROP)
    return reactor


def ensure_reactor(case: Any, flowsheet: Any, args: EnsureReactorArgs) -> Outcome[ReactorData]:
    """确保反应器存在，类型、连接、反应集和压降读回一致。已有同名操作只确认，不一致是冲突。"""
    kind = kind_of(args.reactor_type)
    if args.heat_mode not in kind.heat_modes:
        raise ReactorAgentError(
            ErrorCode.UNSUPPORTED,
            f"{args.reactor_type.value} 反应器的热模式 {args.heat_mode.value} 还没有验证过",
        )
    data = ReactorData(name=args.name, reactor_type=args.reactor_type)
    subject = f"反应器 {args.name}"
    existing = find_by_name(flowsheet.Operations, args.name, "操作")
    if existing is not None:
        snapshot = read_reactor(existing)
        if snapshot is None:
            raise ReactorAgentError(
                ErrorCode.CONFLICT, f"已经有同名的操作，它不是反应器：{args.name}"
            )
        require_match(ErrorCode.CONFLICT, subject, reactor_differences(snapshot, args))
        return Outcome(ResultStatus.UNCHANGED, data)
    _check_streams_exist(flowsheet, args)
    check_reaction_set(case, kind, args)
    reactor = _connect(case, flowsheet, kind, args)
    created = read_reactor(reactor)
    if created is None:
        raise ReactorAgentError(ErrorCode.READBACK_MISMATCH, f"{subject} 创建之后类型读不出来")
    require_match(ErrorCode.READBACK_MISMATCH, subject, reactor_differences(created, args))
    return Outcome(ResultStatus.CREATED, data)


def _require_reactor(flowsheet: Any, name: str) -> Any:
    operation = find_by_name(flowsheet.Operations, name, "操作")
    if operation is None or read_reactor(operation) is None:
        raise ReactorAgentError(ErrorCode.NOT_FOUND, f"没有反应器 {name}")
    return operation


def _write_spec(variable: Any, quantity: Quantity, value: float) -> bool:
    """写入规定值，返回是否真的改了。已经是同值的规定值就不写。"""
    current = read_quantity(variable, quantity)
    unchanged = values_close(current, value) and int(variable.State) == SPECIFIED_STATE
    if not unchanged:
        write_quantity(variable, value, quantity)
    return not unchanged


def set_spec(flowsheet: Any, args: SetSpecArgs) -> Outcome[SetSpecData]:
    """规定反应器的一个工况变量，设完读回。变量当前是计算值（比如绝热时的出口温度）时拒绝。"""
    reactor = _require_reactor(flowsheet, args.object_name)
    locate, quantity = SPEC_TARGETS[args.variable]
    variable = read_optional(lambda: locate(reactor))
    if variable is None:
        raise ReactorAgentError(
            ErrorCode.RULE,
            f"{args.object_name} 没有可规定的 {args.variable.value}：出料或能流没连接",
        )
    with com_call(ErrorCode.READBACK_MISMATCH, f"规定 {args.object_name} 的 {args.variable.value}"):
        if not bool(variable.CanModify):
            raise ReactorAgentError(
                ErrorCode.RULE,
                f"{args.object_name} 的 {args.variable.value} 现在是计算值，不能规定"
                "（热模式与规定的变量不匹配？）",
            )
        changed = _write_spec(variable, quantity, args.value)
        after = read_quantity(variable, quantity)
    if after is None or not values_close(after, args.value):
        raise ReactorAgentError(
            ErrorCode.READBACK_MISMATCH,
            f"{args.object_name} 的 {args.variable.value} 写入 {args.value}，读回 {after}",
        )
    status = ResultStatus.UPDATED if changed else ResultStatus.UNCHANGED
    return Outcome(
        status, SetSpecData(object_name=args.object_name, variable=args.variable, value=after)
    )

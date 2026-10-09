"""结果检查 V1 至 V4（计划 §12.3），以及把 V1 至 V7 排成一张表依次执行。

V5、V6 在 streams.py，V7 在 conservation.py，V8 在 normalized.py。每项检查是一个独立的小函数，
签名都是“上下文 → 检查结果”。检查宁严勿松：读不到的量、不存在的对象，一律算不通过，不让
“没读到”被当作“没问题”。
"""

from collections.abc import Callable, Iterable
from typing import TypeVar

from reactor_agent.spec.balances import sum_or_none
from reactor_agent.spec.enums import CheckId, SpecVariable
from reactor_agent.spec.matching import (
    reaction_differences,
    reaction_set_differences,
    reactor_connection_differences,
    stream_differences,
    thermo_differences,
    values_close,
)
from reactor_agent.spec.plan import (
    BuildPlan,
    energy_stream_names,
    material_stream_names,
    system_feed_names,
)
from reactor_agent.spec.results import CheckContext, CheckResult, check_result, describe
from reactor_agent.spec.snapshot import (
    ModelSnapshot,
    ReactionSetSnapshot,
    ReactionSnapshot,
    ReactorSnapshot,
)
from reactor_agent.spec.tool_args import (
    EnsureReactionArgs,
    EnsureReactionSetArgs,
    EnsureReactorArgs,
    EnsureThermoArgs,
    SetSpecArgs,
)
from reactor_agent.validation.conservation import check_conservation
from reactor_agent.validation.streams import check_outputs, check_physical

# V3：进料读回的相对容差。
FEED_TOLERANCE = 1e-4
# V4：出口温度与目标的最大偏差。
OUTLET_TEMPERATURE_TOLERANCE_C = 0.1

CheckFunction = Callable[[CheckContext], CheckResult]
NamedT = TypeVar("NamedT", ReactionSnapshot, ReactionSetSnapshot, ReactorSnapshot)


def check_solved(context: CheckContext) -> CheckResult:
    """V1：求解器空闲，各对象的状态都是已求解。变量有没有值归 V5。"""
    solve = context.snapshot.solve
    problems = [f"{item.name} 处于 {item.state.value} 状态" for item in solve.unsolved_objects]
    if solve.is_solving:
        problems.insert(0, "求解器仍在求解")
    if not solve.objects:
        problems.append("流程图里没有对象")
    found = f"{len(solve.objects)} 个对象全部已求解"
    return check_result(CheckId.SOLVED, "求解器空闲，全部对象已求解", found, problems)


def _index(items: Iterable[NamedT]) -> dict[str, NamedT]:
    return {item.name: item for item in items}


def _differences_or_missing(subject: str, differences: tuple[str, ...] | None) -> list[str]:
    if differences is None:
        return [f"{subject}不存在"]
    return [f"{subject}：{difference}" for difference in differences]


def _basis_problems(plan: BuildPlan, snapshot: ModelSnapshot) -> list[str]:
    problems: list[str] = []
    for thermo in plan.args_of(EnsureThermoArgs):
        found = snapshot.thermo
        differences = None if found is None else thermo_differences(found, thermo)
        problems += _differences_or_missing("流体包", differences)
    reactions = _index(snapshot.reactions)
    for args in plan.args_of(EnsureReactionArgs):
        item = reactions.get(args.name)
        differences = None if item is None else reaction_differences(item.definition, args.reaction)
        problems += _differences_or_missing(f"反应 {args.name}", differences)
    sets = _index(snapshot.reaction_sets)
    for set_args in plan.args_of(EnsureReactionSetArgs):
        member = sets.get(set_args.name)
        differences = None if member is None else reaction_set_differences(member, set_args)
        problems += _differences_or_missing(f"反应集 {set_args.name}", differences)
    return problems


def _flowsheet_problems(plan: BuildPlan, snapshot: ModelSnapshot) -> list[str]:
    material = {stream.name for stream in snapshot.streams}
    energy = {stream.name for stream in snapshot.energy_streams}
    problems = [f"物流 {n} 不存在" for n in material_stream_names(plan) if n not in material]
    problems += [f"能流 {n} 不存在" for n in energy_stream_names(plan) if n not in energy]
    reactors = _index(snapshot.reactors)
    for args in plan.args_of(EnsureReactorArgs):
        item = reactors.get(args.name)
        differences = None if item is None else reactor_connection_differences(item, args)
        problems += _differences_or_missing(f"反应器 {args.name}", differences)
    return problems


def check_structure(context: CheckContext) -> CheckResult:
    """V2：计划里的对象全部存在，类型、连接和配置与计划一致。期望的对象从计划里取。"""
    plan, snapshot = context.plan, context.snapshot
    planned = sum(1 for step in plan.steps if step.case_name is None)
    problems = [*_basis_problems(plan, snapshot), *_flowsheet_problems(plan, snapshot)]
    expected = f"计划里的 {planned} 个对象全部存在，类型和连接与计划一致"
    return check_result(CheckId.STRUCTURE, expected, "全部存在且一致", problems)


def check_feeds(context: CheckContext) -> CheckResult:
    """V3：进料物流读回的温度、压力、流量和组成与规格一致。名字从计划里取，值和规格比。"""
    names = system_feed_names(context.plan)
    feeds = context.spec.feeds
    problems: list[str] = []
    if len(names) != len(feeds):
        problems.append(f"计划里有 {len(names)} 股进料，规格里有 {len(feeds)} 股")
    for name, feed in zip(names, feeds, strict=False):
        stream = context.snapshot.stream(name)
        differences = None if stream is None else stream_differences(stream, feed, FEED_TOLERANCE)
        problems += _differences_or_missing(f"进料 {name}", differences)
    expected = f"进料的温度、压力、流量和组成与规格一致（相对容差 {FEED_TOLERANCE:.0e}）"
    return check_result(CheckId.FEEDS, expected, f"{len(names)} 股进料一致", problems)


def _actual_spec_value(snapshot: ModelSnapshot, args: SetSpecArgs) -> float | None:
    """规定的变量现在的值：出口温度读气相出料，热负荷读能流。"""
    reactor = _index(snapshot.reactors).get(args.object_name)
    if reactor is None:
        return None
    if args.variable is SpecVariable.OUTLET_TEMPERATURE_C:
        outlet = snapshot.stream(reactor.vapour_product or "")
        return None if outlet is None else outlet.temperature_c
    energy = next((e for e in snapshot.energy_streams if e.name == reactor.energy_stream), None)
    return None if energy is None else energy.duty_kw


def _spec_met(args: SetSpecArgs, actual: float | None) -> bool:
    if actual is None:
        return False
    if args.variable is SpecVariable.OUTLET_TEMPERATURE_C:
        return abs(actual - args.value) <= OUTLET_TEMPERATURE_TOLERANCE_C
    return values_close(actual, args.value)


def _case_spec_problems(context: CheckContext) -> list[str]:
    problems = []
    for step in context.plan.case_steps(context.case.name):
        args = step.args
        if not isinstance(args, SetSpecArgs):
            continue
        actual = _actual_spec_value(context.snapshot, args)
        if not _spec_met(args, actual):
            problems.append(
                f"{args.object_name} 的 {args.variable.value} 应为 {args.value:g}，"
                f"实测 {describe(actual)}"
            )
    return problems


def _pressure_drop_problems(context: CheckContext) -> list[str]:
    reactors = _index(context.snapshot.reactors)
    planned = context.plan.args_of(EnsureReactorArgs)
    drops = [reactors[a.name].pressure_drop_bar if a.name in reactors else None for a in planned]
    total = sum_or_none(drops)
    wanted = context.spec.pressure_drop_bar
    if values_close(total, wanted):
        return []
    return [f"反应器压降合计应为 {wanted:g} bar，实测 {describe(total)} bar"]


def check_specifications(context: CheckContext) -> CheckResult:
    """V4：当前工况的出口温度（±0.1 °C）或热负荷，以及压降，等于规格里的规定。"""
    problems = [*_case_spec_problems(context), *_pressure_drop_problems(context)]
    expected = (
        f"出口温度或热负荷与工况一致（温度 ±{OUTLET_TEMPERATURE_TOLERANCE_C} °C），压降与规格一致"
    )
    return check_result(CheckId.SPECIFICATIONS, expected, "全部满足规定", problems)


COMMON_CHECKS: tuple[CheckFunction, ...] = (
    check_solved,
    check_structure,
    check_feeds,
    check_specifications,
    check_outputs,
    check_physical,
    check_conservation,
)


def run_common_checks(context: CheckContext) -> tuple[CheckResult, ...]:
    """依次执行 V1 至 V7，每项一个结果，按编号排列。"""
    return tuple(check(context) for check in COMMON_CHECKS)

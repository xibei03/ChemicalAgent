"""结果检查 V1 至 V4（计划 §12.3），以及把 V1 至 V7 排成一张表依次执行。

V5、V6 在 streams.py，V7 在 conservation.py，V8 在 normalized.py。每项检查是一个独立的小函数，
签名都是“上下文 → 检查结果”。检查宁严勿松：读不到的量、不存在的对象，一律算不通过，不让
“没读到”被当作“没问题”。期望值尽量取自规格，不取自计划：计划是 Recipe 编译出来的，编译错了，
读回再和计划一致也是错的模型。
"""

from collections.abc import Callable, Iterable
from typing import TypeVar

from reactor_agent.spec.balances import sum_or_none
from reactor_agent.spec.enums import CheckId
from reactor_agent.spec.matching import (
    reaction_differences,
    reaction_set_differences,
    reactor_connection_differences,
    stream_differences,
    thermo_differences,
    values_close,
)
from reactor_agent.spec.model_spec import FeedSpec, ModelSpec
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
    StreamSnapshot,
)
from reactor_agent.spec.tool_args import (
    EnsureReactionArgs,
    EnsureReactionSetArgs,
    EnsureReactorArgs,
    EnsureThermoArgs,
    ReactionDefinition,
)
from reactor_agent.validation.conservation import check_conservation
from reactor_agent.validation.streams import check_outputs, check_physical

# V3：进料读回的容差，温度、压力、流量按相对偏差，摩尔分率按绝对偏差。
FEED_TOLERANCE = 1e-4
# V4：出口温度与目标的最大偏差。
OUTLET_TEMPERATURE_TOLERANCE_C = 0.1

CheckFunction = Callable[[CheckContext], CheckResult]
NamedT = TypeVar("NamedT", ReactionSnapshot, ReactionSetSnapshot, ReactorSnapshot)
FoundT = TypeVar("FoundT")
WantedT = TypeVar("WantedT")


def check_solved(context: CheckContext) -> CheckResult:
    """V1：求解器空闲，各对象的状态都是已求解（HYSYS 的“警告”状态算已求解）。变量有没有值归 V5。"""
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


def _compare(
    subject: str,
    found: FoundT | None,
    compare: Callable[[FoundT, WantedT], tuple[str, ...]],
    wanted: WantedT,
) -> list[str]:
    """已有的对象与期望的比较，列出每处差异；没找到就是“不存在”。"""
    if found is None:
        return [f"{subject}不存在"]
    return [f"{subject}：{difference}" for difference in compare(found, wanted)]


def _snapshot_reaction_differences(
    item: ReactionSnapshot, wanted: EnsureReactionArgs
) -> tuple[str, ...]:
    return reaction_differences(item.definition, wanted.reaction)


def _plan_problems(plan: BuildPlan, spec: ModelSpec) -> list[str]:
    """计划里的流体包和规格里的反应，与规格一致。规格里的反应在计划里排在最前面，顺序相同。"""
    problems: list[str] = []
    for thermo in plan.args_of(EnsureThermoArgs):
        if (thermo.components, thermo.property_package) != (spec.components, spec.property_package):
            problems.append("计划里的流体包与规格的组分表或物性包不一致")
    planned: list[ReactionDefinition] = [a.reaction for a in plan.args_of(EnsureReactionArgs)]
    for index, wanted in enumerate(spec.reactions):
        subject = f"规格的第 {index + 1} 个反应在计划里"
        if index >= len(planned):
            problems.append(f"{subject}不存在")
        else:
            problems += [f"{subject}：{d}" for d in reaction_differences(planned[index], wanted)]
    return problems


def _basis_problems(plan: BuildPlan, snapshot: ModelSnapshot) -> list[str]:
    reactions, sets = _index(snapshot.reactions), _index(snapshot.reaction_sets)
    problems: list[str] = []
    for thermo in plan.args_of(EnsureThermoArgs):
        problems += _compare("流体包", snapshot.thermo, thermo_differences, thermo)
    for args in plan.args_of(EnsureReactionArgs):
        found = reactions.get(args.name)
        problems += _compare(f"反应 {args.name}", found, _snapshot_reaction_differences, args)
    for set_args in plan.args_of(EnsureReactionSetArgs):
        found_set = sets.get(set_args.name)
        problems += _compare(
            f"反应集 {set_args.name}", found_set, reaction_set_differences, set_args
        )
    return problems


def _flowsheet_problems(plan: BuildPlan, snapshot: ModelSnapshot) -> list[str]:
    material = {stream.name for stream in snapshot.streams}
    energy = {stream.name for stream in snapshot.energy_streams}
    problems = [f"物流 {n} 不存在" for n in material_stream_names(plan) if n not in material]
    problems += [f"能流 {n} 不存在" for n in energy_stream_names(plan) if n not in energy]
    reactors = _index(snapshot.reactors)
    for args in plan.args_of(EnsureReactorArgs):
        found = reactors.get(args.name)
        problems += _compare(f"反应器 {args.name}", found, reactor_connection_differences, args)
    return problems


def check_structure(context: CheckContext) -> CheckResult:
    """V2：计划里的对象全部存在，类型、连接和配置与计划一致；计划里的流体包和反应与规格一致。"""
    plan, snapshot = context.plan, context.snapshot
    planned = sum(1 for step in plan.steps if step.case_name is None)
    problems = [
        *_plan_problems(plan, context.spec),
        *_basis_problems(plan, snapshot),
        *_flowsheet_problems(plan, snapshot),
    ]
    expected = (
        f"计划里的 {planned} 个对象全部存在，类型和连接与计划一致；计划里的流体包和反应与规格一致"
    )
    return check_result(CheckId.STRUCTURE, expected, "全部存在且一致", problems)


def _feed_differences(stream: StreamSnapshot, feed: FeedSpec) -> tuple[str, ...]:
    return stream_differences(stream, feed, FEED_TOLERANCE)


def check_feeds(context: CheckContext) -> CheckResult:
    """V3：进料物流读回的温度、压力、流量和组成与规格一致。名字从计划里取，值和规格比。"""
    names = system_feed_names(context.plan)
    feeds = context.spec.feeds
    problems: list[str] = []
    if len(names) != len(feeds):
        problems.append(f"计划里有 {len(names)} 股进料，规格里有 {len(feeds)} 股")
    for name, feed in zip(names, feeds, strict=False):
        problems += _compare(f"进料 {name}", context.snapshot.stream(name), _feed_differences, feed)
    expected = (
        f"进料的温度、压力、流量与规格一致（相对容差 {FEED_TOLERANCE:.0e}），"
        f"摩尔分率的偏差不超过 {FEED_TOLERANCE:.0e}"
    )
    return check_result(CheckId.FEEDS, expected, f"{len(names)} 股进料一致", problems)


def _outlet_temperature(snapshot: ModelSnapshot, reactor_name: str) -> float | None:
    """反应器的出口温度：它的气相出料物流的温度。"""
    reactor = _index(snapshot.reactors).get(reactor_name)
    if reactor is None or reactor.vapour_product is None:
        return None
    outlet = snapshot.stream(reactor.vapour_product)
    return None if outlet is None else outlet.temperature_c


def _duty(snapshot: ModelSnapshot, reactor_name: str) -> float | None:
    """反应器的热负荷：它接的能流的热负荷，吸热为正。"""
    reactor = _index(snapshot.reactors).get(reactor_name)
    if reactor is None or reactor.energy_stream is None:
        return None
    energy = next((e for e in snapshot.energy_streams if e.name == reactor.energy_stream), None)
    return None if energy is None else energy.duty_kw


def _temperature_problems(context: CheckContext) -> list[str]:
    wanted = context.case.outlet_temperature_c
    if wanted is None:
        return []
    problems = []
    for reactor in context.plan.args_of(EnsureReactorArgs):
        actual = _outlet_temperature(context.snapshot, reactor.name)
        if actual is None or abs(actual - wanted) > OUTLET_TEMPERATURE_TOLERANCE_C:
            problems.append(
                f"{reactor.name} 的出口温度应为 {wanted:g} °C，实测 {describe(actual)} °C"
            )
    return problems


def _duty_problems(context: CheckContext) -> list[str]:
    wanted = context.case.duty_kw
    if wanted is None:
        return []
    problems = []
    for reactor in context.plan.args_of(EnsureReactorArgs):
        actual = _duty(context.snapshot, reactor.name)
        if not values_close(actual, wanted):
            problems.append(
                f"{reactor.name} 的热负荷应为 {wanted:g} kW，实测 {describe(actual)} kW"
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
    """V4：当前工况的出口温度（±0.1 °C）或热负荷，以及压降，等于规格里的规定。

    工况的值取自规格里的工况，对计划里的每台反应器都要成立；绝热的工况没有值要比。
    """
    problems = [
        *_temperature_problems(context),
        *_duty_problems(context),
        *_pressure_drop_problems(context),
    ]
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

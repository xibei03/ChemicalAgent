"""Recipe 的接口，以及各种反应器共用的编译步骤和规则。

随反应器类型变化的部分在各自的模块里。这里只有“每种反应器都一样”的东西：物性包、进料、出料、
能流、反应和反应集的入参，各工况的规定，以及对组分和反应的通用规则。对象名按计划 §9.5 的约定
生成，LLM 不参与命名。
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from reactor_agent.errors import ErrorCode
from reactor_agent.spec.components import ComponentTable, atoms_by_component, find_component
from reactor_agent.spec.enums import HeatMode, ReactionKind, ReactorType, SpecVariable, StreamKind
from reactor_agent.spec.model_spec import FeedSpec, ModelSpec, OperatingCase
from reactor_agent.spec.plan import BasisArgs, BuildPlan, FlowsheetArgs, assemble_plan
from reactor_agent.spec.results import CheckContext, CheckResult, Issue
from reactor_agent.spec.tool_args import (
    EnsureReactionArgs,
    EnsureReactionSetArgs,
    EnsureReactorArgs,
    EnsureStreamArgs,
    EnsureThermoArgs,
    FeedConditions,
    ReactionDefinition,
    SetSpecArgs,
)

FEED_NAME = "Feed"
VAPOUR_NAME = "Vap"
LIQUID_NAME = "Liq"
ENERGY_NAME = "Q-100"
REACTION_SET_NAME = "RxnSet-1"
# 反应式里元素的净增量超过这个元素被搬动的总量的这个比例，就算反应式不守恒。
STOICHIOMETRY_BALANCE_TOLERANCE = 1e-3
KIND_NAMES = {ReactionKind.CONVERSION: "转化", ReactionKind.EQUILIBRIUM: "平衡"}


class ReactorRecipe(Protocol):
    """一种反应器怎么从规格建成模型：规则、编译、专有检查。纯函数，不做 I/O，不知道仿真软件。"""

    def rules(self, spec: ModelSpec, components: ComponentTable, /) -> tuple[Issue, ...]:
        """这种反应器对规格的要求，没有问题时是空的。"""
        ...

    def compile(self, spec: ModelSpec, components: ComponentTable, /) -> BuildPlan:
        """规格 → 有序、幂等的建模步骤。规格必须已经通过规则。"""
        ...

    def checks(self, context: CheckContext, /) -> tuple[CheckResult, ...]:
        """只有这种反应器才有的结果检查。"""
        ...


@dataclass(frozen=True)
class ReactorWiring:
    """一台反应器的对象名：它自己、进料、两股出料和能流。"""

    name: str
    feeds: tuple[str, ...]
    vapour: str
    liquid: str
    energy: str


def feed_name(index: int) -> str:
    """第 index 股进料的对象名：Feed、Feed-2、Feed-3……"""
    return FEED_NAME if index == 0 else f"{FEED_NAME}-{index + 1}"


def feed_names(spec: ModelSpec) -> tuple[str, ...]:
    """规格里每股进料的对象名，顺序与规格一致。"""
    return tuple(feed_name(index) for index in range(len(spec.feeds)))


def thermo_args(spec: ModelSpec) -> EnsureThermoArgs:
    """流体包：规格里的组分表和物性包。"""
    return EnsureThermoArgs(components=spec.components, property_package=spec.property_package)


def reaction_args(reactions: Sequence[ReactionDefinition]) -> list[BasisArgs]:
    """每个反应一步（Rxn-1、Rxn-2……），再加一个包含它们全部的反应集；没有反应时是空的。"""
    names = tuple(f"Rxn-{index + 1}" for index in range(len(reactions)))
    steps: list[BasisArgs] = [
        EnsureReactionArgs(name=name, reaction=reaction)
        for name, reaction in zip(names, reactions, strict=True)
    ]
    if names:
        steps.append(EnsureReactionSetArgs(name=REACTION_SET_NAME, reactions=names))
    return steps


def _conditions(feed: FeedSpec) -> FeedConditions:
    """进料的规定。FeedSpec 比 FeedConditions 多一个标签 name，工具的入参里不能带它。"""
    return FeedConditions(
        temperature_c=feed.temperature_c,
        pressure_bar=feed.pressure_bar,
        composition=feed.composition,
        molar_flow_kmol_h=feed.molar_flow_kmol_h,
        mass_flow_kg_h=feed.mass_flow_kg_h,
    )


def feed_streams(spec: ModelSpec) -> list[FlowsheetArgs]:
    """进料物流，一股一步。"""
    return [
        EnsureStreamArgs(name=name, conditions=_conditions(feed))
        for name, feed in zip(feed_names(spec), spec.feeds, strict=True)
    ]


def reactor_block(
    wiring: ReactorWiring,
    reactor_type: ReactorType,
    heat_mode: HeatMode,
    reaction_set: str | None,
    pressure_drop_bar: float,
) -> list[FlowsheetArgs]:
    """一台反应器和它的出料、能流。反应器的连接要求出料和能流已经存在，所以反应器排在最后。"""
    adiabatic = heat_mode is HeatMode.ADIABATIC
    steps: list[FlowsheetArgs] = [
        EnsureStreamArgs(name=wiring.vapour),
        EnsureStreamArgs(name=wiring.liquid),
    ]
    if not adiabatic:
        steps.append(EnsureStreamArgs(name=wiring.energy, kind=StreamKind.ENERGY))
    steps.append(
        EnsureReactorArgs(
            name=wiring.name,
            reactor_type=reactor_type,
            feeds=wiring.feeds,
            vapour_product=wiring.vapour,
            liquid_product=wiring.liquid,
            energy_stream=None if adiabatic else wiring.energy,
            reaction_set=reaction_set,
            pressure_drop_bar=pressure_drop_bar,
            heat_mode=heat_mode,
        )
    )
    return steps


def _case_steps(case: OperatingCase, reactor_names: Sequence[str]) -> list[SetSpecArgs]:
    if case.outlet_temperature_c is not None:
        variable, value = SpecVariable.OUTLET_TEMPERATURE_C, case.outlet_temperature_c
    elif case.duty_kw is not None:
        variable, value = SpecVariable.DUTY_KW, case.duty_kw
    else:
        return []
    return [SetSpecArgs(object_name=name, variable=variable, value=value) for name in reactor_names]


def case_specs(spec: ModelSpec, reactor_names: Sequence[str]) -> dict[str, list[SetSpecArgs]]:
    """每个工况要改的规定值：出口温度或热负荷，对每台反应器各一步；绝热的工况没有。"""
    return {case.name: _case_steps(case, reactor_names) for case in spec.cases}


def single_reactor_plan(spec: ModelSpec, reactor_name: str) -> BuildPlan:
    """一台反应器的计划，即计划 §17 的构建表去掉头两步：Basis、进料、出料和能流、反应器、工况。"""
    wiring = ReactorWiring(
        name=reactor_name,
        feeds=feed_names(spec),
        vapour=VAPOUR_NAME,
        liquid=LIQUID_NAME,
        energy=ENERGY_NAME,
    )
    reaction_set = REACTION_SET_NAME if spec.reactions else None
    block = reactor_block(
        wiring, spec.reactor_type, spec.heat_mode, reaction_set, spec.pressure_drop_bar
    )
    return assemble_plan(
        basis=[thermo_args(spec), *reaction_args(spec.reactions)],
        flowsheet=[*feed_streams(spec), *block],
        cases=case_specs(spec, (reactor_name,)),
    )


def reactions_by_reactor(
    plan: BuildPlan,
) -> tuple[tuple[EnsureReactorArgs, dict[str, ReactionDefinition]], ...]:
    """计划里每台反应器，以及它的反应集里的反应（名字 → 定义）；没有挂反应集的是空的。"""
    reactions = {args.name: args.reaction for args in plan.args_of(EnsureReactionArgs)}
    members = {args.name: args.reactions for args in plan.args_of(EnsureReactionSetArgs)}
    return tuple(
        (reactor, {n: reactions[n] for n in members.get(reactor.reaction_set or "", ())})
        for reactor in plan.args_of(EnsureReactorArgs)
    )


def _component_issues(spec: ModelSpec, table: ComponentTable) -> tuple[Issue, ...]:
    issues = []
    for index, name in enumerate(spec.components):
        entry = find_component(table, name)
        if entry is None:
            message = f"组分 {name!r} 不在组分表里"
        elif entry.name != name:
            message = f"组分要写规范名 {entry.name!r}，不是 {name!r}"
        else:
            continue
        issues.append(
            Issue(
                code=ErrorCode.COMPONENT_NOT_FOUND,
                field_path=f"components[{index}]",
                message=message,
                user_fixable=False,
            )
        )
    return tuple(issues)


def _element_imbalances(
    reaction: ReactionDefinition, atoms: Mapping[str, Mapping[str, int]]
) -> dict[str, float]:
    net: dict[str, float] = {}
    moved: dict[str, float] = {}
    for term in reaction.stoichiometry:
        for element, count in atoms[term.component].items():
            net[element] = net.get(element, 0.0) + term.coefficient * count
            moved[element] = moved.get(element, 0.0) + abs(term.coefficient * count)
    return {el: n for el, n in net.items() if abs(n) > STOICHIOMETRY_BALANCE_TOLERANCE * moved[el]}


def _reaction_balance_issues(spec: ModelSpec, table: ComponentTable) -> tuple[Issue, ...]:
    atoms = atoms_by_component(table)
    issues = []
    for index, reaction in enumerate(spec.reactions):
        if any(term.component not in atoms for term in reaction.stoichiometry):
            continue  # 组分不在组分表里，由 _component_issues 报告
        wrong = _element_imbalances(reaction, atoms)
        if wrong:
            detail = "、".join(
                f"{element} 净增 {net:+.4g}" for element, net in sorted(wrong.items())
            )
            issues.append(
                Issue(
                    code=ErrorCode.REACTION_INVALID,
                    field_path=f"reactions[{index}].stoichiometry",
                    message=f"反应式不满足元素守恒（按分子式计算）：{detail}",
                    user_fixable=False,
                )
            )
    return tuple(issues)


def common_rules(spec: ModelSpec, table: ComponentTable) -> tuple[Issue, ...]:
    """每种反应器都要满足的规则：组分都在组分表里并且用规范名，每个反应元素守恒。"""
    return (*_component_issues(spec, table), *_reaction_balance_issues(spec, table))


def unsupported_heat_modes(
    spec: ModelSpec, supported: frozenset[HeatMode], what: str | None = None
) -> tuple[Issue, ...]:
    """热模式不在验证过的范围内时的问题；what 说明是什么只支持这些，默认是这种反应器。"""
    if spec.heat_mode in supported:
        return ()
    allowed = "、".join(sorted(mode.value for mode in supported))
    message = f"{what or f'{spec.reactor_type.value} 反应器'}只支持这些热模式：{allowed}"
    return (
        Issue(
            code=ErrorCode.UNSUPPORTED, field_path="heat_mode", message=message, user_fixable=False
        ),
    )


def reaction_kind_issues(spec: ModelSpec, kind: ReactionKind) -> tuple[Issue, ...]:
    """转化、平衡反应器的要求：至少一个反应，并且全部是这种类型的反应。"""
    if not spec.reactions:
        message = f"{spec.reactor_type.value} 反应器至少要有一个{KIND_NAMES[kind]}反应"
        return (
            Issue(code=ErrorCode.RULE, field_path="reactions", message=message, user_fixable=True),
        )
    allowed = f"{spec.reactor_type.value} 反应器只能用{KIND_NAMES[kind]}反应"
    return tuple(
        Issue(
            code=ErrorCode.SET_INCOMPATIBLE,
            field_path=f"reactions[{index}]",
            message=f"{allowed}，这里是 {reaction.kind.value}",
            user_fixable=False,
        )
        for index, reaction in enumerate(spec.reactions)
        if reaction.kind is not kind
    )

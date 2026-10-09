"""Gibbs 反应器的 Recipe：不需要反应式，产物由组分表决定，按 Gibbs 自由能最小化求平衡。

进料含固体碳时，库里碳的热力学数据让 Gibbs 反应器算出错误的结果（台账 L24、L25），所以编译成
两段式（D14 方案 A）：先用转化反应器让碳和水按限量反应物生成 CO 和氢气，再让气相进 Gibbs 反应器，
未反应的碳从第一台的液相出料旁路。主模型仍是 Gibbs 反应器，报告里要如实说明这一点。
"""

from collections.abc import Iterable, Mapping

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.recipes.base import (
    REACTION_SET_NAME,
    ReactorWiring,
    case_specs,
    common_rules,
    feed_names,
    feed_streams,
    reaction_args,
    reactor_block,
    single_reactor_plan,
    thermo_args,
    unsupported_heat_modes,
)
from reactor_agent.recipes.conversion import conversion_checks
from reactor_agent.spec.components import (
    ComponentTable,
    atoms_by_component,
    feed_molar_flow_kmol_h,
    find_component,
    names_with_formula,
)
from reactor_agent.spec.enums import ComponentPhase, HeatMode, ReactionPhase, ReactorType
from reactor_agent.spec.model_spec import ModelSpec
from reactor_agent.spec.plan import BuildPlan, assemble_plan
from reactor_agent.spec.results import CheckContext, CheckResult, Issue, make_issue
from reactor_agent.spec.tool_args import ConversionReaction, StoichiometricTerm

REACTOR_NAME = "GBR-100"
FIRST_STAGE_NAME = "CRV-100"
HEAT_MODES = frozenset({HeatMode.SPECIFIED_OUTLET_TEMPERATURE, HeatMode.ADIABATIC})
# 两段式只验证过规定出口温度（台账 E10d）。
TWO_STAGE_HEAT_MODES = frozenset({HeatMode.SPECIFIED_OUTLET_TEMPERATURE})
TWO_STAGE_NAME = "含固体碳的 Gibbs 反应器（两段式）"
# 固体碳的气化反应，系数都是 1：反应物依次是固体和水，产物依次是一氧化碳和氢气。
GASIFICATION_EQUATION = "C + H2O -> CO + H2"
CARBON_FORMULA, WATER_FORMULA, MONOXIDE_FORMULA, HYDROGEN_FORMULA = (
    formula.strip() for side in GASIFICATION_EQUATION.split("->") for formula in side.split("+")
)
FULL_CONVERSION_PERCENT = 100.0


def _fed_components(spec: ModelSpec) -> set[str]:
    return {
        item.component
        for feed in spec.feeds
        for item in feed.composition
        if item.mole_fraction > 0.0
    }


def _is_solid(table: ComponentTable, name: str) -> bool:
    entry = find_component(table, name)
    return entry is not None and entry.phase is ComponentPhase.SOLID


def _solid_feed_components(spec: ModelSpec, table: ComponentTable) -> tuple[str, ...]:
    fed = _fed_components(spec)
    return tuple(name for name in spec.components if name in fed and _is_solid(table, name))


def _elements(names: Iterable[str], atoms: Mapping[str, Mapping[str, int]]) -> set[str]:
    """这些组分里出现的元素。不在 atoms 里的组分由通用规则报告，这里跳过。"""
    return {element for name in names if name in atoms for element in atoms[name]}


def _unfed_solid_issues(spec: ModelSpec, table: ComponentTable) -> tuple[Issue, ...]:
    """固体只能在进料里（两段式）。库里固体碳的热力学数据让它当不了 Gibbs 反应器的产物。"""
    fed = _fed_components(spec)
    return tuple(
        make_issue(
            ErrorCode.UNSUPPORTED,
            f"components[{index}]",
            f"固体组分 {name} 不在进料里；Gibbs 反应器不能让固体作为产物生成",
        )
        for index, name in enumerate(spec.components)
        if name not in fed and _is_solid(table, name)
    )


def _reaction_issues(spec: ModelSpec) -> tuple[Issue, ...]:
    if not spec.reactions:
        return ()
    message = "Gibbs 反应器不使用反应式，副反应通过组分表体现；请删除 reactions，或者改用平衡反应器"
    return (make_issue(ErrorCode.SET_INCOMPATIBLE, "reactions", message),)


def _coverage_issues(spec: ModelSpec, table: ComponentTable) -> tuple[Issue, ...]:
    """进料里的每种元素都要有至少一个非固体的组分可以容纳，固体不能作为 Gibbs 反应器的产物。"""
    atoms = atoms_by_component(table)
    holders = [name for name in spec.components if not _is_solid(table, name)]
    missing = sorted(_elements(_fed_components(spec), atoms) - _elements(holders, atoms))
    if not missing:
        return ()
    message = (
        f"进料里的元素 {missing} 在组分表里没有非固体的组分可以容纳，Gibbs 反应器无法让它们"
        "参与平衡；请把可能生成的产物加进组分表"
    )
    return (make_issue(ErrorCode.RULE, "components", message),)


def _two_stage_issues(
    spec: ModelSpec, table: ComponentTable, solids: tuple[str, ...]
) -> tuple[Issue, ...]:
    carbon = set(names_with_formula(table, CARBON_FORMULA))
    water = set(names_with_formula(table, WATER_FORMULA))
    fed = _fed_components(spec)
    issues = []
    if not set(solids) <= carbon or not fed <= carbon | water:
        message = "含固体的 Gibbs 反应器目前只支持固体碳和水的进料"
        issues.append(make_issue(ErrorCode.UNSUPPORTED, "feeds", message))
    if not fed & water:
        message = "含固体碳的进料需要有水，碳靠水气化"
        issues.append(make_issue(ErrorCode.RULE, "feeds", message, user_fixable=True))
    for formula in (MONOXIDE_FORMULA, HYDROGEN_FORMULA):
        if not set(names_with_formula(table, formula)) & set(spec.components):
            message = f"组分表里要有分子式为 {formula} 的组分，作为碳气化的产物"
            issues.append(make_issue(ErrorCode.RULE, "components", message))
    return (*issues, *unsupported_heat_modes(spec, TWO_STAGE_HEAT_MODES, TWO_STAGE_NAME))


def _component_with(spec: ModelSpec, table: ComponentTable, formula: str) -> str:
    """规格的组分表里分子式为 formula 的第一个组分。规格通过规则之后一定存在。"""
    candidates = set(names_with_formula(table, formula))
    found = next((name for name in spec.components if name in candidates), None)
    if found is None:
        message = f"组分表里没有分子式为 {formula} 的组分；规格要先通过 Recipe 的规则再编译"
        raise ReactorAgentError(ErrorCode.RULE, message)
    return found


def _limiting_reactant(spec: ModelSpec, table: ComponentTable, carbon: str, water: str) -> str:
    """碳和水按 1:1 反应，进料里摩尔量少的是限量反应物；相等时取水。"""
    moles = {carbon: 0.0, water: 0.0}
    for feed in spec.feeds:
        flow = feed_molar_flow_kmol_h(feed, table)
        for item in feed.composition:
            if item.component in moles:
                moles[item.component] += flow * item.mole_fraction
    return carbon if moles[carbon] < moles[water] else water


def _two_stage_plan(spec: ModelSpec, table: ComponentTable) -> BuildPlan:
    formulas = (CARBON_FORMULA, WATER_FORMULA, MONOXIDE_FORMULA, HYDROGEN_FORMULA)
    carbon, water, monoxide, hydrogen = (_component_with(spec, table, f) for f in formulas)
    gasification = ConversionReaction(
        stoichiometry=(
            StoichiometricTerm(component=carbon, coefficient=-1.0),
            StoichiometricTerm(component=water, coefficient=-1.0),
            StoichiometricTerm(component=monoxide, coefficient=1.0),
            StoichiometricTerm(component=hydrogen, coefficient=1.0),
        ),
        base_component=_limiting_reactant(spec, table, carbon, water),
        conversion_percent=FULL_CONVERSION_PERCENT,
        phase=ReactionPhase.COMBINED,  # 进料是固液浆料，反应相要用合并相（D15 对 R4 的补充）
    )
    first = ReactorWiring(
        name=FIRST_STAGE_NAME, feeds=feed_names(spec), vapour="Vap-1", liquid="Liq-1", energy="Q-1"
    )
    second = ReactorWiring(
        name=REACTOR_NAME, feeds=(first.vapour,), vapour="Vap-2", liquid="Liq-2", energy="Q-2"
    )
    heat_mode = spec.heat_mode
    return assemble_plan(
        basis=[thermo_args(spec), *reaction_args((gasification,))],
        flowsheet=[
            *feed_streams(spec),
            *reactor_block(
                first, ReactorType.CONVERSION, heat_mode, REACTION_SET_NAME, spec.pressure_drop_bar
            ),
            *reactor_block(second, ReactorType.GIBBS, heat_mode, None, 0.0),
        ],
        cases=case_specs(spec, (first.name, second.name)),
    )


class GibbsRecipe:
    """Gibbs 反应器：没有反应式；含固体碳时编译成转化反应器加 Gibbs 反应器的两段式。"""

    def rules(self, spec: ModelSpec, components: ComponentTable, /) -> tuple[Issue, ...]:
        """没有反应；元素都有非固体的组分容纳；热模式受限；固体碳的进料有额外要求。"""
        solids = _solid_feed_components(spec, components)
        specific = (
            _two_stage_issues(spec, components, solids)
            if solids
            else unsupported_heat_modes(spec, HEAT_MODES)
        )
        return (
            *common_rules(spec, components),
            *_reaction_issues(spec),
            *_coverage_issues(spec, components),
            *_unfed_solid_issues(spec, components),
            *specific,
        )

    def compile(self, spec: ModelSpec, components: ComponentTable, /) -> BuildPlan:
        """一台 Gibbs 反应器；进料含固体碳时是转化反应器加 Gibbs 反应器。"""
        if _solid_feed_components(spec, components):
            return _two_stage_plan(spec, components)
        return single_reactor_plan(spec, REACTOR_NAME)

    def checks(self, context: CheckContext, /) -> tuple[CheckResult, ...]:
        """两段式的第一台转化反应器：限量反应物的转化率等于设定值；单段没有专有检查。"""
        return conversion_checks(context)

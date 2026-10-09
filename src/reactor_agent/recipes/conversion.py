"""转化反应器的 Recipe：每个反应按给定的转化率进行，不需要动力学和平衡数据。

HYSYS 按进料里基准组分的量计算转化率；同一基准组分的几个反应并行进行（台账 H9 之后的 E6b，D13），
所以基准组分实际的转化率等于这些反应转化率之和。规则保证这个等式成立，专有检查验证它。
"""

from collections.abc import Iterable
from typing import NamedTuple

from reactor_agent.errors import ErrorCode
from reactor_agent.recipes.base import (
    common_rules,
    fed_components,
    reaction_kind_issues,
    reactions_by_reactor,
    single_reactor_plan,
    unsupported_heat_modes,
)
from reactor_agent.spec.balances import conversion_percent
from reactor_agent.spec.components import ComponentTable
from reactor_agent.spec.enums import CheckId, HeatMode, ReactionKind
from reactor_agent.spec.model_spec import ModelSpec
from reactor_agent.spec.plan import BuildPlan
from reactor_agent.spec.results import (
    CheckContext,
    CheckResult,
    Issue,
    check_result,
    describe,
    make_issue,
)
from reactor_agent.spec.tool_args import ConversionReaction, EnsureReactorArgs, ReactionDefinition

REACTOR_NAME = "CRV-100"
HEAT_MODES = frozenset({HeatMode.SPECIFIED_OUTLET_TEMPERATURE, HeatMode.ADIABATIC})
MAX_TOTAL_CONVERSION_PERCENT = 100.0
PERCENT_EPSILON = 1e-9
# 计划 §12.3 V4：转化率等于设定，允许 ±0.1 个百分点。
CONVERSION_TOLERANCE_PERCENT = 0.1


def _totals_by_base(reactions: Iterable[ReactionDefinition]) -> dict[str, float]:
    """每个基准组分的转化率之和（%）。"""
    totals: dict[str, float] = {}
    for reaction in reactions:
        if isinstance(reaction, ConversionReaction):
            base = reaction.base_component
            totals[base] = totals.get(base, 0.0) + reaction.conversion_percent
    return totals


def _parallel_sum_issues(spec: ModelSpec) -> tuple[Issue, ...]:
    return tuple(
        make_issue(
            ErrorCode.RULE,
            "reactions",
            f"以 {base} 为基准的转化率之和是 {total:g}%，超过了 100%",
            user_fixable=True,
        )
        for base, total in _totals_by_base(spec.reactions).items()
        if total - MAX_TOTAL_CONVERSION_PERCENT > PERCENT_EPSILON
    )


def _shared_base_issues(spec: ModelSpec) -> tuple[Issue, ...]:
    bases = set(_totals_by_base(spec.reactions))
    issues = []
    for index, reaction in enumerate(spec.reactions):
        if not isinstance(reaction, ConversionReaction):
            continue
        involved = {term.component for term in reaction.stoichiometry}
        others = sorted((involved & bases) - {reaction.base_component})
        if others:
            message = (
                f"{others} 是别的转化反应的基准组分，又出现在这个反应里；转化率按进料里的量"
                "计算，不支持前后串联的反应"
            )
            issues.append(make_issue(ErrorCode.UNSUPPORTED, f"reactions[{index}]", message))
    return tuple(issues)


def _base_in_feed_issues(spec: ModelSpec) -> tuple[Issue, ...]:
    """基准组分不在进料里，转化率就没有意义：出料里实测的转化率永远是“未知”。"""
    fed = fed_components(spec)
    return tuple(
        make_issue(
            ErrorCode.RULE,
            f"reactions[{index}]",
            f"转化反应的基准组分 {reaction.base_component} 不在进料里",
            user_fixable=True,
        )
        for index, reaction in enumerate(spec.reactions)
        if isinstance(reaction, ConversionReaction) and reaction.base_component not in fed
    )


def _measured_conversion(
    context: CheckContext, reactor: EnsureReactorArgs, base: str
) -> float | None:
    snapshot = context.snapshot
    feeds = snapshot.streams_named(reactor.feeds)
    outlets = snapshot.streams_named((reactor.vapour_product, reactor.liquid_product))
    if feeds is None or outlets is None:
        return None
    return conversion_percent(feeds, outlets, base)


class _ConversionRow(NamedTuple):
    """一台反应器的一个基准组分：规定的转化率和实测的转化率（%）。"""

    reactor: str
    base: str
    wanted: float
    actual: float | None


def conversion_checks(context: CheckContext) -> tuple[CheckResult, ...]:
    """每台挂了转化反应的反应器：基准组分实际的转化率等于各反应转化率之和（±0.1 个百分点）。"""
    rows = [
        _ConversionRow(
            entry.reactor.name, base, wanted, _measured_conversion(context, entry.reactor, base)
        )
        for entry in reactions_by_reactor(context.plan)
        for base, wanted in _totals_by_base(entry.reactions.values()).items()
    ]
    if not rows:
        return ()
    expected = "；".join(f"{row.base} 转化 {row.wanted:g}%" for row in rows)
    found = "；".join(f"{row.base} 转化 {describe(row.actual)}%" for row in rows)
    problems = [
        f"{row.reactor} 的 {row.base} 转化率应为 {row.wanted:g}%，实测 {describe(row.actual)}%"
        for row in rows
        if row.actual is None or abs(row.actual - row.wanted) > CONVERSION_TOLERANCE_PERCENT
    ]
    return (check_result(CheckId.CONVERSION_SPECIFIED, expected, found, problems),)


class ConversionRecipe:
    """转化反应器：反应只能是转化反应，热模式是绝热或规定出口温度。"""

    def rules(self, spec: ModelSpec, components: ComponentTable, /) -> tuple[Issue, ...]:
        """至少一个转化反应、没有平衡反应；同一基准组分的转化率之和不超过 100%；热模式受限。"""
        return (
            *common_rules(spec, components),
            *reaction_kind_issues(spec, ReactionKind.CONVERSION),
            *unsupported_heat_modes(spec, HEAT_MODES),
            *_parallel_sum_issues(spec),
            *_shared_base_issues(spec),
            *_base_in_feed_issues(spec),
        )

    def compile(self, spec: ModelSpec, _components: ComponentTable, /) -> BuildPlan:
        """Basis、进料、出料和能流、转化反应器、各工况的出口温度。"""
        return single_reactor_plan(spec, REACTOR_NAME)

    def checks(self, context: CheckContext, /) -> tuple[CheckResult, ...]:
        """基准组分实际的转化率等于设定值。"""
        return conversion_checks(context)

"""平衡反应器的 Recipe：反应是可逆的平衡反应，平衡常数来自 Gibbs 自由能，或者直接给定。"""

import math
from typing import NamedTuple

from reactor_agent.errors import ErrorCode
from reactor_agent.recipes.base import (
    common_rules,
    reaction_kind_issues,
    reactions_by_reactor,
    single_reactor_plan,
)
from reactor_agent.spec.components import ComponentTable, is_solid
from reactor_agent.spec.enums import CheckId, KeqSource, ReactionKind
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
from reactor_agent.spec.snapshot import StreamSnapshot
from reactor_agent.spec.tool_args import EquilibriumReaction

REACTOR_NAME = "ERV-100"
# 固定 K 的反应商与给定 K 的相对偏差上限。反应商由读回的摩尔分率算出，误差来自分率的有效位数。
FIXED_K_TOLERANCE = 1e-3


def _solid_equilibrium_issues(spec: ModelSpec, table: ComponentTable) -> tuple[Issue, ...]:
    """用 Gibbs 自由能算平衡常数的反应不能含固体组分：库里固体碳的 Gibbs 数据是气态碳原子的。"""
    issues = []
    for index, reaction in enumerate(spec.reactions):
        if not isinstance(reaction, EquilibriumReaction):
            continue
        solids = [t.component for t in reaction.stoichiometry if is_solid(table, t.component)]
        if solids and reaction.keq_source is KeqSource.GIBBS_ENERGY:
            message = (
                f"含固体组分 {solids} 的反应不能用 Gibbs 自由能算平衡常数（库里固体碳的 Gibbs 数据"
                "是气态碳原子的，台账 L25）；请直接给定平衡常数，或者改用转化反应器"
            )
            issues.append(make_issue(ErrorCode.UNSUPPORTED, f"reactions[{index}]", message))
    return tuple(issues)


def _quotient(reaction: EquilibriumReaction, outlet: StreamSnapshot | None) -> float | None:
    """气相出料算出的反应商：各组分摩尔分率的“计量系数次方”之积。有分率读不到或为 0 时是 None。"""
    if outlet is None:
        return None
    fractions = {item.name: item.mole_fraction for item in outlet.components}
    value = 1.0
    for term in reaction.stoichiometry:
        fraction = fractions.get(term.component)
        if fraction is None or fraction <= 0.0:
            return None
        value *= fraction**term.coefficient
    return value


class _QuotientRow(NamedTuple):
    """一个固定 K 的反应：给定的平衡常数，和出料算出的反应商。"""

    reaction: str
    constant: float
    quotient: float | None


def fixed_k_checks(context: CheckContext) -> tuple[CheckResult, ...]:
    """给定了平衡常数 K 的反应：气相出料算出的反应商等于 K（摩尔分率基准，台账 H10）。"""
    rows = []
    for entry in reactions_by_reactor(context.plan):
        outlet = context.snapshot.stream(entry.reactor.vapour_product)
        for name, reaction in entry.reactions.items():
            if not isinstance(reaction, EquilibriumReaction):
                continue
            if reaction.equilibrium_constant is not None:
                quotient = _quotient(reaction, outlet)
                rows.append(_QuotientRow(name, reaction.equilibrium_constant, quotient))
    if not rows:
        return ()
    expected = "；".join(f"{row.reaction}：K = {row.constant:g}" for row in rows)
    found = "；".join(f"{row.reaction}：K = {describe(row.quotient)}" for row in rows)
    problems = [
        f"{row.reaction} 的平衡常数应为 {row.constant:g}，出料算出 {describe(row.quotient)}"
        for row in rows
        if row.quotient is None
        or not math.isclose(row.quotient, row.constant, rel_tol=FIXED_K_TOLERANCE)
    ]
    return (check_result(CheckId.FIXED_K_SATISFIED, expected, found, problems),)


class EquilibriumRecipe:
    """平衡反应器：反应只能是平衡反应。三种热模式都验证过，所以规则不限制热模式。"""

    def rules(self, spec: ModelSpec, components: ComponentTable, /) -> tuple[Issue, ...]:
        """至少一个平衡反应、没有转化反应；Gibbs 自由能算 K 的反应不含固体。"""
        return (
            *common_rules(spec, components),
            *reaction_kind_issues(spec, ReactionKind.EQUILIBRIUM),
            *_solid_equilibrium_issues(spec, components),
        )

    def compile(self, spec: ModelSpec, _components: ComponentTable, /) -> BuildPlan:
        """Basis、进料、出料和能流、平衡反应器、各工况的出口温度或热负荷。"""
        return single_reactor_plan(spec, REACTOR_NAME)

    def checks(self, context: CheckContext, /) -> tuple[CheckResult, ...]:
        """固定 K 的反应：反应商等于 K。Gibbs 自由能算出的 K 没有独立的算法可以核对。"""
        return fixed_k_checks(context)

"""平衡反应器的 Recipe：反应是可逆的平衡反应，平衡常数来自 Gibbs 自由能，或者直接给定。"""

import math

from reactor_agent.recipes.base import (
    common_rules,
    reaction_kind_issues,
    reactions_by_reactor,
    single_reactor_plan,
    unsupported_heat_modes,
)
from reactor_agent.spec.components import ComponentTable
from reactor_agent.spec.enums import CheckId, HeatMode, ReactionKind
from reactor_agent.spec.model_spec import ModelSpec
from reactor_agent.spec.plan import BuildPlan
from reactor_agent.spec.results import CheckContext, CheckResult, Issue, check_result, describe
from reactor_agent.spec.snapshot import StreamSnapshot
from reactor_agent.spec.tool_args import EquilibriumReaction

REACTOR_NAME = "ERV-100"
HEAT_MODES = frozenset(HeatMode)
# 固定 K 的反应商与给定 K 的相对偏差上限。反应商由读回的摩尔分率算出，误差来自分率的有效位数。
FIXED_K_TOLERANCE = 1e-3


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


def fixed_k_checks(context: CheckContext) -> tuple[CheckResult, ...]:
    """给定了平衡常数 K 的反应：气相出料算出的反应商等于 K（摩尔分率基准，台账 H10）。"""
    rows = []
    for reactor, named in reactions_by_reactor(context.plan):
        outlet = context.snapshot.stream(reactor.vapour_product)
        for name, reaction in named.items():
            if not isinstance(reaction, EquilibriumReaction):
                continue
            if reaction.equilibrium_constant is not None:
                rows.append((name, reaction.equilibrium_constant, _quotient(reaction, outlet)))
    if not rows:
        return ()
    expected = "；".join(f"{name}：K = {constant:g}" for name, constant, _ in rows)
    found = "；".join(f"{name}：K = {describe(quotient)}" for name, _, quotient in rows)
    problems = [
        f"{name} 的平衡常数应为 {constant:g}，出料算出 {describe(quotient)}"
        for name, constant, quotient in rows
        if quotient is None or not math.isclose(quotient, constant, rel_tol=FIXED_K_TOLERANCE)
    ]
    return (check_result(CheckId.FIXED_K_SATISFIED, expected, found, problems),)


class EquilibriumRecipe:
    """平衡反应器：反应只能是平衡反应，三种热模式都验证过。"""

    def rules(self, spec: ModelSpec, components: ComponentTable, /) -> tuple[Issue, ...]:
        """至少一个平衡反应、没有转化反应。"""
        return (
            *common_rules(spec, components),
            *reaction_kind_issues(spec, ReactionKind.EQUILIBRIUM),
            *unsupported_heat_modes(spec, HEAT_MODES),
        )

    def compile(self, spec: ModelSpec, _components: ComponentTable, /) -> BuildPlan:
        """Basis、进料、出料和能流、平衡反应器、各工况的出口温度或热负荷。"""
        return single_reactor_plan(spec, REACTOR_NAME)

    def checks(self, context: CheckContext, /) -> tuple[CheckResult, ...]:
        """固定 K 的反应：反应商等于 K。Gibbs 自由能算出的 K 没有独立的算法可以核对。"""
        return fixed_k_checks(context)

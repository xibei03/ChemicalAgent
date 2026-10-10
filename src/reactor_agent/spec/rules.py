"""通用业务规则：计划 §9.4 十条规则里，ModelSpec 自身的校验没有覆盖的那几条。

- 每个反应元素守恒（按组分表的分子式计算）；
- 每个取了默认值的字段都有对应的假设条目；
- 气体体积单位用于含固体或液体的进料时，登记了歧义假设。

数值范围、组分声明、自由度、指标引用的组分由 ModelSpec 的校验器负责；每种反应器专有的规则在
Recipe 里，由 VALIDATE 的处理函数调用，这里不依赖 recipes。
"""

from collections.abc import Mapping, Sequence

from reactor_agent.errors import ErrorCode
from reactor_agent.spec.components import ComponentTable, atoms_by_component
from reactor_agent.spec.enums import ComponentPhase
from reactor_agent.spec.model_spec import ModelSpec, is_assumed
from reactor_agent.spec.results import Issue, make_issue

# 反应式里元素的净增量超过这个元素被搬动的总量的这个比例，就算反应式不守恒。
BALANCE_TOLERANCE = 1e-3


def _imbalances(
    terms: Sequence[tuple[str, float]], atoms: Mapping[str, Mapping[str, int]]
) -> dict[str, float]:
    """每个元素的净增量，只留下超过容差的。"""
    net: dict[str, float] = {}
    moved: dict[str, float] = {}
    for component, coefficient in terms:
        for element, count in atoms[component].items():
            net[element] = net.get(element, 0.0) + coefficient * count
            moved[element] = moved.get(element, 0.0) + abs(coefficient * count)
    return {el: n for el, n in net.items() if abs(n) > BALANCE_TOLERANCE * moved[el]}


def reaction_balance_issues(spec: ModelSpec, table: ComponentTable) -> tuple[Issue, ...]:
    """每个反应按分子式检查元素守恒。出在用户写的反应式上，请用户确认。"""
    atoms = atoms_by_component(table)
    issues = []
    for index, reaction in enumerate(spec.reactions):
        terms = [(term.component, term.coefficient) for term in reaction.stoichiometry]
        if any(component not in atoms for component, _ in terms):
            continue  # 组分不在组分表里，由 Recipe 的通用规则报告
        wrong = _imbalances(terms, atoms)
        if wrong:
            detail = "、".join(f"{el} 净增 {net:+.4g}" for el, net in sorted(wrong.items()))
            message = f"反应式不满足元素守恒（按分子式计算）：{detail}"
            path = f"reactions[{index}].stoichiometry"
            issues.append(make_issue(ErrorCode.RULE, path, message, user_fixable=True))
    return tuple(issues)


def undeclared_default_issues(spec: ModelSpec, defaulted: Sequence[str]) -> tuple[Issue, ...]:
    """每个取了默认值的字段都要有假设条目。没有声明的默认值视为错误。"""
    return tuple(
        make_issue(ErrorCode.RULE, path, f"字段 {path} 取了默认值，却没有登记假设")
        for path in dict.fromkeys(defaulted)
        if not is_assumed(spec, path)
    )


def volume_flow_issues(
    spec: ModelSpec, table: ComponentTable, volume_feeds: Sequence[int]
) -> tuple[Issue, ...]:
    """流量按气体体积单位给出，进料却含固体或液体：要有一条歧义假设说明按摩尔流量理解。"""
    phases = {entry.name: entry.phase for entry in table.components}
    issues = []
    for index in volume_feeds:
        feed = spec.feeds[index]
        non_gas = any(phases[item.component] is not ComponentPhase.GAS for item in feed.composition)
        path = f"feeds[{index}].molar_flow_kmol_h"
        if non_gas and not is_assumed(spec, path):
            message = "气体体积流量单位用于含固体或液体的进料，没有登记歧义假设"
            issues.append(make_issue(ErrorCode.RULE, path, message))
    return tuple(issues)


def general_rules(
    spec: ModelSpec, table: ComponentTable, defaulted: Sequence[str], volume_feeds: Sequence[int]
) -> tuple[Issue, ...]:
    """全部通用规则的问题，没有问题时是空的。"""
    return (
        *reaction_balance_issues(spec, table),
        *undeclared_default_issues(spec, defaulted),
        *volume_flow_issues(spec, table, volume_feeds),
    )

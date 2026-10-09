"""V7 守恒：总质量守恒，以及规格组分里出现的每种元素守恒（计划 §12.3）。

V7 能发现“仿真软件说已求解，但模型本身是错的”这一类问题，比如计量系数写错、固体相丢失。进料和
出料各按全部系统物流合计，固体从哪股出料离开就算在哪股里。
"""

import math

from reactor_agent.spec.balances import total_element_flow_kmol_h, total_mass_flow_kg_h
from reactor_agent.spec.components import atoms_by_component
from reactor_agent.spec.enums import CheckId
from reactor_agent.spec.plan import system_feed_names, system_outlet_names
from reactor_agent.spec.results import CheckContext, CheckResult, check_result, describe
from reactor_agent.spec.snapshot import StreamSnapshot

MASS_BALANCE_TOLERANCE = 1e-4
ELEMENT_BALANCE_TOLERANCE = 1e-3
# 两边都接近 0 的量（比如进料里没有的元素）相对误差没有意义，差在这个范围内就算守恒。
ABSOLUTE_TOLERANCE = 1e-9

# 项目名、进的量、出的量、相对误差上限
BalanceRow = tuple[str, float | None, float | None, float]


def _balance_rows(
    context: CheckContext, feeds: tuple[StreamSnapshot, ...], outlets: tuple[StreamSnapshot, ...]
) -> list[BalanceRow]:
    atoms = atoms_by_component(context.components)
    elements = sorted({e for name in context.spec.components for e in atoms.get(name, {})})
    rows: list[BalanceRow] = [
        (
            "总质量 kg/h",
            total_mass_flow_kg_h(feeds),
            total_mass_flow_kg_h(outlets),
            MASS_BALANCE_TOLERANCE,
        )
    ]
    rows += [
        (
            f"元素 {element} kmol/h",
            total_element_flow_kmol_h(feeds, element, atoms),
            total_element_flow_kmol_h(outlets, element, atoms),
            ELEMENT_BALANCE_TOLERANCE,
        )
        for element in elements
    ]
    return rows


def _relative_error(fed: float | None, left: float | None) -> float | None:
    if fed is None or left is None:
        return None
    scale = max(abs(fed), abs(left))
    return 0.0 if scale <= ABSOLUTE_TOLERANCE else abs(left - fed) / scale


def check_conservation(context: CheckContext) -> CheckResult:
    """V7：进出的总质量和每种元素的原子流量守恒；缺了物流或读不到量，无法核算也算不通过。"""
    expected = (
        f"总质量相对误差 ≤ {MASS_BALANCE_TOLERANCE:.0e}，"
        f"元素相对误差 ≤ {ELEMENT_BALANCE_TOLERANCE:.0e}"
    )
    snapshot, plan = context.snapshot, context.plan
    feeds = snapshot.streams_named(system_feed_names(plan))
    outlets = snapshot.streams_named(system_outlet_names(plan))
    if feeds is None or outlets is None:
        return check_result(CheckId.CONSERVATION, expected, "", ["进料或出料物流不存在，无法核算"])
    problems = []
    errors = []
    for label, fed, left, tolerance in _balance_rows(context, feeds, outlets):
        error = _relative_error(fed, left)
        if error is None:
            problems.append(f"{label} 进出的量读不到，无法核算")
        elif not math.isclose(error, 0.0, abs_tol=tolerance):
            problems.append(
                f"{label} 进 {describe(fed)}，出 {describe(left)}，相对误差 {error:.2e}"
            )
        errors.append(error or 0.0)
    return check_result(CheckId.CONSERVATION, expected, f"最大相对误差 {max(errors):.2e}", problems)

"""组成的规范化：TaskSpec 里的份额（分率、百分数、配比，可以有余量组分，基准可以是质量）→ 摩尔分率。

纯函数。份额写得不对（超过总量、为负、余量算不出来）抛 CompositionError，调用方把它变成一个问题；
质量基准用组分表的分子量换算，体积分率只对气体成立，按理想气体当作摩尔分率。
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from reactor_agent.spec.components import ComponentTable, molecular_weights
from reactor_agent.spec.enums import ComponentPhase
from reactor_agent.spec.task_spec import AmountScale, CompositionBasis, CompositionTask

# 份额之和与总量（1 或 100%）相差不超过这个比例时，按比例归一化并登记一条说明；超过就是问题。
SUM_TOLERANCE_FRACTION = 0.005
EXACT_TOLERANCE = 1e-9
SCALE_TOTALS: Mapping[AmountScale, float] = {AmountScale.FRACTION: 1.0, AmountScale.PERCENT: 100.0}


class CompositionError(ValueError):
    """组成写得不对。user_fixable 为真表示问题出在用户给的数值上，要请用户更正。"""

    def __init__(self, message: str, *, user_fixable: bool) -> None:
        super().__init__(message)
        self.user_fixable = user_fixable


@dataclass(frozen=True)
class MoleComposition:
    """规范化后的组成：规范名 → 摩尔分率（之和为 1），以及需要登记成假设的说明。"""

    fractions: Mapping[str, float]
    notes: tuple[str, ...]


def _check_items(task: CompositionTask) -> None:
    """各项写得合不合格：至少一项，余量组分最多一个，余量的 amount 是空、其余的不是。"""
    if not task.items:
        raise CompositionError("组成里没有任何组分", user_fixable=True)
    if sum(item.is_remainder for item in task.items) > 1:
        raise CompositionError("余量组分最多一个", user_fixable=False)
    for item in task.items:
        if item.is_remainder == (item.amount is not None):
            message = f"组分 {item.component}：余量组分的 amount 写 null，其余组分必须写 amount"
            raise CompositionError(message, user_fixable=False)


def _amounts(task: CompositionTask) -> tuple[list[float], list[str]]:
    """每一项的数值（余量已经算出），和归一化的说明。"""
    _check_items(task)
    given = [item.amount for item in task.items if item.amount is not None]
    if any(amount < 0 for amount in given):
        raise CompositionError("份额不能为负数", user_fixable=True)
    has_remainder = any(item.is_remainder for item in task.items)
    if task.scale is AmountScale.RATIO:
        if has_remainder:
            raise CompositionError("配比写法里不能有余量组分", user_fixable=False)
        return given, []
    total = SCALE_TOTALS[task.scale]
    if has_remainder:
        left = total - math.fsum(given)
        if left <= SUM_TOLERANCE_FRACTION * total:
            message = (
                f"给出的份额之和是 {math.fsum(given):g}，余量组分没有剩下份额（总量 {total:g}）"
            )
            raise CompositionError(message, user_fixable=True)
        return [left if item.amount is None else item.amount for item in task.items], []
    gap = abs(math.fsum(given) - total)
    if gap > SUM_TOLERANCE_FRACTION * total:
        message = f"份额之和是 {math.fsum(given):g}，应当是 {total:g}"
        raise CompositionError(message, user_fixable=True)
    if gap < EXACT_TOLERANCE:
        return given, []
    return given, [f"份额之和是 {math.fsum(given):g} 而不是 {total:g}，按比例归一化"]


def _moles(
    task: CompositionTask, names: Sequence[str], values: Sequence[float], table: ComponentTable
) -> tuple[list[float], list[str]]:
    """按基准把数值换成物质的量；返回物质的量，和基准换算的说明。"""
    if task.basis is CompositionBasis.MASS:
        weights = molecular_weights(table)
        return [value / weights[name] for name, value in zip(names, values, strict=True)], []
    if task.basis is CompositionBasis.VOLUME:
        phases = {e.name: e.phase for e in table.components}
        if any(phases[name] is not ComponentPhase.GAS for name in names):
            raise CompositionError("体积分率只对气体成立，进料里有液体或固体", user_fixable=False)
        return list(values), ["体积分率按理想气体当作摩尔分率"]
    return list(values), []


def mole_fractions(
    task: CompositionTask, names: Sequence[str], table: ComponentTable
) -> MoleComposition:
    """组成换成摩尔分率。names 是各项解析后的规范名，与 task.items 一一对应，都在组分表里。"""
    if len(set(names)) != len(names):
        raise CompositionError("组成里有重复的组分", user_fixable=False)
    values, notes = _amounts(task)
    moles, basis_notes = _moles(task, names, values, table)
    total = math.fsum(moles)
    if total <= 0:
        raise CompositionError("份额之和为零，没法归一化", user_fixable=True)
    fractions = {name: mole / total for name, mole in zip(names, moles, strict=True)}
    return MoleComposition(fractions=fractions, notes=tuple(notes + basis_notes))

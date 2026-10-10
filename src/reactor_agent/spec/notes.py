"""规范化过程中收集问题和假设的地方。

默认值只能通过 Notes.default() 取得：它返回默认值，同时登记一条假设并记下这个字段，所以从结构上
保证不存在没有登记的默认值（rules.py 再核对一遍）。一次规范化用一个 Notes，用完即弃。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import TypeVar

from reactor_agent.errors import ErrorCode
from reactor_agent.spec.components import ComponentTable
from reactor_agent.spec.model_spec import Assumption
from reactor_agent.spec.results import Issue, make_issue
from reactor_agent.spec.units import UnitTable

T = TypeVar("T")


def shown(value: object) -> str:
    """假设里取值的写法：枚举取它的值，浮点数用 %g。"""
    if isinstance(value, Enum):
        return str(value.value)
    return f"{value:g}" if isinstance(value, float) else str(value)


class Notes:
    """问题、假设、取了默认值的字段、流量按标准体积给的进料。"""

    def __init__(self) -> None:
        self.issues: list[Issue] = []
        self.defaulted: list[str] = []
        self.volume_feeds: list[int] = []
        self._assumptions: list[tuple[str, str, str]] = []

    def problem(
        self, code: ErrorCode, path: str, message: str, *, user_fixable: bool = False
    ) -> None:
        """记一个问题；同一个字段上同一个错误码只记一次，先记的说明留下。"""
        if any(item.code is code and item.field_path == path for item in self.issues):
            return
        self.issues.append(make_issue(code, path, message, user_fixable=user_fixable))

    def declare(self, path: str, value: str, reason: str) -> None:
        """登记一条假设：针对哪个字段、取了什么值、为什么。"""
        self._assumptions.append((path, value, reason))

    def default(self, path: str, value: T, reason: str) -> T:
        """用默认值：返回它，同时登记假设并记下这个字段。"""
        self.defaulted.append(path)
        self.declare(path, shown(value), reason)
        return value

    def assumptions(self) -> tuple[Assumption, ...]:
        """按登记的顺序编号 A1、A2……"""
        return tuple(
            Assumption(id=f"A{number}", field_path=path, value=value, reason=reason)
            for number, (path, value, reason) in enumerate(self._assumptions, start=1)
        )


@dataclass(frozen=True)
class Context:
    """规范化用到的组分表、单位表，和收集问题的 Notes。"""

    table: ComponentTable
    units: UnitTable
    notes: Notes = field(default_factory=Notes)

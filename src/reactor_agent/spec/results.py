"""规格问题、结果检查和归一化结果的数据模型。

Issue 是规格阶段的问题（Recipe 的规则、之后的规格校验都产出它）；CheckResult 是求解之后的检查；
NormalizedResult 是一个工况交给报告的全部内容，数字都是规范单位。
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Self

from pydantic import AwareDatetime, model_validator

from reactor_agent.errors import ErrorCode
from reactor_agent.spec.base import FrozenModel
from reactor_agent.spec.components import ComponentTable
from reactor_agent.spec.enums import CheckId, CheckSeverity, MetricUnit
from reactor_agent.spec.model_spec import Assumption, MetricRequest, ModelSpec, OperatingCase
from reactor_agent.spec.plan import BuildPlan
from reactor_agent.spec.snapshot import ModelSnapshot

CHECK_TITLES: Mapping[CheckId, str] = MappingProxyType(
    {
        CheckId.SOLVED: "求解完成",
        CheckId.STRUCTURE: "模型结构",
        CheckId.FEEDS: "进料读回",
        CheckId.SPECIFICATIONS: "规定满足",
        CheckId.OUTPUTS: "输出存在",
        CheckId.PHYSICAL: "物理有效",
        CheckId.CONSERVATION: "守恒",
        CheckId.REQUESTED: "请求满足",
        CheckId.CONVERSION_SPECIFIED: "转化率满足规定",
        CheckId.FIXED_K_SATISFIED: "平衡常数满足规定",
    }
)
# 每个工况的结果里必须有的检查：V1 至 V8（计划 §12.3）。各种反应器的专有检查不在其中。
COMMON_CHECK_IDS: tuple[CheckId, ...] = (
    CheckId.SOLVED,
    CheckId.STRUCTURE,
    CheckId.FEEDS,
    CheckId.SPECIFICATIONS,
    CheckId.OUTPUTS,
    CheckId.PHYSICAL,
    CheckId.CONSERVATION,
    CheckId.REQUESTED,
)
# 说明里最多列出的问题条数，其余只报个数。
MAX_PROBLEMS_SHOWN = 5


class Issue(FrozenModel):
    """规格里的一个问题。user_fixable 为真表示问题出在用户给的信息上，要请用户补充或更正。"""

    code: ErrorCode
    field_path: str
    message: str
    user_fixable: bool


def make_issue(
    code: ErrorCode, field_path: str, message: str, *, user_fixable: bool = False
) -> Issue:
    """构造规格问题。多数问题不是用户给的信息造成的，所以 user_fixable 默认是假。"""
    return Issue(code=code, field_path=field_path, message=message, user_fixable=user_fixable)


class CheckResult(FrozenModel):
    """一项结果检查的结论。期望值和实测值是代码格式化好的文字，不同的检查单位各不相同。"""

    check_id: CheckId
    passed: bool
    severity: CheckSeverity
    expected: str
    actual: str
    message: str


def describe(value: float | None) -> str:
    """检查结论里数值的写法：读不到写“未知”，其余保留 6 位有效数字。"""
    return "未知" if value is None else f"{value:.6g}"


def check_result(
    check_id: CheckId, expected: str, found: str, problems: Sequence[str]
) -> CheckResult:
    """致命检查的结论：没有问题就是通过，实测值写 found；否则实测值和说明里列出问题。"""
    title = CHECK_TITLES[check_id]
    if not problems:
        return CheckResult(
            check_id=check_id,
            passed=True,
            severity=CheckSeverity.FATAL,
            expected=expected,
            actual=found,
            message=f"{title}：通过",
        )
    shown = "；".join(problems[:MAX_PROBLEMS_SHOWN])
    more = (
        f"，另有 {len(problems) - MAX_PROBLEMS_SHOWN} 处"
        if len(problems) > MAX_PROBLEMS_SHOWN
        else ""
    )
    return CheckResult(
        check_id=check_id,
        passed=False,
        severity=CheckSeverity.FATAL,
        expected=expected,
        actual=shown + more,
        message=f"{title}：未通过，{len(problems)} 处不符，如 {problems[0]}",
    )


class CheckContext(FrozenModel):
    """结果检查和指标计算需要的全部输入：规格、当前工况、计划、组分表和读回的快照。"""

    spec: ModelSpec
    case: OperatingCase
    plan: BuildPlan
    components: ComponentTable
    snapshot: ModelSnapshot

    @model_validator(mode="after")
    def _case_belongs_to_the_spec(self) -> Self:
        if self.case not in self.spec.cases:
            raise ValueError(f"工况 {self.case.name!r} 不是规格里的工况")
        return self


class MetricResult(FrozenModel):
    """一项指标的值，以及它的定义。值是 None 表示算不出来（分母为零或者用到的量读不到）。"""

    request: MetricRequest
    name: str
    definition: str
    value: float | None
    unit: MetricUnit


class ResultComponent(FrozenModel):
    """出料里一个组分的量。干基摩尔分率只对气相出料给出，水本身没有干基分率。"""

    name: str
    mole_fraction: float | None
    dry_mole_fraction: float | None
    molar_flow_kmol_h: float | None
    mass_flow_kg_h: float | None


class StreamResult(FrozenModel):
    """一股出料：状态、总流量和各组分的量。"""

    name: str
    temperature_c: float | None
    pressure_bar: float | None
    molar_flow_kmol_h: float | None
    mass_flow_kg_h: float | None
    components: tuple[ResultComponent, ...]


class Provenance(FrozenModel):
    """结果的出处：仿真软件的版本、Case 文件、读取时间和规格哈希。"""

    simulator_version: str
    case_path: Path
    read_at: AwareDatetime
    spec_hash: str


class NormalizedResult(FrozenModel):
    """一个工况交给报告的结果。热负荷是全部能流之和，吸热为正，绝热是 0。"""

    case_name: str
    outlets: tuple[StreamResult, ...]
    duty_kw: float | None
    metrics: tuple[MetricResult, ...]
    checks: tuple[CheckResult, ...]
    assumptions: tuple[Assumption, ...]
    provenance: Provenance

    def failed(self, severity: CheckSeverity) -> tuple[CheckResult, ...]:
        """没有通过的某个级别的检查。"""
        return tuple(c for c in self.checks if not c.passed and c.severity is severity)


class CaseRecord(FrozenModel):
    """一个工况的执行记录：有没有拿到结果，这个工况的 .hsc 有没有保存。"""

    case_name: str
    result: NormalizedResult | None
    case_file_saved: bool

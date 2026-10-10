"""规格评测的打分：用户明确给出的量是否与期望一致，该登记的假设是否登记，病态输入是否被拦住。

不调 LLM，不读运行目录以外的文件，所以可以单独测试。口径（阶段 2B 提示词任务 6）：
  期望参数  只列两类：用户明确给出的量（进料的温度、压力、流量、组成，转化率，反应的计量系数，
            工况，待求指标），规范化之后比较，数值的相对容差 1e-3；必须被登记为假设的字段，
            只检查它们确实在假设清单里（每个期望字段要有自己独立的一条假设）。
  病态输入  两条都要满足：第一次校验的问题清单里出现了期望的问题（错误码和字段）；最终没有把
            用户给的值悄悄改掉——终态是 NEEDS_INPUT 或 FAILED，并且原因里有期望的字段。
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from reactor_agent.errors import ErrorCode
from reactor_agent.spec.enums import HeatMode, MetricKind, ReactionKind, TaskStatus
from reactor_agent.spec.model_spec import ModelSpec, covers, metric_components
from reactor_agent.spec.tool_args import ConversionReaction, ReactionDefinition

RELATIVE_TOLERANCE = 1e-3
ABSOLUTE_TOLERANCE = 1e-9
# 只要终态是这两个之一，就说明没有带着用户给的值建出模型。
STOPPED = frozenset({TaskStatus.NEEDS_INPUT, TaskStatus.FAILED})

Leaf = tuple[str, bool]  # 一项比较：说明，是否一致


class Strict(BaseModel):
    """评测里的数据模型：多余的字段是错误，创建之后不可修改。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ExpectedFeed(Strict):
    temperature_c: float | None = None
    pressure_bar: float | None = None
    molar_flow_kmol_h: float | None = None
    mass_flow_kg_h: float | None = None
    composition: Mapping[str, float] = Field(default_factory=dict)


class SumGroup(Strict):
    """几个组分的系数之和（用户没有给分配时，各自的系数是假设，只比较和）。"""

    components: tuple[str, ...]
    total: float


class ExpectedReaction(Strict):
    kind: ReactionKind
    stoichiometry: Mapping[str, float] = Field(default_factory=dict)
    sums: tuple[SumGroup, ...] = ()
    base_component: str | None = None
    conversion_percent: float | None = None


class ExpectedCase(Strict):
    outlet_temperature_c: float | None = None
    duty_kw: float | None = None


class ExpectedMetric(Strict):
    kind: MetricKind
    components: tuple[str, ...]


class ExpectedParams(Strict):
    feeds: tuple[ExpectedFeed, ...] = ()
    reactions: tuple[ExpectedReaction, ...] = ()
    heat_mode: HeatMode | None = None
    cases: tuple[ExpectedCase, ...] = ()
    metrics: tuple[ExpectedMetric, ...] = ()


class ExpectedIssue(Strict):
    """第一次校验的问题清单里要有的问题。field_path 为空表示不限字段，否则按前缀匹配。"""

    code: ErrorCode
    field_path: str = ""


class IssueKey(Strict):
    """Trace 里的一条问题：错误码和字段。"""

    code: ErrorCode
    field_path: str


class SpecRecord(Strict):
    """一次运行里规格这一步的结果。spec 是 None 表示没有冻结出规格。"""

    status: TaskStatus | None
    spec: ModelSpec | None
    rewrites: int
    first_issues: tuple[IssueKey, ...]
    final_paths: tuple[str, ...]


@dataclass(frozen=True)
class ParamScore:
    """期望参数的得分：一致的个数、总个数，和不一致的地方。"""

    matched: int
    total: int
    misses: tuple[str, ...]


def _close(actual: float | None, wanted: float) -> bool:
    if actual is None:
        return False
    return math.isclose(actual, wanted, rel_tol=RELATIVE_TOLERANCE, abs_tol=ABSOLUTE_TOLERANCE)


def _feed_leaves(index: int, wanted: ExpectedFeed, spec: ModelSpec | None) -> list[Leaf]:
    label = f"feeds[{index}]"
    actual = spec.feeds[index] if spec is not None and index < len(spec.feeds) else None
    found: dict[str, float | None] = {}
    fractions: dict[str, float] = {}
    if actual is not None:
        found = {
            "temperature_c": actual.temperature_c,
            "pressure_bar": actual.pressure_bar,
            "molar_flow_kmol_h": actual.molar_flow_kmol_h,
            "mass_flow_kg_h": actual.mass_flow_kg_h,
        }
        fractions = {item.component: item.mole_fraction for item in actual.composition}
    given = {
        "temperature_c": wanted.temperature_c,
        "pressure_bar": wanted.pressure_bar,
        "molar_flow_kmol_h": wanted.molar_flow_kmol_h,
        "mass_flow_kg_h": wanted.mass_flow_kg_h,
    }
    leaves = [
        (f"{label}.{name}", _close(found.get(name), value))
        for name, value in given.items()
        if value is not None
    ]
    if wanted.composition:
        leaves.append((f"{label}.composition 的组分", set(fractions) == set(wanted.composition)))
    leaves += [
        (f"{label}.composition.{name}", _close(fractions.get(name), value))
        for name, value in wanted.composition.items()
    ]
    return leaves


def _coefficients(reaction: ReactionDefinition) -> dict[str, float]:
    return {term.component: term.coefficient for term in reaction.stoichiometry}


def _reaction_components(wanted: ExpectedReaction) -> set[str]:
    grouped = {name for group in wanted.sums for name in group.components}
    return set(wanted.stoichiometry) | grouped


def _find_reaction(wanted: ExpectedReaction, spec: ModelSpec | None) -> ReactionDefinition | None:
    """同一种反应、组分集合相同的实际反应；反应的先后顺序不重要。"""
    if spec is None:
        return None
    names = _reaction_components(wanted)
    for reaction in spec.reactions:
        if reaction.kind is wanted.kind and set(_coefficients(reaction)) == names:
            return reaction
    return None


def _conversion_leaves(
    label: str, wanted: ExpectedReaction, actual: ReactionDefinition | None
) -> list[Leaf]:
    """转化反应的转化率和基准组分；实际不是转化反应时，期望里有的项都不一致。"""
    converted = actual if isinstance(actual, ConversionReaction) else None
    leaves: list[Leaf] = []
    if wanted.conversion_percent is not None:
        found = converted.conversion_percent if converted is not None else None
        leaves.append((f"{label}.conversion_percent", _close(found, wanted.conversion_percent)))
    if wanted.base_component is not None:
        same = converted is not None and converted.base_component == wanted.base_component
        leaves.append((f"{label}.base_component", same))
    return leaves


def _reaction_leaves(index: int, wanted: ExpectedReaction, spec: ModelSpec | None) -> list[Leaf]:
    label = f"reactions[{index}]"
    actual = _find_reaction(wanted, spec)
    coefficients = _coefficients(actual) if actual is not None else {}
    leaves: list[Leaf] = [(f"{label} 的组分和类型", actual is not None)]
    leaves += [
        (f"{label}.stoichiometry.{name}", _close(coefficients.get(name), value))
        for name, value in wanted.stoichiometry.items()
    ]
    leaves += [
        (
            f"{label}.sum({'+'.join(group.components)})",
            _close(sum(coefficients.get(n, 0.0) for n in group.components), group.total),
        )
        for group in wanted.sums
    ]
    return leaves + _conversion_leaves(label, wanted, actual)


def _case_and_metric_leaves(wanted: ExpectedParams, spec: ModelSpec | None) -> list[Leaf]:
    cases = spec.cases if spec is not None else ()
    leaves: list[Leaf] = []
    if wanted.cases:
        leaves.append(("cases 的个数", len(cases) == len(wanted.cases)))
    for key in ("outlet_temperature_c", "duty_kw"):
        wanted_values = sorted(v for c in wanted.cases if (v := getattr(c, key)) is not None)
        found_values = sorted(v for c in cases if (v := getattr(c, key)) is not None)
        leaves += [
            (f"cases.{key}[{k}]", k < len(found_values) and _close(found_values[k], value))
            for k, value in enumerate(wanted_values)
        ]
    actual = {(m.kind, metric_components(m)) for m in spec.metrics} if spec is not None else set()
    leaves += [
        (f"metrics {m.kind.value} {'/'.join(m.components)}", (m.kind, m.components) in actual)
        for m in wanted.metrics
    ]
    return leaves


def score_params(wanted: ExpectedParams, spec: ModelSpec | None) -> ParamScore:
    """规格与期望参数逐项比较。没有规格时每一项都不一致。"""
    leaves: list[Leaf] = []
    for index, feed in enumerate(wanted.feeds):
        leaves += _feed_leaves(index, feed, spec)
    for index, reaction in enumerate(wanted.reactions):
        leaves += _reaction_leaves(index, reaction, spec)
    if wanted.heat_mode is not None:
        leaves.append(("heat_mode", spec is not None and spec.heat_mode is wanted.heat_mode))
    leaves += _case_and_metric_leaves(wanted, spec)
    misses = tuple(label for label, ok in leaves if not ok)
    return ParamScore(len(leaves) - len(misses), len(leaves), misses)


def missing_assumptions(wanted: Sequence[str], spec: ModelSpec | None) -> tuple[str, ...]:
    """期望登记成假设、但没有被登记的字段。

    每个期望的字段要有自己的一条假设，同一条假设不能同时撑起两个字段；能覆盖时优先用字段路径
    最长（最具体）的那一条。
    """
    available = [item.field_path for item in spec.assumptions] if spec is not None else []
    missing = []
    for path in wanted:
        candidates = [a for a in available if covers(a, path)]
        if not candidates:
            missing.append(path)
            continue
        available.remove(max(candidates, key=len))
    return tuple(missing)


@dataclass(frozen=True)
class IssueVerdict:
    """病态输入的判定：第一次的问题清单对不对，终态和原因对不对。"""

    first_ok: bool
    final_ok: bool

    @property
    def passed(self) -> bool:
        return self.first_ok and self.final_ok


def judge_issues(
    wanted: Sequence[ExpectedIssue], final: Sequence[TaskStatus], record: SpecRecord
) -> IssueVerdict:
    """问题清单里要有期望的问题；终态在期望的终态里、原因里有期望的字段、没有冻结出规格。"""
    first_ok = all(
        any(k.code is w.code and k.field_path.startswith(w.field_path) for k in record.first_issues)
        for w in wanted
    )
    reasons = all(any(p.startswith(w.field_path) for p in record.final_paths) for w in wanted)
    stopped = record.status in final and record.status in STOPPED
    return IssueVerdict(first_ok, record.spec is None and stopped and reasons)

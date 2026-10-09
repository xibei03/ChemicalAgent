"""选型评测的用例模型、打分和报告渲染。不调 LLM，不读运行目录之外的文件，所以可以单独测试。

打分的口径（阶段 2A 提示词）：
  类型准确率    最终结论（规则与 LLM 对照之后）是否等于期望的类型；不是反应过程的期望是“无”。
  LLM 原始推荐  第一次回答里的推荐，不经规则校正、不经重问。
  规则从第一次特征推出的类型  只用 LLM 第一次抽取的特征，由规则推出。
  重复一致性    同一个用例重复运行，最终结论是否全部相同。
  关键特征准确率  用例里 expected.features 列出的特征，与最终结果里的取值是否一致。
  输出合法率    选型这一步拿到了通过校验的输出（含客户端的一次校验重问）。
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, field_validator

from reactor_agent.spec.enums import ReactorType
from reactor_agent.spec.selection import (
    REACTOR_NAMES,
    Decision,
    EquipmentForm,
    FeedPhase,
    SelectionFeatures,
    SelectionResult,
)

NONE_TYPE = "none"
# 门槛（阶段 2A 完成标准第 3 条）：三个原文场景全部正确，其余用例至多错这么多个。
MAX_WRONG = 1
FLAG_FEATURES = frozenset(
    {
        "is_reaction_process",
        "kinetics_given",
        "dimensions_given",
        "conversion_data_given",
        "reaction_defined",
        "black_box_system",
        "equilibrium_constant_given",
        "polymerization",
    }
)


class ExpectedFeatures(BaseModel):
    """用例里期望的关键特征，只有写出来的才参与打分。"""

    model_config = ConfigDict(extra="forbid")

    is_reaction_process: bool | None = None
    named_reactor: ReactorType | None = None
    kinetics_given: bool | None = None
    dimensions_given: bool | None = None
    equipment_form: EquipmentForm | None = None
    conversion_data_given: bool | None = None
    reaction_defined: bool | None = None
    black_box_system: bool | None = None
    equilibrium_constant_given: bool | None = None
    phase: FeedPhase | None = None
    polymerization: bool | None = None


class Expected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reactor: ReactorType | None
    features: ExpectedFeatures

    @field_validator("reactor", mode="before")
    @classmethod
    def _none_means_no_reactor(cls, value: object) -> object:
        return None if value == NONE_TYPE else value


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    purpose: str
    input: str
    source: str | None = None
    scenario: bool = False  # 是不是三个考核场景的原文：门槛要求它们全部正确
    repeats: int = 1
    expected: Expected


def load_cases(directory: Path) -> list[EvalCase]:
    """读 directory 下全部用例，按编号排序。"""
    cases = [
        EvalCase.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        for path in sorted(directory.glob("*.yaml"))
    ]
    return sorted(cases, key=lambda case: (not case.scenario, case.id))


class RunRecord(BaseModel):
    """一次运行的结果。selection 是 None 表示没有走到选型结论（LLM 出错之类）。"""

    case_id: str
    repeat: int
    selection: SelectionResult | None
    first_recommendation: ReactorType | None
    first_rule_type: ReactorType | None
    has_first_answer: bool
    error: str | None
    tokens: int
    seconds: float
    reasked: bool

    @property
    def final_type(self) -> ReactorType | None:
        return None if self.selection is None else self.selection.reactor_type


def actual_value(features: SelectionFeatures, name: str) -> object:
    """最终特征里这个名字的取值，和 ExpectedFeatures 里的写法一致。"""
    if name == "named_reactor":
        return features.named_reactor.reactor_type
    if name in FLAG_FEATURES:
        return getattr(features, name).value
    return getattr(features, name)


def feature_matches(case: EvalCase, record: RunRecord) -> tuple[int, int]:
    """关键特征：(一致的个数, 总个数)。没有最终结果时一个都不算一致。"""
    wanted = case.expected.features
    names = sorted(wanted.model_fields_set)
    if record.selection is None:
        return 0, len(names)
    features = record.selection.features
    matched = sum(1 for name in names if actual_value(features, name) == getattr(wanted, name))
    return matched, len(names)


def type_correct(case: EvalCase, record: RunRecord) -> bool:
    return record.selection is not None and record.final_type == case.expected.reactor


def case_passes(case: EvalCase, records: Sequence[RunRecord]) -> bool:
    return bool(records) and all(type_correct(case, record) for record in records)


class Summary(BaseModel):
    """全部用例的汇总。"""

    runs: int
    final_accuracy: float
    llm_first_accuracy: float
    rules_first_accuracy: float
    scenario_correct: int
    scenario_runs: int
    other_wrong_cases: int
    other_cases: int
    legal_rate: float
    reask_rate: float
    feature_accuracy: float
    decisions: Mapping[str, int]
    consistent_cases: int
    repeated_cases: int
    tokens: int
    seconds: float
    gate_passed: bool


def _rate(part: int, whole: int) -> float:
    return part / whole if whole else 0.0


def _decision_counts(records: Sequence[RunRecord]) -> dict[str, int]:
    return dict(Counter(r.selection.decision.value for r in records if r.selection is not None))


def _consistent_cases(cases: Sequence[EvalCase], by_case: Mapping[str, list[RunRecord]]) -> int:
    """重复运行的用例里，每次的最终结论都相同的个数。"""
    repeated = [by_case[case.id] for case in cases if len(by_case[case.id]) > 1]
    return sum(1 for runs in repeated if len({r.final_type for r in runs}) == 1)


def summarize(cases: Sequence[EvalCase], records: Sequence[RunRecord]) -> Summary:
    by_case = {case.id: [r for r in records if r.case_id == case.id] for case in cases}
    pairs = [(case, record) for case in cases for record in by_case[case.id]]
    scenario_pairs = [(c, r) for c, r in pairs if c.scenario]
    others = [case for case in cases if not case.scenario]
    matched = [feature_matches(case, record) for case, record in pairs]
    wrong_others = sum(1 for case in others if not case_passes(case, by_case[case.id]))
    scenario_correct = sum(1 for case, record in scenario_pairs if type_correct(case, record))
    first_llm = sum(
        r.has_first_answer and r.first_recommendation == c.expected.reactor for c, r in pairs
    )
    first_rules = sum(
        r.has_first_answer and r.first_rule_type == c.expected.reactor for c, r in pairs
    )
    return Summary(
        runs=len(records),
        final_accuracy=_rate(sum(type_correct(c, r) for c, r in pairs), len(pairs)),
        llm_first_accuracy=_rate(first_llm, len(pairs)),
        rules_first_accuracy=_rate(first_rules, len(pairs)),
        scenario_correct=scenario_correct,
        scenario_runs=len(scenario_pairs),
        other_wrong_cases=wrong_others,
        other_cases=len(others),
        legal_rate=_rate(sum(r.selection is not None for r in records), len(records)),
        reask_rate=_rate(sum(r.reasked for r in records), len(records)),
        feature_accuracy=_rate(sum(m for m, _ in matched), sum(t for _, t in matched)),
        decisions=_decision_counts(records),
        consistent_cases=_consistent_cases(cases, by_case),
        repeated_cases=sum(1 for case in cases if len(by_case[case.id]) > 1),
        tokens=sum(r.tokens for r in records),
        seconds=sum(r.seconds for r in records),
        gate_passed=bool(scenario_pairs)
        and scenario_correct == len(scenario_pairs)
        and wrong_others <= MAX_WRONG,
    )


def _name(reactor: ReactorType | None) -> str:
    return "无" if reactor is None else REACTOR_NAMES[reactor]


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _case_row(case: EvalCase, records: Sequence[RunRecord]) -> str:
    got = " ".join(
        ("✓" if type_correct(case, r) else "✗") + _name(r.final_type) if r.selection else "✗出错"
        for r in records
    )
    decisions = Counter(r.selection.decision for r in records if r.selection)
    shown = "、".join(f"{DECISION_SHORT[d]}×{n}" for d, n in decisions.items())
    matched = [feature_matches(case, r) for r in records]
    features = f"{sum(m for m, _ in matched)}/{sum(t for _, t in matched)}"
    status = "通过" if case_passes(case, records) else "**未通过**"
    return (
        f"| {case.id} | {_name(case.expected.reactor)} | {got} | {shown} | {features} | {status} |"
    )


DECISION_SHORT: Mapping[Decision, str] = {
    Decision.AGREED: "一致",
    Decision.AGREED_AFTER_REASK: "重问后一致",
    Decision.RULES_PREVAILED: "规则推翻",
}


def _failure_details(case: EvalCase, records: Sequence[RunRecord]) -> list[str]:
    lines = []
    for record in records:
        if type_correct(case, record):
            continue
        lines.append(f"### {case.id}（第 {record.repeat} 次）")
        if record.selection is None:
            lines.append(f"- 没有得到选型结论：{record.error}")
            continue
        result = record.selection
        lines.append(f"- 期望 {_name(case.expected.reactor)}，得到 {_name(result.reactor_type)}")
        first, last = _name(record.first_recommendation), _name(result.llm_recommendation)
        lines.append(f"- LLM 第一次推荐 {first}，最终推荐 {last}")
        lines.append(f"- 决定方式：{DECISION_SHORT[result.decision]}")
        lines.extend(f"- 规则：{note}" for note in result.rule_notes)
        wanted = case.expected.features
        for name in sorted(wanted.model_fields_set):
            actual = actual_value(result.features, name)
            if actual != getattr(wanted, name):
                lines.append(f"- 特征 {name}：期望 {getattr(wanted, name)}，得到 {actual}")
    return lines


def render_report(
    cases: Sequence[EvalCase], records: Sequence[RunRecord], meta: Mapping[str, str]
) -> str:
    """docs/EVAL_RESULTS.md 的全文。meta 是模型名、Skill 版本、提交哈希、时间等。"""
    s = summarize(cases, records)
    lines = ["# 选型评测结果", "", "由 `evals/run_evals.py` 生成，不要手工修改。", ""]
    lines += [f"- {key}：{value}" for key, value in meta.items()]
    verdict = "**通过**" if s.gate_passed else "**未通过**"
    lines += ["", f"## 汇总：{verdict}", "", "| 指标 | 结果 | 门槛 |", "|---|---|---|"]
    lines += [
        f"| 三个原文场景的类型（各 5 次） | {s.scenario_correct} / {s.scenario_runs} | 全部正确 |",
        f"| 其余用例 | 错 {s.other_wrong_cases} / {s.other_cases} 个 | 至多错 {MAX_WRONG} 个 |",
        f"| 输出经校验合法的比例（含一次重问） | {_percent(s.legal_rate)} | 100% |",
        f"| 最终结论的类型准确率（全部运行） | {_percent(s.final_accuracy)} | 记录 |",
        f"| LLM 第一次推荐的类型准确率 | {_percent(s.llm_first_accuracy)} | 记录 |",
        f"| 规则用第一次抽的特征推出的类型准确率 | {_percent(s.rules_first_accuracy)} | 记录 |",
        f"| 需要重问的运行占比 | {_percent(s.reask_rate)} | 记录 |",
        f"| 重复运行的一致性 | {s.consistent_cases} / {s.repeated_cases} 个用例结论相同 | 记录 |",
        f"| 关键特征准确率 | {_percent(s.feature_accuracy)} | 记录，不设门槛 |",
        f"| 用量 | {s.runs} 次运行，{s.tokens} tokens，{s.seconds:.0f} 秒 | 记录 |",
    ]
    shown = "、".join(f"{DECISION_SHORT[Decision(k)]} {v}" for k, v in s.decisions.items())
    lines += ["", f"决定方式的分布：{shown}", ""]
    lines += [
        "## 逐个用例",
        "",
        "| 用例 | 期望 | 每次运行的结论 | 决定方式 | 关键特征 | 结果 |",
        "|---|---|---|---|---|---|",
    ]
    by_case = {case.id: [r for r in records if r.case_id == case.id] for case in cases}
    lines += [_case_row(case, by_case[case.id]) for case in cases]
    details: list[str] = []
    for case in cases:
        details += _failure_details(case, by_case[case.id])
    if details:
        lines += ["", "## 错误的运行", "", *details]
    return "\n".join(lines) + "\n"

"""规格评测的汇总和报告：三个原文场景的期望参数正确率、规格合法率、假设登记、病态输入。

门槛（阶段 2B 完成标准第 3 条）：三个原文场景的期望参数正确率不低于 95%；经不超过 2 轮重写后
规格合法的比例为 100%；病态输入全部按任务 6 的条件通过。场景的改写（L1-S?b）只记录，不设门槛。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import NamedTuple

from scoring import EvalCase, RunRecord
from spec_scoring import ParamScore, SpecRecord, judge_issues, missing_assumptions, score_params

PARAM_GATE = 0.95


class SpecRun(NamedTuple):
    """一次跑到了规格这一步的运行：第几次，和规格这一步的结果。"""

    repeat: int
    record: SpecRecord


class CaseGroups(NamedTuple):
    """报告里的三类用例：原文场景、改写、病态输入。"""

    scenarios: list[EvalCase]
    rewrites: list[EvalCase]
    abnormal: list[EvalCase]

    def all(self) -> list[EvalCase]:
        return [*self.scenarios, *self.rewrites, *self.abnormal]


def _spec_runs(case: EvalCase, records: Sequence[RunRecord]) -> list[SpecRun]:
    return [
        SpecRun(r.repeat, r.spec) for r in records if r.case_id == case.id and r.spec is not None
    ]


@dataclass(frozen=True)
class CaseSpecResult:
    """一个用例在规格这一步的汇总。"""

    runs: int
    legal: int
    params: ParamScore
    assumptions_ok: int
    abnormal_ok: int
    rewrites: tuple[int, ...]


def case_spec_result(case: EvalCase, records: Sequence[RunRecord]) -> CaseSpecResult:
    """一个用例的全部运行汇总：规格合法的次数、参数得分、假设登记、病态输入的判定。"""
    runs = _spec_runs(case, records)
    total = ParamScore(0, 0, ())
    legal = assumed = abnormal = 0
    for run in runs:
        legal += run.record.spec is not None
        if case.expected.params is not None:
            score = score_params(case.expected.params, run.record.spec)
            total = ParamScore(
                total.matched + score.matched,
                total.total + score.total,
                (*total.misses, *score.misses),
            )
            missing = missing_assumptions(case.expected.assumed, run.record.spec)
            assumed += not missing
        if case.expected.issues:
            verdict = judge_issues(case.expected.issues, case.expected.final, run.record)
            abnormal += verdict.passed
    return CaseSpecResult(
        runs=len(runs),
        legal=legal,
        params=total,
        assumptions_ok=assumed,
        abnormal_ok=abnormal,
        rewrites=tuple(run.record.rewrites for run in runs),
    )


def _percent(part: int, whole: int) -> str:
    return "—" if whole == 0 else f"{part / whole * 100:.1f}%"


def _split(cases: Sequence[EvalCase]) -> CaseGroups:
    spec_cases = [c for c in cases if c.runs_spec]
    return CaseGroups(
        scenarios=[c for c in spec_cases if c.scenario],
        rewrites=[c for c in spec_cases if c.expected.params is not None and not c.scenario],
        abnormal=[c for c in spec_cases if c.expected.issues],
    )


def spec_gate(cases: Sequence[EvalCase], records: Sequence[RunRecord]) -> bool:
    """规格评测的门槛有没有通过。没有规格用例（只跑了选型）时不适用，算通过。"""
    groups = _split(cases)
    if not groups.scenarios and not groups.abnormal:
        return True
    results = [case_spec_result(c, records) for c in groups.scenarios]
    matched = sum(r.params.matched for r in results)
    total = sum(r.params.total for r in results)
    legal = all(r.legal == r.runs for r in results)
    outcomes = [case_spec_result(c, records) for c in groups.abnormal]
    abnormal_ok = all(r.abnormal_ok == r.runs for r in outcomes)
    return legal and abnormal_ok and (total == 0 or matched / total >= PARAM_GATE)


def _row(case: EvalCase, result: CaseSpecResult) -> str:
    rewrites = "/".join(str(n) for n in result.rewrites) or "—"
    params = f"{result.params.matched}/{result.params.total}" if result.params.total else "—"
    assumed = f"{result.assumptions_ok}/{result.runs}" if case.expected.params is not None else "—"
    kind = f"{result.abnormal_ok}/{result.runs}" if case.expected.issues else "—"
    return (
        f"| {case.id} | {result.runs} | {result.legal}/{result.runs} | {params} | {assumed} "
        f"| {kind} | {rewrites} |"
    )


def _run_problems(case: EvalCase, record: SpecRecord) -> list[str]:
    """一次运行里和期望不一致的地方，一条一句话。"""
    problems: list[str] = []
    if case.expected.params is not None:
        score = score_params(case.expected.params, record.spec)
        problems += [f"参数不一致：{label}" for label in score.misses]
        problems += [
            f"没有登记的假设：{path}"
            for path in missing_assumptions(case.expected.assumed, record.spec)
        ]
    if not case.expected.issues:
        return problems
    verdict = judge_issues(case.expected.issues, case.expected.final, record)
    if not verdict.first_ok:
        found = "、".join(f"{k.code.value}@{k.field_path}" for k in record.first_issues)
        problems.append(f"第一次校验的问题清单里没有期望的问题（实际：{found or '无'}）")
    if not verdict.final_ok:
        paths = "、".join(record.final_paths) or "无"
        status = record.status.value if record.status else "进入了计划"
        problems.append(f"终态不对：{status}，原因的字段：{paths}")
    return problems


def _details(case: EvalCase, records: Sequence[RunRecord]) -> list[str]:
    lines: list[str] = []
    for run in _spec_runs(case, records):
        problems = _run_problems(case, run.record)
        if problems:
            lines.append(f"### {case.id}（第 {run.repeat} 次，重写 {run.record.rewrites} 轮）")
            lines += [f"- {text}" for text in problems]
    return lines


def render_spec_report(cases: Sequence[EvalCase], records: Sequence[RunRecord]) -> str:
    """规格评测一节的全文（接在选型评测的报告后面）。没有规格用例时是空字符串。"""
    groups = _split(cases)
    shown = groups.all()
    if not shown:
        return ""
    results = {c.id: case_spec_result(c, records) for c in shown}
    scenario_results = [results[c.id] for c in groups.scenarios]
    matched = sum(r.params.matched for r in scenario_results)
    total = sum(r.params.total for r in scenario_results)
    legal = sum(r.legal for r in scenario_results)
    runs = sum(r.runs for r in scenario_results)
    abnormal = groups.abnormal
    abnormal_passed = sum(1 for c in abnormal if results[c.id].abnormal_ok == results[c.id].runs)
    verdict = "**通过**" if spec_gate(cases, records) else "**未通过**"
    lines = ["", f"## 规格评测：{verdict}", "", "| 指标 | 结果 | 门槛 |", "|---|---|---|"]
    lines += [
        f"| 三个原文场景的期望参数正确率 | {matched} / {total}（{_percent(matched, total)}）"
        " | ≥ 95% |",
        f"| 经不超过 2 轮重写后规格合法的比例（三个原文场景） | {legal} / {runs} | 100% |",
        f"| 病态输入 | 通过 {abnormal_passed} / {len(abnormal)} 个 | 全部通过 |",
    ]
    lines += ["", "| 用例 | 运行 | 规格合法 | 期望参数 | 假设登记 | 病态输入 | 重写轮数 |"]
    lines += ["|---|---|---|---|---|---|---|"]
    lines += [_row(c, results[c.id]) for c in shown]
    details = [line for case in shown for line in _details(case, records)]
    if details:
        lines += ["", "### 规格评测里不一致的运行", "", *details]
    return "\n".join(lines) + "\n"

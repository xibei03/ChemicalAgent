"""规格评测的汇总和报告：三个原文场景的期望参数正确率、规格合法率、假设登记、病态输入。

门槛（阶段 2B 完成标准第 3 条）：三个原文场景的期望参数正确率不低于 95%；经不超过 2 轮重写后
规格合法的比例为 100%；病态输入全部按任务 6 的条件通过。场景的改写（L1-S?b）只记录，不设门槛。
"""

from collections.abc import Sequence
from dataclasses import dataclass

from scoring import EvalCase, RunRecord
from spec_scoring import ParamScore, judge_issues, missing_assumptions, score_params

PARAM_GATE = 0.95


def _runs(case: EvalCase, records: Sequence[RunRecord]) -> list[RunRecord]:
    return [r for r in records if r.case_id == case.id and r.spec is not None]


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
    runs = _runs(case, records)
    total = ParamScore(0, 0, ())
    legal = assumed = abnormal = 0
    for record in runs:
        spec_record = record.spec
        assert spec_record is not None
        legal += spec_record.spec is not None
        if case.expected.params is not None:
            score = score_params(case.expected.params, spec_record.spec)
            total = ParamScore(
                total.matched + score.matched,
                total.total + score.total,
                (*total.misses, *score.misses),
            )
            missing = missing_assumptions(case.expected.assumed, spec_record.spec)
            assumed += not missing
        if case.expected.issues:
            abnormal += judge_issues(case.expected.issues, case.expected.final, spec_record).passed
    return CaseSpecResult(
        runs=len(runs),
        legal=legal,
        params=total,
        assumptions_ok=assumed,
        abnormal_ok=abnormal,
        rewrites=tuple(r.spec.rewrites for r in runs if r.spec is not None),
    )


def _percent(part: int, whole: int) -> str:
    return "—" if whole == 0 else f"{part / whole * 100:.1f}%"


def _split(cases: Sequence[EvalCase]) -> tuple[list[EvalCase], list[EvalCase], list[EvalCase]]:
    spec_cases = [c for c in cases if c.runs_spec]
    scenarios = [c for c in spec_cases if c.scenario]
    rewrites = [c for c in spec_cases if c.expected.params is not None and not c.scenario]
    abnormal = [c for c in spec_cases if c.expected.issues]
    return scenarios, rewrites, abnormal


def spec_gate(cases: Sequence[EvalCase], records: Sequence[RunRecord]) -> bool:
    """规格评测的门槛有没有通过。没有规格用例（只跑了选型）时不适用，算通过。"""
    scenarios, _, abnormal = _split(cases)
    if not scenarios and not abnormal:
        return True
    results = [case_spec_result(c, records) for c in scenarios]
    matched = sum(r.params.matched for r in results)
    total = sum(r.params.total for r in results)
    legal = all(r.legal == r.runs for r in results)
    outcomes = [case_spec_result(c, records) for c in abnormal]
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


def _details(case: EvalCase, records: Sequence[RunRecord]) -> list[str]:
    lines = []
    for record in _runs(case, records):
        spec_record = record.spec
        assert spec_record is not None
        problems = []
        if case.expected.params is not None:
            score = score_params(case.expected.params, spec_record.spec)
            problems += [f"参数不一致：{label}" for label in score.misses]
            problems += [
                f"没有登记的假设：{path}"
                for path in missing_assumptions(case.expected.assumed, spec_record.spec)
            ]
        if case.expected.issues:
            verdict = judge_issues(case.expected.issues, case.expected.final, spec_record)
            if not verdict.first_ok:
                found = "、".join(
                    f"{k.code.value}@{k.field_path}" for k in spec_record.first_issues
                )
                problems.append(f"第一次校验的问题清单里没有期望的问题（实际：{found or '无'}）")
            if not verdict.final_ok:
                paths = "、".join(spec_record.final_paths) or "无"
                status = spec_record.status.value if spec_record.status else "进入了计划"
                problems.append(f"终态不对：{status}，原因的字段：{paths}")
        if problems:
            lines.append(f"### {case.id}（第 {record.repeat} 次，重写 {spec_record.rewrites} 轮）")
            lines += [f"- {text}" for text in problems]
    return lines


def render_spec_report(cases: Sequence[EvalCase], records: Sequence[RunRecord]) -> str:
    """规格评测一节的全文（接在选型评测的报告后面）。没有规格用例时是空字符串。"""
    scenarios, rewrites, abnormal = _split(cases)
    if not (scenarios or rewrites or abnormal):
        return ""
    results = {c.id: case_spec_result(c, records) for c in [*scenarios, *rewrites, *abnormal]}
    scenario_results = [results[c.id] for c in scenarios]
    matched = sum(r.params.matched for r in scenario_results)
    total = sum(r.params.total for r in scenario_results)
    legal = sum(r.legal for r in scenario_results)
    runs = sum(r.runs for r in scenario_results)
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
    lines += [_row(c, results[c.id]) for c in [*scenarios, *rewrites, *abnormal]]
    details: list[str] = []
    for case in [*scenarios, *rewrites, *abnormal]:
        details += _details(case, records)
    if details:
        lines += ["", "### 规格评测里不一致的运行", "", *details]
    return "\n".join(lines) + "\n"

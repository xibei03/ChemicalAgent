"""组装一个工况的归一化结果，以及判定任务的结局（计划 §7.5、§12.4）。

归一化结果的数字都是规范单位。干基组成总是给出，不需要用户请求；V8（规格请求的每项指标都算出了值）
在组装时判断，作为一条检查结果放进去。任务的终态只由代码根据检查结果和文件是否保存判定，
LLM 的任何输出都不能改变它。
"""

from collections.abc import Mapping, Sequence

from reactor_agent.spec.balances import ZERO_FLOW_KMOL_H, sum_or_none
from reactor_agent.spec.components import WATER_FORMULA, names_with_formula
from reactor_agent.spec.enums import CheckId, CheckSeverity, TaskStatus
from reactor_agent.spec.plan import energy_stream_names, system_outlet_names, system_vapour_outlets
from reactor_agent.spec.results import (
    CHECK_TITLES,
    COMMON_CHECK_IDS,
    CaseRecord,
    CheckContext,
    CheckResult,
    MetricResult,
    NormalizedResult,
    Provenance,
    ResultComponent,
    StreamResult,
    check_result,
)
from reactor_agent.spec.snapshot import StreamSnapshot
from reactor_agent.validation.metrics import compute_metrics


def _dry_fractions(stream: StreamSnapshot, water: frozenset[str]) -> dict[str, float]:
    """扣除水之后各组分的摩尔分率。有量读不到、或者扣除水之后什么都不剩时是空的。"""
    dry = [
        (item.name, item.molar_flow_kmol_h) for item in stream.components if item.name not in water
    ]
    total = sum_or_none(flow for _, flow in dry)
    if total is None or total <= ZERO_FLOW_KMOL_H:
        return {}
    return {name: flow / total for name, flow in dry if flow is not None}


def _stream_result(stream: StreamSnapshot, dry: Mapping[str, float] | None) -> StreamResult:
    components = tuple(
        ResultComponent(
            name=item.name,
            mole_fraction=item.mole_fraction,
            dry_mole_fraction=None if dry is None else dry.get(item.name),
            molar_flow_kmol_h=item.molar_flow_kmol_h,
            mass_flow_kg_h=item.mass_flow_kg_h,
        )
        for item in stream.components
    )
    return StreamResult(
        name=stream.name,
        temperature_c=stream.temperature_c,
        pressure_bar=stream.pressure_bar,
        molar_flow_kmol_h=stream.molar_flow_kmol_h,
        mass_flow_kg_h=stream.mass_flow_kg_h,
        components=components,
    )


def _outlet_results(context: CheckContext) -> tuple[StreamResult, ...]:
    """系统的每股出料；气相出料带干基组成。缺失的物流不出现，那是 V2 和 V5 的事。"""
    vapour = set(system_vapour_outlets(context.plan))
    water = frozenset(names_with_formula(context.components, WATER_FORMULA))
    results = []
    for name in system_outlet_names(context.plan):
        stream = context.snapshot.stream(name)
        if stream is not None:
            dry = _dry_fractions(stream, water) if name in vapour else None
            results.append(_stream_result(stream, dry))
    return tuple(results)


def _total_duty_kw(context: CheckContext) -> float | None:
    """全部能流的热负荷之和，吸热为正；绝热没有能流，是 0。"""
    duties = {item.name: item.duty_kw for item in context.snapshot.energy_streams}
    return sum_or_none(duties.get(name) for name in energy_stream_names(context.plan))


def requested_check(metrics: Sequence[MetricResult]) -> CheckResult:
    """V8：规格请求的每项指标都算出了值。"""
    problems = [f"{metric.name} 没有算出值" for metric in metrics if metric.value is None]
    expected = f"请求的 {len(metrics)} 项指标都有值"
    return check_result(CheckId.REQUESTED, expected, f"{len(metrics)} 项都有值", problems)


def missing_checks(checks: Sequence[CheckResult]) -> tuple[CheckId, ...]:
    """V1 至 V8 里没有出现在这些检查结果里的编号。"""
    present = {check.check_id for check in checks}
    return tuple(check_id for check_id in COMMON_CHECK_IDS if check_id not in present)


def _not_run(check_id: CheckId) -> CheckResult:
    """漏跑的检查按失败记：结果不完整，不能判定为完成。"""
    title = CHECK_TITLES[check_id]
    return CheckResult(
        check_id=check_id,
        passed=False,
        severity=CheckSeverity.FATAL,
        expected=f"{title}已经运行",
        actual="没有运行",
        message=f"{title}：没有运行，结果不完整",
    )


def assemble_result(
    context: CheckContext, checks: Sequence[CheckResult], provenance: Provenance
) -> NormalizedResult:
    """一个工况的归一化结果：出料、热负荷、指标、全部检查（外加 V8）、假设和出处。

    传进来的检查应当是 V1 至 V7 和 Recipe 的专有检查；漏了的编号按失败记在结果里。
    """
    metrics = compute_metrics(context)
    provided = (*checks, requested_check(metrics))
    return NormalizedResult(
        case_name=context.case.name,
        outlets=_outlet_results(context),
        duty_kw=_total_duty_kw(context),
        metrics=metrics,
        checks=(*provided, *(_not_run(check_id) for check_id in missing_checks(provided))),
        assumptions=context.spec.assumptions,
        provenance=provenance,
    )


def _complete_result(record: CaseRecord | None, name: str) -> NormalizedResult | None:
    """这个工况可以拿来判定的结果。

    没有结果、结果属于别的工况、V1 至 V8 不齐、.hsc 没保存，都是 None。
    """
    if record is None or record.result is None or not record.case_file_saved:
        return None
    if record.result.case_name != name or missing_checks(record.result.checks):
        return None
    return record.result


def decide_outcome(case_names: Sequence[str], records: Sequence[CaseRecord]) -> TaskStatus:
    """任务的结局（计划 §7.5，不含第 4 条“报告已生成”）：完成、带警告完成或失败。

    没有工况、有工况没有可判定的结果（没有结果、检查不齐、.hsc 没保存）、有任何致命检查失败，
    是失败；只有警告级检查没通过，是带警告完成。警告级的检查要等 V9 落地（阶段 3A）才会出现。
    不支持和需要补充信息由执行器在别处给出。
    """
    by_name = {record.case_name: record for record in records}
    found = [_complete_result(by_name.get(name), name) for name in case_names]
    results = [result for result in found if result is not None]
    if not results or len(results) < len(found):
        return TaskStatus.FAILED
    if any(result.failed(CheckSeverity.FATAL) for result in results):
        return TaskStatus.FAILED
    if any(result.failed(CheckSeverity.WARNING) for result in results):
        return TaskStatus.COMPLETE_WITH_WARNINGS
    return TaskStatus.COMPLETE

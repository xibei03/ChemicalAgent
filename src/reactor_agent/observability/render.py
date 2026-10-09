"""把 Trace 和任务结果渲染成人能读的文本：时间线、失败诊断、结果摘要。

这些都是纯函数，输出文本，不打印。执行器只管流程，文本的拼接在这里。
"""

from collections.abc import Mapping, Sequence
from itertools import groupby

from reactor_agent.errors import ErrorCode
from reactor_agent.observability.trace import TraceEvent
from reactor_agent.spec.enums import EventType, MetricUnit
from reactor_agent.spec.llm import LlmCallSummary
from reactor_agent.spec.results import FailureReport, NormalizedResult, RunResult, StreamResult
from reactor_agent.spec.selection import REACTOR_NAMES, Decision, SelectionResult

LABEL_WIDTH = 18
LABEL_GAP = 2
INDENT = "  "
SESSION_CODES = frozenset({ErrorCode.COM_UNAVAILABLE, ErrorCode.COM_DISCONNECTED})
DETAIL_HEADINGS: Mapping[ErrorCode, str] = {
    ErrorCode.NOT_SOLVED: "各对象的状态（缺什么规定看这里）",
    ErrorCode.RULE: "规格不合规的地方",
    ErrorCode.VALIDATION_FATAL: "没有通过的检查",
}
DEFAULT_DETAIL_HEADING = "详情"
DECISION_TEXT: Mapping[Decision, str] = {
    Decision.AGREED: "规则的推导与 LLM 的推荐一致",
    Decision.AGREED_AFTER_REASK: "对照原文重新核对特征之后，规则的推导与 LLM 的推荐一致",
    Decision.RULES_PREVAILED: "规则的推导与 LLM 的推荐不一致，采用规则的结论",
}
# 出料里摩尔分率低于这个值的组分不在摘要里列出，避免一长串零。
SHOWN_FRACTION = 1e-4


def _group_label(event: TraceEvent) -> str:
    state = event.state.value
    return state if event.case is None else f"{state}[{event.case}]"


def _code_of(event: TraceEvent) -> str:
    """事件里 “E_X: 说明” 形式的错误的错误码部分。"""
    return (event.error or "").split(":")[0]


def _event_text(event: TraceEvent) -> str | None:
    """一个事件在时间线上的写法。状态迁移是分组的依据，错误由恢复决定那一条说明，都不单独占位。"""
    if event.type is EventType.TOOL_CALL:
        failed = f" ✗{_code_of(event)}" if event.error else ""
        again = f" (第 {event.attempt} 次)" if event.attempt and event.attempt > 1 else ""
        return f"{event.name}{again}{failed}"
    if event.type is EventType.VALIDATION:
        return _validation_text(event)
    if event.type is EventType.CHECKPOINT:
        return f"[{event.name}]"
    if event.type is EventType.RECOVERY:
        return f"→ {event.name} ({_code_of(event)})"
    if event.type is EventType.LLM_CALL and event.llm is not None:
        return _llm_text(event.name, event.llm, event.duration_ms)
    return None


def _llm_text(point: str, call: LlmCallSummary, duration_ms: int | None) -> str:
    seconds = (duration_ms or 0) / 1000
    again = f"，校验重问 {call.attempts - 1} 次" if call.attempts > 1 else ""
    tokens = call.prompt_tokens + call.completion_tokens
    return f"LLM {point}（{call.model}，{tokens} tokens，{seconds:.1f} 秒{again}）"


def _validation_text(event: TraceEvent) -> str:
    if not event.verdict:
        return "（没有检查结果）"
    failed = [check.value for check, passed in event.verdict.items() if not passed]
    if failed:
        return f"检查未通过：{', '.join(failed)}"
    return f"检查 {len(event.verdict)} 项全部通过"


def _merged(texts: Sequence[str]) -> str:
    """连续相同的写法合并成“名字 x 次数”。"""
    parts = []
    for text, repeats in groupby(texts):
        count = len(list(repeats))
        parts.append(text if count == 1 else f"{text} x{count}")
    return ", ".join(parts)


def render_timeline(events: Sequence[TraceEvent]) -> str:
    """任务的时间线：每个状态一行，同一个状态里连续调用同一个工具合并成一行。"""
    if not events:
        return "（没有事件）"
    groups = [(label, list(group)) for label, group in groupby(events, key=_group_label)]
    width = max(LABEL_WIDTH, max(len(label) for label, _ in groups) + LABEL_GAP)
    frozen = events[-1].spec_hash  # 规格冻结之前的事件没有哈希，所以看最后一条
    lines = [f"Task {events[0].task_id}" + (f"   规格哈希 {frozen[:12]}" if frozen else "")]
    for label, group in groups:
        texts = [text for text in map(_event_text, group) if text is not None]
        lines.append(f"{INDENT}{label:<{width}}{_merged(texts)}".rstrip())
    return "\n".join(lines)


def render_failure(report: FailureReport) -> str:
    """没有完成的任务的诊断：停在哪里、哪一步、什么错、试过什么、文件在哪里、下一步怎么办。"""
    lines = [
        f"任务 {report.task_id} 没有完成：{report.status.value}",
        f"停在状态：{report.state.value}",
    ]
    if report.tool is not None:
        lines.append(f"出错的步骤：{report.tool} {report.arguments or ''}".rstrip())
    lines.append(f"错误：{report.code.value}：{report.message}")
    if report.details:
        heading = DETAIL_HEADINGS.get(report.code, DEFAULT_DETAIL_HEADING)
        lines.append(f"{heading}：")
        lines.extend(f"{INDENT}{key}：{value}" for key, value in report.details.items())
    lines.append(f"已重试 {report.retries} 次，已干净重建 {report.rebuilds} 次")
    lines.append(f"Trace：{report.trace_path}")
    if report.case_path is not None:
        lines.append(f"Case 文件（供检查）：{report.case_path}")
    if report.code in SESSION_CODES:
        lines.append("HYSYS 会话已经失效。重启 HYSYS 之后，用同一份冻结的规格重跑：")
        lines.append(f'{INDENT}reactor-agent run --spec "{report.spec_path}"')
    return "\n".join(lines)


def _stream_text(stream: StreamResult) -> list[str]:
    head = (
        f"{stream.name}：{_number(stream.temperature_c)} °C，{_number(stream.pressure_bar)} bar，"
        f"{_number(stream.molar_flow_kmol_h)} kmol/h"
    )
    fractions = [
        f"{item.name} {item.mole_fraction:.4f}"
        for item in stream.components
        if item.mole_fraction is not None and item.mole_fraction >= SHOWN_FRACTION
    ]
    flowing = stream.molar_flow_kmol_h is not None and stream.molar_flow_kmol_h > 0
    return [head, f"{INDENT}摩尔分率：{'，'.join(fractions)}"] if flowing else [head]


def _number(value: float | None) -> str:
    return "未知" if value is None else f"{value:.6g}"


def _case_text(result: NormalizedResult) -> list[str]:
    lines = [f"工况 {result.case_name}（{result.provenance.case_path}）"]
    for stream in result.outlets:
        lines.extend(f"{INDENT}{line}" for line in _stream_text(stream))
    lines.append(f"{INDENT}热负荷：{_number(result.duty_kw)} kW（吸热为正）")
    for metric in result.metrics:
        unit = " %" if metric.unit is MetricUnit.PERCENT else ""
        lines.append(f"{INDENT}{metric.name}：{_number(metric.value)}{unit}")
    failed = [check for check in result.checks if not check.passed]
    lines.append(f"{INDENT}检查：{len(result.checks) - len(failed)}/{len(result.checks)} 项通过")
    lines.extend(f"{INDENT}{INDENT}✗ {check.message}" for check in failed)
    return lines


def render_summary(result: RunResult) -> str:
    """一次运行的结果摘要：终态，以及每个工况的出料、热负荷、指标和检查。"""
    status = "运行中" if result.status is None else result.status.value
    lines = [f"任务 {result.task_id}：{status}"]
    for record in result.cases:
        if record.result is not None:
            lines.extend(_case_text(record.result))
    return "\n".join(lines)


def _selection_lines(result: SelectionResult) -> list[str]:
    if result.reactor_type is None:
        head = "选型结论：无（这不是反应过程的模拟请求）"
    else:
        head = f"选型结论：{REACTOR_NAMES[result.reactor_type]}"
    lines = [f"{head}（{DECISION_TEXT[result.decision]}）", "规则的推导："]
    lines.extend(f"{INDENT}- {note}" for note in result.rule_notes)
    if result.decision is not Decision.RULES_PREVAILED:
        lines.append(f"LLM 的理由：{result.llm_rationale}")
        return lines
    if result.llm_recommendation is None:
        said = "认为这不是反应过程"
    else:
        said = f"推荐 {REACTOR_NAMES[result.llm_recommendation]}"
    lines.append(f"LLM 曾{said}（理由：{result.llm_rationale}），规则没有采纳。")
    return lines


def render_selection(result: SelectionResult) -> str:
    """选型结果：类型和怎么定的、规则的推导、LLM 的理由、原文依据、备选和不选的原因。"""
    lines = _selection_lines(result)
    quotes = result.features.quotes()
    if quotes:
        lines.append("原文依据：")
        lines.extend(f"{INDENT}[{quote.label}] “{quote.text}”" for quote in quotes)
    if result.alternatives:
        lines.append("备选类型：")
        for item in result.alternatives:
            marks = ["能建" if item.buildable else "不能建"]
            if item.recommended_by_llm:
                marks.append("LLM 曾推荐")
            name = REACTOR_NAMES[item.reactor_type]
            lines.append(f"{INDENT}{name}（{'，'.join(marks)}）：{item.reason}")
    if result.dropped_evidence:
        lines.append("已丢弃的依据（在原文里找不到原话）：")
        lines.extend(f"{INDENT}“{text}”" for text in result.dropped_evidence)
    return "\n".join(lines)

"""Trace 的写入和读回，以及时间线、失败诊断、结果摘要的渲染。"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from builders import provenance
from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.observability.render import render_failure, render_summary, render_timeline
from reactor_agent.observability.trace import (
    TRACE_FILE,
    EventBody,
    TraceEvent,
    TraceWriter,
    read_events,
)
from reactor_agent.spec.enums import EventType, TaskStatus, WorkflowState
from reactor_agent.spec.results import CaseRecord, FailureReport, RunResult
from reactor_agent.validation.checks import run_common_checks
from reactor_agent.validation.normalized import assemble_result

TASK_ID = "20261009-120000-ab"
SPEC_HASH = "a3f1c2d4e5f60718293a4b5c6d7e8f90"
STAMP = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


def event(seq: int, state: str, kind: EventType, name: str, **fields: object) -> TraceEvent:
    return TraceEvent(
        ts=STAMP,
        task_id=TASK_ID,
        seq=seq,
        state=state,
        case=fields.pop("case", None),
        spec_hash=SPEC_HASH,
        type=kind,
        name=name,
        **fields,
    )


def tool(seq: int, state: str, name: str, **fields: object) -> TraceEvent:
    return event(seq, state, EventType.TOOL_CALL, name, **fields)


def transition(seq: int, state: str, case: str | None = None) -> TraceEvent:
    return event(seq, state, EventType.STATE_TRANSITION, state, case=case)


def test_events_are_appended_in_order_as_one_json_object_per_line(tmp_path):
    (tmp_path / TASK_ID).mkdir()
    writer = TraceWriter(tmp_path)
    for name in ("spec_frozen", "plan_saved", "case_saved"):
        body = EventBody(type=EventType.CHECKPOINT, name=name)
        writer.append(TASK_ID, SPEC_HASH, WorkflowState.INIT, None, body)
    lines = (tmp_path / TASK_ID / TRACE_FILE).read_text(encoding="utf-8").splitlines()
    parsed = [json.loads(line) for line in lines]
    assert [item["seq"] for item in parsed] == [0, 1, 2]
    assert [item["name"] for item in parsed] == ["spec_frozen", "plan_saved", "case_saved"]
    assert {item["spec_hash"] for item in parsed} == {SPEC_HASH}


def test_a_new_writer_continues_the_numbering_of_an_existing_trace(tmp_path):
    (tmp_path / TASK_ID).mkdir()
    body = EventBody(type=EventType.CHECKPOINT, name="x")
    TraceWriter(tmp_path).append(TASK_ID, SPEC_HASH, WorkflowState.INIT, None, body)
    TraceWriter(tmp_path).append(TASK_ID, SPEC_HASH, WorkflowState.PLAN, None, body)
    events = read_events(tmp_path / TASK_ID / TRACE_FILE)
    assert [(e.seq, e.state) for e in events] == [(0, WorkflowState.INIT), (1, WorkflowState.PLAN)]


def written_events(path: Path, count: int) -> None:
    """用 TraceWriter 写 count 个事件到 path 所在的任务目录。"""
    path.parent.mkdir(exist_ok=True)
    writer = TraceWriter(path.parent.parent)
    for number in range(count):
        body = EventBody(type=EventType.CHECKPOINT, name=f"e{number}")
        writer.append(path.parent.name, SPEC_HASH, WorkflowState.INIT, None, body)


def test_reading_a_missing_trace_gives_no_events(tmp_path):
    assert read_events(tmp_path / TRACE_FILE) == []


def test_a_last_line_cut_short_by_an_interrupted_process_is_ignored(tmp_path):
    path = tmp_path / TASK_ID / TRACE_FILE
    written_events(path, 3)
    with path.open("a", encoding="utf-8") as stream:
        stream.write('{"ts": "2026-10-09T12:00:00+08:00", "task_id": "20261009')
    assert [e.name for e in read_events(path)] == ["e0", "e1", "e2"]


def test_a_broken_line_in_the_middle_is_a_domain_error_that_names_the_line(tmp_path):
    path = tmp_path / TASK_ID / TRACE_FILE
    written_events(path, 3)
    lines = path.read_text(encoding="utf-8").splitlines()
    damaged = [lines[0], "not json", lines[2]]
    path.write_text("\n".join(damaged) + "\n", encoding="utf-8")
    with pytest.raises(ReactorAgentError) as caught:
        read_events(path)
    assert caught.value.code is ErrorCode.SCHEMA
    assert "第 2 行" in caught.value.message


def test_the_timeline_has_one_line_per_state_and_merges_repeated_calls():
    events = [
        event(0, "INIT", EventType.CHECKPOINT, "spec_frozen"),
        transition(1, "PLAN"),
        event(2, "PLAN", EventType.CHECKPOINT, "plan_saved"),
        transition(3, "PREFLIGHT"),
        tool(4, "PREFLIGHT", "session.connect"),
        tool(5, "PREFLIGHT", "case.ensure"),
        transition(6, "BUILD_BASIS"),
        tool(7, "BUILD_BASIS", "basis.ensure_thermo"),
        tool(8, "BUILD_BASIS", "basis.ensure_reaction"),
        tool(9, "BUILD_BASIS", "basis.ensure_reaction"),
        transition(10, "SOLVE", "T710"),
        tool(11, "SOLVE", "solver.solve", case="T710"),
        transition(12, "VERIFY", "T710"),
        event(
            13,
            "VERIFY",
            EventType.VALIDATION,
            "T710",
            case="T710",
            verdict={"V1": True, "V2": True},
        ),
        transition(14, "complete"),
    ]
    text = render_timeline(events)
    assert text.splitlines() == [
        f"Task {TASK_ID}   规格哈希 {SPEC_HASH[:12]}",
        "  INIT              [spec_frozen]",
        "  PLAN              [plan_saved]",
        "  PREFLIGHT         session.connect, case.ensure",
        "  BUILD_BASIS       basis.ensure_thermo, basis.ensure_reaction x2",
        "  SOLVE[T710]       solver.solve",
        "  VERIFY[T710]      检查 2 项全部通过",
        "  complete",
    ]


def test_the_timeline_shows_retries_failures_and_the_rebuild():
    events = [
        transition(0, "BUILD_FLOWSHEET"),
        tool(1, "BUILD_FLOWSHEET", "flowsheet.ensure_stream", attempt=1, error="E_CONFLICT: 重名"),
        event(2, "BUILD_FLOWSHEET", EventType.ERROR, "E_CONFLICT", error="E_CONFLICT: 重名"),
        event(3, "BUILD_FLOWSHEET", EventType.RECOVERY, "rebuild", error="E_CONFLICT: 重名"),
        transition(4, "PREFLIGHT"),
        tool(5, "PREFLIGHT", "case.ensure", attempt=2),
        transition(6, "VERIFY"),
        event(7, "VERIFY", EventType.VALIDATION, "T710", verdict={"V1": True, "V5": False}),
    ]
    lines = render_timeline(events).splitlines()
    assert (
        lines[1]
        == "  BUILD_FLOWSHEET   flowsheet.ensure_stream ✗E_CONFLICT, → rebuild (E_CONFLICT)"
    )
    assert lines[2] == "  PREFLIGHT         case.ensure (第 2 次)"
    assert lines[3] == "  VERIFY            检查未通过：V5"


def test_an_empty_trace_renders_without_failing():
    assert render_timeline([]) == "（没有事件）"


def test_a_validation_event_without_a_verdict_does_not_claim_the_checks_passed():
    events = [
        transition(0, "VERIFY", "T710"),
        event(1, "VERIFY", EventType.VALIDATION, "T710", case="T710"),
    ]
    assert render_timeline(events).splitlines()[1] == "  VERIFY[T710]      （没有检查结果）"


def test_a_long_label_still_leaves_a_gap_before_the_text():
    events = [
        transition(0, "VERIFY", "high_temperature_case"),
        event(
            1,
            "VERIFY",
            EventType.VALIDATION,
            "x",
            case="high_temperature_case",
            verdict={"V1": True},
        ),
    ]
    line = render_timeline(events).splitlines()[1]
    assert line.startswith("  VERIFY[high_temperature_case]  检查")


def failure(**changes: object) -> FailureReport:
    fields = {
        "task_id": TASK_ID,
        "status": TaskStatus.FAILED,
        "state": WorkflowState.SOLVE,
        "tool": "solver.solve",
        "arguments": '{"timeout_s":120.0}',
        "code": ErrorCode.NOT_SOLVED,
        "message": "模型没有求解",
        "details": {"CRV-100": "under_specified"},
        "retries": 1,
        "rebuilds": 1,
        "trace_path": Path("runs/t/trace.jsonl"),
        "case_path": Path("runs/t/working-2.hsc"),
        "spec_path": Path("runs/t/artifacts/model_spec.json"),
    }
    return FailureReport(**{**fields, **changes})


def test_the_diagnosis_names_the_state_step_error_attempts_and_files():
    text = render_failure(failure())
    for expected in (
        TASK_ID,
        "SOLVE",
        "solver.solve",
        '{"timeout_s":120.0}',
        "E_NOT_SOLVED",
        "模型没有求解",
        "CRV-100：under_specified",
        "各对象的状态",
        "重试 1 次",
        "重建 1 次",
        "trace.jsonl",
        "working-2.hsc",
    ):
        assert expected in text
    assert "reactor-agent run" not in text


@pytest.mark.parametrize("code", [ErrorCode.COM_DISCONNECTED, ErrorCode.COM_UNAVAILABLE])
def test_a_lost_session_diagnosis_gives_the_command_to_rerun_with_the_same_spec(code):
    text = render_failure(failure(code=code, details={}))
    assert 'reactor-agent run --spec "runs' in text
    assert "model_spec.json" in text


def test_a_failure_without_a_tool_or_case_file_leaves_those_lines_out():
    text = render_failure(failure(tool=None, arguments=None, case_path=None, details={}))
    assert "出错的步骤" not in text
    assert "Case 文件" not in text


def test_the_summary_lists_outlets_metrics_duty_and_checks(equilibrium):
    context = equilibrium.context
    result = assemble_result(context, run_common_checks(context), provenance())
    record = CaseRecord(case_name=result.case_name, result=result, case_file_saved=True)
    text = render_summary(RunResult(task_id=TASK_ID, status=TaskStatus.COMPLETE, cases=(record,)))
    assert f"任务 {TASK_ID}：complete" in text
    assert "Vap：710 °C" in text
    assert "Hydrogen" in text
    assert "热负荷：39989 kW" in text
    assert "转化率" in text and "%" in text
    assert "项通过" in text
    assert "✗" not in text


def test_the_summary_of_a_task_that_is_still_running_has_no_cases():
    text = render_summary(RunResult(task_id=TASK_ID, status=None, cases=()))
    assert text == f"任务 {TASK_ID}：运行中"


def test_the_summary_says_unknown_for_values_it_could_not_read_and_lists_failed_checks(equilibrium):
    broken = equilibrium.with_stream("Vap", temperature_c=None, molar_flow_kmol_h=None)
    context = broken.context
    result = assemble_result(context, run_common_checks(context), provenance())
    record = CaseRecord(case_name=result.case_name, result=result, case_file_saved=True)
    text = render_summary(RunResult(task_id=TASK_ID, status=TaskStatus.FAILED, cases=(record,)))
    assert "Vap：未知 °C" in text and "未知 kmol/h" in text
    assert "✗" in text
    assert "Hydrogen/CO" in text and "%" not in text.split("Hydrogen/CO")[1].splitlines()[0]

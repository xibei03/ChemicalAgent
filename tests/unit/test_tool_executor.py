"""ToolExecutor：未知工具、入参类型不对、Backend 抛错三种情况的信封，以及成功时的回调事件。"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.enums import (
    ObjectState,
    PropertyPackage,
    ReactionKind,
    ReactorType,
    ResultStatus,
    SpecVariable,
    StreamKind,
    ToolName,
)
from reactor_agent.spec.snapshot import ModelSnapshot, ObjectStatus, SolveStatus
from reactor_agent.spec.tool_args import (
    CloseCaseArgs,
    ConnectArgs,
    EnsureCaseArgs,
    EnsureThermoArgs,
    SolveArgs,
)
from reactor_agent.spec.tool_results import (
    CaseData,
    CloseData,
    ConnectData,
    Outcome,
    ReactionData,
    ReactionSetData,
    ReactorData,
    SaveData,
    SetSpecData,
    SolveData,
    StreamData,
    ThermoData,
    ToolError,
    ToolResult,
)
from reactor_agent.tools.definitions import register_tools
from reactor_agent.tools.registry import ToolExecutor

CASE_PATH = Path("C:/runs/demo/model.hsc")
SOLVED = SolveStatus(is_solving=False, objects=())
SNAPSHOT = ModelSnapshot(
    case_path=CASE_PATH,
    thermo=None,
    reactions=(),
    reaction_sets=(),
    streams=(),
    energy_streams=(),
    reactors=(),
    solve=SOLVED,
)
ANSWERS = {
    "connect": ConnectData(version="V15", process_id=4242, reused_instance=False),
    "ensure_case": CaseData(path=CASE_PATH),
    "save_case": SaveData(path=CASE_PATH, size_bytes=1024),
    "close_case": CloseData(path=CASE_PATH),
    "ensure_thermo": ThermoData(
        fluid_package="Basis-1",
        components=("Methane",),
        property_package=PropertyPackage.PENG_ROBINSON,
    ),
    "ensure_reaction": ReactionData(
        name="Rxn-1", kind=ReactionKind.CONVERSION, balance_error_kg_per_kmol=0.0
    ),
    "ensure_reaction_set": ReactionSetData(name="RxnSet-1", reactions=("Rxn-1",)),
    "ensure_stream": StreamData(name="Feed", kind=StreamKind.MATERIAL),
    "ensure_reactor": ReactorData(name="CRV-100", reactor_type=ReactorType.CONVERSION),
    "set_spec": SetSpecData(
        object_name="CRV-100", variable=SpecVariable.OUTLET_TEMPERATURE_C, value=710.0
    ),
    "solve": SolveData(duration_s=0.1, status=SOLVED),
    "read_snapshot": SNAPSHOT,
}


class StubBackend:
    """测试用的桩：每个方法记下自己被调用，然后返回固定的结果，或者抛出预先设好的错误。"""

    def __init__(self, failure=None):
        self.failure = failure
        self.calls = []

    def __getattr__(self, name):
        if name not in ANSWERS:
            raise AttributeError(name)

        def answer(_args):
            self.calls.append(name)
            if self.failure is not None:
                raise self.failure
            return Outcome(ResultStatus.CREATED, ANSWERS[name])

        return answer


def executor(backend, events=None):
    handler = None if events is None else events.append
    return ToolExecutor(register_tools(backend), on_event=handler)


def test_every_tool_name_is_registered():
    assert set(register_tools(StubBackend())) == set(ToolName)


def test_success_returns_status_and_typed_data():
    result = executor(StubBackend()).call(ToolName.SESSION_CONNECT, ConnectArgs())
    assert result.ok
    assert result.status is ResultStatus.CREATED
    assert result.data == ANSWERS["connect"]
    assert result.error is None


def test_success_hands_one_event_to_the_callback():
    events = []
    args = ConnectArgs(visible=False)
    result = executor(StubBackend(), events).call("session.connect", args)
    assert len(events) == 1
    event = events[0]
    assert event.tool == "session.connect"
    assert event.args is args
    assert event.result == result
    assert event.duration_s >= 0.0


def test_event_serializes_the_arguments_of_the_concrete_tool():
    events = []
    executor(StubBackend(), events).call("case.close", CloseCaseArgs(save=True))
    dumped = events[0].model_dump(mode="json")
    assert dumped["args"] == {"save": True}
    assert dumped["result"]["ok"] is True


def test_unknown_tool_is_rejected_without_calling_the_backend():
    backend, events = StubBackend(), []
    result = executor(backend, events).call("case.explode", ConnectArgs())
    assert not result.ok
    assert result.error.code is ErrorCode.TOOL_NOT_ALLOWED
    assert not result.error.retryable
    assert backend.calls == []
    assert len(events) == 1
    assert events[0].result == result


def test_args_of_the_wrong_type_are_rejected_without_calling_the_backend():
    backend = StubBackend()
    result = executor(backend).call(ToolName.CASE_ENSURE, ConnectArgs())
    assert not result.ok
    assert result.error.code is ErrorCode.SCHEMA
    assert not result.error.retryable
    assert "EnsureCaseArgs" in result.error.message
    assert backend.calls == []


def test_backend_error_becomes_a_failure_envelope_with_code_and_details():
    failure = ReactorAgentError(ErrorCode.TIMEOUT, "等待超时", {"CRV-100": "not_solved"})
    result = executor(StubBackend(failure)).call(
        ToolName.CASE_ENSURE, EnsureCaseArgs(path=CASE_PATH)
    )
    assert not result.ok
    assert result.error.code is ErrorCode.TIMEOUT
    assert result.error.message == "等待超时"
    assert result.error.details == {"CRV-100": "not_solved"}
    assert result.error.retryable
    assert result.status is None
    assert result.data is None


def test_failure_also_hands_an_event_to_the_callback():
    events = []
    failure = ReactorAgentError(ErrorCode.CONFLICT, "物流已存在")
    executor(StubBackend(failure), events).call("session.connect", ConnectArgs())
    assert len(events) == 1
    assert events[0].result.error.code is ErrorCode.CONFLICT


def test_errors_that_are_not_domain_errors_are_program_bugs_and_propagate():
    with pytest.raises(RuntimeError):
        executor(StubBackend(RuntimeError("bug"))).call("session.connect", ConnectArgs())


def test_executor_works_without_a_callback():
    assert executor(StubBackend()).call("solver.solve", SolveArgs()).ok


def test_each_tool_accepts_only_its_own_argument_model():
    thermo = EnsureThermoArgs(components=("CO",), property_package="peng_robinson")
    result = executor(StubBackend()).call(ToolName.BASIS_ENSURE_THERMO, thermo)
    assert result.ok
    assert result.data == ANSWERS["ensure_thermo"]


class TestEnvelopeInvariants:
    def test_success_envelope_needs_status_and_data(self):
        with pytest.raises(ValidationError):
            ToolResult(ok=True)

    def test_failure_envelope_has_only_an_error(self):
        error = ToolError.of(ErrorCode.IO, "文件不存在")
        with pytest.raises(ValidationError):
            ToolResult(ok=False, error=error, status=ResultStatus.CREATED)

    def test_envelope_cannot_be_both_ok_and_failed(self):
        error = ToolError.of(ErrorCode.IO, "文件不存在")
        with pytest.raises(ValidationError):
            ToolResult(ok=True, status=ResultStatus.CREATED, data=ANSWERS["connect"], error=error)

    def test_retryable_flag_cannot_disagree_with_the_code(self):
        with pytest.raises(ValidationError, match="错误码"):
            ToolError(code=ErrorCode.IO, message="x", retryable=False)

    def test_failure_envelope_serializes_the_retryable_flag(self):
        result = ToolResult.failure(ErrorCode.TIMEOUT, "超时", {"a": "b"})
        error = result.model_dump(mode="json")["error"]
        assert error == {
            "code": "E_TIMEOUT",
            "message": "超时",
            "retryable": True,
            "details": {"a": "b"},
        }


class TestSolveStatus:
    def test_solved_needs_objects_that_are_all_ok_and_an_idle_solver(self):
        def status(state, is_solving=False):
            objects = (ObjectStatus(name="A", type_name="stream", state=state),)
            return SolveStatus(is_solving=is_solving, objects=objects)

        assert status(ObjectState.OK).solved
        assert status(ObjectState.WARNING).solved
        assert not status(ObjectState.UNDER_SPECIFIED).solved
        assert not status(ObjectState.NOT_SOLVED).solved
        assert not status(ObjectState.OK, is_solving=True).solved
        assert not SolveStatus(is_solving=False, objects=()).solved

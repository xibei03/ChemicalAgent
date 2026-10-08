"""求解检查：放开求解器、等待空闲、按流程图状态映射错误码。用假的 Case，不需要 HYSYS。"""

import pytest

from reactor_agent.backends.hysys_com.solving import read_solve_status, solve
from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.enums import ObjectState
from reactor_agent.spec.tool_args import SolveArgs

OK, NOT_SOLVED, WARNING, UNDER_SPECIFIED, ERROR = 1, 2, 4, 8, 16


class FakeSolver:
    def __init__(self, can_solve=True, solving_polls=0):
        self.CanSolve = can_solve
        self.polls_left = solving_polls

    @property
    def IsSolving(self):
        if self.polls_left > 0:
            self.polls_left -= 1
            return True
        return False


class FakeCase:
    """objects 是 {状态位: [(类型, 名字), ...]}。"""

    def __init__(self, objects, **solver_options):
        self.objects = objects
        self.Solver = FakeSolver(**solver_options)

    def GetFlowsheetStatus(self, flag):
        return len(self.objects.get(flag, ()))

    def GetFlowsheetObjectTypeAndName(self, flag):
        return tuple(self.objects.get(flag, ())) or None


def error_of(case, timeout_s=5.0):
    with pytest.raises(ReactorAgentError) as caught:
        solve(case, SolveArgs(timeout_s=timeout_s))
    return caught.value


def test_every_object_ok_means_solved_and_reports_each_object():
    case = FakeCase({OK: [("MaterialStream", "Feed"), ("ConversionReactorOpObject", "R-1")]})
    outcome = solve(case, SolveArgs())
    assert outcome.data.status.solved
    assert {item.name for item in outcome.data.status.objects} == {"Feed", "R-1"}


def test_status_flags_are_mapped_to_object_states():
    case = FakeCase(
        {
            OK: [("MaterialStream", "A")],
            NOT_SOLVED: [("MaterialStream", "B")],
            WARNING: [("MaterialStream", "C")],
            UNDER_SPECIFIED: [("Reactor", "D")],
            ERROR: [("Reactor", "E")],
        }
    )
    states = {item.name: item.state for item in read_solve_status(case).objects}
    assert states == {
        "A": ObjectState.OK,
        "B": ObjectState.NOT_SOLVED,
        "C": ObjectState.WARNING,
        "D": ObjectState.UNDER_SPECIFIED,
        "E": ObjectState.ERROR,
    }


def test_warnings_do_not_stop_a_model_from_counting_as_solved():
    case = FakeCase({OK: [("MaterialStream", "A")], WARNING: [("MaterialStream", "B")]})
    assert solve(case, SolveArgs()).data.status.solved


def test_under_specified_objects_are_reported_with_their_state_and_are_not_retryable():
    case = FakeCase({OK: [("MaterialStream", "Feed")], UNDER_SPECIFIED: [("Reactor", "CRV")]})
    error = error_of(case)
    assert error.code is ErrorCode.NOT_SOLVED
    assert error.details == {"CRV": "under_specified"}
    assert not error.retryable


def test_error_state_is_reported_as_not_converged_and_is_retryable():
    case = FakeCase({ERROR: [("Reactor", "GBR")], NOT_SOLVED: [("MaterialStream", "Out")]})
    error = error_of(case)
    assert error.code is ErrorCode.NOT_CONVERGED
    assert error.details == {"GBR": "error", "Out": "not_solved"}
    assert error.retryable


def test_a_flowsheet_without_objects_is_not_a_solved_model():
    assert error_of(FakeCase({})).code is ErrorCode.NOT_SOLVED


def test_held_solver_is_released_and_the_release_is_read_back():
    case = FakeCase({OK: [("MaterialStream", "Feed")]}, can_solve=False)
    solve(case, SolveArgs())
    assert case.Solver.CanSolve is True


def test_solver_that_refuses_to_be_released_is_detected():
    class Stubborn(FakeSolver):
        @property
        def CanSolve(self):
            return False

        @CanSolve.setter
        def CanSolve(self, value):
            pass

    case = FakeCase({OK: [("MaterialStream", "Feed")]})
    case.Solver = Stubborn()
    assert error_of(case).code is ErrorCode.READBACK_MISMATCH


def test_waiting_for_a_solver_that_never_finishes_times_out():
    case = FakeCase({OK: [("MaterialStream", "Feed")]}, solving_polls=10_000)
    error = error_of(case, timeout_s=0.3)
    assert error.code is ErrorCode.TIMEOUT
    assert error.retryable


def test_solver_that_finishes_within_the_limit_is_waited_for():
    case = FakeCase({OK: [("MaterialStream", "Feed")]}, solving_polls=2)
    assert solve(case, SolveArgs(timeout_s=5.0)).data.status.solved

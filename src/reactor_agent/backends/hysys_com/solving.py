"""求解：HYSYS 没有单独的“求解”调用。

求解器放开时，每次写入都同步重算，写完就是解完的状态（台账 H17）。所以 solve 实际是“检查”：
确保求解器放开，等它空闲，再按流程图的状态判断有没有解出来。建模期间不挂起求解器。等待上限
靠轮询 IsSolving 实现，COM 调用本身不能被中断。
"""

import time
from typing import Any

from reactor_agent.backends.hysys_com.com_errors import com_call
from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.enums import ObjectState, ResultStatus
from reactor_agent.spec.snapshot import ObjectStatus, SolveStatus
from reactor_agent.spec.tool_args import SolveArgs
from reactor_agent.spec.tool_results import Outcome, SolveData

# GetFlowsheetStatus 的状态位（FlowSheetObjStatusFlag_enum，台账 H19）。
STATUS_FLAGS = {
    1: ObjectState.OK,
    2: ObjectState.NOT_SOLVED,
    4: ObjectState.WARNING,
    8: ObjectState.UNDER_SPECIFIED,
    16: ObjectState.ERROR,
}
UNSOLVED_STATES = (ObjectState.NOT_SOLVED, ObjectState.UNDER_SPECIFIED, ObjectState.ERROR)
POLL_INTERVAL_S = 0.2


def read_solve_status(case: Any) -> SolveStatus:
    """流程图里每个对象的求解状态，以及求解器是否还在求解。"""
    with com_call(ErrorCode.NOT_FOUND, "读取流程图状态"):
        objects: list[ObjectStatus] = []
        for flag, state in STATUS_FLAGS.items():
            if int(case.GetFlowsheetStatus(flag)) == 0:
                continue
            for type_name, name in case.GetFlowsheetObjectTypeAndName(flag) or ():
                objects.append(ObjectStatus(name=str(name), type_name=str(type_name), state=state))
        return SolveStatus(is_solving=bool(case.Solver.IsSolving), objects=tuple(objects))


def _wait_until_idle(case: Any, timeout_s: float) -> SolveStatus:
    deadline = time.monotonic() + timeout_s
    while True:
        status = read_solve_status(case)
        if not status.is_solving:
            return status
        if time.monotonic() >= deadline:
            raise ReactorAgentError(ErrorCode.TIMEOUT, f"等待求解超过 {timeout_s} 秒")
        time.sleep(POLL_INTERVAL_S)


def _raise_unless_solved(status: SolveStatus) -> None:
    if not status.objects:
        raise ReactorAgentError(ErrorCode.NOT_SOLVED, "流程图里还没有任何对象")
    unsolved = {
        item.name: item.state.value for item in status.objects if item.state in UNSOLVED_STATES
    }
    if not unsolved:
        return
    # 台账 H30 没有不收敛的样本：这里把 Error 状态当作不收敛，缺规定和未求解当作欠规定，没有验证过。
    errored = ObjectState.ERROR.value in unsolved.values()
    code = ErrorCode.NOT_CONVERGED if errored else ErrorCode.NOT_SOLVED
    raise ReactorAgentError(code, f"模型没有解出来：{unsolved}", unsolved)


def solve(case: Any, args: SolveArgs) -> Outcome[SolveData]:
    """确认模型已经求解完成。超时、缺规定、不收敛分别用不同的错误码。"""
    started = time.monotonic()
    with com_call(ErrorCode.NOT_SOLVED, "放开求解器"):
        if not bool(case.Solver.CanSolve):
            case.Solver.CanSolve = True
    status = _wait_until_idle(case, args.timeout_s)
    _raise_unless_solved(status)
    return Outcome(
        ResultStatus.UNCHANGED, SolveData(duration_s=time.monotonic() - started, status=status)
    )

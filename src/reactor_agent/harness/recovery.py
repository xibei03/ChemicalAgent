"""恢复策略：错误码 → 重试几次、能不能重建。

决定做什么是这里的纯函数（查表），去做是执行器的事。表是计划 §13.2 的子集：自动重启会话（R1）、
让 LLM 重述规格（R3）、向用户提问（R4）都还没有，所以会话失效、规格问题这几类错误直接中止。
每个错误码最多重试几次写在这张表里；其余的上限（求解等待、重建次数）在 budgets.py。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from reactor_agent.errors import ErrorCode
from reactor_agent.harness.budgets import MAX_REBUILDS
from reactor_agent.spec.enums import RecoveryAction


@dataclass(frozen=True)
class Policy:
    """一个错误码的策略链：先重试 retries 次，然后（如果允许）重建一次，最后中止。"""

    retries: int
    rebuild: bool


ABORT_ONLY = Policy(retries=0, rebuild=False)
TRANSIENT = Policy(retries=2, rebuild=True)
ONCE = Policy(retries=1, rebuild=True)
REBUILD_ONLY = Policy(retries=0, rebuild=True)

POLICIES: Mapping[ErrorCode, Policy] = MappingProxyType(
    {
        ErrorCode.NOT_FOUND: TRANSIENT,
        ErrorCode.READBACK_MISMATCH: TRANSIENT,
        ErrorCode.ATTACH_FAILED: TRANSIENT,
        ErrorCode.CONNECT_FAILED: TRANSIENT,
        ErrorCode.IO: TRANSIENT,
        ErrorCode.CASE_OPEN: TRANSIENT,
        ErrorCode.TIMEOUT: ONCE,
        ErrorCode.NOT_CONVERGED: ONCE,
        ErrorCode.VALIDATION_FATAL: ONCE,
        ErrorCode.CONFLICT: REBUILD_ONLY,
        ErrorCode.BASIS_LOCKED: REBUILD_ONLY,
        # 多数是确定的欠规定，重建一次还解不出来就中止，诊断里有各对象的状态；但 HYSYS 偶尔
        # 也会建出结构全对却不求解的模型（台账 L38），新建一个 Case 重来能避开它。
        ErrorCode.NOT_SOLVED: REBUILD_ONLY,
    }
)


def decide(
    code: ErrorCode, retries_used: int, rebuilds_used: int, *, case_exists: bool = True
) -> RecoveryAction:
    """下一步做什么：这个位置的重试还没用完就重试，否则重建（如果允许且还没用掉），否则中止。

    还没有 Case 的阶段（选型、写规格）没有可以丢弃重建的东西，所以不重建。
    """
    policy = POLICIES.get(code, ABORT_ONLY)
    if retries_used < policy.retries:
        return RecoveryAction.RETRY
    if policy.rebuild and case_exists and rebuilds_used < MAX_REBUILDS:
        return RecoveryAction.REBUILD
    return RecoveryAction.ABORT

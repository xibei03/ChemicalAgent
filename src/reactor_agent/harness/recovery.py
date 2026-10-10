"""恢复策略：错误码 → 重试几次、能不能重建；规格没有通过校验之后做什么。

决定做什么是这里的纯函数（查表），去做是执行器的事。表是计划 §13.2 的子集：自动重启会话（R1）
还没有，所以会话失效这类错误直接中止；让 LLM 重述规格（R3）和向用户提问（R4）是 decide_spec。
每个错误码最多重试几次写在这张表里；其余的上限（求解等待、重建次数、重写轮数）在 budgets.py。
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from reactor_agent.errors import ErrorCode
from reactor_agent.harness.budgets import MAX_REBUILDS, MAX_SPEC_REWRITES
from reactor_agent.spec.enums import RecoveryAction
from reactor_agent.spec.results import Issue


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


class SpecAction(StrEnum):
    """规格没有通过校验之后：交回给 LLM 重写、请用户补充或更正、中止。"""

    REWRITE = "rewrite"
    ASK_USER = "ask_user"
    ABORT = "abort"


def decide_spec(issues: Sequence[Issue], missing_declared: bool, rewrites_used: int) -> SpecAction:
    """规格没有通过校验之后做什么。

    不可以假设的信息缺失，重写也变不出来，直接请用户补充；否则重写，轮数用完了再看问题出在哪：
    出在用户给的信息上请用户确认，别的中止。
    """
    if missing_declared:
        return SpecAction.ASK_USER
    if rewrites_used < MAX_SPEC_REWRITES:
        return SpecAction.REWRITE
    return SpecAction.ASK_USER if any(i.user_fixable for i in issues) else SpecAction.ABORT

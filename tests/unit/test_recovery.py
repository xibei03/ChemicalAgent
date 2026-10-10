"""恢复策略：每个错误码的策略链，以及与可重试集合的一致性。"""

import pytest

from reactor_agent.errors import RETRYABLE_ERROR_CODES, ErrorCode
from reactor_agent.harness.budgets import MAX_SPEC_REWRITES
from reactor_agent.harness.recovery import ABORT_ONLY, POLICIES, SpecAction, decide, decide_spec
from reactor_agent.spec.enums import RecoveryAction
from reactor_agent.spec.results import make_issue

RETRY = RecoveryAction.RETRY
REBUILD = RecoveryAction.REBUILD
ABORT = RecoveryAction.ABORT

# 提示词里的策略表：重试几次，然后是否重建。其余错误码一律直接中止。
RETRY_TWICE = {
    ErrorCode.NOT_FOUND,
    ErrorCode.READBACK_MISMATCH,
    ErrorCode.ATTACH_FAILED,
    ErrorCode.CONNECT_FAILED,
    ErrorCode.IO,
    ErrorCode.CASE_OPEN,
}
RETRY_ONCE = {ErrorCode.TIMEOUT, ErrorCode.NOT_CONVERGED, ErrorCode.VALIDATION_FATAL}
REBUILD_AT_ONCE = {ErrorCode.CONFLICT, ErrorCode.BASIS_LOCKED, ErrorCode.NOT_SOLVED}
LONGEST_CHAIN = 6


def chain(code: ErrorCode) -> list[RecoveryAction]:
    """沿着策略一直走下去：重试用的是同一个位置的次数，重建之后位置变了，次数从零开始。"""
    retries, rebuilds, actions = 0, 0, []
    for _ in range(LONGEST_CHAIN + 1):  # decide 一旦不再给出 ABORT，测试要失败而不是挂死
        if ABORT in actions:
            break
        action = decide(code, retries, rebuilds)
        actions.append(action)
        if action is RETRY:
            retries += 1
        elif action is REBUILD:
            retries, rebuilds = 0, rebuilds + 1
    return actions


def expected_chain(code: ErrorCode) -> list[RecoveryAction]:
    if code in RETRY_TWICE:
        return [RETRY, RETRY, REBUILD, RETRY, RETRY, ABORT]
    if code in RETRY_ONCE:
        return [RETRY, REBUILD, RETRY, ABORT]
    if code in REBUILD_AT_ONCE:
        return [REBUILD, ABORT]
    return [ABORT]


@pytest.mark.parametrize("code", list(ErrorCode))
def test_every_error_code_follows_its_policy_chain(code):
    assert chain(code) == expected_chain(code)


@pytest.mark.parametrize("code", list(ErrorCode))
def test_a_code_that_cannot_be_retried_is_never_retried(code):
    assert (RETRY in chain(code)) == (code in RETRYABLE_ERROR_CODES)


def test_policy_table_retries_exactly_the_retryable_codes():
    with_retries = {code for code in ErrorCode if POLICIES.get(code, ABORT_ONLY).retries > 0}
    assert with_retries == set(RETRYABLE_ERROR_CODES)


@pytest.mark.parametrize("code", list(ErrorCode))
def test_the_number_of_recovery_actions_is_bounded(code):
    assert len(chain(code)) <= LONGEST_CHAIN


def test_a_rebuild_that_was_already_used_is_not_offered_again():
    assert decide(ErrorCode.CONFLICT, retries_used=0, rebuilds_used=1) is ABORT
    assert decide(ErrorCode.NOT_FOUND, retries_used=2, rebuilds_used=1) is ABORT


@pytest.mark.parametrize("code", [ErrorCode.CONFLICT, ErrorCode.NOT_SOLVED, ErrorCode.IO])
def test_nothing_is_rebuilt_before_a_case_exists(code):
    retries = POLICIES[code].retries
    assert decide(code, retries, 0, case_exists=False) is ABORT
    if retries:
        assert decide(code, 0, 0, case_exists=False) is RETRY


# ---- 规格没有通过校验之后 ----

FIXABLE = make_issue(ErrorCode.RULE, "feeds[0].temperature_c", "没有给", user_fixable=True)
NOT_FIXABLE = make_issue(ErrorCode.SCHEMA, "feeds[0].flow", "没有流量")
UNSUPPORTED = make_issue(ErrorCode.UNSUPPORTED, "reactions[0]", "不支持")


@pytest.mark.parametrize("used", range(MAX_SPEC_REWRITES + 1))
def test_missing_information_that_cannot_be_assumed_asks_the_user_at_once(used):
    assert decide_spec([NOT_FIXABLE], True, used) is SpecAction.ASK_USER


@pytest.mark.parametrize("issue", [FIXABLE, NOT_FIXABLE, UNSUPPORTED])
def test_every_problem_is_sent_back_for_a_rewrite_while_rounds_remain(issue):
    for used in range(MAX_SPEC_REWRITES):
        assert decide_spec([issue], False, used) is SpecAction.REWRITE


def test_when_the_rounds_are_used_up_a_problem_in_what_the_user_gave_asks_the_user():
    assert decide_spec([NOT_FIXABLE, FIXABLE], False, MAX_SPEC_REWRITES) is SpecAction.ASK_USER


@pytest.mark.parametrize("issues", [[NOT_FIXABLE], [UNSUPPORTED], [NOT_FIXABLE, UNSUPPORTED]])
def test_when_the_rounds_are_used_up_nothing_the_user_can_fix_aborts(issues):
    assert decide_spec(issues, False, MAX_SPEC_REWRITES) is SpecAction.ABORT

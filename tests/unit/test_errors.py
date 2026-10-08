"""错误码与计划 §13.2 的对照，以及异常的基本行为。"""

import pytest

from reactor_agent.errors import RETRYABLE_ERROR_CODES, ErrorCode, ReactorAgentError

# 计划 §13.2 的表：错误码 -> 策略链的第一步。R0 表示重试、重新求解或重新读取。
FIRST_STRATEGY_STEP = {
    "E_LLM": "客户端内部退避重试",
    "E_SCHEMA": "R3",
    "E_RULE": "R3",
    "E_UNSUPPORTED": "终态",
    "E_COM_UNAVAILABLE": "R1",
    "E_COM_DISCONNECTED": "R1",
    "E_TIMEOUT": "R0",
    "E_NOT_FOUND": "R0",
    "E_READBACK_MISMATCH": "R0",
    "E_ATTACH_FAILED": "R0",
    "E_CONNECT_FAILED": "R0",
    "E_IO": "R0",
    "E_CASE_OPEN": "R0",
    "E_VERSION": "R5",
    "E_LICENSE": "R5",
    "E_CONFLICT": "R2",
    "E_BASIS_LOCKED": "R2",
    "E_COMPONENT_NOT_FOUND": "R3",
    "E_PP_UNSUPPORTED": "R3",
    "E_REACTION_INVALID": "R3",
    "E_SET_INCOMPATIBLE": "R3",
    "E_NOT_SOLVED": "收集对象状态",
    "E_NOT_CONVERGED": "R0",
    "E_VALIDATION_FATAL": "R0",
    "E_BUDGET": "R5",
    "E_TOOL_NOT_ALLOWED": "R5",
    "E_VAR_NOT_ALLOWED": "R5",
}


def test_error_codes_are_exactly_the_ones_in_the_plan():
    assert {code.value for code in ErrorCode} == set(FIRST_STRATEGY_STEP)


@pytest.mark.parametrize("code", list(ErrorCode))
def test_retryable_means_strategy_chain_starts_with_r0(code):
    assert code.retryable == (FIRST_STRATEGY_STEP[code.value] == "R0")


def test_retryable_set_is_the_single_source():
    assert {code for code in ErrorCode if code.retryable} == RETRYABLE_ERROR_CODES


def test_llm_errors_are_not_retryable_by_the_executor():
    assert not ErrorCode.LLM.retryable


def test_not_found_and_component_not_found_are_different_codes():
    assert ErrorCode.NOT_FOUND.retryable
    assert not ErrorCode.COMPONENT_NOT_FOUND.retryable


def test_error_carries_code_message_and_details():
    error = ReactorAgentError(ErrorCode.CONFLICT, "物流已存在", {"Feed": "温度不同"})
    assert error.code is ErrorCode.CONFLICT
    assert error.message == "物流已存在"
    assert error.details == {"Feed": "温度不同"}
    assert str(error) == "E_CONFLICT: 物流已存在"
    assert not error.retryable


def test_error_retryable_follows_its_code():
    assert ReactorAgentError(ErrorCode.TIMEOUT, "超时").retryable


def test_error_details_default_to_empty_and_cannot_be_modified():
    error = ReactorAgentError(ErrorCode.IO, "文件不存在")
    assert error.details == {}
    with pytest.raises(TypeError):
        error.details["x"] = "y"

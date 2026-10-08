"""COM 异常转成领域错误的唯一位置：错误码映射、进程没了的识别、可能没有值的读取。"""

import pytest
import pywintypes

from reactor_agent.backends.hysys_com.com_errors import (
    RPC_CALL_FAILED,
    RPC_SERVER_UNAVAILABLE,
    attempt_cleanup,
    com_call,
    read_optional,
)
from reactor_agent.errors import ErrorCode, ReactorAgentError

E_FAIL = -2147467259
DISP_E_EXCEPTION = -2147352567


def hysys_failure(description="Could not add component", scode=E_FAIL):
    """HYSYS 常见的失败形式：外层是 DISP_E_EXCEPTION，内层 scode 和说明在 excepinfo 里。"""
    excepinfo = (0, "HYSYS", description, None, 0, scode)
    return pywintypes.com_error(DISP_E_EXCEPTION, "Exception occurred.", excepinfo, None)


def raising(error):
    def call():
        raise error

    return call


class TestComCall:
    def test_com_error_becomes_a_domain_error_with_the_requested_code(self):
        with (
            pytest.raises(ReactorAgentError) as caught,
            com_call(ErrorCode.CONNECT_FAILED, "接进料"),
        ):
            raising(hysys_failure())()
        error = caught.value
        assert error.code is ErrorCode.CONNECT_FAILED
        assert "接进料" in error.message
        assert "Could not add component" in error.message
        assert error.details["hresult"] == str(DISP_E_EXCEPTION)
        assert error.details["scode"] == str(E_FAIL)
        assert isinstance(error.__cause__, pywintypes.com_error)

    @pytest.mark.parametrize("hresult", [RPC_SERVER_UNAVAILABLE, RPC_CALL_FAILED])
    def test_lost_process_is_always_a_disconnection_whatever_code_was_requested(self, hresult):
        lost = pywintypes.com_error(hresult, "The RPC server is unavailable.", None, None)
        with pytest.raises(ReactorAgentError) as caught, com_call(ErrorCode.IO, "保存"):
            raising(lost)()
        assert caught.value.code is ErrorCode.COM_DISCONNECTED

    def test_error_without_exception_info_uses_the_system_text(self):
        plain = pywintypes.com_error(E_FAIL, "Unspecified error", None, None)
        with pytest.raises(ReactorAgentError) as caught, com_call(ErrorCode.NOT_FOUND, "读取"):
            raising(plain)()
        assert "Unspecified error" in caught.value.message
        assert "scode" not in caught.value.details

    def test_domain_errors_and_bugs_pass_through_untouched(self):
        with pytest.raises(ReactorAgentError) as caught, com_call(ErrorCode.IO, "保存"):
            raise ReactorAgentError(ErrorCode.CONFLICT, "已有")
        assert caught.value.code is ErrorCode.CONFLICT
        with pytest.raises(AttributeError), com_call(ErrorCode.IO, "保存"):
            raise AttributeError("bug")

    def test_no_error_means_no_effect(self):
        with com_call(ErrorCode.IO, "保存"):
            value = 3
        assert value == 3


class TestReadOptional:
    def test_value_is_returned(self):
        assert read_optional(lambda: "Q-100") == "Q-100"

    def test_unconnected_reference_is_none(self):
        assert read_optional(raising(hysys_failure())) is None

    def test_lost_process_is_not_the_same_as_no_value(self):
        lost = pywintypes.com_error(RPC_SERVER_UNAVAILABLE, "gone", None, None)
        with pytest.raises(ReactorAgentError) as caught:
            read_optional(raising(lost))
        assert caught.value.code is ErrorCode.COM_DISCONNECTED


class TestAttemptCleanup:
    def test_failure_of_a_cleanup_action_is_reported_not_raised(self):
        assert attempt_cleanup(raising(hysys_failure())) is False

    def test_success_is_reported(self):
        assert attempt_cleanup(lambda: None) is True

"""COM 异常转成领域错误的唯一位置。

`com_error` 这个名字只出现在这个文件里：HYSYS 的失败各有各的表现，上层只应该看到领域错误。
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TypeVar

import pywintypes

from reactor_agent.errors import ErrorCode, ReactorAgentError

# HRESULT：RPC 服务器不可用（两次调用之间进程没了）、RPC 调用失败（调用期间进程没了）。台账 L26。
RPC_SERVER_UNAVAILABLE = -2147023174
RPC_CALL_FAILED = -2147023170
PROCESS_GONE_CODES = frozenset({RPC_SERVER_UNAVAILABLE, RPC_CALL_FAILED})
# com_error.args 是 (hresult, 系统文字, excepinfo, 出错的参数序号)；
# excepinfo 里有 HYSYS 的说明文字和内层 scode。
ARG_HRESULT = 0
ARG_MESSAGE = 1
ARG_EXCEPTION_INFO = 2
INFO_DESCRIPTION = 2
INFO_SCODE = 5

ValueT = TypeVar("ValueT")


def _hresult(error: pywintypes.com_error) -> int:
    return int(error.args[ARG_HRESULT])


def _info(error: pywintypes.com_error, index: int) -> object:
    """excepinfo 里的一项；没有 excepinfo 或者这一项为空时是 None。"""
    info = error.args[ARG_EXCEPTION_INFO] if len(error.args) > ARG_EXCEPTION_INFO else None
    return info[index] if info and len(info) > index and info[index] else None


def _describe(error: pywintypes.com_error) -> str:
    """优先用 HYSYS 给的说明文字；没有时用系统的错误文字。"""
    return str(_info(error, INFO_DESCRIPTION) or error.args[ARG_MESSAGE])


def _details(error: pywintypes.com_error) -> dict[str, str]:
    details = {"hresult": str(_hresult(error)), "message": _describe(error)}
    scode = _info(error, INFO_SCODE)
    if scode is not None:
        details["scode"] = str(scode)
    return details


def _translate(error: pywintypes.com_error, code: ErrorCode, action: str) -> ReactorAgentError:
    details = _details(error)
    if _hresult(error) in PROCESS_GONE_CODES:
        return ReactorAgentError(
            ErrorCode.COM_DISCONNECTED, f"HYSYS 进程已经不可用（{action}时）", details
        )
    return ReactorAgentError(code, f"{action}失败：{details['message']}", details)


@contextmanager
def com_call(code: ErrorCode, action: str) -> Iterator[None]:
    """所有 COM 调用都经过这里：HYSYS 的 COM 异常转成领域错误，并带着原始异常的上下文。

    code 是这次调用失败时用的错误码；进程没了（RPC 断开）一律是 E_COM_DISCONNECTED。
    """
    try:
        yield
    except pywintypes.com_error as error:
        raise _translate(error, code, action) from error


def read_optional(read: Callable[[], ValueT]) -> ValueT | None:
    """读一个可能没有值的成员。

    HYSYS 对没有连接的引用（能流、反应集）和还没有闪蒸的物流相态抛 com_error，这里当作 None；
    进程没了不是“没有值”，照样转成领域错误。
    """
    try:
        return read()
    except pywintypes.com_error as error:
        if _hresult(error) in PROCESS_GONE_CODES:
            raise _translate(error, ErrorCode.COM_DISCONNECTED, "读取") from error
        return None


def attempt_cleanup(action: Callable[[], object]) -> bool:
    """做一个收尾动作（比如退出实例）。失败返回 False：收尾时进程可能已经不在了，不值得再抛错。"""
    try:
        action()
    except pywintypes.com_error:
        return False
    return True

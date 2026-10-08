"""领域错误：错误码、可重试的判定和统一的异常类型。不依赖项目内的任何模块。"""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType


class ErrorCode(StrEnum):
    """错误码，与计划 §13.2 一一对应。上层按错误码决定恢复策略，所以每种失败都要有明确的码。"""

    # LLM
    LLM = "E_LLM"
    # 规格与范围
    SCHEMA = "E_SCHEMA"
    RULE = "E_RULE"
    UNSUPPORTED = "E_UNSUPPORTED"
    COMPONENT_NOT_FOUND = "E_COMPONENT_NOT_FOUND"
    PP_UNSUPPORTED = "E_PP_UNSUPPORTED"
    REACTION_INVALID = "E_REACTION_INVALID"
    SET_INCOMPATIBLE = "E_SET_INCOMPATIBLE"
    # 会话与环境
    COM_UNAVAILABLE = "E_COM_UNAVAILABLE"
    COM_DISCONNECTED = "E_COM_DISCONNECTED"
    VERSION = "E_VERSION"
    LICENSE = "E_LICENSE"
    # 执行
    TIMEOUT = "E_TIMEOUT"
    NOT_FOUND = "E_NOT_FOUND"
    READBACK_MISMATCH = "E_READBACK_MISMATCH"
    ATTACH_FAILED = "E_ATTACH_FAILED"
    CONNECT_FAILED = "E_CONNECT_FAILED"
    IO = "E_IO"
    CASE_OPEN = "E_CASE_OPEN"
    # 状态污染
    CONFLICT = "E_CONFLICT"
    BASIS_LOCKED = "E_BASIS_LOCKED"
    # 求解与结果
    NOT_SOLVED = "E_NOT_SOLVED"
    NOT_CONVERGED = "E_NOT_CONVERGED"
    VALIDATION_FATAL = "E_VALIDATION_FATAL"
    # 预算与程序缺陷
    BUDGET = "E_BUDGET"
    TOOL_NOT_ALLOWED = "E_TOOL_NOT_ALLOWED"
    VAR_NOT_ALLOWED = "E_VAR_NOT_ALLOWED"

    @property
    def retryable(self) -> bool:
        """原样再调用一次是否有可能成功。只由 RETRYABLE_ERROR_CODES 决定。"""
        return self in RETRYABLE_ERROR_CODES


# 计划 §13.2 里策略链以 R0（重试、重新求解、重新读取）开头的错误码。E_LLM 不在其中：
# LLM 调用的重试在 LLM 客户端内部完成，执行器不再重试。
RETRYABLE_ERROR_CODES: frozenset[ErrorCode] = frozenset(
    {
        ErrorCode.TIMEOUT,
        ErrorCode.NOT_FOUND,
        ErrorCode.READBACK_MISMATCH,
        ErrorCode.ATTACH_FAILED,
        ErrorCode.CONNECT_FAILED,
        ErrorCode.IO,
        ErrorCode.CASE_OPEN,
        ErrorCode.NOT_CONVERGED,
        ErrorCode.VALIDATION_FATAL,
    }
)


class ReactorAgentError(Exception):
    """领域错误。带错误码、给人看的消息和一份细节（键是对象名或字段名，值是说明文字）。"""

    def __init__(
        self, code: ErrorCode, message: str, details: Mapping[str, str] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details: Mapping[str, str] = MappingProxyType(dict(details or {}))

    @property
    def retryable(self) -> bool:
        """是否可重试，由错误码决定，不由抛出的地方各自指定。"""
        return self.code.retryable

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

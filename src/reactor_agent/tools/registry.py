"""ToolExecutor：按名字调用工具。"""

import time
from collections.abc import Callable, Mapping

from pydantic import BaseModel

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.enums import ToolName
from reactor_agent.spec.tool_results import ToolCallEvent, ToolResult

ToolRunner = Callable[[BaseModel], ToolResult]
EventHandler = Callable[[ToolCallEvent], None]


class ToolExecutor:
    """按名字调用工具：Backend 抛的领域错误转成失败的信封，计时，并把调用事件交给回调。

    工具和 Backend 都不重试，重试由 harness 按错误码决定。非领域异常是程序缺陷，不在这里吞掉。
    """

    def __init__(
        self, tools: Mapping[ToolName, ToolRunner], on_event: EventHandler | None = None
    ) -> None:
        self._tools = tools
        self._on_event = on_event

    def call(self, name: str, args: BaseModel) -> ToolResult:
        """调用名为 name 的工具。成功和失败都返回信封，每次调用交给回调一个事件。"""
        started = time.monotonic()
        result = self._run(name, args)
        if self._on_event is not None:
            duration_s = time.monotonic() - started
            self._on_event(
                ToolCallEvent(tool=name, args=args, result=result, duration_s=duration_s)
            )
        return result

    def _runner(self, name: str) -> ToolRunner | None:
        try:
            return self._tools.get(ToolName(name))
        except ValueError:
            return None  # 不是任何一个工具名

    def _run(self, name: str, args: BaseModel) -> ToolResult:
        runner = self._runner(name)
        if runner is None:
            return ToolResult.failure(ErrorCode.TOOL_NOT_ALLOWED, f"没有这个工具：{name}")
        try:
            return runner(args)
        except ReactorAgentError as error:
            return ToolResult.failure(error.code, error.message, error.details)

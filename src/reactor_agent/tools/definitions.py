"""工具登记：把工具名、入参模型和 Backend 方法放在一起。"""

from collections.abc import Callable, Mapping
from typing import TypeVar

from pydantic import BaseModel

from reactor_agent.backends.base import SimBackend
from reactor_agent.errors import ErrorCode
from reactor_agent.spec.enums import ToolName
from reactor_agent.spec.tool_args import (
    CloseCaseArgs,
    ConnectArgs,
    EnsureCaseArgs,
    EnsureReactionArgs,
    EnsureReactionSetArgs,
    EnsureReactorArgs,
    EnsureStreamArgs,
    EnsureThermoArgs,
    ReadSnapshotArgs,
    SaveCaseArgs,
    SetSpecArgs,
    SolveArgs,
)
from reactor_agent.spec.tool_results import DataT, Outcome, ToolResult
from reactor_agent.tools.registry import ToolRunner

ArgsT = TypeVar("ArgsT", bound=BaseModel)


def bind(model: type[ArgsT], handler: Callable[[ArgsT], Outcome[DataT]]) -> ToolRunner:
    """把“核对入参的类型”和“调用 Backend 方法”包成签名统一的可调用对象。

    非法的值在构造入参模型时就被 pydantic 拒绝了，所以这里只核对它是不是这个工具的入参类型。
    """

    def run(args: BaseModel) -> ToolResult:
        if not isinstance(args, model):
            message = f"入参应当是 {model.__name__}，实际是 {type(args).__name__}"
            return ToolResult.failure(ErrorCode.SCHEMA, message)
        return ToolResult.success(handler(args))

    return run


def register_tools(backend: SimBackend) -> Mapping[ToolName, ToolRunner]:
    """把全部 12 个工具登记到同一个 Backend 上。"""
    return {
        ToolName.SESSION_CONNECT: bind(ConnectArgs, backend.connect),
        ToolName.CASE_ENSURE: bind(EnsureCaseArgs, backend.ensure_case),
        ToolName.CASE_SAVE: bind(SaveCaseArgs, backend.save_case),
        ToolName.CASE_CLOSE: bind(CloseCaseArgs, backend.close_case),
        ToolName.BASIS_ENSURE_THERMO: bind(EnsureThermoArgs, backend.ensure_thermo),
        ToolName.BASIS_ENSURE_REACTION: bind(EnsureReactionArgs, backend.ensure_reaction),
        ToolName.BASIS_ENSURE_REACTION_SET: bind(
            EnsureReactionSetArgs, backend.ensure_reaction_set
        ),
        ToolName.FLOWSHEET_ENSURE_STREAM: bind(EnsureStreamArgs, backend.ensure_stream),
        ToolName.FLOWSHEET_ENSURE_REACTOR: bind(EnsureReactorArgs, backend.ensure_reactor),
        ToolName.FLOWSHEET_SET_SPEC: bind(SetSpecArgs, backend.set_spec),
        ToolName.SOLVER_SOLVE: bind(SolveArgs, backend.solve),
        ToolName.MODEL_READ_SNAPSHOT: bind(ReadSnapshotArgs, backend.read_snapshot),
    }

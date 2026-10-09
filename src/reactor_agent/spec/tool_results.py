"""工具的结果：Backend 的 Outcome、各工具的结果数据、结果信封和工具调用事件。

结果信封（ToolResult）成功时带状态和这个工具自己的结果数据，失败时带错误码、消息、是否可重试和细节。
读回比对在工具内部完成，不一致就是失败，所以信封里没有 readback 字段。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, Self, TypeVar

from pydantic import BaseModel, Field, SerializeAsAny, model_validator

from reactor_agent.errors import ErrorCode
from reactor_agent.spec.base import FrozenModel
from reactor_agent.spec.enums import (
    PropertyPackage,
    ReactionKind,
    ReactorType,
    ResultStatus,
    SpecVariable,
    StreamKind,
)
from reactor_agent.spec.snapshot import ModelSnapshot, SolveStatus


class ConnectData(FrozenModel):
    """session.connect：版本、进程号，以及这个实例是不是复用了已经在运行的。

    复用的实例可能是用户自己开着的，不能结束它。
    """

    version: str
    process_id: int | None
    reused_instance: bool


class CaseData(FrozenModel):
    """case.ensure：Case 的路径（以 HYSYS 读回的为准）。"""

    path: Path


class SaveData(FrozenModel):
    """case.save：写出的文件。"""

    path: Path
    size_bytes: int


class CloseData(FrozenModel):
    """case.close：被关闭的 Case 的路径；本来就没有打开的 Case 时是 None。"""

    path: Path | None


class ThermoData(FrozenModel):
    """basis.ensure_thermo：流体包、组分表（读回的规范名）和物性包。"""

    fluid_package: str
    components: tuple[str, ...]
    property_package: PropertyPackage


class ReactionData(FrozenModel):
    """basis.ensure_reaction：反应和仿真软件算出的质量不守恒量。"""

    name: str
    kind: ReactionKind
    balance_error_kg_per_kmol: float | None


class ReactionSetData(FrozenModel):
    """basis.ensure_reaction_set：反应集和它的成员。"""

    name: str
    reactions: tuple[str, ...]


class StreamData(FrozenModel):
    """flowsheet.ensure_stream：物流的名字和种类。"""

    name: str
    kind: StreamKind


class ReactorData(FrozenModel):
    """flowsheet.ensure_reactor：反应器的名字和类型。"""

    name: str
    reactor_type: ReactorType


class SetSpecData(FrozenModel):
    """flowsheet.set_spec：读回的规定值。"""

    object_name: str
    variable: SpecVariable
    value: float


class SolveData(FrozenModel):
    """solver.solve：等待求解的耗时和各对象的状态。"""

    duration_s: float
    status: SolveStatus


ToolData = (
    ConnectData
    | CaseData
    | SaveData
    | CloseData
    | ThermoData
    | ReactionData
    | ReactionSetData
    | StreamData
    | ReactorData
    | SetSpecData
    | SolveData
    | ModelSnapshot
)
DataT = TypeVar("DataT", bound=ToolData)


@dataclass(frozen=True)
class Outcome(Generic[DataT]):
    """Backend 一次成功的工具调用：对象发生了什么变化，以及这个工具自己的数据。"""

    status: ResultStatus
    data: DataT


class ToolError(FrozenModel):
    """失败信封里的错误。retryable 必须与错误码一致，构造时用 of()。"""

    code: ErrorCode
    message: str
    retryable: bool
    details: Mapping[str, str] = Field(default_factory=dict)

    @classmethod
    def of(cls, code: ErrorCode, message: str, details: Mapping[str, str] | None = None) -> Self:
        """按错误码填好 retryable。"""
        return cls(code=code, message=message, retryable=code.retryable, details=details or {})

    @model_validator(mode="after")
    def _retryable_follows_the_code(self) -> Self:
        if self.retryable != self.code.retryable:
            raise ValueError("retryable 只能由错误码决定")
        return self


class ToolResult(FrozenModel):
    """统一的结果信封。成功时有 status 和 data，失败时有 error。"""

    ok: bool
    status: ResultStatus | None = None
    data: ToolData | None = None
    error: ToolError | None = None

    @model_validator(mode="after")
    def _shape_matches_ok(self) -> Self:
        succeeded_shape = self.status is not None and self.data is not None and self.error is None
        failed_shape = self.status is None and self.data is None and self.error is not None
        if self.ok and not succeeded_shape:
            raise ValueError("成功的结果要有 status 和 data，不能有 error")
        if not self.ok and not failed_shape:
            raise ValueError("失败的结果只有 error")
        return self

    def data_as(self, expected: type[DataT]) -> DataT:
        """成功的信封里这个工具自己的数据。类型不对是程序缺陷，不是运行时的失败。"""
        if not isinstance(self.data, expected):
            raise TypeError(f"工具返回的数据应当是 {expected.__name__}，实际是 {self.data!r}")
        return self.data

    @classmethod
    def success(cls, outcome: Outcome[DataT]) -> Self:
        """把 Backend 的 Outcome 包成成功的信封。"""
        return cls(ok=True, status=outcome.status, data=outcome.data)

    @classmethod
    def failure(
        cls, code: ErrorCode, message: str, details: Mapping[str, str] | None = None
    ) -> Self:
        """构造失败的信封。"""
        return cls(ok=False, error=ToolError.of(code, message, details))


class ToolCallEvent(FrozenModel):
    """一次工具调用：工具名、入参、结果信封和耗时。Trace 记录它。"""

    tool: str
    args: SerializeAsAny[BaseModel]
    result: ToolResult
    duration_s: float

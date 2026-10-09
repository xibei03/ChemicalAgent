"""执行器测试用的 ToolExecutor 桩：记录收到的调用，按脚本返回成功或某个错误码。

成功的回答只带执行器用得到的数据；read_snapshot 返回预先给定的快照，第 n 次求解之后读到第 n 份。
这个桩只放在 tests/ 里。
"""

from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import BaseModel

from reactor_agent.errors import ErrorCode
from reactor_agent.spec.enums import ReactionKind, ResultStatus, ToolName
from reactor_agent.spec.snapshot import ModelSnapshot, SolveStatus
from reactor_agent.spec.tool_args import (
    EnsureCaseArgs,
    EnsureReactionArgs,
    EnsureReactionSetArgs,
    EnsureReactorArgs,
    EnsureStreamArgs,
    EnsureThermoArgs,
    SaveCaseArgs,
    SetSpecArgs,
)
from reactor_agent.spec.tool_results import (
    CaseData,
    CloseData,
    ConnectData,
    Outcome,
    ReactionData,
    ReactionSetData,
    ReactorData,
    SaveData,
    SetSpecData,
    SolveData,
    StreamData,
    ThermoData,
    ToolData,
    ToolResult,
)
from reactor_agent.tools.registry import ToolExecutor

PROCESS_ID = 4242
CREATED = ResultStatus.CREATED
UNCHANGED = ResultStatus.UNCHANGED
CASE_TOOLS = frozenset({ToolName.CASE_ENSURE, ToolName.CASE_SAVE, ToolName.CASE_CLOSE})


class FakeTools(ToolExecutor):
    """按脚本回答的 ToolExecutor。

    snapshots: 第 n 次求解之后读到第 n 份（超出取最后一份）。
    failures: 每个工具一串结果，按调用顺序消耗，None 是成功，错误码是失败；用完之后一律成功。
    always: 这个工具每次都失败。
    reads: 给了就按读取的次序依次给快照（超出取最后一份），不管求解了几次；用来模拟“同一个状态，
        第一次读坏、第二次读好”。
    """

    def __init__(
        self,
        snapshots: Sequence[ModelSnapshot],
        failures: Mapping[ToolName, Sequence[ErrorCode | None]] | None = None,
        always: Mapping[ToolName, ErrorCode] | None = None,
        reads: Sequence[ModelSnapshot] | None = None,
    ) -> None:
        super().__init__({})
        self.calls: list[tuple[ToolName, BaseModel]] = []
        self._snapshots = snapshots
        self._reads = reads
        self._reads_made = 0
        self._failures = {tool: list(codes) for tool, codes in (failures or {}).items()}
        self._always = always or {}
        self.active_case: Path | None = None
        self.solves = 0

    @property
    def tools_called(self) -> list[ToolName]:
        return [tool for tool, _ in self.calls]

    def args_of(self, tool: ToolName) -> list[BaseModel]:
        return [args for called, args in self.calls if called is tool]

    def call(self, name: str, args: BaseModel) -> ToolResult:
        tool = ToolName(name)
        self.calls.append((tool, args))
        code = self._always.get(tool) or self._next_failure(tool)
        if code is not None:
            return ToolResult.failure(
                code, f"注入的故障 {code.value}", {"CRV-100": "under_specified"}
            )
        status, data = self._answer(tool, args)
        return ToolResult.success(Outcome(status, data))

    def _next_failure(self, tool: ToolName) -> ErrorCode | None:
        queue = self._failures.get(tool)
        return queue.pop(0) if queue else None

    def _answer(self, tool: ToolName, args: BaseModel) -> tuple[ResultStatus, ToolData]:
        if tool is ToolName.SESSION_CONNECT:
            return CREATED, ConnectData(
                version="Fake HYSYS", process_id=PROCESS_ID, reused_instance=False
            )
        if tool in CASE_TOOLS:
            return self._answer_case(tool, args)
        if tool is ToolName.SOLVER_SOLVE:
            self.solves += 1
            return UNCHANGED, SolveData(
                duration_s=0.1, status=SolveStatus(is_solving=False, objects=())
            )
        if tool is ToolName.MODEL_READ_SNAPSHOT:
            return UNCHANGED, self._next_snapshot()
        return self._answer_build(args)

    def _next_snapshot(self) -> ModelSnapshot:
        if self._reads is not None:
            snapshot = self._reads[min(self._reads_made, len(self._reads) - 1)]
            self._reads_made += 1
            return snapshot
        assert self.solves > 0, "还没有求解就读快照：执行器的调用顺序错了"
        return self._snapshots[min(self.solves, len(self._snapshots)) - 1]

    def _answer_case(self, tool: ToolName, args: BaseModel) -> tuple[ResultStatus, ToolData]:
        if isinstance(args, EnsureCaseArgs):
            self.active_case, self.solves = args.path, 0
            return CREATED, CaseData(path=args.path)
        if isinstance(args, SaveCaseArgs):
            self.active_case = args.path or self.active_case
            assert self.active_case is not None
            return UNCHANGED, SaveData(path=self.active_case, size_bytes=1)
        closed, self.active_case = self.active_case, None
        return UNCHANGED, CloseData(path=closed)

    def _answer_build(self, args: BaseModel) -> tuple[ResultStatus, ToolData]:
        if isinstance(args, EnsureThermoArgs):
            data = ThermoData(
                fluid_package="Basis-1",
                components=args.components,
                property_package=args.property_package,
            )
        elif isinstance(args, EnsureReactionArgs):
            kind = ReactionKind(args.reaction.kind)
            data = ReactionData(name=args.name, kind=kind, balance_error_kg_per_kmol=0.0)
        elif isinstance(args, EnsureReactionSetArgs):
            data = ReactionSetData(name=args.name, reactions=args.reactions)
        elif isinstance(args, EnsureStreamArgs):
            data = StreamData(name=args.name, kind=args.kind)
        elif isinstance(args, EnsureReactorArgs):
            data = ReactorData(name=args.name, reactor_type=args.reactor_type)
        elif isinstance(args, SetSpecArgs):
            spec = SetSpecData(
                object_name=args.object_name, variable=args.variable, value=args.value
            )
            return ResultStatus.UPDATED, spec
        else:
            raise AssertionError(f"桩不认识这个入参：{args!r}")
        return CREATED, data

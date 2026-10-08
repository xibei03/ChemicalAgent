"""仿真软件的接口。它不提 HYSYS，也不提 COM；以后换仿真软件，只需要再写一个实现。"""

from typing import Protocol

from reactor_agent.spec.snapshot import ModelSnapshot
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
)


class SimBackend(Protocol):
    """每个方法对应一个工具，入参和返回值都是 spec 里的模型。

    ensure_* 的语义是“创建或确认”：对象不存在就创建，读回比对后返回 CREATED；存在且与期望一致
    返回 UNCHANGED；存在但有任何不一致抛 E_CONFLICT。ensure_* 从不修改已有的对象，只有 set_spec
    修改白名单里的工况变量。出了问题抛 ReactorAgentError；Backend 不重试，怎么恢复由上层决定。
    """

    def connect(self, args: ConnectArgs) -> Outcome[ConnectData]:
        """连接仿真软件。"""

    def ensure_case(self, args: EnsureCaseArgs) -> Outcome[CaseData]:
        """新建空白 Case 并另存到指定路径，或者打开已有的文件；已经打开则不变。"""

    def save_case(self, args: SaveCaseArgs) -> Outcome[SaveData]:
        """保存当前 Case，读回文件存在且非空。"""

    def close_case(self, args: CloseCaseArgs) -> Outcome[CloseData]:
        """关闭当前 Case。"""

    def ensure_thermo(self, args: EnsureThermoArgs) -> Outcome[ThermoData]:
        """确保组分表和物性包就绪，并结束 Basis 的修改。"""

    def ensure_reaction(self, args: EnsureReactionArgs) -> Outcome[ReactionData]:
        """确保反应存在，计量系数和类型参数读回一致。"""

    def ensure_reaction_set(self, args: EnsureReactionSetArgs) -> Outcome[ReactionSetData]:
        """确保反应集存在、成员一致并且已挂到流体包。"""

    def ensure_stream(self, args: EnsureStreamArgs) -> Outcome[StreamData]:
        """确保物流或能流存在；给了规定时，规定值读回一致。"""

    def ensure_reactor(self, args: EnsureReactorArgs) -> Outcome[ReactorData]:
        """确保反应器存在，类型、连接、反应集和压降读回一致。"""

    def set_spec(self, args: SetSpecArgs) -> Outcome[SetSpecData]:
        """规定反应器的一个工况变量（出口温度、热负荷），设完读回。"""

    def solve(self, args: SolveArgs) -> Outcome[SolveData]:
        """确认模型已经求解完成；超时、欠规定、不收敛分别用不同的错误码。"""

    def read_snapshot(self, args: ReadSnapshotArgs) -> Outcome[ModelSnapshot]:
        """全量读取模型的状态，只读，没有副作用。"""

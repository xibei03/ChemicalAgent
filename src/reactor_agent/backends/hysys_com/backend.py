"""HysysComBackend：把十二个工具交给各个关注点的模块，自己只管会话、当前 Case 和弹窗看门狗。

构造时不连接 HYSYS，连接只发生在 connect 里。这里不做业务判断，不重试，不等待重连：
出了问题就抛领域错误，怎么恢复由上层决定。
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from reactor_agent.backends.base import SimBackend
from reactor_agent.backends.hysys_com import cases, session, snapshot, solving
from reactor_agent.backends.hysys_com.com_errors import com_call
from reactor_agent.backends.hysys_com.dialogs import DialogGuard
from reactor_agent.backends.hysys_com.lookup import flowsheet_of
from reactor_agent.backends.hysys_com.reactions import ensure_reaction, ensure_reaction_set
from reactor_agent.backends.hysys_com.reactors import ensure_reactor, set_spec
from reactor_agent.backends.hysys_com.streams import ensure_stream
from reactor_agent.backends.hysys_com.thermo import ensure_thermo
from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.enums import ResultStatus
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


class HysysComBackend(SimBackend):
    """通过 COM 操作本机的 Aspen HYSYS V15。"""

    def __init__(self) -> None:
        self._session: session.Session | None = None
        self._case: Any | None = None
        self._guard = DialogGuard()

    def dialog_messages(self) -> tuple[str, ...]:
        """看门狗处理过的对话框文字。正常的建模流程不应该触发任何弹窗。"""
        return tuple(self._guard.messages)

    def is_running(self) -> bool:
        """自己连接的 HYSYS 进程是否还在。只看进程号，不碰 COM，所以进程崩溃之后也能调用。"""
        if self._session is None:
            return False
        process_id = self._session.process_id
        return process_id is None or process_id in session.running_process_ids()

    def shutdown(self) -> None:
        """结束自己启动的 HYSYS 实例并停掉弹窗看门狗。接管来的实例不动。"""
        if self._session is not None:
            session.shutdown(self._session)
        self._guard.stop()
        self._session = None
        self._case = None

    @contextmanager
    def _guarded(self) -> Iterator[None]:
        """每个工具调用的外层保护。

        漏过内层包装的 COM 异常（比如进程崩溃时读集合属性）也转成领域错误；失败时，把调用期间
        看门狗处理过的弹窗文字放进错误的细节，方便诊断。
        """
        before = len(self._guard.messages)
        try:
            with com_call(ErrorCode.NOT_FOUND, "调用 HYSYS"):
                yield
        except ReactorAgentError as error:
            dialogs = self._guard.messages[before:]
            if not dialogs:
                raise
            details = {**error.details, "dialogs": " || ".join(dialogs)}
            raise ReactorAgentError(error.code, error.message, details) from error

    def _app(self) -> Any:
        if self._session is None:
            raise ReactorAgentError(
                ErrorCode.COM_UNAVAILABLE, "还没有连接 HYSYS，先调用 session.connect"
            )
        return self._session.app

    def _active_case(self) -> Any:
        self._app()
        if self._case is None:
            raise ReactorAgentError(ErrorCode.NOT_FOUND, "还没有打开 Case，先调用 case.ensure")
        return self._case

    def connect(self, args: ConnectArgs) -> Outcome[ConnectData]:
        """连接 HYSYS；已经连接并且进程还在则原样返回，进程没了就丢掉旧会话重新连接。"""
        if self._session is not None and not self.is_running():
            self.shutdown()
        status = ResultStatus.UNCHANGED
        if self._session is None:
            self._session = session.connect(args.mode, args.visible)
            self._case = None
            if self._session.process_id is not None:
                self._guard.start(self._session.process_id)
            status = ResultStatus.CREATED
        data = ConnectData(
            version=self._session.version,
            process_id=self._session.process_id,
            reused_instance=self._session.reused_instance,
        )
        return Outcome(status, data)

    def ensure_case(self, args: EnsureCaseArgs) -> Outcome[CaseData]:
        """新建空白 Case 并另存，或者打开已有的文件。"""
        app = self._app()
        with self._guarded():
            ensured = cases.ensure_case(app, self._case, args)
        self._case = ensured.case
        return Outcome(ensured.status, CaseData(path=cases.case_path(ensured.case)))

    def save_case(self, args: SaveCaseArgs) -> Outcome[SaveData]:
        """保存当前 Case。"""
        with self._guarded():
            data = cases.save_case(self._active_case(), args.path)
        return Outcome(ResultStatus.UPDATED, data)

    def close_case(self, args: CloseCaseArgs) -> Outcome[CloseData]:
        """关闭当前 Case；本来就没有打开的 Case 则什么都不做。"""
        if self._case is None:
            return Outcome(ResultStatus.UNCHANGED, CloseData(path=None))
        with self._guarded():
            path = cases.close_case(self._app(), self._case, args.save)
        self._case = None
        return Outcome(ResultStatus.UPDATED, CloseData(path=path))

    def ensure_thermo(self, args: EnsureThermoArgs) -> Outcome[ThermoData]:
        """确保组分表和物性包就绪。"""
        with self._guarded():
            return ensure_thermo(self._active_case(), args)

    def ensure_reaction(self, args: EnsureReactionArgs) -> Outcome[ReactionData]:
        """确保反应存在。"""
        with self._guarded():
            return ensure_reaction(self._active_case(), args)

    def ensure_reaction_set(self, args: EnsureReactionSetArgs) -> Outcome[ReactionSetData]:
        """确保反应集存在并挂到流体包。"""
        with self._guarded():
            return ensure_reaction_set(self._active_case(), args)

    def ensure_stream(self, args: EnsureStreamArgs) -> Outcome[StreamData]:
        """确保物流或能流存在。"""
        case = self._active_case()
        with self._guarded():
            return ensure_stream(case, flowsheet_of(case), args)

    def ensure_reactor(self, args: EnsureReactorArgs) -> Outcome[ReactorData]:
        """确保反应器存在并连接好。"""
        case = self._active_case()
        with self._guarded():
            return ensure_reactor(case, flowsheet_of(case), args)

    def set_spec(self, args: SetSpecArgs) -> Outcome[SetSpecData]:
        """规定反应器的出口温度或热负荷。"""
        with self._guarded():
            return set_spec(flowsheet_of(self._active_case()), args)

    def solve(self, args: SolveArgs) -> Outcome[SolveData]:
        """确认模型已经求解完成。"""
        with self._guarded():
            return solving.solve(self._active_case(), args)

    def read_snapshot(self, args: ReadSnapshotArgs) -> Outcome[ModelSnapshot]:
        """全量读取模型的状态。"""
        with self._guarded():
            return Outcome(ResultStatus.UNCHANGED, snapshot.read_snapshot(self._active_case()))

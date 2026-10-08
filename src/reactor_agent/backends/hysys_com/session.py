"""连接 HYSYS：启动或接管实例、取得进程号、检查版本、结束自己启动的实例。

构造 Backend 时不连接，连接只发生在 connect 里。进程号靠 tasklist 在连接前后的差集取得（台账 H27）：
新出现的进程就是这次启动的实例。接管的实例可能是用户自己开着的，不能结束。
"""

import csv
import subprocess
import time
from dataclasses import dataclass
from typing import Any

from win32com.client import gencache

from reactor_agent.backends.hysys_com.com_errors import attempt_cleanup, com_call
from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.enums import ConnectMode

NEW_INSTANCE_PROGID = "HYSYS.Application.NewInstance"
SHARED_INSTANCE_PROGID = "HYSYS.Application"
PROCESS_IMAGE = "AspenHysys.exe"
IMAGE_COLUMN = 0
PID_COLUMN = 1
EXPECTED_VERSION_MARKER = "Version 15"
SUBPROCESS_TIMEOUT_S = 30.0
QUIT_WAIT_S = 10.0
QUIT_POLL_S = 0.5


@dataclass(frozen=True)
class Session:
    """一次连接：应用对象、进程号（不确定时是 None）和这个实例是不是复用了已经在运行的。"""

    app: Any
    process_id: int | None
    reused_instance: bool
    version: str


def running_process_ids() -> frozenset[int]:
    """正在运行的 HYSYS 界面进程的进程号。"""
    command = ["tasklist", "/FO", "CSV", "/NH", "/FI", f"IMAGENAME eq {PROCESS_IMAGE}"]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
        timeout=SUBPROCESS_TIMEOUT_S,
    )
    rows = (row for row in csv.reader(result.stdout.splitlines()) if row)
    return frozenset(
        int(row[PID_COLUMN])
        for row in rows
        if len(row) > PID_COLUMN and row[IMAGE_COLUMN].lower() == PROCESS_IMAGE.lower()
    )


def _kill(process_id: int) -> None:
    subprocess.run(
        ["taskkill", "/PID", str(process_id), "/T", "/F"],
        capture_output=True,
        check=False,
        timeout=SUBPROCESS_TIMEOUT_S,
    )


def _locate_process(mode: ConnectMode, before: frozenset[int]) -> tuple[int | None, bool]:
    """连接之后判断进程号和是否复用：新出现的进程是这次启动的，没有新进程说明复用了。"""
    after = running_process_ids()
    launched = sorted(after - before)
    if mode is ConnectMode.LAUNCH:
        if len(launched) != 1:
            raise ReactorAgentError(
                ErrorCode.COM_UNAVAILABLE,
                f"新开实例后没有恰好出现一个新的 {PROCESS_IMAGE} 进程：{launched}",
            )
        return launched[0], False
    if launched:
        return launched[0], False
    return (next(iter(after)) if len(after) == 1 else None), True


def connect(mode: ConnectMode, visible: bool) -> Session:
    """连接 HYSYS。launch 总是新开实例；attach 接管已经在运行的实例，没有就启动一个。"""
    progid = NEW_INSTANCE_PROGID if mode is ConnectMode.LAUNCH else SHARED_INSTANCE_PROGID
    before = running_process_ids()
    with com_call(ErrorCode.COM_UNAVAILABLE, "连接 HYSYS"):
        app = gencache.EnsureDispatch(progid)
        version = str(app.Version)
        app.Visible = visible
    try:
        process_id, reused = _locate_process(mode, before)
    except ReactorAgentError:
        attempt_cleanup(app.Quit)  # 进程号不明，没法按进程号结束，至少让这个实例正常退出
        raise
    session = Session(app, process_id, reused, version)
    if EXPECTED_VERSION_MARKER not in version:
        shutdown(session)
        raise ReactorAgentError(
            ErrorCode.VERSION, f"需要 HYSYS V15，实际是 {version!r}", {"version": version}
        )
    return session


def shutdown(session: Session) -> None:
    """结束自己启动的实例：先正常退出，退不掉再按进程号强制结束。复用的实例不动。"""
    if session.reused_instance:
        return
    attempt_cleanup(session.app.Quit)
    process_id = session.process_id
    if process_id is None:
        return
    deadline = time.monotonic() + QUIT_WAIT_S
    while process_id in running_process_ids() and time.monotonic() < deadline:
        time.sleep(QUIT_POLL_S)
    if process_id in running_process_ids():
        _kill(process_id)

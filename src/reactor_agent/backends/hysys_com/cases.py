"""Case 的创建、打开、保存和关闭。

新建的 Case 路径在 HYSYS 进程的当前目录里（台账 H3），没保存前不能当身份，所以新建后立刻另存。
SaveAs 到不存在的目录既不报错也不写文件（L26），打开不存在的文件报 E_ACCESSDENIED（H2），
所以路径要在入口校验，写完要读回文件。给 HYSYS 的路径一律是长路径（8.3 短路径打不开，H2）。
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reactor_agent.backends.hysys_com.com_errors import com_call
from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.enums import CaseMode, ResultStatus
from reactor_agent.spec.tool_args import EnsureCaseArgs

ILLEGAL_FILENAME_CHARACTERS = frozenset('<>:"/|?*\\')


@dataclass(frozen=True)
class EnsuredCase:
    """case.ensure 的结果：当前的 Case 对象，以及它是新建的、打开的还是本来就在。"""

    case: Any
    status: ResultStatus


def normalize_path(path: Path) -> Path:
    """校验 Case 路径并解析成长路径：目录必须存在，文件名不含非法字符。"""
    if not path.parent.is_dir():
        raise ReactorAgentError(ErrorCode.IO, f"目录不存在：{path.parent}")
    if ILLEGAL_FILENAME_CHARACTERS & set(path.name):
        raise ReactorAgentError(ErrorCode.IO, f"文件名含有非法字符：{path.name}")
    return path.parent.resolve() / path.name


def case_path(case: Any) -> Path:
    """HYSYS 读回的 Case 路径。"""
    with com_call(ErrorCode.READBACK_MISMATCH, "读取 Case 路径"):
        return Path(str(case.FullName))


def _same_path(first: Path, second: Path) -> bool:
    return os.path.normcase(os.path.normpath(first)) == os.path.normcase(os.path.normpath(second))


def _verify_file(path: Path) -> int:
    """文件存在且非空，返回字节数。"""
    if not path.is_file() or path.stat().st_size == 0:
        raise ReactorAgentError(ErrorCode.IO, f"文件没有写出，或者是空的：{path}")
    return path.stat().st_size


def _verify_identity(case: Any, path: Path) -> None:
    actual = case_path(case)
    if not _same_path(actual, path):
        raise ReactorAgentError(
            ErrorCode.READBACK_MISMATCH, f"Case 的路径读回不一致：期望 {path}，实际 {actual}"
        )


def _save_as(case: Any, path: Path) -> int:
    with com_call(ErrorCode.IO, f"另存为 {path}"):
        case.SaveAs(str(path))
    _verify_identity(case, path)
    return _verify_file(path)


def _create(app: Any, path: Path) -> Any:
    if path.exists():
        raise ReactorAgentError(
            ErrorCode.CONFLICT, f"文件已经存在：{path}。新建 Case 要用新的文件名"
        )
    with com_call(ErrorCode.CASE_OPEN, "新建 Case"):
        case = app.SimulationCases.Add(path.stem)
    _save_as(case, path)
    return case


def _open(app: Any, path: Path) -> Any:
    if not path.is_file():
        raise ReactorAgentError(ErrorCode.IO, f"文件不存在：{path}")
    with com_call(ErrorCode.CASE_OPEN, f"打开 {path}"):
        case = app.SimulationCases.Open(str(path))
    _verify_identity(case, path)
    return case


def ensure_case(app: Any, active: Any | None, args: EnsureCaseArgs) -> EnsuredCase:
    """创建或确认 Case。已经有打开的 Case 时，同一个路径不变，另一个路径是冲突。"""
    path = normalize_path(args.path)
    if active is not None:
        opened = case_path(active)
        if _same_path(opened, path):
            return EnsuredCase(active, ResultStatus.UNCHANGED)
        raise ReactorAgentError(
            ErrorCode.CONFLICT, f"已经打开了另一个 Case：{opened}。先关闭它再打开 {path}"
        )
    if args.mode is CaseMode.OPEN:
        return EnsuredCase(_open(app, path), ResultStatus.UPDATED)
    return EnsuredCase(_create(app, path), ResultStatus.CREATED)


def save_case(active: Any, path: Path | None) -> tuple[Path, int]:
    """保存 Case，返回路径和字节数。path 为空时写回当前路径。"""
    if path is None:
        target = case_path(active)
        with com_call(ErrorCode.IO, "保存 Case"):
            active.Save()
        _verify_identity(active, target)
        return target, _verify_file(target)
    target = normalize_path(path)
    return target, _save_as(active, target)


def close_case(active: Any, save: bool) -> Path:
    """关闭 Case（save 为真时先保存），返回被关闭的 Case 的路径。"""
    path = case_path(active)
    if save:
        save_case(active, None)
    with com_call(ErrorCode.CASE_OPEN, "关闭 Case"):
        active.Close()
    return path

"""E1：连接 HYSYS V15，弄清 ProgID、实例复用、进程号和退出方式。

要回答的问题：
  Q1 注册表里 HYSYS 的 ProgID 是什么，通用的和带版本号的各是哪个？
  Q2 HYSYS 已经在运行时，Dispatch 得到的是已有的实例还是新启动的实例？
  Q3 怎样得到这个实例的进程号？用 tasklist 核对。
  Q4 脚本结束时怎样让实例退出，怎样让它留着？

用法：
  python spikes/e1_connect.py                      默认：连接，打印，只退出本次启动的实例
  python spikes/e1_connect.py --progid HYSYS.Application.NewInstance --tag newinstance
  python spikes/e1_connect.py --exit keep|quit|release|kill --tag run1
  python spikes/e1_connect.py --binding early      用 EnsureDispatch（早绑定）

输出：spikes/out/e1_connect_<tag>.txt（UTF-8，由脚本自己写）。
"""

import argparse
import gc
import subprocess
import time
import winreg

import pythoncom
import win32com.client
from _common import (
    EXIT_WAIT_S,
    Log,
    gui_pids,
    hysys_processes,
    hysys_window_pids,
    use_utf8,
    wait_gone,
    watch,
)

use_utf8()

PROGID_PREFIX = "HYSYS.Application"
MEMBERS_TO_TRY = ("Version", "Name", "name", "FullName", "Path", "Visible", "ActiveDocument")


def reg_default(root: int, path: str) -> str | None:
    try:
        with winreg.OpenKey(root, path) as key:
            return str(winreg.QueryValueEx(key, "")[0])
    except OSError:
        return None


def reg_subkeys(root: int, path: str) -> list[str]:
    names: list[str] = []
    try:
        with winreg.OpenKey(root, path) as key:
            i = 0
            while True:
                names.append(winreg.EnumKey(key, i))
                i += 1
    except OSError:
        return names


def report_registry(log: Log) -> None:
    """Q1：列出 HYSYS.Application 开头的 ProgID，以及各 CLSID 的服务器登记。"""
    log.say("== Q1 注册表中的 ProgID ==")
    hkcr = winreg.HKEY_CLASSES_ROOT
    progids = sorted(n for n in reg_subkeys(hkcr, "") if n.startswith(PROGID_PREFIX))
    clsids: dict[str, str] = {}
    for name in progids:
        clsid = reg_default(hkcr, name + r"\CLSID") or "-"
        cur = reg_default(hkcr, name + r"\CurVer") or "-"
        desc = reg_default(hkcr, name) or "-"
        log.say(f"  {name:45} CLSID={clsid}  CurVer={cur}  ({desc})")
        if clsid != "-":
            clsids[clsid] = name
    for clsid, name in clsids.items():
        base = rf"CLSID\{clsid}"
        log.say(f"  -- {name} 的服务器登记 --")
        for sub in reg_subkeys(hkcr, base):
            log.say(f"     {sub} = {reg_default(hkcr, base + chr(92) + sub)}")
        log.say(f"     (AppID 子键的值: {reg_default(hkcr, base + chr(92) + 'AppID')})")


def connect(progid: str, binding: str) -> object:
    if binding == "early":
        return win32com.client.gencache.EnsureDispatch(progid)
    return win32com.client.Dispatch(progid)


def pick_pid(log: Log, new: dict[int, str]) -> int | None:
    """Q3：找出刚连上的实例的界面进程号。有新进程就取新的，否则取窗口所属的进程。"""
    windows = hysys_window_pids()
    gui = gui_pids()
    log.say(f"  tasklist: {hysys_processes()}")
    log.say(f"  可见的 HYSYS 窗口所属进程: {windows}")
    new_gui = [pid for pid in new if pid in gui]
    pid = new_gui[0] if new_gui else next(iter(windows), gui[0] if gui else None)
    log.conclude(
        f"界面进程号 {pid}；新进程中的界面进程 {new_gui}，窗口所属进程 {sorted(windows)}，"
        f"tasklist 中的 AspenHysys.exe {gui}"
    )
    return pid


def do_exit(log: Log, mode: str, holder: list, pid: int | None) -> None:
    """Q4：按指定方式结束或保留实例，并用 tasklist 验证结果。

    holder 里放着唯一的 COM 引用，release 模式要把它真正丢掉。
    """
    log.say(f"== Q4 退出方式: {mode} ==")
    if mode == "keep" or pid is None:
        log.conclude("不做任何退出动作，实例留着")
        return
    if mode == "quit":
        log.attempt("app.Quit()", holder[0].Quit)
    elif mode == "release":
        holder.clear()
        gc.collect()
        pythoncom.CoUninitialize()
        log.say("  已丢掉 COM 引用并 CoUninitialize")
    elif mode == "kill":
        out = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True
        )
        log.say(f"  taskkill: {out.stdout.strip()} {out.stderr.strip()}")
    gone = wait_gone(pid)
    if gone is None:
        log.conclude(f"{mode} 之后 {EXIT_WAIT_S} 秒内进程 {pid} 仍在")
    else:
        log.conclude(f"{mode} 之后进程 {pid} 在 {gone:.1f} 秒内消失")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--progid", default="HYSYS.Application")
    parser.add_argument("--binding", choices=("late", "early"), default="late")
    parser.add_argument("--exit", dest="exit_mode", default="auto")
    parser.add_argument("--tag", default="default")
    args = parser.parse_args()
    log = Log(f"e1_connect_{args.tag}")

    report_registry(log)
    log.say("== Q2 连接前后的 HYSYS 进程 ==")
    before = hysys_processes()
    log.say(f"  连接前: {before or '没有 HYSYS 进程'}")
    start = time.time()
    with watch(log, f"Dispatch({args.progid})"):
        holder = [connect(args.progid, args.binding)]
    log.say(f"  Dispatch({args.progid!r}, {args.binding}) 用时 {time.time() - start:.1f} 秒")
    after = hysys_processes()
    log.say(f"  连接后: {after}")
    new = {pid: name for pid, name in after.items() if pid not in before}
    if before and not new:
        log.conclude("连接前已有 HYSYS 进程，连接后没有新进程：取得的是已有的实例")
    elif new:
        log.conclude(f"连接后出现新进程 {new}：新启动了实例")

    log.say("== 取 Application 的成员 ==")
    log.attempt("type(app)", lambda: f"{type(holder[0]).__module__}.{type(holder[0]).__name__}")
    log.attempt("type(app.SimulationCases)", lambda: type(holder[0].SimulationCases).__name__)
    for name in MEMBERS_TO_TRY:
        log.attempt(f"app.{name}", lambda name=name: getattr(holder[0], name))
    holder[0].Visible = True
    log.attempt("设置 Visible=True 后读回", lambda: holder[0].Visible)

    log.say("== Q3 进程号 ==")
    pid = pick_pid(log, new)

    mode = args.exit_mode
    if mode == "auto":
        mode = "quit" if new else "keep"
    do_exit(log, mode, holder, pid)
    log.say(f"  结束时的 HYSYS 进程: {hysys_processes() or '无'}")


if __name__ == "__main__":
    main()

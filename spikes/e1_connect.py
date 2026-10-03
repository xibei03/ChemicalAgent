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
import csv
import gc
import subprocess
import sys
import time
import winreg
from pathlib import Path

import pythoncom
import win32com.client
import win32gui
import win32process

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

OUT_DIR = Path(__file__).resolve().parent / "out"
PROGID_PREFIX = "HYSYS.Application"
# 和 HYSYS 有关的进程映像名（小写）。AspenHysys.exe 是界面进程。
HYSYS_IMAGES = ("aspenhysys.exe", "hysyssvr.exe", "hysysengine.exe", "aspenhysysreportwriter.exe")
MEMBERS_TO_TRY = ("Version", "Name", "FullName", "Path", "Visible", "ActiveDocument")
EXIT_WAIT_S = 60

LOG: list[str] = []


def say(text: str = "") -> None:
    """打印并记入输出文件。"""
    print(text, flush=True)
    LOG.append(text)


def conclude(text: str) -> None:
    say(f"结论: {text}")


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


def report_registry() -> None:
    """Q1：列出 HYSYS.Application 开头的 ProgID，以及各 CLSID 的服务器登记。"""
    say("== Q1 注册表中的 ProgID ==")
    hkcr = winreg.HKEY_CLASSES_ROOT
    progids = sorted(n for n in reg_subkeys(hkcr, "") if n.startswith(PROGID_PREFIX))
    clsids: dict[str, str] = {}
    for name in progids:
        clsid = reg_default(hkcr, name + r"\CLSID") or "-"
        cur = reg_default(hkcr, name + r"\CurVer") or "-"
        desc = reg_default(hkcr, name) or "-"
        say(f"  {name:45} CLSID={clsid}  CurVer={cur}  ({desc})")
        if clsid != "-":
            clsids[clsid] = name
    for clsid, name in clsids.items():
        base = rf"CLSID\{clsid}"
        say(f"  -- {name} 的服务器登记 --")
        for sub in reg_subkeys(hkcr, base):
            say(f"     {sub} = {reg_default(hkcr, base + chr(92) + sub)}")
        app_id = reg_default(hkcr, base + r"\AppID")
        say(f"     (AppID 子键的值: {app_id})")


def hysys_processes() -> dict[int, str]:
    """用 tasklist 取得 HYSYS 相关进程：{进程号: 映像名}。"""
    result = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, errors="replace"
    )
    found: dict[int, str] = {}
    for row in csv.reader(result.stdout.splitlines()):
        if len(row) >= 2 and row[0].lower() in HYSYS_IMAGES:
            found[int(row[1])] = row[0]
    return found


def window_pids() -> dict[int, str]:
    """可见的、标题含 HYSYS 的顶层窗口所属的进程号：{进程号: 窗口标题}。"""
    found: dict[int, str] = {}

    def visit(hwnd: int, _extra: object) -> None:
        title = win32gui.GetWindowText(hwnd)
        if win32gui.IsWindowVisible(hwnd) and "hysys" in title.lower():
            found[win32process.GetWindowThreadProcessId(hwnd)[1]] = title

    win32gui.EnumWindows(visit, None)
    return found


def describe_app(app) -> None:
    say("== 取 Application 的成员（晚绑定下逐个试） ==")
    for name in MEMBERS_TO_TRY:
        try:
            say(f"  app.{name} = {getattr(app, name)!r}")
        except Exception as exc:  # 探针：任何失败都要记录下来，而不是中断
            say(f"  app.{name} 失败: {type(exc).__name__}: {exc}")


def connect(progid: str, binding: str):
    if binding == "early":
        return win32com.client.gencache.EnsureDispatch(progid)
    return win32com.client.Dispatch(progid)


def wait_gone(pid: int) -> float | None:
    """等进程消失，返回用时；超时返回 None。"""
    start = time.time()
    while time.time() - start < EXIT_WAIT_S:
        if pid not in hysys_processes():
            return time.time() - start
        time.sleep(0.5)
    return None


def do_exit(mode: str, app, pid: int | None) -> None:
    """Q4：按指定方式结束或保留实例，并用 tasklist 验证结果。"""
    say(f"== Q4 退出方式: {mode} ==")
    if mode == "keep" or pid is None:
        conclude("不做任何退出动作，实例留着")
        return
    if mode == "quit":
        try:
            app.Quit()
        except Exception as exc:  # 探针：记录失败原因
            say(f"  app.Quit() 失败: {type(exc).__name__}: {exc}")
    elif mode == "release":
        del app
        gc.collect()
        pythoncom.CoUninitialize()
    elif mode == "kill":
        out = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True
        )
        say(f"  taskkill: {out.stdout.strip()} {out.stderr.strip()}")
    gone = wait_gone(pid)
    if gone is None:
        conclude(f"{mode} 之后 {EXIT_WAIT_S} 秒内进程 {pid} 仍在")
    else:
        conclude(f"{mode} 之后进程 {pid} 在 {gone:.1f} 秒内消失")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--progid", default="HYSYS.Application")
    parser.add_argument("--binding", choices=("late", "early"), default="late")
    parser.add_argument("--exit", dest="exit_mode", default="auto")
    parser.add_argument("--tag", default="default")
    args = parser.parse_args()

    report_registry()
    say("== Q2 连接前后的 HYSYS 进程 ==")
    before = hysys_processes()
    say(f"  连接前: {before or '没有 HYSYS 进程'}")
    start = time.time()
    app = connect(args.progid, args.binding)
    say(f"  Dispatch({args.progid!r}, {args.binding}) 用时 {time.time() - start:.1f} 秒")
    after = hysys_processes()
    say(f"  连接后: {after}")
    new = {pid: name for pid, name in after.items() if pid not in before}
    if before and not new:
        conclude("连接前已有 HYSYS 进程，连接后没有新进程：取得的是已有的实例")
    elif new:
        conclude(f"连接后出现新进程 {new}：新启动了实例")

    describe_app(app)
    try:
        app.Visible = True
        say(f"  设置 Visible=True 后读回: {app.Visible}")
    except Exception as exc:  # 探针：记录失败原因
        say(f"  设置 Visible 失败: {type(exc).__name__}: {exc}")

    say("== Q3 进程号 ==")
    say(f"  tasklist: {hysys_processes()}")
    windows = window_pids()
    say(f"  可见的 HYSYS 窗口所属进程: {windows}")
    gui = [pid for pid, name in hysys_processes().items() if name.lower() == "aspenhysys.exe"]
    pid = next(iter(windows), gui[0] if gui else None)
    conclude(
        f"界面进程号 {pid}；窗口所属进程 {sorted(windows)}，tasklist 中的 AspenHysys.exe {gui}"
    )

    mode = args.exit_mode
    if mode == "auto":
        mode = "quit" if new else "keep"
    do_exit(mode, app, pid)
    say(f"  结束时的 HYSYS 进程: {hysys_processes() or '无'}")

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / f"e1_connect_{args.tag}.txt").write_text("\n".join(LOG) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

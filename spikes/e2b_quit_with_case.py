"""E2b：HYSYS 里有打开的 Case 时，Quit() 和 Close() 会不会弹窗？

要回答的问题：
  Q1 Case 没有改过时，直接 app.Quit() 会弹窗吗？进程在多久之内消失？
  Q2 Case 改过（IsDirty）时，case.Close() 会弹窗吗？弹窗上写什么、有哪些按钮？
  Q3 Case 改过时，app.Quit() 会弹窗吗？
  Q4 弹窗能不能用 Win32 点按钮的办法关掉，让被阻塞的 COM 调用继续返回？
做法：每种情况各用一个 NewInstance 打开示例的副本。主线程调用可能阻塞的 COM 方法，
另一个线程在 8 秒后读出弹窗文字和按钮，并点名字像"否/No"的按钮。
找不到按钮就记下来，由主线程超时后按进程号结束。全程不保存。

用法：python spikes/e2b_quit_with_case.py
输出：spikes/out/e2b_quit_with_case.txt
"""

import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import win32api
import win32com.client
import win32con
import win32gui
from _common import Log, child_texts, hysys_processes, use_utf8, wait_gone, windows_of

use_utf8()

INSTALL_DIR = Path(r"C:\Program Files\AspenTech\Aspen HYSYS V15.0")
SAMPLE = INSTALL_DIR / "Samples" / "Synthesis Gas Production.hsc"
DIALOG_DELAY_S = 8.0
GIVE_UP_S = 40.0
DECLINE_WORDS = ("no", "否", "不", "don't")


def buttons_of(hwnd: int) -> list[tuple[int, str]]:
    """对话框里所有按钮：[(句柄, 文字)]。"""
    found: list[tuple[int, str]] = []

    def visit(child: int, _extra: object) -> None:
        if win32gui.GetClassName(child) == "Button":
            found.append((child, win32gui.GetWindowText(child)))

    win32gui.EnumChildWindows(hwnd, visit, None)
    return found


def dismiss_dialog_later(log: Log, pid: int, results: list[str]) -> threading.Thread:
    """在后台线程里等一会儿，读出弹窗并点"否"一类的按钮。"""

    def work() -> None:
        time.sleep(DIALOG_DELAY_S)
        dialogs = [w for w in windows_of([pid]) if w.visible and w.class_name == "#32770"]
        if not dialogs:
            results.append("没有弹窗")
            return
        for dialog in dialogs:
            labels = buttons_of(dialog.hwnd)
            log.say(f"    弹窗 标题={dialog.title!r} 文字={child_texts(dialog.hwnd)} 按钮={labels}")
            results.append(f"弹窗 {dialog.title!r} 按钮 {[t for _, t in labels]}")
            pick = next(
                (
                    h
                    for h, t in labels
                    if any(w in t.replace("&", "").lower() for w in DECLINE_WORDS)
                ),
                None,
            )
            if pick is None:
                results.append("没有找到否定按钮")
                continue
            win32gui.PostMessage(pick, win32con.BM_CLICK, 0, 0)
            results.append("已点否定按钮")

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    return thread


def run_case(log: Log, label: str, modify: bool, action: str) -> None:
    log.say(f"== {label} ==")
    before = hysys_processes()
    app = win32com.client.gencache.EnsureDispatch("HYSYS.Application.NewInstance")
    pid = next((p for p in hysys_processes() if p not in before), None)
    app.Visible = True
    scratch = Path(tempfile.mkdtemp(prefix="hysys_e2b_")).resolve()
    copy = scratch / SAMPLE.name
    shutil.copyfile(SAMPLE, copy)
    case = app.SimulationCases.Open(str(copy))
    log.say(f"  实例 {pid}，已打开 {case.FullName}")
    if modify:
        stream = case.Flowsheet.MaterialStreams.Item("Natural Gas")
        value = stream.Temperature.GetValue("C")
        stream.Temperature.SetValue(value + 1.0, "C")
    log.attempt("case.IsDirty", lambda: case.IsDirty)
    results: list[str] = []
    helper = dismiss_dialog_later(log, pid, results)
    start = time.time()
    # COM 调用必须在创建对象的线程里执行：主线程调用，弹窗由后台线程处理
    ok, _ = log.attempt(action, case.Close if action == "case.Close()" else app.Quit)
    outcome = "返回" if ok else "抛异常"
    log.say(f"  {action} 用时 {time.time() - start:.1f} 秒，{outcome}")
    helper.join(timeout=1)
    log.say(f"  弹窗情况: {results or '没有记录'}")
    if pid is not None:
        gone = wait_gone(pid, timeout_s=10)
        if gone is None:
            log.say(f"  实例 {pid} 仍在运行，按进程号结束")
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
            wait_gone(pid, timeout_s=10)
        else:
            log.say(f"  实例 {pid} 在 {gone:.1f} 秒内退出")
    shutil.rmtree(scratch, ignore_errors=True)
    win32api.Sleep(500)


def main() -> None:
    log = Log("e2b_quit_with_case")
    run_case(log, "Q1 没改过的 Case，直接 Quit", modify=False, action="app.Quit()")
    run_case(log, "Q2 改过的 Case，先 Close", modify=True, action="case.Close()")
    run_case(log, "Q3 改过的 Case，直接 Quit", modify=True, action="app.Quit()")
    log.say(f"结束时的 HYSYS 进程: {hysys_processes() or '无'}")


if __name__ == "__main__":
    main()

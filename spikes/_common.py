"""探针共用的小工具：UTF-8 输出、边打印边落盘的日志、HYSYS 进程和窗口检测。

每个探针仍然可以单独运行（`python spikes/xxx.py`）。探针和本模块在同一个目录，
直接 `from _common import ...` 即可。只放三个以上探针都会用到的东西。
"""

import csv
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import win32gui
import win32process

OUT_DIR = Path(__file__).resolve().parent / "out"
HYSYS_IMAGES = ("aspenhysys.exe", "hysyssvr.exe", "hysysengine.exe", "aspenhysysreportwriter.exe")
GUI_IMAGE = "aspenhysys.exe"
EXIT_WAIT_S = 60


def use_utf8() -> None:
    """把标准输出和标准错误设成 UTF-8，管道接走时不受系统代码页影响。"""
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


class Log:
    """打印的同时追加写入 spikes/out/<name>.txt，脚本中途卡住或被杀也留得下已有的输出。"""

    def __init__(self, name: str) -> None:
        OUT_DIR.mkdir(exist_ok=True)
        self.path = OUT_DIR / f"{name}.txt"
        self.path.write_text("", encoding="utf-8")

    def say(self, text: str = "") -> None:
        print(text, flush=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(text + "\n")

    def conclude(self, text: str) -> None:
        self.say(f"结论: {text}")

    def attempt(self, label: str, call: Callable[[], object]) -> tuple[bool, object]:
        """试一次调用，成功和失败都记下来。探针里任何失败都是有用的信息，不能中断脚本。"""
        try:
            value = call()
        except Exception as exc:  # 探针：失败原因本身就是要记录的结果
            self.say(f"  {label} -> 失败 {type(exc).__name__}: {exc}")
            return False, None
        self.say(f"  {label} -> {value!r}")
        return True, value


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


def gui_pids() -> list[int]:
    """界面进程 AspenHysys.exe 的进程号。"""
    return [pid for pid, name in hysys_processes().items() if name.lower() == GUI_IMAGE]


def wait_gone(pid: int, timeout_s: float = EXIT_WAIT_S) -> float | None:
    """等进程消失，返回用时；超时返回 None。"""
    start = time.time()
    while time.time() - start < timeout_s:
        if pid not in hysys_processes():
            return time.time() - start
        time.sleep(0.5)
    return None


@dataclass(frozen=True)
class WindowInfo:
    """一个顶层窗口。弹窗多半是类名 #32770 的顶层窗口。"""

    hwnd: int
    pid: int
    class_name: str
    title: str
    visible: bool


def windows_of(pids: Iterable[int]) -> list[WindowInfo]:
    """属于指定进程的全部顶层窗口。"""
    wanted = set(pids)
    found: list[WindowInfo] = []

    def visit(hwnd: int, _extra: object) -> None:
        pid = win32process.GetWindowThreadProcessId(hwnd)[1]
        if pid in wanted:
            found.append(
                WindowInfo(
                    hwnd,
                    pid,
                    win32gui.GetClassName(hwnd),
                    win32gui.GetWindowText(hwnd),
                    bool(win32gui.IsWindowVisible(hwnd)),
                )
            )

    win32gui.EnumWindows(visit, None)
    return found


def child_texts(hwnd: int) -> list[str]:
    """窗口里所有有文字的子控件，用来读弹窗的提示文字。"""
    texts: list[str] = []

    def visit(child: int, _extra: object) -> None:
        text = win32gui.GetWindowText(child)
        if text:
            texts.append(f"{win32gui.GetClassName(child)}: {text}")

    win32gui.EnumChildWindows(hwnd, visit, None)
    return texts


def hysys_window_pids() -> dict[int, str]:
    """可见的、标题含 hysys 的顶层窗口所属的进程号：{进程号: 窗口标题}。"""
    return {
        w.pid: w.title
        for w in windows_of(list(hysys_processes()))
        if w.visible and "hysys" in w.title.lower()
    }


def describe_windows(log: Log) -> None:
    """列出 HYSYS 进程的可见顶层窗口和弹窗的文字。"""
    shown = [w for w in windows_of(list(hysys_processes())) if w.visible and w.title]
    if not shown:
        log.say("    （HYSYS 进程没有带标题的可见窗口）")
    for w in shown:
        log.say(f"    窗口 pid={w.pid} 类名={w.class_name!r} 标题={w.title!r}")
        for text in child_texts(w.hwnd)[:8]:
            log.say(f"        控件 {text}")


@contextmanager
def watch(log: Log, label: str, seconds: float = 45.0) -> Iterator[None]:
    """一次调用超过 seconds 秒还没返回时，打印 HYSYS 的窗口，用来找阻塞的模态弹窗。"""

    def report() -> None:
        log.say(f"  [看门狗] {label} 已超过 {seconds:.0f} 秒没有返回，HYSYS 窗口如下：")
        describe_windows(log)

    timer = threading.Timer(seconds, report)
    timer.daemon = True
    timer.start()
    try:
        yield
    finally:
        timer.cancel()

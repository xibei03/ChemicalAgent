"""弹窗看门狗（D12 批准的唯一线程）。

HYSYS 的模态对话框会让 COM 调用一直不返回（台账 H23、L24、L26）。守护线程每隔一会儿枚举 HYSYS 进程的
对话框，记下文字，点“确定”让被卡住的调用返回。线程只调用 Win32，不碰任何 COM 对象；其余代码仍然是
同步、单线程的。对话框文字记在 messages 里，调用结束后可以据此判断刚才的调用有没有触发弹窗。
"""

import logging
import threading
import time

import pywintypes
import win32con
import win32gui
import win32process

logger = logging.getLogger(__name__)

DIALOG_CLASS = "#32770"
STATIC_CLASS = "Static"
BUTTON_CLASS = "Button"
POLL_INTERVAL_S = 0.5
# 同一个对话框点过之后多久内不再点：HYSYS 有时会在点击后接着弹同一个窗口，连点没有用。
CLICK_COOLDOWN_S = 5.0
STOP_WAIT_S = 2.0
AFFIRMATIVE_BUTTONS = ("ok", "确定", "yes", "是")
# 台账里见过的对话框文字片段（H23、L24、L26）。见到别的文字也会点，但记成未知弹窗。
KNOWN_DIALOGS = (
    "Aspen Properties in HYSYS",
    "is not the correct type to attach",
    "operates at an adiabatic condition",
    "Duplicate Object Name",
)


def _dialogs_of(process_id: int) -> list[int]:
    """属于该进程的所有对话框窗口（含不可见的：窗口隐藏的实例里弹窗可能不可见）。"""
    found: list[int] = []

    def visit(hwnd: int, _extra: object) -> None:
        owner = win32process.GetWindowThreadProcessId(hwnd)[1]
        if owner == process_id and win32gui.GetClassName(hwnd) == DIALOG_CLASS:
            found.append(hwnd)

    win32gui.EnumWindows(visit, None)
    return found


def _children(hwnd: int, class_name: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []

    def visit(child: int, _extra: object) -> None:
        if win32gui.GetClassName(child) == class_name:
            found.append((child, win32gui.GetWindowText(child)))

    win32gui.EnumChildWindows(hwnd, visit, None)
    return found


def _click_affirmative(hwnd: int) -> bool:
    for button, text in _children(hwnd, BUTTON_CLASS):
        if text.replace("&", "").strip().lower() in AFFIRMATIVE_BUTTONS:
            win32gui.PostMessage(button, win32con.BM_CLICK, 0, 0)
            return True
    return False


class DialogGuard:
    """盯着一个 HYSYS 进程的对话框的守护线程。"""

    def __init__(self) -> None:
        self.messages: list[str] = []
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, process_id: int) -> None:
        """开始盯这个进程。已经在盯时先停掉旧的。"""
        self.stop()
        self._stopped.clear()
        self._thread = threading.Thread(target=self._watch, args=(process_id,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止线程。"""
        self._stopped.set()
        if self._thread is not None:
            self._thread.join(timeout=STOP_WAIT_S)
            self._thread = None

    def _watch(self, process_id: int) -> None:
        last_click: dict[int, float] = {}
        while not self._stopped.wait(POLL_INTERVAL_S):
            try:
                windows = _dialogs_of(process_id)
            except pywintypes.error:
                continue  # 枚举窗口时窗口刚好关闭，下一轮再看
            for hwnd in windows:
                if time.monotonic() - last_click.get(hwnd, -CLICK_COOLDOWN_S) >= CLICK_COOLDOWN_S:
                    last_click[hwnd] = time.monotonic()
                    self._handle(hwnd)

    def _handle(self, hwnd: int) -> None:
        try:
            text = " | ".join(label for _, label in _children(hwnd, STATIC_CLASS) if label)
            clicked = _click_affirmative(hwnd)
        except pywintypes.error:
            return  # 读文字或点击时对话框已经被关掉，目的达到了
        self.messages.append(text)
        known = any(fragment in text for fragment in KNOWN_DIALOGS)
        level = logging.INFO if known else logging.WARNING
        logger.log(level, "HYSYS 弹窗 %r，已点确定=%s，已知弹窗=%s", text, clicked, known)

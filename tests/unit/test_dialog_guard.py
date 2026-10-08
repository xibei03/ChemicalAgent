"""弹窗看门狗：用一个真实的 Win32 模态对话框检查它能读出文字、点“确定”让被卡住的进程继续。"""

import subprocess
import sys

import pytest

from reactor_agent.backends.hysys_com.dialogs import DialogGuard

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="需要 Win32 对话框")

DIALOG_TEXT = "Duplicate Object Name: Basis-1 - Creating New Object Basis-2"
# 虚拟环境里的 python.exe 是个启动器，真正的解释器是它的子进程，对话框属于后者，
# 所以让子进程自己报出进程号。
SHOW_DIALOG = (
    "import ctypes, os; print(os.getpid(), flush=True); "
    f"ctypes.windll.user32.MessageBoxW(0, {DIALOG_TEXT!r}, 'HYSYS', 0)"
)
WAIT_FOR_DIALOG_S = 20


def test_modal_dialog_is_dismissed_and_its_text_recorded():
    process = subprocess.Popen(
        [sys.executable, "-c", SHOW_DIALOG], stdout=subprocess.PIPE, text=True
    )
    assert process.stdout is not None
    guard = DialogGuard()
    guard.start(int(process.stdout.readline()))
    try:
        assert process.wait(timeout=WAIT_FOR_DIALOG_S) == 0
    finally:
        guard.stop()
        if process.poll() is None:
            process.kill()
    assert guard.messages == [DIALOG_TEXT]


def test_guard_can_be_stopped_when_nothing_ever_happens():
    guard = DialogGuard()
    guard.start(process_id=0)
    guard.stop()
    guard.stop()
    assert guard.messages == []

"""E13a（0C 任务 5）：备选路线之一，界面自动化。最小任务：在空白 Case 里加一台转化反应器。

用 pywinauto（只装在虚拟环境里，没有写进 pyproject.toml）的 UIA 后端导出 HYSYS 主窗口的控件树，
看反应器相关的界面元素能不能被程序定位和操作，再试着只靠界面把一台转化反应器加进流程图，
最后用 COM 读 Operations.Names 验证有没有真的加上。每一步记耗时。

要回答的问题（对照主路线 COM，各记四项：是否可行、耗时、可重复性、结果能否由程序验证）：
  Q1 主窗口的控件树能导出多少个元素？哪些类型？有没有反应器相关的元素？
  Q2 能不能靠界面（快捷键、面板、对话框）把转化反应器加进去？
  Q3 加上之后，结果能不能由程序验证（COM 读回）？

用法：python spikes/e13a_ui_automation.py [--tag 名字]
输出：spikes/out/e13a_ui_automation_<tag>.txt
"""

import argparse
import collections
import time
import traceback

from _common import Log, describe_windows, new_instance, use_utf8, windows_of
from chain_kit import new_case_with_basis
from pywinauto import Application, keyboard

use_utf8()

TREE_LIMIT = 6000
KEYWORDS = (
    "reactor",
    "conversion",
    "palette",
    "unit op",
    "flowsheet",
    "pfd",
    "object",
    "simulation",
)
DESCENDANT_TIMEOUT_S = 240.0
COMPONENTS = ("Toluene", "Benzene", "p-Xylene")


def element_row(element) -> tuple[str, str, str, str]:
    info = element.element_info
    return (str(info.control_type), str(info.name), str(info.automation_id), str(info.class_name))


def dump_tree(log: Log, window, label: str) -> list[tuple[str, str, str, str]]:
    """导出一个窗口的全部后代元素，打印类型统计和反应器相关的元素。"""
    start = time.time()
    elements = window.descendants()
    seconds = time.time() - start
    rows = [element_row(e) for e in elements[:TREE_LIMIT]]
    log.say(
        f"  [{label}] 后代元素 {len(elements)} 个（记录前 {len(rows)} 个），"
        f"导出用时 {seconds:.1f} 秒"
    )
    counts = collections.Counter(row[0] for row in rows)
    log.say(f"      控件类型统计 {dict(counts.most_common(12))}")
    hits = [row for row in rows if any(k in row[1].lower() for k in KEYWORDS)]
    log.say(f"      名字含 {KEYWORDS} 的元素 {len(hits)} 个")
    for row in hits[:25]:
        log.say(f"        {row}")
    named = [row for row in rows if row[1]]
    log.say(f"      有名字的元素 {len(named)} 个；前 25 个：")
    for row in named[:25]:
        log.say(f"        {row}")
    return rows


REACTOR_WORDS = (
    "conversion",
    "equilibrium",
    "gibbs",
    "cstr",
    "plug",
    "reactor",
    "yield",
    "kinetic",
)


def names_like(window, words: tuple[str, ...], limit: int = 40) -> list[tuple[str, str, str, str]]:
    """主窗口里名字含指定词的元素。"""
    rows = [element_row(e) for e in window.descendants()]
    return [row for row in rows if any(w in row[1].lower() for w in words)][:limit]


def by_automation_id(window, automation_id: str, control_type: str) -> list:
    """按自动化 ID 找元素（pywinauto 0.6.9 的 descendants 不支持按 ID 过滤）。"""
    return [
        e
        for e in window.descendants(control_type=control_type)
        if e.element_info.automation_id == automation_id
    ]


def place_reactor(log: Log, main_window, flowsheet) -> None:
    """按自动化 ID 找到 ConversionReactor 按钮，先双击，再拖到流程图上，用 COM 读回有没有加上。"""
    buttons = by_automation_id(main_window, "ConversionReactor", "Button")
    log.say(f"  自动化 ID 为 ConversionReactor 的按钮 {len(buttons)} 个")
    if not buttons:
        return
    button = buttons[0]
    canvases = by_automation_id(main_window, "_AnonymousScreen1", "Custom")
    log.say(f"  流程图画布（Flowsheet Case 的 ContentPane）{len(canvases)} 个")
    for label, action in (
        ("双击按钮", lambda: button.double_click_input()),
        ("拖到画布中央", lambda: drag_to_center(button, canvases)),
    ):
        before = list(flowsheet.Operations.Names)
        start = time.time()
        try:
            action()
        except Exception as exc:  # 探针：界面操作失败的原因就是要记录的结果
            log.say(f"  {label} 失败 {type(exc).__name__}: {exc}")
            continue
        time.sleep(3.0)
        after = list(flowsheet.Operations.Names)
        log.say(f"  {label}：用时 {time.time() - start:.1f} 秒；COM 读回操作 {before} -> {after}")
        if after != before:
            log.attempt(
                "  新操作的 TypeName",
                lambda after=after: flowsheet.Operations.Item(after[-1]).TypeName,
            )
            break


def drag_to_center(button, canvases) -> None:
    """把按钮拖到画布矩形的中央。"""
    if not canvases:
        raise RuntimeError("找不到流程图画布")
    rect = canvases[0].rectangle()
    target = ((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
    button.drag_mouse_input(dst=target)


def try_palette(log: Log, main_window, flowsheet) -> None:
    """Q2：靠 Model Palette 把转化反应器加进流程图：先点 Reactor 页签，再双击转化反应器。"""
    log.say("== Q2 靠界面加转化反应器：Model Palette 的 Reactor 页签 ==")
    tabs = main_window.descendants(title="Reactor", control_type="TabItem")
    log.say(f"  名叫 Reactor 的页签 {len(tabs)} 个")
    if not tabs:
        return
    start = time.time()
    tabs[0].click_input()
    time.sleep(1.5)
    items = names_like(main_window, REACTOR_WORDS)
    log.say(
        f"  点开页签后，名字含反应器关键词的元素 {len(items)} 个"
        f"（用时 {time.time() - start:.1f} 秒）："
    )
    for row in items:
        log.say(f"      {row}")
    palette = main_window.descendants(title="Model Palette", control_type="Window")
    if palette:
        log.say("  Model Palette 窗口里的全部元素（类型, 名字, 自动化 ID, 类名, 矩形）：")
        elements = palette[0].descendants()
        log.say(f"      共 {len(elements)} 个")
        for element in elements[:120]:
            info = element.element_info
            log.say(f"      {element_row(element)} {info.rectangle}")
    place_reactor(log, main_window, flowsheet)
    describe_windows(log)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    args = parser.parse_args()
    log = Log(f"e13a_ui_automation_{args.tag}")
    try:
        with new_instance(log, visible=True) as (app, pid):
            basis = new_case_with_basis(app, "e13a", COMPONENTS)
            basis.manager.EndBasisChange()
            flowsheet = basis.case.Flowsheet
            log.say(f"  COM 建好空白 Case（只有 Basis）；操作 {list(flowsheet.Operations.Names)}")
            log.attempt("  case.Visible（COM 新建的 Case 默认值）", lambda: basis.case.Visible)
            log.attempt("  case.Visible = True", lambda: setattr(basis.case, "Visible", True))
            time.sleep(3.0)
            log.attempt("  case.Visible（设置之后）", lambda: basis.case.Visible)
            log.say("== Q1 控件树 ==")
            describe_windows(log)
            start = time.time()
            ui = Application(backend="uia").connect(process=pid, timeout=30)
            log.say(f"  pywinauto 连接用时 {time.time() - start:.1f} 秒")
            windows = ui.windows()
            log.say(
                f"  UIA 顶层窗口 {[(w.window_text(), w.friendly_class_name()) for w in windows]}"
            )
            main_window = max(windows, key=lambda w: w.rectangle().width() * w.rectangle().height())
            log.say(f"  主窗口 {main_window.window_text()!r} 矩形 {main_window.rectangle()}")
            dump_tree(log, main_window, "主窗口")
            log.say("== Q2 靠界面加转化反应器：F12（Unit Ops） ==")
            main_window.set_focus()
            if not main_window.descendants(title="Reactor", control_type="TabItem"):
                log.say("  Model Palette 没有显示，按 F12 打开")
                keyboard.send_keys("{F12}")
                time.sleep(2.0)
            after = [w for w in windows_of([pid]) if w.visible and w.title]
            log.say(f"  可见窗口 {[(w.title, w.class_name) for w in after]}")
            try_palette(log, main_window, flowsheet)
            log.say("== Q3 COM 读回 ==")
            log.say(f"  操作 {list(flowsheet.Operations.Names)}")
    except Exception:  # 探针：任何失败都要连同堆栈记进日志
        log.say(traceback.format_exc())
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

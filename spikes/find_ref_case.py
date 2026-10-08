"""任务 7：在 HYSYS 自带的示例里找含反应器的 Case，顺带看 COM 对象的第一手样子。

要回答的问题：
  Q1 哪些示例含转化、平衡、Gibbs 反应器？它们的 TypeName 字符串是什么？
  Q2 打开 Case 之后得到的对象是什么类型？集合的 Count、Item 下标从几开始？
  Q3 哪个示例适合做反向探测的参考 Case？

做法：把示例复制到临时目录，用新开的 HYSYS 实例（NewInstance）打开，枚举单元操作
（含子流程图），不保存，关闭。全程限时 20 分钟，卡住时看门狗会打印 HYSYS 的窗口。

用法：python spikes/find_ref_case.py [--tag 名字] [示例相对安装目录的路径 ...]
输出：spikes/out/find_ref_case_<tag>.txt
"""

import argparse
import shutil
import stat
import tempfile
import time
from pathlib import Path

import win32com.client
from _common import Log, hysys_processes, use_utf8, wait_gone, watch

use_utf8()

INSTALL_DIR = Path(r"C:\Program Files\AspenTech\Aspen HYSYS V15.0")
DEFAULT_CANDIDATES = (
    "Samples/Synthesis Gas Production.hsc",
    "Samples/Ammonia Synthesis.hsc",
    "Samples/CSTR - Dynamic Model.hsc",
    "Samples/Ethanol Dehydration.hsc",
    "Samples/Refining Cases/MB Examples/Toluene_Disproportionation_Example.hsc",
)
TIME_BOX_S = 20 * 60
MAX_SUBFLOWSHEET_DEPTH = 3


def first_ok(log: Log, label: str, *calls):
    """依次试几种写法，返回第一个成功的结果；都失败返回 None。"""
    for call in calls:
        ok, value = log.attempt(label, call)
        if ok:
            return value
    return None


def list_items(log: Log, label: str, collection) -> list:
    """取出集合的全部元素。先试 Count 加 Item(i)，下标从 0 开始。"""
    ok, count = log.attempt(f"{label}.Count", lambda: collection.Count)
    if not ok:
        return []
    items = []
    for i in range(int(count)):
        ok, item = log.attempt(f"{label}.Item({i})", lambda i=i: collection.Item(i))
        if ok:
            items.append(item)
    return items


def describe_operation(log: Log, op, flowsheet_name: str) -> tuple[str, str]:
    name = first_ok(log, "op.name", lambda: op.name, lambda: op.Name)
    type_name = first_ok(log, "op.TypeName", lambda: op.TypeName)
    visible = first_ok(log, "op.VisibleTypeName", lambda: op.VisibleTypeName)
    log.say(f"      [{flowsheet_name}] {name!r:30} TypeName={type_name!r}  Visible={visible!r}")
    return str(name), str(type_name)


def walk_flowsheet(log: Log, flowsheet, flowsheet_name: str, depth: int) -> list[tuple[str, str]]:
    """列出一个流程图（以及子流程图）里的全部单元操作：[(名字, TypeName)]。"""
    found: list[tuple[str, str]] = []
    operations = first_ok(
        log, "flowsheet.Operations", lambda: flowsheet.Operations, lambda: flowsheet.Operations()
    )
    if operations is not None:
        log.attempt("Operations.Names", lambda: list(operations.Names))
        for op in list_items(log, "Operations", operations):
            found.append(describe_operation(log, op, flowsheet_name))
    if depth >= MAX_SUBFLOWSHEET_DEPTH:
        return found
    subs = first_ok(log, "flowsheet.Flowsheets", lambda: flowsheet.Flowsheets)
    if subs is None:
        return found
    for sub in list_items(log, "Flowsheets", subs):
        sub_name = first_ok(log, "sub.name", lambda sub=sub: sub.name) or "?"
        found += walk_flowsheet(log, sub, f"{flowsheet_name}/{sub_name}", depth + 1)
    return found


def inspect_case(log: Log, app, source: Path, scratch: Path) -> None:
    copy = scratch / source.name
    shutil.copyfile(source, copy)
    copy.chmod(stat.S_IREAD | stat.S_IWRITE)
    log.say(f"== {source.name}（{source.stat().st_size // 1024} KB），复制到 {copy} ==")
    start = time.time()
    with watch(log, f"Open({source.name})"):
        ok, case = log.attempt("SimulationCases.Open", lambda: app.SimulationCases.Open(str(copy)))
    log.say(
        f"  Open 用时 {time.time() - start:.1f} 秒，对象类型 {type(case).__name__ if ok else '-'}"
    )
    if not ok:
        return
    log.attempt("ActiveDocument 是同一个 Case 吗", lambda: app.ActiveDocument.FullName)
    log.attempt("case.FullName", lambda: case.FullName)
    flowsheet = first_ok(log, "case.Flowsheet", lambda: case.Flowsheet)
    ops = walk_flowsheet(log, flowsheet, "主流程图", 0) if flowsheet is not None else []
    reactors = [(n, t) for n, t in ops if "react" in t.lower() or "gibbs" in t.lower()]
    log.conclude(f"{source.name}：共 {len(ops)} 个单元操作；反应器类 {reactors or '没有'}")
    log.attempt("case.Close", lambda: case.Close())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="default")
    parser.add_argument("cases", nargs="*")
    args = parser.parse_args()
    log = Log(f"find_ref_case_{args.tag}")
    names = args.cases or list(DEFAULT_CANDIDATES)
    deadline = time.time() + TIME_BOX_S
    before = hysys_processes()
    log.say(f"开始前的 HYSYS 进程: {before or '无'}")
    app = win32com.client.gencache.EnsureDispatch("HYSYS.Application.NewInstance")
    mine = next((pid for pid in hysys_processes() if pid not in before), None)
    log.say(f"新实例的进程号: {mine}")
    app.Visible = True
    scratch = Path(tempfile.mkdtemp(prefix="hysys_samples_")).resolve()
    try:
        for rel in names:
            if time.time() > deadline:
                log.conclude("超过 20 分钟的时间盒，停止")
                break
            inspect_case(log, app, INSTALL_DIR / rel, scratch)
    finally:
        log.attempt("app.Quit()", app.Quit)
        if mine is not None:
            gone = wait_gone(mine)
            state = "仍在运行" if gone is None else f"已退出，用时 {gone:.1f} 秒"
            log.say(f"  实例 {mine} {state}")
        shutil.rmtree(scratch, ignore_errors=True)
    log.say(f"结束时的 HYSYS 进程: {hysys_processes() or '无'}")


if __name__ == "__main__":
    main()

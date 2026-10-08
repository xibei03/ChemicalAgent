"""E12（0C 任务 4）：保存已求解的 Case，关闭后重新打开，结果和求解状态是否一致。

模型：E8 的平衡反应器（出口 710 °C），带能流。
要回答的问题：
  Q1 另存（SaveAs）之后，case.FullName 是原来的路径还是新的？旁边多出什么文件？
  Q2 关闭后用 Open 重新打开，不重新求解就读到的出料和热负荷与保存前一致吗？
     流程图状态和求解器状态保留吗？
  Q3 重开后改规定（出口 600 °C）能重新求解，结果与保存前同一规定下的结果一致吗？
  Q4 Save()（不带路径）写回当前路径吗？
  Q5 另一个新实例打开同一个文件，结果一致吗？
  Q6 app.ActiveDocument 在 Open 之后是什么？

用法：python spikes/e12_save_reopen.py [--tag 名字]
输出：spikes/out/e12_save_reopen_<tag>.txt；Case 另存为同名 .hsc。
"""

import argparse
import time
import traceback
from pathlib import Path

from _common import OUT_DIR, Log, dialog_guard, new_instance, use_utf8
from chain_kit import new_case_with_basis, read_stream, status_counts
from e8_equilibrium_chain import COMPONENTS, build_train, step_reactions

use_utf8()

REOPEN_TOLERANCE = 1e-6
STREAM_NAME = "Vap-100"
ENERGY_NAME = "Q-100"
REACTOR_NAME = "ERV-100"


def snapshot(case) -> dict[str, object]:
    """出料、热负荷、流程图状态、求解器状态，直接按名字从 Case 里读。"""
    flowsheet = case.Flowsheet
    outlet = read_stream(flowsheet.MaterialStreams.Item(STREAM_NAME), COMPONENTS)
    outlet["duty_kw"] = flowsheet.EnergyStreams.Item(ENERGY_NAME).HeatFlow.GetValue("kW")
    outlet["status"] = status_counts(case)
    outlet["solver"] = (case.Solver.CanSolve, case.Solver.IsSolving)
    return outlet


def same(log: Log, label: str, first: dict[str, object], second: dict[str, object]) -> bool:
    """两份快照的出料摩尔分率、总流量、热负荷、状态是否一致。"""
    diff = max(abs(first["fractions"][k] - second["fractions"][k]) for k in first["fractions"])
    flow = abs(first["kmol_h"] - second["kmol_h"]) / first["kmol_h"]
    duty = abs(first["duty_kw"] - second["duty_kw"]) / max(abs(first["duty_kw"]), 1.0)
    ok = diff <= REOPEN_TOLERANCE and flow <= REOPEN_TOLERANCE and duty <= REOPEN_TOLERANCE
    log.say(
        f"  [{'一致' if ok else '不一致'}] {label}：摩尔分率最大差 {diff:.2e}，"
        f"总流量相对差 {flow:.2e}，热负荷相对差 {duty:.2e}；"
        f"T={second['T_C']:.2f} C，状态 {second['status']}，"
        f"求解器(CanSolve, IsSolving) {second['solver']}"
    )
    return ok


def build_and_solve(log: Log, app):
    """建 E8 的模型，710 °C 求解；顺便取 600 °C 的快照当作重开后的对照。"""
    basis = new_case_with_basis(app, "e12_save", COMPONENTS)
    reaction_set = step_reactions(log, basis)
    basis.manager.EndBasisChange()
    train = build_train(basis.case.Flowsheet, basis, "-100", reaction_set, with_energy=True)
    train.vapour.Temperature.SetValue(710.0, "C")
    at_710 = snapshot(basis.case)
    train.vapour.Temperature.SetValue(600.0, "C")
    at_600 = snapshot(basis.case)
    train.vapour.Temperature.SetValue(710.0, "C")
    again_710 = snapshot(basis.case)
    log.say("  保存前 710 C / 600 C / 回到 710 C 的快照已取")
    same(log, "保存前 710 C 与回到 710 C", at_710, again_710)
    return basis.case, train, at_710, at_600


def list_folder(log: Log, path: Path) -> None:
    files = {f.name: f.stat().st_size for f in sorted(path.parent.iterdir()) if f.stem == path.stem}
    log.say(f"  旁边的文件和大小 {files}")


def run_once(log: Log, path: Path) -> bool:
    results = []
    with new_instance(log) as (app, pid), dialog_guard(log, pid, include_hidden=True) as dialogs:
        case, _train, at_710, at_600 = build_and_solve(log, app)
        log.say("== Q1 另存 ==")
        log.say(f"  SaveAs 之前 case.FullName = {case.FullName!r}")
        start = time.time()
        case.SaveAs(str(path))
        log.say(
            f"  SaveAs 用时 {time.time() - start:.2f} 秒；之后 case.FullName = {case.FullName!r}"
        )
        log.attempt("  case.IsDirty", lambda: case.IsDirty)
        list_folder(log, path)
        case.Close()
        log.say(f"  Close 之后 Case 数 {app.SimulationCases.Count}")
        log.say("== Q2 关闭后重开，不重新求解就读 ==")
        start = time.time()
        reopened = app.SimulationCases.Open(str(path))
        log.say(f"  Open 用时 {time.time() - start:.2f} 秒；FullName = {reopened.FullName!r}")
        log.attempt("  Open 之后 app.ActiveDocument（Q6）", lambda: app.ActiveDocument)
        log.attempt("  Open 之后 Case 数", lambda: app.SimulationCases.Count)
        results.append(same(log, "重开后 710 C 与保存前", at_710, snapshot(reopened)))
        log.say("== Q3 重开后改规定 ==")
        stream = reopened.Flowsheet.MaterialStreams.Item(STREAM_NAME)
        stream.Temperature.SetValue(600.0, "C")
        results.append(same(log, "重开后改成 600 C 与保存前 600 C", at_600, snapshot(reopened)))
        stream.Temperature.SetValue(710.0, "C")
        results.append(same(log, "再改回 710 C 与保存前 710 C", at_710, snapshot(reopened)))
        log.say("== Q4 Save()（不带路径） ==")
        before = path.stat().st_mtime
        stream.Temperature.SetValue(650.0, "C")
        time.sleep(1.1)
        log.attempt("  reopened.Save()", reopened.Save)
        log.say(
            f"  文件修改时间变了吗 {path.stat().st_mtime != before}；"
            f"FullName = {reopened.FullName!r}"
        )
        list_folder(log, path)
        reopened.Close()
        log.say(f"  弹窗 {len(dialogs)} 个：{dialogs}")
    log.say("== Q5 另一个新实例打开同一个文件 ==")
    with new_instance(log) as (app, _pid):
        other = app.SimulationCases.Open(str(path))
        snap = snapshot(other)
        log.say(
            f"  Save() 之后的文件里，出口温度 {snap['T_C']:.2f} C（期望 650），"
            f"状态 {snap['status']}"
        )
        results.append(abs(snap["T_C"] - 650.0) < 0.01)
        other.Close()
    return all(results)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    args = parser.parse_args()
    log = Log(f"e12_save_reopen_{args.tag}")
    try:
        passed = run_once(log, OUT_DIR / f"e12_save_reopen_{args.tag}.hsc")
    except Exception:  # 探针：任何失败都要连同堆栈记进日志，再以非零状态退出
        log.say(traceback.format_exc())
        return 1
    log.say(f"== E12 {'通过' if passed else '未通过'} ==")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

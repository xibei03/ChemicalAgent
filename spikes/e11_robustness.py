"""E11（0C 任务 4）：鲁棒性观察。后面的错误码和恢复策略按这里记下的异常原文设计。

A 同名对象  在已经建好的模型里，每个创建调用各做两次（再加跨类型同名），
            记录报错、返回已有对象还是新建
B 进程中断  主线程做 COM 调用，定时器在几秒后 taskkill /F /PID：B1 两次调用之间；B2 SaveAs 期间；
            B3 Open 期间。记录 Python 一侧的异常类型、错误号、消息，以及之后实例和文件的状态
C 弹窗      主动制造三种情况（关闭改过没保存的 Case；打开不存在或损坏的文件；另存到不存在的目录），
            可见和隐藏两种窗口各做一次。看门狗线程（包括不可见的对话框）记下并关闭弹窗，
            再用 120 秒的安全网结束进程，防止真的卡死
D 窗口隐藏  Visible=False 时建模、求解的结果与 Visible=True 是否一致

用法：python spikes/e11_robustness.py [--tag 名字] [--only A|B|C|D]
输出：spikes/out/e11_robustness_<tag>.txt
"""

import argparse
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
from pathlib import Path

from _common import OUT_DIR, Log, dialog_guard, hysys_processes, new_instance, use_utf8
from chain_kit import new_case_with_basis, read_stream
from e8_equilibrium_chain import COMPONENTS, build_train, step_reactions

use_utf8()

SOLVED_CASE = OUT_DIR / "e8_equilibrium_chain_run1.hsc"
SAFETY_NET_S = 120.0
INTERRUPT_DELAY_S = 3.0
LOOP_LIMIT_S = 40.0
DIFFERENCE_TOLERANCE = 1e-6


def describe_exception(exc: BaseException) -> str:
    """异常的类型和参数原文（com_error 的 args 里有错误号和消息）。"""
    return f"{type(exc).__name__}{getattr(exc, 'args', ())!r}"


def kill_after(log: Log, pid: int, seconds: float, reason: str) -> threading.Timer:
    """定时 taskkill /F /PID，既用来制造中断，也用来当安全网。"""

    def kill() -> None:
        log.say(f"  [定时器] {reason}：{seconds:.1f} 秒到，taskkill /F /PID {pid}")
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)

    timer = threading.Timer(seconds, kill)
    timer.daemon = True
    timer.start()
    return timer


def twice(log: Log, label: str, call) -> None:
    """同一个创建调用连做两次，记录两次各自的结果。"""
    outcomes = []
    for _ in range(2):
        try:
            value = call()
            outcomes.append(f"成功，返回 {getattr(value, 'name', value)!r}")
        except Exception as exc:  # 探针：异常原文就是要记录的结果
            outcomes.append(f"失败 {describe_exception(exc)}")
    log.say(f"  {label}\n      第 1 次 {outcomes[0]}\n      第 2 次 {outcomes[1]}")


def duplicate_basis_objects(log: Log, app) -> None:
    """A1：Case、Basis、反应、反应集一侧和流程图物流的同名对象。"""
    log.say("== A1 同名对象：Case、Basis、反应、物流 ==")
    basis = new_case_with_basis(app, "e11_dup", COMPONENTS)
    manager, case = basis.manager, basis.case
    log.say(f"  Case 数 {app.SimulationCases.Count}，名字 {list(app.SimulationCases.Names)}")
    twice(
        log,
        "SimulationCases.Add('e11_dup')（与已有的 Case 同名）",
        lambda: app.SimulationCases.Add("e11_dup"),
    )
    log.say(f"  之后 Case 数 {app.SimulationCases.Count}，名字 {list(app.SimulationCases.Names)}")
    twice(log, "ComponentLists.Add('CL-1')", lambda: manager.ComponentLists.Add("CL-1"))
    log.say(f"  组分列表 {list(manager.ComponentLists.Names)}")
    twice(log, "FluidPackages.Add('Basis-1')", lambda: manager.FluidPackages.Add("Basis-1"))
    log.say(f"  流体包 {list(manager.FluidPackages.Names)}")
    twice(log, "Components.Add('Methane')", lambda: basis.package.Components.Add("Methane"))
    reactions = manager.ReactionPackageManager.Reactions
    twice(
        log,
        "Reactions.Add('Rxn-1', 'equilibriumrxn')",
        lambda: reactions.Add("Rxn-1", "equilibriumrxn"),
    )
    log.say(f"  反应 {list(reactions.Names)}")
    reaction = reactions.Item("Rxn-1")
    twice(log, "Reactants.Add('Methane')", lambda: reaction.Reactants.Add("Methane"))
    log.say(f"  反应物 {list(reaction.Reactants.Names)}")
    sets = manager.ReactionPackageManager.ReactionSets
    twice(log, "ReactionSets.Add('RxnSet-1')", lambda: sets.Add("RxnSet-1"))
    reaction_set = sets.Item("RxnSet-1")
    twice(log, "ActiveReactions.Add('Rxn-1')", lambda: reaction_set.ActiveReactions.Add("Rxn-1"))
    log.say(f"  反应集成员 {list(reaction_set.ActiveReactions.Names)}")
    reaction_set.AssociateFluidPackage(basis.package)
    twice(
        log,
        "AssociateFluidPackage（第二次）",
        lambda: reaction_set.AssociateFluidPackage(basis.package),
    )
    manager.EndBasisChange()
    flowsheet = case.Flowsheet
    twice(log, "MaterialStreams.Add('Feed')", lambda: flowsheet.MaterialStreams.Add("Feed"))
    twice(log, "EnergyStreams.Add('Q-1')", lambda: flowsheet.EnergyStreams.Add("Q-1"))
    case.Close()


OPERATION_SCENARIOS = (
    "same-type",
    "other-type",
    "stream-named-like-operation",
    "feed-twice",
    "product-of-two-reactors",
)


def operation_scenario(log: Log, app, scenario: str, dialogs: list[str]) -> None:
    """A2：操作一侧的同名对象。每个场景在新实例里做，防止一个场景把实例弄死、影响后面的场景。"""
    basis = new_case_with_basis(app, f"e11_{scenario}", COMPONENTS)
    basis.manager.EndBasisChange()
    flowsheet = basis.case.Flowsheet
    feed = flowsheet.MaterialStreams.Add("Feed")
    vapour = flowsheet.MaterialStreams.Add("Vap")
    flowsheet.MaterialStreams.Add("Liq")
    first = flowsheet.Operations.Add("ERV-100", "EquilibriumReactorOp")
    log.say(f"  先建了 ERV-100；操作 {list(flowsheet.Operations.Names)}")
    calls = {
        "same-type": lambda: flowsheet.Operations.Add("ERV-100", "EquilibriumReactorOp"),
        "other-type": lambda: flowsheet.Operations.Add("ERV-100", "GibbsReactorOp"),
        "stream-named-like-operation": lambda: flowsheet.MaterialStreams.Add("ERV-100"),
        "feed-twice": lambda: [first.Feeds.Add(feed), first.Feeds.Add(feed)],
        "product-of-two-reactors": lambda: [
            setattr(first, "VapourProduct", vapour),
            setattr(
                flowsheet.Operations.Add("ERV-200", "EquilibriumReactorOp"), "VapourProduct", vapour
            ),
        ],
    }
    before = len(dialogs)
    log.attempt(f"场景 {scenario}", calls[scenario])
    texts = sorted(set(dialogs[before:]))
    log.say(f"      调用期间弹窗点击 {len(dialogs) - before} 次，不同的文字 {texts}")
    log.attempt("      实例还活着吗：app.name", lambda: app.name)
    log.attempt("      操作", lambda: list(flowsheet.Operations.Names))
    log.attempt("      物流", lambda: list(flowsheet.MaterialStreams.Names))
    log.attempt("      ERV-100 的进料", lambda: list(first.Feeds.Names))


def duplicate_operations(log: Log, only: str | None, redo_after_s: float) -> None:
    """A2：每个场景一个新实例。"""
    log.say("== A2 同名对象：操作和连接 ==")
    for scenario in OPERATION_SCENARIOS:
        if only and scenario != only:
            continue
        log.say(f"-- 场景 {scenario}（对话框同一窗口 {redo_after_s:g} 秒内只点一次） --")
        with (
            new_instance(log) as (app, pid),
            dialog_guard(log, pid, include_hidden=True) as dialogs,
        ):
            safety = kill_after(log, pid, SAFETY_NET_S, f"A2-{scenario} 安全网")
            try:
                operation_scenario(log, app, scenario, dialogs)
            except Exception:  # 探针：场景里任何失败都要记进日志，再做下一个场景
                log.say(traceback.format_exc())
            safety.cancel()


def interrupt_between_calls(log: Log) -> None:
    """B1：两次调用之间结束进程。"""
    log.say("== B1 进程中断：两次调用之间 ==")
    with new_instance(log) as (app, pid):
        basis = new_case_with_basis(app, "e11_b1", COMPONENTS)
        basis.manager.EndBasisChange()
        stream = basis.case.Flowsheet.MaterialStreams.Add("S")
        stream.Temperature.SetValue(25.0, "C")
        timer = kill_after(log, pid, INTERRUPT_DELAY_S, "B1")
        start, calls, error = time.time(), 0, None
        while time.time() - start < LOOP_LIMIT_S and error is None:
            try:
                stream.Temperature.GetValue("C")
                calls += 1
            except Exception as exc:  # 探针：异常原文就是要记录的结果
                error = (time.time() - start, describe_exception(exc))
            time.sleep(0.05)
        timer.cancel()
        log.say(
            f"  循环里成功读了 {calls} 次；第一次失败发生在 {error[0]:.2f} 秒：{error[1]}"
            if error
            else "  没有出现失败"
        )
        for label, call in (
            ("同一个物流对象再读一次", lambda: stream.Temperature.GetValue("C")),
            ("app.name", lambda: app.name),
            ("app.SimulationCases.Count", lambda: app.SimulationCases.Count),
            ("case.Flowsheet", lambda: basis.case.Flowsheet),
            ("case.Close()", basis.case.Close),
        ):
            start = time.time()
            log.attempt(label, call)
            log.say(f"      这一次调用用时 {time.time() - start:.2f} 秒")
        log.say(f"  tasklist 里的 HYSYS 进程 {hysys_processes()}")


def interrupt_during(log: Log, kind: str) -> None:
    """B2、B3：SaveAs 或 Open 期间结束进程。"""
    log.say(
        f"== B{2 if kind == 'save' else 3} 进程中断："
        f"{'SaveAs' if kind == 'save' else 'Open'} 期间 =="
    )
    folder = Path(tempfile.mkdtemp(prefix="e11_")).resolve()
    source = folder / "source.hsc"
    shutil.copyfile(SOLVED_CASE, source)
    target = folder / "target.hsc"
    with new_instance(log) as (app, pid):
        case = app.SimulationCases.Open(str(source))
        timer = kill_after(log, pid, INTERRUPT_DELAY_S, f"B-{kind}")
        start, rounds, error = time.time(), 0, None
        while time.time() - start < LOOP_LIMIT_S and error is None:
            step = "SaveAs"
            try:
                if kind == "save":
                    case.SaveAs(str(target))
                else:
                    step = "Close"
                    case.Close()
                    step = "Open"
                    case = app.SimulationCases.Open(str(source))
                rounds += 1
            except Exception as exc:  # 探针：异常原文就是要记录的结果
                error = (time.time() - start, step, describe_exception(exc))
        timer.cancel()
        log.say(f"  成功循环 {rounds} 轮；失败：{error}" if error else "  没有出现失败")
        log.say(f"  tasklist 里的 HYSYS 进程 {hysys_processes()}")
    sizes = {p.name: p.stat().st_size for p in folder.iterdir()}
    log.say(f"  之后目录里的文件和大小 {sizes}")
    with new_instance(log) as (app, _pid):
        log.attempt("  新实例能正常用：Case 数", lambda: app.SimulationCases.Count)
        for path in sorted(folder.glob("*.hsc")):
            ok, reopened = log.attempt(
                f"  新实例打开 {path.name}", lambda path=path: app.SimulationCases.Open(str(path))
            )
            if ok:
                log.attempt(
                    "      读回物流 Names",
                    lambda reopened=reopened: list(reopened.Flowsheet.MaterialStreams.Names),
                )
                reopened.Close()
    shutil.rmtree(folder, ignore_errors=True)


def timed_call(log: Log, label: str, call, dialogs: list[str]) -> None:
    """做一次可能触发弹窗的调用，记录用时、异常、期间被看门狗处理的弹窗。"""
    before = len(dialogs)
    start = time.time()
    try:
        value = call()
        outcome = f"成功，返回 {getattr(value, 'name', value)!r}"
    except Exception as exc:  # 探针：异常原文就是要记录的结果
        outcome = f"失败 {describe_exception(exc)}"
    seconds = time.time() - start
    log.say(
        f"  {label}\n      用时 {seconds:.2f} 秒；"
        f"调用期间弹窗 {len(dialogs) - before} 个；{outcome}"
    )


def open_missing_then_corrupt(app, case, folder: Path, broken: Path):
    """第一次探测（C1）的顺序：关掉 Case，打开不存在的文件（报错），再打开损坏的文件。"""
    case.Close()
    try:
        app.SimulationCases.Open(str(folder / "no_such_file.hsc"))
    except Exception:  # 探针：第一次打开本来就应该失败，失败之后的行为才是要看的
        pass
    return app.SimulationCases.Open(str(broken))


POPUP_SCENARIOS = (
    "close-modified",
    "close-unsaved-new",
    "open-missing",
    "open-corrupt",
    "open-corrupt-after-close",
    "open-missing-then-corrupt",
    "saveas-missing-dir",
    "saveas-bad-name",
)


def popup_scenario(log: Log, app, scenario: str, folder: Path, dialogs: list[str]) -> None:
    """C：一种可能触发弹窗的情况。先建好并保存一个小 Case，再做被测的调用。"""
    basis = new_case_with_basis(app, f"e11_{scenario}", COMPONENTS)
    basis.manager.EndBasisChange()
    case = basis.case
    flowsheet = case.Flowsheet
    flowsheet.MaterialStreams.Add("S")
    saved = folder / f"{scenario}.hsc"
    case.SaveAs(str(saved))
    broken = folder / "broken.hsc"
    broken.write_text("这不是一个 HYSYS Case", encoding="utf-8")
    calls = {
        "close-modified": lambda: (flowsheet.MaterialStreams.Add("S-2"), case.Close()),
        "close-unsaved-new": lambda: app.SimulationCases.Add("e11_unsaved").Close(),
        "open-missing": lambda: app.SimulationCases.Open(str(folder / "no_such_file.hsc")),
        "open-corrupt": lambda: app.SimulationCases.Open(str(broken)),
        "open-corrupt-after-close": lambda: (case.Close(), app.SimulationCases.Open(str(broken))),
        "open-missing-then-corrupt": lambda: open_missing_then_corrupt(app, case, folder, broken),
        "saveas-missing-dir": lambda: case.SaveAs(str(folder / "no_such_dir" / "x.hsc")),
        "saveas-bad-name": lambda: case.SaveAs(str(folder / "a<b>.hsc")),
    }
    if scenario == "close-modified":
        log.say(f"  case.IsDirty={case.IsDirty}（保存后）")
    timed_call(log, f"场景 {scenario}", calls[scenario], dialogs)
    log.attempt("      实例还活着吗：app.name", lambda: app.name)
    log.attempt("      Case 数", lambda: app.SimulationCases.Count)
    if scenario.startswith("saveas"):
        target = folder / ("no_such_dir" if "missing" in scenario else "a<b>.hsc")
        log.say(f"      目标 {target.name} 是否存在 {target.exists()}")
        if target.is_dir():
            log.say(f"      目录里的文件 {[f.name for f in target.iterdir()]}")
        log.attempt("      case.FullName", lambda: case.FullName)


def popups(log: Log, visible: bool, only: str | None) -> None:
    """C：每种情况一个新实例，窗口可见和隐藏各做一遍。"""
    state = "可见" if visible else "隐藏"
    log.say(f"== C 弹窗（窗口{state}） ==")
    for scenario in POPUP_SCENARIOS:
        if only and scenario != only:
            continue
        log.say(f"-- 场景 {scenario}（窗口{state}） --")
        folder = Path(tempfile.mkdtemp(prefix="e11c_")).resolve()
        with (
            new_instance(log, visible=visible) as (app, pid),
            dialog_guard(log, pid, include_hidden=True) as dialogs,
        ):
            safety = kill_after(log, pid, SAFETY_NET_S, f"C-{scenario}-{state} 安全网")
            try:
                popup_scenario(log, app, scenario, folder, dialogs)
            except Exception:  # 探针：场景里任何失败都要记进日志，再做下一个场景
                log.say(traceback.format_exc())
            safety.cancel()
            log.say(f"  看门狗处理弹窗 {len(dialogs)} 个：{sorted(set(dialogs))}")
        shutil.rmtree(folder, ignore_errors=True)


def solve_equilibrium(log: Log, visible: bool) -> dict[str, object]:
    """D：建 E8 的平衡反应器模型，710 °C 求解，返回出料。"""
    start = time.time()
    with new_instance(log, visible=visible) as (app, _pid):
        basis = new_case_with_basis(app, "e11_hidden", COMPONENTS)
        reaction_set = step_reactions(log, basis)
        basis.manager.EndBasisChange()
        train = build_train(basis.case.Flowsheet, basis, "-100", reaction_set, with_energy=True)
        train.vapour.Temperature.SetValue(710.0, "C")
        outlet = read_stream(train.vapour, basis.components)
        outlet["duty_kw"] = train.energy.HeatFlow.GetValue("kW")
        outlet["seconds"] = time.time() - start
        log.say(f"  app.Visible={app.Visible}；用时 {outlet['seconds']:.1f} 秒（含启动）")
        basis.case.Close()
    return outlet


def hidden_window(log: Log) -> None:
    """D：窗口隐藏时建模和求解是否正常。"""
    log.say("== D 窗口隐藏 ==")
    results = {}
    for visible in (True, False):
        log.say(f"-- Visible={visible} --")
        results[visible] = solve_equilibrium(log, visible)
    shown, hidden = results[True], results[False]
    diff = max(abs(shown["fractions"][k] - hidden["fractions"][k]) for k in shown["fractions"])
    log.say(
        f"  可见与隐藏的摩尔分率最大差 {diff:.2e}（要求 ≤ {DIFFERENCE_TOLERANCE}）；"
        f"热负荷 {shown['duty_kw']:.1f} 与 {hidden['duty_kw']:.1f} kW"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    parser.add_argument("--only", default=None, choices=["A", "B", "C", "D"])
    parser.add_argument("--scenario", default=None, help="A2 和 C 只跑这个场景")
    parser.add_argument(
        "--redo-after", type=float, default=0.0, help="同一对话框点击的最小间隔秒数"
    )
    args = parser.parse_args()
    log = Log(f"e11_robustness_{args.tag}")
    sections = {
        "A": lambda: [
            _with_instance(log, duplicate_basis_objects),
            duplicate_operations(log, args.scenario, args.redo_after),
        ],
        "B": lambda: [
            interrupt_between_calls(log),
            interrupt_during(log, "save"),
            interrupt_during(log, "open"),
        ],
        "C": lambda: [popups(log, True, args.scenario), popups(log, False, args.scenario)],
        "D": lambda: hidden_window(log),
    }
    for name, run in sections.items():
        if args.only and name != args.only:
            continue
        try:
            run()
        except Exception:  # 探针：任何失败都要连同堆栈记进日志，再接着做下一节
            log.say(traceback.format_exc())
    log.say(f"== 结束后残留的 HYSYS 进程 {hysys_processes()} ==")
    return 0


def _with_instance(log: Log, section) -> None:
    with new_instance(log) as (app, pid), dialog_guard(log, pid, include_hidden=True):
        section(log, app)


if __name__ == "__main__":
    raise SystemExit(main())

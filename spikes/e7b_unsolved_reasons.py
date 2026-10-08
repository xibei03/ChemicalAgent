"""E7b：模型没有求解时，从哪里能读到原因（哪个量没有规定、哪个连接缺了）。

要回答的问题（阶段提示词 0B 任务 4）：
  Q1 一台转化反应器逐步连接的过程中，每一步之后流程图的状态怎么变？
     （GetFlowsheetStatus、GetFlowsheetObjectTypeAndName 能定位到什么？）
  Q2 少一样东西时（没接进料、没接气相出料、没接液相出料、没挂反应集、压降没规定、
     反应集没加入流体包、反应集里的反应类型与反应器不匹配、进料流量没规定）
     状态各是什么？反应器自己的哪些成员能指出缺了什么？
  Q3 压降新建时是不是已经有规定值？
做法：在建好 Basis 和反应的 Case 里，用独立的反应器各试一种缺陷，读状态和成员。

用法：python spikes/e7b_unsolved_reasons.py [--tag 名字]
输出：spikes/out/e7b_unsolved_reasons_<tag>.txt
"""

import argparse

import pywintypes
from _common import Log, dialog_guard, new_instance, use_utf8, watch

use_utf8()

COMPONENTS = ("Toluene", "Benzene", "p-Xylene", "m-Xylene", "o-Xylene")
STATUS_FLAGS = {"OK": 1, "NotSolved": 2, "Warning": 4, "UnderSpecified": 8, "Error": 16}
STOICHIOMETRY = (
    ("Toluene", -2.0),
    ("Benzene", 1.0),
    ("p-Xylene", 0.24),
    ("m-Xylene", 0.52),
    ("o-Xylene", 0.24),
)


def build_basis(log: Log, app):
    """Basis、转化反应 Tol-Disp、好的反应集 Conv-Set、没加入流体包的反应集 Loose-Set、
    平衡反应 Eq-Test 和它的反应集 Eq-Set。结束 Basis。"""
    case = app.SimulationCases.Add("e7b")
    manager = case.BasisManager
    component_list = manager.ComponentLists.Add("CL-1")
    for name in COMPONENTS:
        component_list.Components.Add(name)
    package = manager.FluidPackages.Add("Basis-1")
    package.ComponentList = component_list
    package.PropertyPackageName = "pengrob"
    reactions = manager.ReactionPackageManager.Reactions
    sets = manager.ReactionPackageManager.ReactionSets
    reaction = reactions.Add("Tol-Disp", "conversionrxn")
    for name, coefficient in STOICHIOMETRY:
        reaction.Reactants.Add(name).StoichiometricCoefficientValue = coefficient
    reaction.BaseComponent = package.Components.Item("Toluene")
    reaction.Conversion = 50.0
    reaction.ReactionPhase = 0
    good = sets.Add("Conv-Set")
    good.ActiveReactions.Add("Tol-Disp")
    good.AssociateFluidPackage(package)
    loose = sets.Add("Loose-Set")
    loose.ActiveReactions.Add("Tol-Disp")
    equilibrium = reactions.Add("Eq-Test", "equilibriumrxn")
    for name, coefficient in (("Toluene", -2.0), ("Benzene", 1.0), ("p-Xylene", 1.0)):
        equilibrium.Reactants.Add(name).StoichiometricCoefficientValue = coefficient
    equilibrium.ReactionPhase = 0
    eq_set = sets.Add("Eq-Set")
    eq_set.ActiveReactions.Add("Eq-Test")
    eq_set.AssociateFluidPackage(package)
    manager.EndBasisChange()
    log.say(
        f"  流体包的反应集: {list(package.ReactionPackage.ReactionSets.Names)}（Loose-Set 没加入）"
    )
    return case, {"good": good, "loose": loose, "equilibrium": eq_set}


def make_feed(flowsheet, name: str, with_flow: bool = True):
    feed = flowsheet.MaterialStreams.Add(name)
    feed.Temperature.SetValue(380.0, "C")
    feed.Pressure.SetValue(2500.0, "kPa")
    feed.ComponentMolarFraction.Values = (1.0, 0.0, 0.0, 0.0, 0.0)
    if with_flow:
        feed.MassFlow.SetValue(10000.0, "kg/h")
    return feed


def status(log: Log, case, label: str, watched_names: tuple[str, ...] = ()) -> None:
    """流程图状态：各状态的对象个数和清单（只列没有 OK 的）。"""
    counts = {name: case.GetFlowsheetStatus(flag) for name, flag in STATUS_FLAGS.items()}
    log.say(f"  [{label}] 状态计数 {counts}")
    for name in ("NotSolved", "UnderSpecified", "Warning", "Error"):
        if counts[name]:
            objects = case.GetFlowsheetObjectTypeAndName(STATUS_FLAGS[name])
            shown = [o for o in objects if not watched_names or o[1] in watched_names]
            log.say(f"      {name}: {shown}")


def reactor_members(log: Log, reactor, label: str) -> None:
    """反应器自己的成员里，哪些能指出缺了什么。"""

    def read(call):
        try:
            value = call()
        except pywintypes.com_error as exc:
            return f"抛 com_error({exc.args[0]})"
        return value.name if hasattr(value, "name") else value

    log.say(
        f"      [{label}] Feeds={read(lambda: list(reactor.Feeds.Names))}，"
        f"VapourProduct={read(lambda: reactor.VapourProduct)}，"
        f"LiquidProduct={read(lambda: reactor.LiquidProduct)}，"
        f"ReactionSet={read(lambda: reactor.ReactionSet)}，"
        f"PressureDrop.IsKnown={read(lambda: reactor.PressureDrop.IsKnown)}，"
        f"PressureDrop.State={read(lambda: reactor.PressureDrop.State)}"
    )


def staged_connection(log: Log, case, flowsheet, sets) -> None:
    """Q1、Q3：一台反应器逐步连接，每步看状态。"""
    log.say("== Q1、Q3 逐步连接（反应器 R-Stage） ==")
    feed = make_feed(flowsheet, "F-Stage")
    vapour = flowsheet.MaterialStreams.Add("V-Stage")
    liquid = flowsheet.MaterialStreams.Add("L-Stage")
    status(log, case, "只有三股物流", ("F-Stage", "V-Stage", "L-Stage"))
    reactor = flowsheet.Operations.Add("R-Stage", "ConversionReactorOp")
    reactor_members(log, reactor, "新建后")
    log.attempt("PressureDrop 新建后的值 kPa", lambda: reactor.PressureDrop.GetValue("kPa"))
    status(log, case, "S0 新建反应器，什么都没连")
    reactor.Feeds.Add(feed)
    status(log, case, "S1 接进料")
    reactor.VapourProduct = vapour
    status(log, case, "S2 接气相出料")
    reactor.LiquidProduct = liquid
    status(log, case, "S3 接液相出料")
    reactor.ReactionSet = sets["good"]
    reactor_members(log, reactor, "S4 之后")
    status(log, case, "S4 挂反应集（压降没动）")
    log.attempt("气相出料流量是否已知", lambda: vapour.MolarFlow.IsKnown)
    log.attempt("气相出料摩尔流量 kgmole/h", lambda: vapour.MolarFlow.GetValue("kgmole/h"))
    reactor.PressureDrop.SetValue(0.0, "kPa")
    reactor_members(log, reactor, "S5 之后")
    status(log, case, "S5 显式写压降 0")


def defect_case(log: Log, case, flowsheet, sets, name, build) -> None:
    """Q2：一台只缺一样东西的反应器。build 返回反应器。"""
    log.say(f"-- 缺陷：{name} --")
    reactor = build(flowsheet, sets)
    tag = reactor.name.split("-", 1)[1]
    reactor_members(log, reactor, name)
    status(log, case, name, tuple(f"{kind}-{tag}" for kind in ("F", "V", "L", "R")))


def make_defects(log: Log, case, flowsheet, sets) -> None:
    log.say("== Q2 每次只缺一样东西 ==")

    def complete(
        tag: str,
        with_flow=True,
        set_key="good",
        feed_connected=True,
        vapour_on=True,
        liquid_on=True,
    ):
        feed = make_feed(flowsheet, f"F-{tag}", with_flow)
        vapour = flowsheet.MaterialStreams.Add(f"V-{tag}")
        liquid = flowsheet.MaterialStreams.Add(f"L-{tag}")
        reactor = flowsheet.Operations.Add(f"R-{tag}", "ConversionReactorOp")
        if feed_connected:
            reactor.Feeds.Add(feed)
        if vapour_on:
            reactor.VapourProduct = vapour
        if liquid_on:
            reactor.LiquidProduct = liquid
        if set_key:
            log.attempt(
                f"挂反应集 {set_key}", lambda: setattr(reactor, "ReactionSet", sets[set_key])
            )
        reactor.PressureDrop.SetValue(0.0, "kPa")
        return reactor

    cases = (
        ("对照：什么都不缺", lambda fs, st: complete("OK")),
        ("没接进料", lambda fs, st: complete("D1", feed_connected=False)),
        ("没接气相出料", lambda fs, st: complete("D2", vapour_on=False)),
        ("没接液相出料", lambda fs, st: complete("D3", liquid_on=False)),
        ("没挂反应集", lambda fs, st: complete("D4", set_key=None)),
        ("反应集没加入流体包", lambda fs, st: complete("D5", set_key="loose")),
        ("反应集里是平衡反应（类型不匹配）", lambda fs, st: complete("D6", set_key="equilibrium")),
        ("进料流量没规定", lambda fs, st: complete("D7", with_flow=False)),
    )
    for name, build in cases:
        defect_case(log, case, flowsheet, sets, name, build)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    args = parser.parse_args()
    log = Log(f"e7b_unsolved_reasons_{args.tag}")
    with new_instance(log) as (app, pid), dialog_guard(log, pid) as dialogs:
        with watch(log, "build_basis"):
            case, sets = build_basis(log, app)
        flowsheet = case.Flowsheet
        staged_connection(log, case, flowsheet, sets)
        make_defects(log, case, flowsheet, sets)
        log.say(f"== 全程看门狗处理过的弹窗 {len(dialogs)} 个 ==")
        for message in dialogs:
            log.say(f"  {message}")
        log.attempt("case.Close()", case.Close)


if __name__ == "__main__":
    main()

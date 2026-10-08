"""E3：反向探测。打开一个已经建好的 Case，看 GUI 建出来的东西在 COM 里长什么样。

要回答的问题：
  Q1 反应器的进料、气相出料、液相出料、能流、反应集、压降、热负荷分别是哪个成员？
  Q2 出口温度规定在哪里（出料物流上，还是反应器上）？计算值和规定值的 State 各是多少？
  Q3 Gibbs 反应器的类型选项、转化率、Keq 来源、基准组分、计量系数在哪些成员上？
  Q4 反应和反应集：Reactions 集合里的对象是什么类型？ActiveReactions 里放什么？
     反应集怎么和流体包关联？
  Q5 反应对象上还有哪些能读到的设置（相态、基准、温度范围、Keq 公式系数）？
  Q6 GetXMLForCase / ProvideXMLForOperation 的输出里有没有反应和反应集？
做法：把 Case 复制到临时目录（长路径）后用 NewInstance 的实例打开，只读，不保存。
默认的 Case 是自带示例 Synthesis Gas Production（转化和平衡反应器，没有 Gibbs）；
用户手工建好 spikes/ref_cases/three_reactors.hsc 之后用 --case 指给它。

用法：python spikes/e3_reverse_probe.py [--case 路径] [--tag 名字]
输出：spikes/out/e3_reverse_probe_<tag>.txt
"""

import argparse
import functools
import shutil
import subprocess
import tempfile
from pathlib import Path

import pywintypes
import win32com.client
from _common import Log, hysys_processes, use_utf8, wait_gone, watch

use_utf8()

DEFAULT_CASE = Path(
    r"C:\Program Files\AspenTech\Aspen HYSYS V15.0\Samples\Synthesis Gas Production.hsc"
)
REACTOR_TYPES = ("conversionreactorop", "equilibriumreactorop", "gibbsreactorop")
STATE_MEMBERS = ("IsKnown", "State", "CanModify")
XML_SNIPPET_CHARS = 1200
XML_FLAGS_TO_TRY = (0, 1)
XML_KEYWORDS = (
    "Stoich",
    "rxnset",
    "ReactionSet",
    "EquilibriumRxn",
    "Rxn-4",
    "LnK",
    "KEq",
    "Conversion",
)

# 每种反应器上能读到的结果和设置（来自类型库，E3 逐个验证）
RESULT_MEMBERS = {
    "conversionreactorop": (
        "rxnName.Values",
        "RxnBaseCmpName.Values",
        "ConversionValue",
        "RxnPercentConversionValue",
        "HeatOfReactionValue",
        "ComponentName.Values",
        "ComponentTotalInValue",
        "ComponentTotalReactedValue",
        "ComponentTotalOutValue",
    ),
    "equilibriumreactorop": (
        "rxnName.Values",
        "RxnBaseCmpName.Values",
        "RxnPercentConversionValue",
        "EqConstantValue",
        "RxnExtentValue",
        "HeatOfReactionValue",
        "ComponentName.Values",
        "ComponentTotalInValue",
        "ComponentTotalReactedValue",
        "ComponentTotalOutValue",
        "EquilibriumConstantParameterArrayValue",
        "EquilibriumTemperatureApproachParameterArrayValue",
        "EquilibriumFractionalApproachParameterArrayValue",
    ),
    "gibbsreactorop": (
        "ReactorType",
        "ComponentName.Values",
        "ComponentTotalFeedValue",
        "ComponentTotalProductValue",
        "InertSpeciesValue",
        "FractionSpecifiedValue",
        "FixedSpecificationValue",
    ),
}
# 按组分给出的进出量：带单位读（kgmole/h），不用以 kgmole/s 为单位的 …Value 属性
AMOUNT_MEMBERS = {
    "conversionreactorop": ("ComponentTotalIn", "ComponentTotalReacted", "ComponentTotalOut"),
    "equilibriumreactorop": ("ComponentTotalIn", "ComponentTotalReacted", "ComponentTotalOut"),
    "gibbsreactorop": ("ComponentTotalFeed", "ComponentTotalProduct"),
}
REACTION_COMMON = ("name", "TypeName", "VisibleTypeName", "ReactionPhase", "HeatOfReactionValue")
REACTION_MEMBERS = {
    "ConversionReaction": (
        "BaseComponent",
        "Conversion",
        "ConversionCoefficientsValue",
        "ReactantStoichCoefValue",
        "ReactantName.Values",
    ),
    "EquilibriumReaction": (
        "LnKSource",
        "Basis",
        "BasisUnits",
        "EquilibriumConstant",
        "LnKEquationAParameter",
        "LnKEquationBParameter",
        "LnKEquationCParameter",
        "LnKEquationDParameter",
        "MinTemperatureValue",
        "MaxTemperatureValue",
        "TemperatureApproachValue",
        "KEqValue",
        "KCalculatedValue",
        "AutoDetect",
        "LogBasis",
        "ActivateKTable",
        "ReactantStoichCoefValue",
        "ReactantName.Values",
    ),
}


def friendly(value: object) -> object:
    """COM 对象显示成 类型名(名字)，其余原样。"""
    if hasattr(value, "_oleobj_"):
        return f"{type(value).__name__}({getattr(value, 'name', '?')})"
    return value


def lookup(obj, dotted: str):
    """按"a.b.c"逐级取属性。"""
    return functools.reduce(getattr, dotted.split("."), obj)


def peek(log: Log, label: str, obj, dotted: str) -> None:
    log.attempt(f"{label}.{dotted}", lambda: friendly(lookup(obj, dotted)))


def peek_all(log: Log, label: str, obj, members: tuple[str, ...]) -> None:
    for member in members:
        peek(log, label, obj, member)


def optional_attr(obj, name: str):
    """取属性；没有连接对象时 HYSYS 抛 com_error（E_FAIL），这里当作 None。"""
    try:
        return getattr(obj, name)
    except pywintypes.com_error:
        return None


def peek_state(log: Log, label: str, variable) -> None:
    """已知性三件套，外加以 -32767 判空时要用的 IsKnown。"""
    for member in STATE_MEMBERS:
        log.attempt(f"{label}.{member}", lambda member=member: getattr(variable, member))


def probe_streams_of(log: Log, op) -> None:
    """进出料和能流：每股物流的 T、P、流量的 State，找出规定值落在哪一股上。"""
    feeds = op.Feeds
    log.attempt("Feeds.Count", lambda: feeds.Count)
    log.attempt("Feeds.Names", lambda: list(feeds.Names))
    log.attempt("Feeds.Item(0) 的类型", lambda: friendly(feeds.Item(0)))
    for role in ("VapourProduct", "LiquidProduct", "EnergyStream"):
        target = optional_attr(op, role)
        if target is None:
            log.say(f"  {role} -> 没有连接（取属性抛 com_error）")
            continue
        log.say(f"  {role} -> {friendly(target)}")
        if role == "EnergyStream":
            log.attempt(
                "EnergyStream.HeatFlow(kW)", lambda target=target: target.HeatFlow.GetValue("kW")
            )
            peek_state(log, "EnergyStream.HeatFlow", target.HeatFlow)
            continue
        for var in ("Temperature", "Pressure", "MolarFlow"):
            peek_state(log, f"{role}.{var}", getattr(target, var))
        log.attempt(f"{role}.T(C)", lambda target=target: target.Temperature.GetValue("C"))
        log.attempt(
            f"{role}.F(kgmole/h)", lambda target=target: target.MolarFlow.GetValue("kgmole/h")
        )
    for feed_name in list(feeds.Names):
        feed = op.Flowsheet.MaterialStreams.Item(feed_name)
        for var in ("Temperature", "MolarFlow"):
            peek_state(log, f"进料 {feed_name}.{var}", getattr(feed, var))


def probe_reactor(log: Log, op) -> None:
    type_name = str(op.TypeName)
    log.say(f"== 反应器 {op.name}（TypeName={type_name}，界面名 {op.VisibleTypeName}）==")
    log.attempt("类型化对象", lambda: type(op).__name__)
    log.attempt("Moniker", lambda: op.Moniker)
    probe_streams_of(log, op)
    peek(log, "反应器", op, "ReactionSet")
    log.attempt("ReactionSet 是否为空", lambda: op.ReactionSet is None)
    log.attempt("PressureDrop(kPa)", lambda: op.PressureDrop.GetValue("kPa"))
    peek_state(log, "PressureDrop", op.PressureDrop)
    log.attempt("HeatFlow(kW)", lambda: op.HeatFlow.GetValue("kW"))
    peek_state(log, "HeatFlow", op.HeatFlow)
    peek_all(log, "反应器", op, ("VesselType", "FluidPackage"))
    peek_all(log, "反应器", op, RESULT_MEMBERS.get(type_name, ()))
    for member in AMOUNT_MEMBERS.get(type_name, ()):
        variable = getattr(op, member)
        log.attempt(
            f"{member}.GetValues('kgmole/h')",
            lambda variable=variable: variable.GetValues("kgmole/h"),
        )


def probe_reactions(log: Log, case) -> None:
    log.say("== 反应（Basis 一侧） ==")
    manager = case.BasisManager.ReactionPackageManager
    reactions = manager.Reactions
    log.attempt("Reactions.Count", lambda: reactions.Count)
    log.attempt("Reactions.Names", lambda: list(reactions.Names))
    for i in range(int(reactions.Count)):
        reaction = reactions.Item(i)
        kind = type(reaction).__name__
        log.say(f"  -- 第 {i} 个反应：类型 {kind} --")
        peek_all(log, f"反应[{i}]", reaction, REACTION_COMMON)
        peek_all(log, f"反应[{i}]", reaction, REACTION_MEMBERS.get(kind, ()))
        reactants = reaction.Reactants
        log.attempt(f"反应[{i}].Reactants.Names", lambda reactants=reactants: list(reactants.Names))
        for j in range(int(reactants.Count)):
            item = reactants.Item(j)
            log.attempt(
                f"反应[{i}].Reactants[{j}]",
                lambda item=item: (item.Component.name, item.StoichiometricCoefficientValue),
            )


def probe_reaction_sets(log: Log, case) -> None:
    log.say("== 反应集和流体包的关联 ==")
    manager = case.BasisManager.ReactionPackageManager
    sets = manager.ReactionSets
    log.attempt("ReactionSets.Count", lambda: sets.Count)
    log.attempt("ReactionSets.Names", lambda: list(sets.Names))
    for i in range(int(sets.Count)):
        rset = sets.Item(i)
        log.say(f"  -- 第 {i} 个反应集：类型 {type(rset).__name__} --")
        peek_all(log, f"反应集[{i}]", rset, ("name", "TypeName", "SolverMethod", "TraceLevel"))
        for member in ("ActiveReactions", "InactiveReactions"):
            log.attempt(
                f"反应集[{i}].{member}.Names",
                lambda member=member, rset=rset: list(getattr(rset, member).Names),
            )
        log.attempt(f"反应集[{i}].Operations.Names", lambda rset=rset: list(rset.Operations.Names))
        peek(log, f"反应集[{i}]", rset, "ReactionPackage.FluidPackage.name")
    package = case.BasisManager.FluidPackages.Item(0)
    log.attempt(
        "流体包[0].ReactionPackage.ReactionSets.Names",
        lambda: list(package.ReactionPackage.ReactionSets.Names),
    )
    log.attempt(
        "流体包[0].ReactionPackage.FluidPackage.name",
        lambda: package.ReactionPackage.FluidPackage.name,
    )


def probe_xml(log: Log, case, operation_name: str) -> None:
    log.say("== Q6 XML 路线 ==")
    for flags in XML_FLAGS_TO_TRY:
        ok, _ = log.attempt(
            f"ProvideXMLForCase({flags}) 的长度",
            lambda flags=flags: len(case.ProvideXMLForCase(flags)),
        )
        if ok:
            text = case.ProvideXMLForCase(flags)
            lowered = text.lower()
            log.say(
                f"  flags={flags}: 含 'reaction' {lowered.count('reaction')} 次，"
                f"含 'reactionset' {lowered.count('reactionset')} 次"
            )
            counts = {word: lowered.count(word.lower()) for word in XML_KEYWORDS}
            log.say(f"  flags={flags}: 关键词出现次数 {counts}")
            i = lowered.find("stoich")
            if i >= 0:
                log.say(f"  'Stoich' 首次出现处附近: {text[max(0, i - 300) : i + 600]!r}")
    log.attempt("GetXMLForCase() 的长度", lambda: len(case.GetXMLForCase()))
    ok, _ = log.attempt(
        f"ProvideXMLForOperation({operation_name!r}, 0) 的长度",
        lambda: len(case.ProvideXMLForOperation(operation_name, 0)),
    )
    if ok:
        text = case.ProvideXMLForOperation(operation_name, 0)
        log.say(f"  开头: {text[:XML_SNIPPET_CHARS]!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", default=str(DEFAULT_CASE))
    parser.add_argument("--tag", default="sample")
    args = parser.parse_args()
    log = Log(f"e3_reverse_probe_{args.tag}")
    source = Path(args.case).resolve()
    before = hysys_processes()
    app = win32com.client.gencache.EnsureDispatch("HYSYS.Application.NewInstance")
    mine = next((pid for pid in hysys_processes() if pid not in before), None)
    log.say(f"新实例的进程号: {mine}；Case: {source}")
    app.Visible = True
    scratch = Path(tempfile.mkdtemp(prefix="hysys_e3_")).resolve()
    try:
        copy = scratch / source.name
        shutil.copyfile(source, copy)
        with watch(log, "Open"):
            case = app.SimulationCases.Open(str(copy))
        flowsheet = case.Flowsheet
        operations = [flowsheet.Operations.Item(i) for i in range(int(flowsheet.Operations.Count))]
        reactors = [op for op in operations if str(op.TypeName) in REACTOR_TYPES]
        log.say(f"单元操作 {[(op.name, op.TypeName) for op in operations]}")
        for op in reactors:
            probe_reactor(log, op)
        probe_reactions(log, case)
        probe_reaction_sets(log, case)
        if reactors:
            probe_xml(log, case, reactors[0].name)
    finally:
        if mine is not None:
            subprocess.run(["taskkill", "/PID", str(mine), "/T", "/F"], capture_output=True)
            gone = wait_gone(mine)
            log.say(f"  实例 {mine} {'已结束' if gone is not None else '仍在运行'}")
        shutil.rmtree(scratch, ignore_errors=True)
    log.say(f"结束时的 HYSYS 进程: {hysys_processes() or '无'}")


if __name__ == "__main__":
    main()

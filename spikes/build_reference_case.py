"""D11：用代码从空白 Case 建出含三种反应器的参考 Case，另存为 spikes/ref_cases/three_reactors.hsc。

同时回答 0B、0C 的这些问题（对应探针 E5、E7、E8、E9）：
  E5 新建物流和能流，规定 T、P、流量、组成，闪蒸完成
  E7 转化反应器：Operations.Add 的类型字符串，进出料、反应集、压降怎么连，求解后读结果
  E8 平衡反应器：Keq 来源 Gibbs 自由能，带能流，出口温度规定在气相出料上；710 °C 和 600 °C 两个工况
  E9 Gibbs 反应器：不挂反应集，ReactorType 的默认值，带能流，出口温度规定在气相出料上
每一步都读回验证；改规定之后模型随写入同步重算（H17）。

模型（阶段提示词 0A 任务 7 的清单）：
  流体包 Peng-Robinson（pengrob）：甲烷、水、CO、CO2、氢气、甲苯、苯、对二甲苯
  转化反应 Tol-Disp：2 甲苯 → 苯 + 对二甲苯，转化率 50%；反应集 Conv-Set
  平衡反应 SMR、WGS（Keq 来源 Gibbs 自由能，默认）；反应集 Eq-Set；两个反应集都加入流体包
  转化反应器 R-Conv（绝热）、平衡反应器 R-Eq（带能流，出口 710 °C）
  Gibbs 反应器 R-Gibbs（带能流，出口 710 °C）
  每台反应器一股进料、气相和液相两股出料，全部求解

用法：python spikes/build_reference_case.py [--tag 名字] [--out 路径]
输出：spikes/out/build_reference_case_<tag>.txt；
参考 Case 默认存到 spikes/ref_cases/three_reactors.hsc。
"""

import argparse
import math
from pathlib import Path

from _common import Log, first_ok, new_instance, use_utf8, watch

use_utf8()

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO / "spikes" / "ref_cases" / "three_reactors.hsc"
COMPONENTS = ("Methane", "H2O", "CO", "CO2", "Hydrogen", "Toluene", "Benzene", "p-Xylene")
REFORMING_FRACTIONS = {"Methane": 0.2703, "H2O": 0.7297}
REACTOR_TYPES = {
    "R-Conv": ("ConversionReactorOp", "conversionreactorop"),
    "R-Eq": ("EquilibriumReactorOp", "equilibriumreactorop"),
    "R-Gibbs": ("GibbsReactorOp", "gibbsreactorop"),
}
# 阶段提示词 0C 任务 1 给的独立计算参照值（理想气体平衡）：出口湿基摩尔分率和总流量
REFERENCE = {
    710.0: ({"Methane": 0.094, "H2O": 0.381, "Hydrogen": 0.411, "CO": 0.047, "CO2": 0.067}, 4800.0),
    600.0: ({"Methane": 0.162, "H2O": 0.499, "Hydrogen": 0.269, "CO": 0.012, "CO2": 0.058}, 4305.0),
}
FRACTION_TOLERANCE = 0.02
TOLUENE_EXPECTED = {"Toluene": 0.5, "Benzene": 0.25, "p-Xylene": 0.25}
TOLUENE_TOLERANCE = 0.001
MASS_BALANCE_TOLERANCE = 1e-4
STATUS_FLAGS = {"OK": 1, "NotSolved": 2, "Warning": 4, "UnderSpecified": 8, "Error": 16}


def fraction_vector(fractions: dict[str, float]) -> tuple[float, ...]:
    """按流体包的组分顺序排的摩尔分率向量。"""
    return tuple(fractions.get(name, 0.0) for name in COMPONENTS)


def as_dict(values) -> dict[str, float]:
    return dict(zip(COMPONENTS, values, strict=True))


def build_basis(log: Log, app):
    log.say("== Basis：组分列表、流体包、物性包 ==")
    case = app.SimulationCases.Add("three_reactors")
    manager = case.BasisManager
    component_list = manager.ComponentLists.Add("CL-1")
    for name in COMPONENTS:
        component_list.Components.Add(name)
    package = manager.FluidPackages.Add("Basis-1")
    package.ComponentList = component_list
    package.PropertyPackageName = "pengrob"
    log.say(f"  组分 {list(package.Components.Names)}；物性包 {package.PropertyPackageName}")
    return case, manager, package


def add_reaction(log: Log, reactions, name, type_name, stoichiometry, base=None, **settings):
    reaction = reactions.Add(name, type_name)
    for component, coefficient in stoichiometry:
        reaction.Reactants.Add(component).StoichiometricCoefficientValue = coefficient
    if base is not None:
        reaction.BaseComponent = base
    for member, value in settings.items():
        setattr(reaction, member, value)
    log.say(
        f"  {name}（{type(reaction).__name__}）：{list(reaction.Reactants.Names)}，"
        f"系数 {reaction.ReactantStoichCoefValue}"
    )


def build_reactions(log: Log, manager, package):
    log.say("== 反应和反应集 ==")
    reactions = manager.ReactionPackageManager.Reactions
    add_reaction(
        log,
        reactions,
        "Tol-Disp",
        "conversionrxn",
        (("Toluene", -2.0), ("Benzene", 1.0), ("p-Xylene", 1.0)),
        base=package.Components.Item("Toluene"),
        Conversion=50.0,
        ReactionPhase=0,
    )
    steam_reforming = (("Methane", -1.0), ("H2O", -1.0), ("CO", 1.0), ("Hydrogen", 3.0))
    add_reaction(log, reactions, "SMR", "equilibriumrxn", steam_reforming, ReactionPhase=0)
    water_gas_shift = (("CO", -1.0), ("H2O", -1.0), ("CO2", 1.0), ("Hydrogen", 1.0))
    add_reaction(log, reactions, "WGS", "equilibriumrxn", water_gas_shift, ReactionPhase=0)
    sets = manager.ReactionPackageManager.ReactionSets
    result = {}
    for set_name, members in (("Conv-Set", ("Tol-Disp",)), ("Eq-Set", ("SMR", "WGS"))):
        reaction_set = sets.Add(set_name)
        for member in members:
            reaction_set.ActiveReactions.Add(member)
        reaction_set.AssociateFluidPackage(package)
        log.say(f"  {set_name}：{list(reaction_set.ActiveReactions.Names)}")
        result[set_name] = reaction_set
    log.say(f"  流体包的反应集：{list(package.ReactionPackage.ReactionSets.Names)}")
    return result


def make_material_stream(log: Log, flowsheet, name: str):
    stream = flowsheet.MaterialStreams.Add(name)
    log.say(f"  物流 {name}（{type(stream).__name__}）")
    return stream


def make_feed(log: Log, flowsheet, name, temperature_c, pressure_kpa, flow, flow_unit, fractions):
    """E5：新建进料物流，规定 T、P、组成和流量，读回，确认闪蒸完成。"""
    stream = make_material_stream(log, flowsheet, name)
    stream.Temperature.SetValue(temperature_c, "C")
    stream.Pressure.SetValue(pressure_kpa, "kPa")
    stream.ComponentMolarFraction.Values = fraction_vector(fractions)
    if flow_unit == "kg/h":
        stream.MassFlow.SetValue(flow, "kg/h")
    else:
        stream.MolarFlow.SetValue(flow, flow_unit)
    log.say(
        f"    读回：T={stream.Temperature.GetValue('C'):.2f} C，"
        f"P={stream.Pressure.GetValue('kPa'):.1f} kPa，"
        f"F={stream.MolarFlow.GetValue('kgmole/h'):.3f} kgmole/h，"
        f"{stream.MassFlow.GetValue('kg/h'):.2f} kg/h，气相分率 {stream.VapourFractionValue:.4f}"
    )
    return stream


def connect_reactor(log: Log, flowsheet, name, feed, vapour, liquid, energy, reaction_set):
    """E7：新建反应器并连接。每一步试几种写法，记录哪种成功。"""
    help_name, lower_name = REACTOR_TYPES[name]
    ok, reactor, _ = first_ok(
        log,
        f"Operations.Add({name!r}, {help_name!r})",
        lambda: flowsheet.Operations.Add(name, help_name),
        lambda: flowsheet.Operations.Add(name, lower_name),
    )
    if not ok:
        return None
    log.say(f"    类型 {type(reactor).__name__}，TypeName={reactor.TypeName}")
    first_ok(
        log,
        "Feeds.Add(进料物流)",
        lambda: reactor.Feeds.Add(feed),
        lambda: reactor.Feeds.Add(feed.name),
    )
    log.attempt("Feeds.Names", lambda: list(reactor.Feeds.Names))
    log.attempt("VapourProduct = ...", lambda: setattr(reactor, "VapourProduct", vapour))
    log.attempt("LiquidProduct = ...", lambda: setattr(reactor, "LiquidProduct", liquid))
    if energy is not None:
        log.attempt("EnergyStream = ...", lambda: setattr(reactor, "EnergyStream", energy))
    if reaction_set is not None:
        log.attempt("ReactionSet = ...", lambda: setattr(reactor, "ReactionSet", reaction_set))
    log.attempt("PressureDrop = 0 kPa", lambda: reactor.PressureDrop.SetValue(0.0, "kPa"))
    return reactor


def outlet(vapour, liquid) -> dict[str, object]:
    """读出料：温度、压力、流量、组成。"""
    return {
        "T_C": vapour.Temperature.GetValue("C"),
        "P_kPa": vapour.Pressure.GetValue("kPa"),
        "vapour_kmol_h": vapour.MolarFlow.GetValue("kgmole/h"),
        "liquid_kmol_h": liquid.MolarFlow.GetValue("kgmole/h"),
        "vapour_kg_h": vapour.MassFlow.GetValue("kg/h"),
        "liquid_kg_h": liquid.MassFlow.GetValue("kg/h"),
        "fractions": as_dict(vapour.ComponentMolarFraction.Values),
        "flows": as_dict(vapour.ComponentMolarFlow.GetValues("kgmole/h")),
    }


def report_outlet(log: Log, label: str, feed, vapour, liquid, energy) -> dict[str, object]:
    result = outlet(vapour, liquid)
    log.say(f"  -- {label}：出料 --")
    log.say(
        f"    气相 T={result['T_C']:.2f} C，P={result['P_kPa']:.1f} kPa，"
        f"F={result['vapour_kmol_h']:.3f} kgmole/h，{result['vapour_kg_h']:.2f} kg/h；"
        f"液相 F={result['liquid_kmol_h']:.4f} kgmole/h"
    )
    log.say(
        f"    气相摩尔分率 { {k: round(v, 4) for k, v in result['fractions'].items() if v > 1e-9} }"
    )
    flows = {k: round(v, 3) for k, v in result["flows"].items() if v > 1e-9}
    log.say(f"    气相各组分 kgmole/h {flows}")
    feed_kg = feed.MassFlow.GetValue("kg/h")
    out_kg = result["vapour_kg_h"] + result["liquid_kg_h"]
    error = abs(out_kg - feed_kg) / feed_kg
    verdict = "通过" if error < MASS_BALANCE_TOLERANCE else "未通过"
    log.say(
        f"    质量守恒：进 {feed_kg:.3f}，出 {out_kg:.3f} kg/h，相对误差 {error:.2e}，{verdict}"
    )
    if energy is not None:
        log.attempt("    能流热负荷 HeatFlow(kW)", lambda: energy.HeatFlow.GetValue("kW"))
        log.attempt(
            "    能流热负荷 State/CanModify",
            lambda: (energy.HeatFlow.State, energy.HeatFlow.CanModify),
        )
    return result


def compare_reforming(
    log: Log, label: str, temperature_c: float, result, feed_methane: float
) -> None:
    """E8：与独立参照值比较。"""
    fractions_ref, total_ref = REFERENCE[temperature_c]
    worst = 0.0
    for name, ref in fractions_ref.items():
        diff = abs(result["fractions"][name] - ref)
        worst = max(worst, diff)
        actual = result["fractions"][name]
        log.say(
            f"    {label} {temperature_c:.0f} C {name}: HYSYS {actual:.4f}，"
            f"参照 {ref:.3f}，差 {diff:.4f}"
        )
    conversion = 1.0 - result["flows"]["Methane"] / feed_methane
    verdict = "通过" if worst <= FRACTION_TOLERANCE else "未通过"
    log.say(
        f"    {label} {temperature_c:.0f} C：五个摩尔分率最大偏差 {worst:.4f}"
        f"（容差 {FRACTION_TOLERANCE}），{verdict}；CH4 转化率 {conversion:.1%}；"
        f"总流量 {result['vapour_kmol_h']:.1f}（参照约 {total_ref:.0f}）"
    )


def check_conversion(log: Log, result) -> None:
    worst = max(abs(result["fractions"][k] - v) for k, v in TOLUENE_EXPECTED.items())
    toluene_in = 10000.0 / 92.1384
    log.say(
        f"    转化反应器：摩尔分率最大偏差 {worst:.5f}（容差 {TOLUENE_TOLERANCE}），"
        f"{'通过' if worst <= TOLUENE_TOLERANCE else '未通过'}；"
        f"甲苯进料 {toluene_in:.3f} kmol/h；出口 T {result['T_C']:.2f} C（进料 380 C）"
    )


def flowsheet_status(log: Log, case, label: str) -> None:
    """H19：按状态位查流程图里有多少对象、分别是哪些。"""
    for name, flag in STATUS_FLAGS.items():
        log.attempt(
            f"{label} 状态 {name}：对象数 / 清单",
            lambda flag=flag: (
                case.GetFlowsheetStatus(flag),
                case.GetFlowsheetObjectTypeAndName(flag),
            ),
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    log = Log(f"build_reference_case_{args.tag}")
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with new_instance(log) as (app, _pid):
        with watch(log, "build_basis"):
            case, manager, package = build_basis(log, app)
        sets = build_reactions(log, manager, package)
        log.attempt("CanEndBasisChange", lambda: manager.CanEndBasisChange)
        log.attempt("EndBasisChange()", manager.EndBasisChange)
        flowsheet = case.Flowsheet
        log.say("== 流程图：进料 ==")
        feeds = {
            "R-Conv": make_feed(
                log, flowsheet, "F-Conv", 380.0, 2500.0, 10000.0, "kg/h", {"Toluene": 1.0}
            ),
            "R-Eq": make_feed(
                log, flowsheet, "F-Eq", 520.0, 1350.0, 3700.0, "kgmole/h", REFORMING_FRACTIONS
            ),
            "R-Gibbs": make_feed(
                log, flowsheet, "F-Gibbs", 520.0, 1350.0, 3700.0, "kgmole/h", REFORMING_FRACTIONS
            ),
        }
        feed_methane = 3700.0 * REFORMING_FRACTIONS["Methane"]
        log.say("== 流程图：反应器 ==")
        results = {}
        for name, set_name, with_energy in (
            ("R-Conv", "Conv-Set", False),
            ("R-Eq", "Eq-Set", True),
            ("R-Gibbs", None, True),
        ):
            log.say(f"-- {name} --")
            vapour = make_material_stream(log, flowsheet, f"{name}-V")
            liquid = make_material_stream(log, flowsheet, f"{name}-L")
            energy = None
            if with_energy:
                _, energy, _ = first_ok(
                    log,
                    f"EnergyStreams.Add('Q-{name}')",
                    lambda name=name: flowsheet.EnergyStreams.Add(f"Q-{name}"),
                )
            reactor = connect_reactor(
                log,
                flowsheet,
                name,
                feeds[name],
                vapour,
                liquid,
                energy,
                sets[set_name] if set_name else None,
            )
            if reactor is None:
                continue
            if name == "R-Gibbs":
                log.attempt(
                    "Gibbs ReactorType（默认值）", lambda reactor=reactor: reactor.ReactorType
                )
            if not with_energy:
                result = report_outlet(log, name, feeds[name], vapour, liquid, energy)
                check_conversion(log, result)
                continue
            for temperature in (710.0, 600.0, 710.0):
                log.attempt(
                    f"气相出料 T = {temperature} C",
                    lambda vapour=vapour, temperature=temperature: vapour.Temperature.SetValue(
                        temperature, "C"
                    ),
                )
                result = report_outlet(
                    log, f"{name} @ {temperature:.0f} C", feeds[name], vapour, liquid, energy
                )
                compare_reforming(log, name, temperature, result, feed_methane)
                results[(name, temperature)] = result
        eq, gibbs = results[("R-Eq", 710.0)], results[("R-Gibbs", 710.0)]
        worst = max(abs(eq["fractions"][k] - gibbs["fractions"][k]) for k in COMPONENTS)
        closeness = "接近" if worst < 0.005 else "有差别"
        log.say(f"== Gibbs 与平衡反应器（710 C）的摩尔分率最大偏差 {worst:.5f}，{closeness} ==")
        flowsheet_status(log, case, "全部求解后")
        log.attempt("Solver.CanSolve", lambda: case.Solver.CanSolve)
        log.attempt("保存", lambda: case.SaveAs(str(out_path)))
        size_kb = out_path.stat().st_size // 1024 if out_path.exists() else 0
        log.say(f"参考 Case: {out_path}，{size_kb} KB")
        log.attempt("case.Close()", case.Close)
    if not math.isfinite(worst):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

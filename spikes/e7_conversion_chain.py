"""E7（闸门 G0）：从空白 Case 用代码建出甲苯歧化的转化反应器，求解，与解析解对比。

模型（阶段提示词 0B）：
  流体包 Peng-Robinson（物性包内部名 pengrob）；组分 甲苯、苯、对二甲苯、间二甲苯、邻二甲苯
  转化反应 2 甲苯 → 1 苯 + 0.24 对二甲苯 + 0.52 间二甲苯 + 0.24 邻二甲苯，基准组分甲苯，转化率 50%
  反应集 Conv-Set 包含这个反应，并加入流体包
  进料 纯甲苯 10000 kg/h，380 °C，2500 kPa（绝压）
  转化反应器：一股进料、气相和液相两股出料，不接能流（绝热），压降 0，挂反应集

这个脚本是后面 Backend 的蓝本，所以按步骤拆成函数，每个函数对应台账"调用序列"里的一步。
求解随写入同步完成，没有单独的"求解"调用（H17）；--hold-solver 在建模期间挂起求解器，
建完再释放，用来比较两种做法。--repeat N 连续从空白 Case 建 N 次（每次一个新实例），
比较各次出料各组分摩尔流量的相对偏差。

用法：python spikes/e7_conversion_chain.py [--tag 名字] [--repeat N] [--hold-solver]
输出：spikes/out/e7_conversion_chain_<tag>.txt
"""

import argparse
import time
import traceback
from dataclasses import dataclass

from _common import Log, new_instance, use_utf8, watch

use_utf8()

COMPONENTS = ("Toluene", "Benzene", "p-Xylene", "m-Xylene", "o-Xylene")
PROPERTY_PACKAGE = "pengrob"
STOICHIOMETRY = (
    ("Toluene", -2.0),
    ("Benzene", 1.0),
    ("p-Xylene", 0.24),
    ("m-Xylene", 0.52),
    ("o-Xylene", 0.24),
)
CONVERSION_PERCENT = 50.0
FEED_TEMPERATURE_C = 380.0
FEED_PRESSURE_KPA = 2500.0
FEED_MASS_FLOW_KG_H = 10000.0
TOLUENE_MOLECULAR_WEIGHT = 92.14  # 与阶段提示词里的解析解一致
# 解析解：出口摩尔分率和质量流量（阶段提示词 0B）
EXPECTED_FRACTIONS = {
    "Toluene": 0.500,
    "Benzene": 0.250,
    "p-Xylene": 0.060,
    "m-Xylene": 0.130,
    "o-Xylene": 0.060,
}
EXPECTED_MASS_KG_H = {
    "Toluene": 5000.0,
    "Benzene": 2119.0,
    "p-Xylene": 691.0,
    "m-Xylene": 1498.0,
    "o-Xylene": 691.0,
}
FRACTION_TOLERANCE = 0.001
MASS_BALANCE_TOLERANCE = 1e-4
OUTLET_TEMPERATURE_TOLERANCE_C = 10.0
REPEAT_TOLERANCE = 1e-4
STATUS_FLAGS = {"OK": 1, "NotSolved": 2, "Warning": 4, "UnderSpecified": 8, "Error": 16}


@dataclass
class Model:
    """建模过程中用到的对象。"""

    case: object
    manager: object
    package: object
    reaction: object = None
    reaction_set: object = None
    flowsheet: object = None
    feed: object = None
    vapour: object = None
    liquid: object = None
    reactor: object = None


def step_new_case(app) -> Model:
    """步骤 1：新建空白 Case。新 Case 处在 Basis 修改状态。"""
    case = app.SimulationCases.Add("e7_toluene")
    return Model(case=case, manager=case.BasisManager, package=None)


def step_basis(model: Model) -> None:
    """步骤 2：组分列表、流体包、物性包。"""
    component_list = model.manager.ComponentLists.Add("CL-1")
    for name in COMPONENTS:
        component_list.Components.Add(name)
    model.package = model.manager.FluidPackages.Add("Basis-1")
    model.package.ComponentList = component_list
    model.package.PropertyPackageName = PROPERTY_PACKAGE


def step_reaction(model: Model) -> None:
    """步骤 3：转化反应（分数计量系数、基准组分、转化率）。"""
    reactions = model.manager.ReactionPackageManager.Reactions
    reaction = reactions.Add("Tol-Disp", "conversionrxn")
    for name, coefficient in STOICHIOMETRY:
        reaction.Reactants.Add(name).StoichiometricCoefficientValue = coefficient
    reaction.BaseComponent = model.package.Components.Item("Toluene")
    reaction.Conversion = CONVERSION_PERCENT
    reaction.ReactionPhase = 0
    model.reaction = reaction


def step_reaction_set(model: Model) -> None:
    """步骤 4：反应集，放进反应，加入流体包。"""
    reaction_set = model.manager.ReactionPackageManager.ReactionSets.Add("Conv-Set")
    reaction_set.ActiveReactions.Add("Tol-Disp")
    reaction_set.AssociateFluidPackage(model.package)
    model.reaction_set = reaction_set


def step_end_basis(model: Model) -> None:
    """步骤 5：结束 Basis，流程图可用。"""
    model.manager.EndBasisChange()
    model.flowsheet = model.case.Flowsheet


def step_feed(model: Model) -> None:
    """步骤 6：进料物流。顺序不影响结果：T、P、组成写完闪蒸就完成，流量最后写。"""
    feed = model.flowsheet.MaterialStreams.Add("Feed")
    feed.Temperature.SetValue(FEED_TEMPERATURE_C, "C")
    feed.Pressure.SetValue(FEED_PRESSURE_KPA, "kPa")
    feed.ComponentMolarFraction.Values = (1.0, 0.0, 0.0, 0.0, 0.0)
    feed.MassFlow.SetValue(FEED_MASS_FLOW_KG_H, "kg/h")
    model.feed = feed


def step_outlets(model: Model) -> None:
    """步骤 7、8：气相和液相出料物流（只建，不规定任何量）。"""
    model.vapour = model.flowsheet.MaterialStreams.Add("Vap")
    model.liquid = model.flowsheet.MaterialStreams.Add("Liq")


def step_reactor(model: Model) -> None:
    """步骤 9：转化反应器，连接进出料，挂反应集，压降 0，不接能流（绝热）。"""
    reactor = model.flowsheet.Operations.Add("CRV-100", "ConversionReactorOp")
    reactor.Feeds.Add(model.feed)
    reactor.VapourProduct = model.vapour
    reactor.LiquidProduct = model.liquid
    reactor.ReactionSet = model.reaction_set
    reactor.PressureDrop.SetValue(0.0, "kPa")
    model.reactor = reactor


def solver_state(model: Model) -> dict[str, object]:
    """判断\"已经求解完成\"：求解器不在求解，流程图里没有未求解、欠规定、错误的对象。"""
    counts = {name: model.case.GetFlowsheetStatus(flag) for name, flag in STATUS_FLAGS.items()}
    return {
        "IsSolving": model.case.Solver.IsSolving,
        "CanSolve": model.case.Solver.CanSolve,
        "状态计数": counts,
        "出料已知": model.vapour.MolarFlow.IsKnown and model.vapour.Temperature.IsKnown,
    }


def read_results(model: Model) -> dict[str, object]:
    """读出料：温度、压力、流量、各组分摩尔流量。"""
    vapour, liquid = model.vapour, model.liquid
    flows = dict(zip(COMPONENTS, vapour.ComponentMolarFlow.GetValues("kgmole/h"), strict=True))
    masses = dict(zip(COMPONENTS, vapour.ComponentMassFlow.GetValues("kg/h"), strict=True))
    return {
        "T_C": vapour.Temperature.GetValue("C"),
        "P_kPa": vapour.Pressure.GetValue("kPa"),
        "vapour_kmol_h": vapour.MolarFlow.GetValue("kgmole/h"),
        "liquid_kmol_h": liquid.MolarFlow.GetValue("kgmole/h"),
        "vapour_kg_h": vapour.MassFlow.GetValue("kg/h"),
        "liquid_kg_h": liquid.MassFlow.GetValue("kg/h"),
        "flows_kmol_h": flows,
        "masses_kg_h": masses,
        "feed_kmol_h": model.feed.MolarFlow.GetValue("kgmole/h"),
    }


def compare(log: Log, result: dict[str, object]) -> bool:
    """与解析解对比，打印表格，返回是否全部通过。"""
    flows = result["flows_kmol_h"]
    total = sum(flows.values())
    log.say("  组分          HYSYS kmol/h   摩尔分率   期望分率   偏差      HYSYS kg/h   期望 kg/h")
    worst = 0.0
    for name in COMPONENTS:
        fraction = flows[name] / total
        diff = abs(fraction - EXPECTED_FRACTIONS[name])
        worst = max(worst, diff)
        log.say(
            f"  {name:<12}{flows[name]:>12.3f}{fraction:>11.4f}{EXPECTED_FRACTIONS[name]:>11.3f}"
            f"{diff:>10.5f}{result['masses_kg_h'][name]:>13.1f}{EXPECTED_MASS_KG_H[name]:>12.0f}"
        )
    out_kg = result["vapour_kg_h"] + result["liquid_kg_h"]
    balance = abs(out_kg - FEED_MASS_FLOW_KG_H) / FEED_MASS_FLOW_KG_H
    expected_feed = FEED_MASS_FLOW_KG_H / TOLUENE_MOLECULAR_WEIGHT
    temperature_diff = abs(result["T_C"] - FEED_TEMPERATURE_C)
    checks = {
        f"摩尔分率最大偏差 {worst:.5f} ≤ {FRACTION_TOLERANCE}": worst <= FRACTION_TOLERANCE,
        f"质量守恒相对误差 {balance:.2e} ≤ {MASS_BALANCE_TOLERANCE}": balance
        <= MASS_BALANCE_TOLERANCE,
        f"出口温度 {result['T_C']:.2f} C 与 380 C 相差 {temperature_diff:.2f} ≤ "
        f"{OUTLET_TEMPERATURE_TOLERANCE_C}": temperature_diff <= OUTLET_TEMPERATURE_TOLERANCE_C,
        f"液相出口流量 {result['liquid_kmol_h']:.4f} kgmole/h 为 0": result["liquid_kmol_h"] < 1e-6,
        f"进料 {result['feed_kmol_h']:.3f} kgmole/h，解析 {expected_feed:.3f}": (
            abs(result["feed_kmol_h"] - expected_feed) / expected_feed < 1e-3
        ),
    }
    for text, passed in checks.items():
        log.say(f"  [{'通过' if passed else '未通过'}] {text}")
    return all(checks.values())


def run_once(log: Log, hold_solver: bool) -> dict[str, object]:
    """从空白 Case 到读出结果的全部步骤，返回结果字典。"""
    with new_instance(log) as (app, _pid):
        timings: list[tuple[str, float]] = []

        def timed(name, step, *args):
            start = time.time()
            value = step(*args)
            timings.append((name, time.time() - start))
            return value

        with watch(log, "步骤 1 至 2"):
            model = timed("1 新建 Case", step_new_case, app)
            timed("2 Basis", step_basis, model)
        timed("3 反应", step_reaction, model)
        timed("4 反应集", step_reaction_set, model)
        timed("5 结束 Basis", step_end_basis, model)
        if hold_solver:
            model.case.Solver.CanSolve = False
            log.say("  建模期间求解器已挂起（CanSolve=False）")
        timed("6 进料", step_feed, model)
        timed("7、8 出料物流", step_outlets, model)
        timed("9 反应器", step_reactor, model)
        log.say(f"  建完时的求解器状态: {solver_state(model)}")
        if hold_solver:
            start = time.time()
            model.case.Solver.CanSolve = True
            timings.append(("释放求解器", time.time() - start))
            log.say(f"  释放后的求解器状态: {solver_state(model)}")
        for name, seconds in timings:
            log.say(f"  步骤用时 {name}: {seconds:.2f} 秒")
        result = read_results(model)
        result["passed"] = compare(log, result)
        result["state"] = solver_state(model)
        model.case.Close()
        return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--hold-solver", action="store_true")
    args = parser.parse_args()
    log = Log(f"e7_conversion_chain_{args.tag}")
    results = []
    for index in range(args.repeat):
        log.say(f"==== 第 {index + 1} 次，从空白 Case 开始（hold_solver={args.hold_solver}） ====")
        try:
            results.append(run_once(log, args.hold_solver))
        except Exception:  # 探针：任何失败都要连同堆栈记进日志，再以非零状态退出
            log.say(traceback.format_exc())
            return 1
    if len(results) > 1:
        worst = 0.0
        for name in COMPONENTS:
            values = [r["flows_kmol_h"][name] for r in results]
            worst = max(worst, (max(values) - min(values)) / max(abs(values[0]), 1e-12))
        log.say(
            f"== {len(results)} 次运行各组分摩尔流量的最大相对偏差 {worst:.2e}"
            f"（要求 ≤ {REPEAT_TOLERANCE}） =="
        )
        if worst > REPEAT_TOLERANCE:
            return 1
    ok = all(r["passed"] for r in results)
    log.say(f"== G0 {'通过' if ok else '未通过'}：{len(results)} 次运行，全部对比通过={ok} ==")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

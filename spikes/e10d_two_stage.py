"""E10d（0C 任务 3 的可行性证据，没有采用）：计划 §17.3 的两段式替代做法能不能得到参照结果。

提示词要求 Gibbs 反应器不能正确处理固体碳时不自行改用两段式，要把现象交给用户决定（进度文件 D14）。
这个探针不改任何正式模型，只回答一个问题：如果用户选了两段式，结果和参照值差多少？

两段式（计划 §17.3）：
  第一段  转化反应器 CRV-1：C + H2O → CO + H2，基准组分水，转化率 100%（水是限量反应物），
          气相出料（CO、H2）出口 1400 °C，液相出料里是没反应掉的碳，旁路，不进第二段
  第二段  Gibbs 反应器 GBR-2：进料是第一段的气相，纯自由能最小化，出口 1400 °C，没有碳

通过条件和 e10 一样（四条）。热负荷是两段的能流之和。

用法：python spikes/e10d_two_stage.py [--tag 名字]
输出：spikes/out/e10d_two_stage_<tag>.txt；Case 另存为同名 .hsc。
"""

import argparse
import traceback

from _common import OUT_DIR, Log, dialog_guard, new_instance, use_utf8
from chain_kit import (
    add_reaction,
    add_reaction_set,
    add_reactor,
    make_feed,
    new_case_with_basis,
    read_stream,
    status_counts,
)
from e10_gibbs_carbon import (
    COMPONENTS,
    FEED_FLOW_KMOL_H,
    FEED_PRESSURE_KPA,
    FEED_TEMPERATURE_C,
    OUTLET_TEMPERATURE_C,
    describe_stream,
    judge,
)

use_utf8()

CARBON_FRACTION = 0.710
GASIFICATION = (("Carbon", -1.0), ("H2O", -1.0), ("CO", 1.0), ("Hydrogen", 1.0))


def build_stage_one(log: Log, basis, flowsheet, feed):
    """第一段：转化反应器，水为基准组分、转化率 100%，带能流，气相出料写 1400 °C。"""
    water = basis.package.Components.Item("H2O")
    add_reaction(
        basis, "Gasif", "conversionrxn", GASIFICATION, BaseComponent=water, Conversion=100.0
    )
    reaction_set = add_reaction_set(basis, "Gasif-Set", ("Gasif",))
    vapour = flowsheet.MaterialStreams.Add("Gas-1")
    liquid = flowsheet.MaterialStreams.Add("Carbon-1")
    energy = flowsheet.EnergyStreams.Add("Q-1")
    reactor = add_reactor(
        flowsheet, "CRV-1", "ConversionReactorOp", (feed,), vapour, liquid, energy, reaction_set
    )
    log.say(f"  连完的状态 {status_counts(basis.case)}")
    vapour.Temperature.SetValue(OUTLET_TEMPERATURE_C, "C")
    log.say(f"  写出口温度之后的状态 {status_counts(basis.case)}")
    return reactor, vapour, liquid, energy


def build_stage_two(log: Log, flowsheet, gas_in):
    """第二段：Gibbs 反应器，进料是第一段的气相，带能流，出口 1400 °C。"""
    vapour = flowsheet.MaterialStreams.Add("Gas-2")
    liquid = flowsheet.MaterialStreams.Add("Liq-2")
    energy = flowsheet.EnergyStreams.Add("Q-2")
    reactor = flowsheet.Operations.Add("GBR-2", "GibbsReactorOp")
    reactor.Feeds.Add(gas_in)
    reactor.EnergyStream = energy
    reactor.VapourProduct = vapour
    reactor.LiquidProduct = liquid
    reactor.PressureDrop.SetValue(0.0, "kPa")
    vapour.Temperature.SetValue(OUTLET_TEMPERATURE_C, "C")
    return reactor, vapour, liquid, energy


def run_once(log: Log, app, save_path) -> bool:
    basis = new_case_with_basis(app, "e10d", COMPONENTS)
    basis.manager.EndBasisChange()
    flowsheet = basis.case.Flowsheet
    feed = make_feed(
        flowsheet,
        basis,
        "Feed",
        FEED_TEMPERATURE_C,
        FEED_PRESSURE_KPA,
        {"Carbon": CARBON_FRACTION, "H2O": 1.0 - CARBON_FRACTION},
        FEED_FLOW_KMOL_H,
    )
    log.say("== 第一段：转化反应器 ==")
    _reactor1, gas1, carbon1, energy1 = build_stage_one(log, basis, flowsheet, feed)
    describe_stream(log, "第一段气相出料", gas1, basis)
    describe_stream(log, "第一段液相出料（没反应掉的碳）", carbon1, basis)
    log.say(f"  第一段热负荷 {energy1.HeatFlow.GetValue('kW') / 1000:.2f} MW")
    log.say("== 第二段：Gibbs 反应器 ==")
    _reactor2, gas2, liquid2, energy2 = build_stage_two(log, flowsheet, gas1)
    vapour_data = describe_stream(log, "第二段气相出料", gas2, basis)
    liquid_two = read_stream(liquid2, basis.components)
    carbon_data = read_stream(carbon1, basis.components)
    for name in basis.components:
        carbon_data["flows"][name] += liquid_two["flows"][name]
    duty_kw = energy1.HeatFlow.GetValue("kW") + energy2.HeatFlow.GetValue("kW")
    log.say(
        f"  第二段热负荷 {energy2.HeatFlow.GetValue('kW') / 1000:.2f} MW；"
        f"流程图状态 {status_counts(basis.case)}"
    )
    carbon_in = FEED_FLOW_KMOL_H * CARBON_FRACTION
    passed = judge(log, carbon_in, vapour_data, carbon_data, duty_kw)
    basis.case.SaveAs(str(save_path))
    log.say(f"  Case 已另存为 {save_path}")
    basis.case.Close()
    return passed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="run1")
    args = parser.parse_args()
    log = Log(f"e10d_two_stage_{args.tag}")
    try:
        with new_instance(log) as (app, pid), dialog_guard(log, pid, include_hidden=True):
            passed = run_once(log, app, OUT_DIR / f"e10d_two_stage_{args.tag}.hsc")
    except Exception:  # 探针：任何失败都要连同堆栈记进日志，再以非零状态退出
        log.say(traceback.format_exc())
        return 1
    log.say(f"== E10d 两段式：{'四条通过条件都满足' if passed else '有未通过的条件'} ==")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
